# PlaylistBuilder

A self-hosted web app that imports Apple Music playlists into [Navidrome](https://www.navidrome.org/) by downloading tracks via yt-dlp, tagging them with beets, and creating the playlist through the Subsonic API.

> **This project was created with the assistance of [Claude Code](https://claude.ai/code), Anthropic's AI coding assistant.**

---

## What it does

1. **Upload** an iTunes Library XML export or a single Apple Music playlist `.txt` export
2. **Browse** your playlists and click Import — optionally set a custom name for the Navidrome playlist
3. For each track the app:
   - Checks if it already exists in your Navidrome library (via Lidarr or otherwise) — if so, skips the download
   - Searches SoundCloud first, falls back to YouTube
   - Downloads the best available audio with embedded metadata and cover art
   - Tags and organises the file with beets
4. Triggers a Navidrome library scan and creates/updates the playlist automatically

Track progress is shown live in the browser and updates automatically. Jobs can be cancelled mid-run, retried for failed tracks only, and removed cleanly (downloaded files are deleted and tracks reset for a fresh retry).

---

## Stack

- **Python / Flask 3** — web app and background job runner
- **yt-dlp** — audio download from SoundCloud and YouTube
- **beets** — file tagging and library organisation
- **Navidrome** — music server (Subsonic-compatible API)
- **SQLite / SQLAlchemy** — job and track state
- **HTMX + Tailwind CSS** — live-updating UI, no JavaScript framework
- **Docker Compose** — single-command deployment

---

## Requirements

- Docker and Docker Compose
- A running Navidrome instance
- The host path to your music library (the folder Navidrome scans)

---

## Setup

### Option A — Portainer (recommended for remote self-hosting)

A pre-built image is published to GitHub Container Registry automatically on every push to `main`.

1. In Portainer go to **Stacks → Add stack → Web editor**
2. Paste the contents of [`stack.yml`](stack.yml) from this repo
3. Update the `/path/to/your/music` bind mount to your actual host music path
4. Switch to the **Environment variables** tab and set:

   | Variable | Value |
   |---|---|
   | `NAVIDROME_URL` | `http://your-navidrome-host:4533` |
   | `NAVIDROME_USER` | your Navidrome username |
   | `NAVIDROME_PASSWORD` | your Navidrome password |
   | `SECRET_KEY` | any long random string |
   | `JOB_RETENTION_DAYS` | how many days to keep completed jobs (default `30`) |
   | `YT_COOKIES_FILE` | *(optional)* path inside the container to a Netscape cookies file for age-restricted YouTube videos — see [Age-restricted YouTube videos](#age-restricted-youtube-videos) |

   > **Do not hardcode passwords directly in the stack file.** Use Portainer's Environment variables tab or Docker Secrets instead.

5. Click **Deploy the stack**

Two named volumes (`playlistbuilder_data` and `playlistbuilder_beets`) are created automatically to persist the database and beets library across container updates.

---

### Option B — Local Docker Compose

```bash
git clone <repo-url>
cd PlaylistBuilder
cp .env.example .env
```

Edit `.env`:

```env
MUSIC_DIR=/path/to/your/music        # host path Navidrome scans
NAVIDROME_URL=http://your-host:4533  # your Navidrome instance URL
NAVIDROME_USER=admin
NAVIDROME_PASSWORD=your-password
SECRET_KEY=change-me-to-something-random
JOB_RETENTION_DAYS=30
```

```bash
docker compose up --build -d
```

Open **http://localhost:8080**.

---

## Usage

### Export from Apple Music

**Full library (all playlists):**
Music.app → `File` → `Library` → `Export Library…` → upload the `.xml` file

**Single playlist:**
Right-click a playlist in the sidebar → `Export…` → upload the `.txt` file

### Import a playlist

The home page shows your library and upload drawer in one place.

1. Click **update library from file** to expand the upload drawer, then upload an `.xml` or `.txt` export — re-uploads merge into the existing library without resetting already-imported tracks
2. Sort playlists by name (a–z) or track count using the toolbar
3. Optionally type a custom Navidrome playlist name in the field next to a playlist — leave it blank to use the Apple Music name as-is
4. Click **import** on that row, or use the checkboxes and **import (N)** button to queue multiple playlists at once
5. Watch progress update live on the job page — each track shows its status and source (SoundCloud, YouTube, or already in library). Failed tracks show the error inline
6. When complete, the playlist appears in Navidrome automatically

### Managing jobs

Actions are available on both the individual job page and the jobs list:

- **Cancel** — stops after the current track finishes downloading
- **Retry failed (N)** — resets all failed and unprocessed tracks back to pending and starts a new run, preserving tracks that already completed successfully. Available after a job finishes, fails, or is cancelled
- **Remove** — deletes any downloaded files and resets tracks to pending so you can re-import cleanly. Prompts for confirmation before proceeding

The jobs list refreshes automatically every few seconds while any import is active, so you can monitor multiple jobs at once without manually reloading.

---

## Notes

- Tracks already in your Navidrome library (e.g. managed by Lidarr) are detected first and added to the playlist without re-downloading
- Downloads from SoundCloud/YouTube are lossy (MP3, M4A, Opus). Lidarr-managed tracks retain their original quality
- Cover art is embedded automatically from the download source
- Re-uploading a library file **merges** into the existing library — playlists that were already imported are not reset
- If a playlist with the same name already exists in Navidrome it will be **replaced** with the current import's tracks — use the custom name field if you want to keep an existing playlist untouched
- The beets library (`config/beets/library.db`) tracks what has been imported. If you manually delete music files, remove the job through the UI rather than deleting files directly — this keeps the beets database consistent
- Jobs that were running when the container last stopped are automatically marked as failed on startup so you can retry them cleanly
- Completed, failed, and cancelled jobs are automatically purged after `JOB_RETENTION_DAYS` days (default 30) — this runs on startup and every 24 hours

---

## Age-restricted YouTube videos

Most age-restricted videos are handled automatically using the YouTube Android player client (no configuration needed).

For videos that still fail, you can provide a cookies file from a logged-in YouTube session:

1. Install the **"Get cookies.txt LOCALLY"** extension (Chrome/Edge) or **"cookies.txt"** (Firefox)
2. Go to `youtube.com` while logged in, then use the extension to export cookies for the current site
3. Place the file somewhere the container can read it — the `/data` volume is the easiest:
   ```
   /your/host/data/youtube-cookies.txt
   ```
4. Set the env var in Portainer (or your compose file):
   ```
   YT_COOKIES_FILE=/data/youtube-cookies.txt
   ```
   No restart needed if the volume is already mounted — the path is read on each download.

YouTube cookies typically expire after a few weeks. When they do, re-export and overwrite the file at the same path.

---

## AI Disclosure

This project was built with the assistance of **Claude Code** (Anthropic). The architecture, all source code, Docker configuration, and documentation were generated and iterated through a conversational session with the AI. The human author directed requirements, made design decisions, and tested the result.
