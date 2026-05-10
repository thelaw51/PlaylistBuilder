"""Beets wrapper: imports and removes files from the music library."""

import os
import subprocess

BEETS_CONFIG = os.environ.get("BEETS_CONFIG", "/config/beets/config.yaml")


def import_file(file_path: str) -> tuple[bool, str]:
    """Run ``beet import -q -A`` on *file_path*.

    Uses ``-A`` (no autotag) so beets trusts the existing tags from yt-dlp
    and just moves/organises the file. Returns ``(success, error_message)``.
    """
    cmd = [
        "beet",
        "--config",
        BEETS_CONFIG,
        "import",
        "--quiet",
        "-A",
        "--",
        file_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            shell=False,
        )
        if result.returncode == 0:
            return True, ""
        return False, (result.stderr or result.stdout or "beets returned non-zero exit").strip()[
            :500
        ]
    except subprocess.TimeoutExpired:
        return False, "beet import timed out after 120 s"
    except OSError as exc:
        return False, str(exc)


def remove_from_library(title: str, artist: str) -> None:
    """Remove a track from the beets library and delete its file from disk.

    Uses ``beet remove --delete --yes`` with a title+artist query.
    Silently ignores failures — beets may not know about every file we imported.
    """
    # Beets query terms never start with '-' so no '--' sentinel is needed here.
    cmd = [
        "beet",
        "--config",
        BEETS_CONFIG,
        "remove",
        "--delete",
        "--force",
        f"title:{title}",
        f"artist:{artist}",
    ]

    try:
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
    except Exception:
        pass
