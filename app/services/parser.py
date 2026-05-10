"""iTunes Library XML and playlist .txt parsers. Upsert playlists/tracks into the DB."""

import hashlib
import plistlib
from app import db
from app.models import Playlist, Track

# iTunes distinguished kinds that indicate system/auto playlists to skip.
_SKIP_KINDS = {2, 3, 4, 5, 6, 7, 10, 19, 26}

_LIBRARY_ID = 1  # singleton global library


def parse_library(file_path: str) -> int:
    """Parse an iTunes Library XML file and merge playlists/tracks into the global library.

    Skips system playlists (Master, Purchased, etc.). New tracks on existing
    playlists are added as pending; already-imported tracks keep their status.
    Returns the number of user playlists found.
    """
    with open(file_path, 'rb') as f:
        data = plistlib.load(f)

    tracks_dict: dict = data.get('Tracks', {})
    playlists_data: list = data.get('Playlists', [])

    count = 0
    for pl_data in playlists_data:
        if _should_skip(pl_data):
            continue

        name: str = pl_data.get('Name', '').strip()
        itunes_id: str = str(pl_data.get('Playlist Persistent ID', ''))
        if not name or not itunes_id:
            continue

        playlist = Playlist.query.filter_by(
            itunes_id=itunes_id, library_id=_LIBRARY_ID
        ).first()
        if not playlist:
            playlist = Playlist(library_id=_LIBRARY_ID, name=name, itunes_id=itunes_id)
            db.session.add(playlist)
            db.session.flush()
        elif playlist.name != name:
            playlist.name = name

        existing_itunes_ids = {t.itunes_id for t in playlist.tracks if t.itunes_id}

        for item in pl_data.get('Playlist Items', []):
            track_id = str(item.get('Track ID', ''))
            track_data = tracks_dict.get(track_id, {})

            itunes_track_id = str(track_data.get('Persistent ID', track_id))
            if itunes_track_id in existing_itunes_ids:
                continue

            title = (track_data.get('Name') or '').strip()
            if not title:
                continue

            track = Track(
                playlist_id=playlist.id,
                itunes_id=itunes_track_id,
                title=title,
                artist=(track_data.get('Artist') or '').strip(),
                album=(track_data.get('Album') or '').strip(),
                duration_ms=track_data.get('Total Time'),
                status='pending',
            )
            db.session.add(track)

        count += 1

    db.session.commit()
    return count


def parse_playlist_txt(file_path: str, playlist_name: str) -> int:
    """Parse an Apple Music playlist .txt export and merge it into the global library.

    The file is UTF-16 LE tab-separated with a header row. The playlist name is
    supplied by the caller (derived from the sanitised filename). Existing tracks
    are kept as-is; new tracks are added as pending. Returns 1 on success.
    """
    with open(file_path, 'rb') as f:
        raw = f.read()

    text = raw.decode('utf-16')
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return 0

    headers = lines[0].split('\t')

    def col(row: list[str], name: str, fallback: int) -> str:
        try:
            idx = headers.index(name)
            return row[idx].strip() if idx < len(row) else ''
        except ValueError:
            return row[fallback].strip() if fallback < len(row) else ''

    # Stable ID keyed on playlist name only (no library_id — singleton library)
    pl_itunes_id = hashlib.md5(playlist_name.encode()).hexdigest()

    playlist = Playlist.query.filter_by(
        itunes_id=pl_itunes_id, library_id=_LIBRARY_ID
    ).first()
    if not playlist:
        playlist = Playlist(
            library_id=_LIBRARY_ID, name=playlist_name, itunes_id=pl_itunes_id
        )
        db.session.add(playlist)
        db.session.flush()

    existing_ids = {t.itunes_id for t in playlist.tracks if t.itunes_id}

    for line in lines[1:]:
        cols = line.split('\t')
        title = col(cols, 'Name', 0)
        artist = col(cols, 'Artist', 1)
        album = col(cols, 'Album', 3)

        if not title:
            continue

        # Synthetic track ID: md5 of title + artist (no persistent ID in this format)
        track_itunes_id = hashlib.md5(f'{title}:{artist}'.encode()).hexdigest()
        if track_itunes_id in existing_ids:
            continue

        track = Track(
            playlist_id=playlist.id,
            itunes_id=track_itunes_id,
            title=title,
            artist=artist,
            album=album,
            status='pending',
        )
        db.session.add(track)

    db.session.commit()
    return 1


def _should_skip(pl_data: dict) -> bool:
    if pl_data.get('Master'):
        return True
    if pl_data.get('Distinguished Kind') in _SKIP_KINDS:
        return True
    if not pl_data.get('Playlist Items'):
        return True
    return False
