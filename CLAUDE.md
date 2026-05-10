# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

PlaylistBuilder is a self-hosted Flask web app that imports Apple Music playlists into Navidrome. It accepts iTunes Library XML exports or single-playlist `.txt` exports, then for each track: checks Navidrome for existing matches (via Lidarr), downloads via yt-dlp (SoundCloud first, YouTube fallback), tags with beets, and creates/updates the Navidrome playlist through the Subsonic API.

## Running locally

The app is Docker-only in normal use. For local dev:

```bash
# Build and run via Docker Compose
docker compose up --build -d

# Tail logs
docker compose logs -f

# Rebuild after code changes
docker compose up --build -d
```

The app is at `http://localhost:8080`. The container maps port 8080 → internal 5000 (gunicorn).

Run Flask directly (no Docker, requires yt-dlp, beets, ffmpeg installed locally):

```bash
pip install -r requirements.txt
FLASK_APP=run.py python run.py   # debug mode
```

There are no automated tests.

## Code formatting

Ruff handles formatting and linting. Run after every change before committing:

```bash
ruff format .
ruff check .
```

## Environment variables

| Variable | Purpose |
|---|---|
| `NAVIDROME_URL` | Navidrome base URL (e.g. `http://host:4533`) |
| `NAVIDROME_USER` / `NAVIDROME_PASSWORD` | Subsonic auth credentials |
| `SECRET_KEY` | Flask session secret |
| `DATABASE_URL` | SQLite path (default `/data/playlist_builder.db`) |
| `BEETS_CONFIG` | Beets config path (default `/config/beets/config.yaml`) |
| `DOWNLOAD_DIR` | yt-dlp temp output (default `/tmp/pb_downloads`) |
| `JOB_RETENTION_DAYS` | Days to keep terminal jobs (default `30`) |

## Architecture

**Entry point:** `run.py` → `app/__init__.py:create_app()`

`create_app()` initialises SQLAlchemy, runs startup migrations (manual `ALTER TABLE` with try/except), marks any jobs that were `running` at last shutdown as `failed`, registers the two blueprints, then starts the maintenance thread.

**Blueprints:**
- `app/routes/library.py` — file upload, library display, import trigger
- `app/routes/jobs.py` — job list, progress polling, cancel, retry, delete

**Background jobs:** `app/services/worker.py` — one daemon thread per import job, tracked via `_active_jobs: set[int]`. Cancellation is cooperative: routes add to `_cancelled_jobs`; the worker checks it between tracks. No task queue — just Python `threading`.

**Job lifecycle:** `pending → running → done / failed / cancelled`. Track lifecycle: `pending → downloading → tagging → done / failed`. On retry, failed tracks reset to `pending` and the old job is deleted; a new job replaces it.

**Services:**
- `downloader.py` — yt-dlp subprocess wrapper. Tries `scsearch1:` then `ytsearch1:`. After download, overwrites tags with iTunes metadata via mutagen so beets can organise reliably.
- `tagger.py` — beets subprocess wrapper. Runs `beet import -q -A` (no autotag, trusts existing tags). A beets success that leaves the file in place is treated as a silent failure.
- `navidrome.py` — Subsonic API client using token auth. Triggers scan, polls `getScanStatus`, then resolves track IDs and calls `createPlaylist`.
- `parser.py` — parses iTunes Library XML (plistlib) and Apple Music `.txt` exports (UTF-16 LE tab-separated). Upserts playlists and tracks; re-uploads don't reset already-imported tracks.

**UI:** Jinja2 templates with HTMX polling. `_progress.html` and `_jobs_list.html` are HTMX partials returned by `/jobs/<id>/progress` and `/jobs/list`. No JS framework.

**Database:** SQLite via SQLAlchemy. Schema lives in `app/models.py` (`Library → Playlist → Track`, `ImportJob`). Schema migrations are manual `ALTER TABLE` with bare try/except in `create_app()`.

**Beets config** (`config/beets/config.yaml`) is baked into the image and copied to the `/config/beets` volume on first run by `docker-entrypoint.sh`. Organises files under `/music` with the path pattern `$albumartist/$album ($year)/$title`.

**Image publishing:** Pushing to `main` triggers a GitHub Actions workflow that publishes `ghcr.io/thelaw51/playlistbuilder:latest`. `stack.yml` is the Portainer deployment template.

## Key invariants

- Gunicorn runs with `--workers 1 --threads 4`. Multi-worker would break the in-process `_active_jobs` set.
- beets uses `move: yes` — after a successful import the original download file is gone. The worker detects this: file absent = success; file still present after beets exit 0 = silent failure.
- `createPlaylist` with `playlistId` replaces the playlist's song list atomically — importing a playlist twice replaces it rather than duplicating.
- `Track.source = 'navidrome'` marks tracks already in the Lidarr library; `cleanup_tracks` skips file deletion for these since they were never downloaded.
