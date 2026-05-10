"""yt-dlp wrapper: tries SoundCloud first, falls back to YouTube."""

import glob
import logging
import os
import re
import subprocess
import tempfile

from mutagen import File as MutagenFile
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError
from mutagen.mp4 import MP4

DOWNLOAD_BASE = os.environ.get("DOWNLOAD_DIR", "/tmp/pb_downloads")
YT_COOKIES_FILE = os.environ.get("YT_COOKIES_FILE", "")
logger = logging.getLogger(__name__)


def download_track(title: str, artist: str, album: str = "") -> tuple[str | None, str | None, str]:
    """Download a track, trying SoundCloud then YouTube.

    After a successful download the file's tags are overwritten with the
    iTunes-known title/artist/album so beets can reliably organise it.
    Returns ``(local_path, source, error_msg)``.
    On failure local_path and source are None; error_msg describes what happened.
    """
    os.makedirs(DOWNLOAD_BASE, exist_ok=True)
    query = _build_query(artist, title)

    errors: list[str] = []
    for source, prefix in (("soundcloud", "scsearch1"), ("youtube", "ytsearch1")):
        search_term = f"{prefix}:{query}"
        path, err = _run_yt_dlp(search_term)
        if path:
            _write_tags(path, title=title, artist=artist, album=album)
            return path, source, ""
        if err:
            errors.append(f"{source.capitalize()}: {err}")

    return None, None, " | ".join(errors) if errors else "No results on SoundCloud or YouTube"


def _build_query(artist: str, title: str) -> str:
    """Combine and sanitize artist + title into a search query string."""
    combined = f"{artist} {title}".strip()
    combined = re.sub(r"[\x00-\x1f\x7f]", "", combined)
    combined = combined.lstrip("-").strip()
    return combined


def _run_yt_dlp(search_term: str) -> tuple[str | None, str]:
    """Run yt-dlp for the given search term inside a temp directory.

    Uses list-form argv (shell=False) and the POSIX ``--`` sentinel before the
    user-derived search term so flag-like content in artist/title is never
    parsed as a yt-dlp option.
    Returns ``(local_path, error_msg)``.
    """
    is_youtube = search_term.startswith("ytsearch")
    with tempfile.TemporaryDirectory(prefix="pb_", dir=DOWNLOAD_BASE) as tmpdir:
        output_template = os.path.join(tmpdir, "%(id)s.%(ext)s")
        cmd = [
            "yt-dlp",
            "--extract-audio",
            "--audio-format",
            "best",
            "--audio-quality",
            "0",
            "--embed-metadata",
            "--embed-thumbnail",
            "--no-playlist",
            "--output",
            output_template,
            "--no-warnings",
        ]
        if is_youtube:
            cmd += ["--extractor-args", "youtube:player_client=android,web"]
            if YT_COOKIES_FILE:
                cmd += ["--cookies", YT_COOKIES_FILE]
        cmd += ["--", search_term]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return None, "download timed out after 5 min"
        except OSError as exc:
            return None, str(exc)

        if result.returncode != 0:
            # Extract the first ERROR: line from stderr for a clean message
            err = _extract_ytdlp_error(result.stderr or result.stdout or "")
            return None, err

        files = glob.glob(os.path.join(tmpdir, "*"))
        if not files:
            return None, "yt-dlp returned success but downloaded no file"

        src = files[0]
        dest = os.path.join(DOWNLOAD_BASE, os.path.basename(src))
        os.replace(src, dest)
        return dest, ""


def _extract_ytdlp_error(stderr: str) -> str:
    """Pull the first ERROR: line out of yt-dlp output, or fall back to a trim."""
    for line in stderr.splitlines():
        if "ERROR:" in line:
            return line.strip()[:300]
    return stderr.strip()[:300] or "unknown error"


def _write_tags(path: str, title: str, artist: str, album: str) -> None:
    """Overwrite the downloaded file's tags with iTunes-known metadata."""
    try:
        ext = os.path.splitext(path)[1].lower()

        if ext == ".mp3":
            try:
                tags = EasyID3(path)
            except ID3NoHeaderError:
                tags = EasyID3()
                tags.save(path)
                tags = EasyID3(path)
            if title:
                tags["title"] = [title]
            if artist:
                tags["artist"] = [artist]
            if album:
                tags["album"] = [album]
            tags.save()
        elif ext in (".m4a", ".mp4", ".aac"):
            tags = MP4(path)
            if title:
                tags["\xa9nam"] = [title]
            if artist:
                tags["\xa9ART"] = [artist]
            if album:
                tags["\xa9alb"] = [album]
            tags.save()
        else:
            tags = MutagenFile(path)
            if tags is not None:
                if title:
                    tags["title"] = [title]
                if artist:
                    tags["artist"] = [artist]
                if album:
                    tags["album"] = [album]
                tags.save()
    except Exception as exc:
        logger.debug("Tag write failed for %s: %s", path, exc)
