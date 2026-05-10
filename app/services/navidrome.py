"""Navidrome client using the Subsonic-compatible REST API."""

import hashlib
import os
import random
import string
import time

import httpx

NAVIDROME_URL = os.environ.get("NAVIDROME_URL", "http://navidrome:4533")
NAVIDROME_USER = os.environ.get("NAVIDROME_USER", "admin")
NAVIDROME_PASSWORD = os.environ.get("NAVIDROME_PASSWORD", "")

_SCAN_POLL_INTERVAL = 5  # seconds between scan-status checks
_SCAN_POLL_MAX = 120  # max checks (10 minutes)


def _auth() -> dict:
    """Build Subsonic token-based auth params."""
    salt = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    token = hashlib.md5((NAVIDROME_PASSWORD + salt).encode()).hexdigest()
    return {
        "u": NAVIDROME_USER,
        "t": token,
        "s": salt,
        "v": "1.16.1",
        "c": "playlistbuilder",
        "f": "json",
    }


def _get(client: httpx.Client, endpoint: str, **extra_params) -> dict:
    params = {**_auth(), **extra_params}
    resp = client.get(f"{NAVIDROME_URL}/rest/{endpoint}", params=params)
    resp.raise_for_status()
    body = resp.json().get("subsonic-response", {})
    if body.get("status") == "failed":
        error = body.get("error", {})
        raise RuntimeError(f"Subsonic error {error.get('code')}: {error.get('message')}")
    return body


def trigger_scan() -> None:
    """Ask Navidrome to start a full library scan."""
    with httpx.Client(timeout=10) as client:
        _get(client, "startScan")


def wait_for_scan() -> None:
    """Block until Navidrome reports scanning=false or the 10-minute cap is reached."""
    with httpx.Client(timeout=10) as client:
        for _ in range(_SCAN_POLL_MAX):
            data = _get(client, "getScanStatus")
            if not data.get("scanStatus", {}).get("scanning", False):
                return
            time.sleep(_SCAN_POLL_INTERVAL)


def find_track_id(title: str, artist: str, *, client: httpx.Client | None = None) -> str | None:
    """Return the Navidrome song ID for the best match, or None.

    Pass an existing *client* to reuse a connection when calling in a loop.
    """
    query = f"{artist} {title}".strip()

    def _search(c: httpx.Client) -> str | None:
        data = _get(c, "search3", query=query, songCount=5, albumCount=0, artistCount=0)
        songs = data.get("searchResult3", {}).get("song", [])
        return songs[0]["id"] if songs else None

    if client is not None:
        return _search(client)
    with httpx.Client(timeout=10) as c:
        return _search(c)


def create_or_update_playlist(name: str, song_ids: list[str]) -> str | None:
    """Create (or find existing) playlist by name and replace its contents.

    Uses ``createPlaylist`` with ``playlistId`` to atomically replace the song
    list on subsequent runs, preventing duplicates.  Returns the Navidrome
    playlist ID, or None on failure.
    """
    if not song_ids:
        return None

    with httpx.Client(timeout=30) as client:
        data = _get(client, "getPlaylists")
        playlists = data.get("playlists", {}).get("playlist", [])
        existing = next((p for p in playlists if p.get("name") == name), None)

        # httpx accepts list of tuples for repeated query params.
        if existing:
            # createPlaylist with playlistId replaces the song list entirely.
            params = (
                list(_auth().items())
                + [("playlistId", existing["id"])]
                + [("songId", sid) for sid in song_ids]
            )
        else:
            params = (
                list(_auth().items()) + [("name", name)] + [("songId", sid) for sid in song_ids]
            )

        resp = client.get(f"{NAVIDROME_URL}/rest/createPlaylist", params=params)
        resp.raise_for_status()
        return resp.json().get("subsonic-response", {}).get("playlist", {}).get("id")
