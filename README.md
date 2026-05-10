# PlaylistBuilder

A self-hosted web app that imports Apple Music playlists into [Navidrome](https://www.navidrome.org/) by downloading tracks via yt-dlp, tagging them with beets, and creating the playlist through the Subsonic API.

> **This project was created with the assistance of [Claude Code](https://claude.ai/code), Anthropic's AI coding assistant.**

---

## What it does

1. **Upload** an iTunes Library XML export or a single Apple Music playlist `.txt` export
2. **Browse** your playlists and click Import
3. For each track the app:
   - Checks if it already exists in your Navidrome library (via Lidarr or otherwise) — if so, skips the download
   - Searches SoundCloud first, falls back to YouTube
   - Downloads the best available audio with embedded metadata and cover art
   - Tags and organises the file with beets
4. Triggers a Navidrome library scan and creates/updates the playlist automatically

Track progress is shown live in the browser. Jobs can be cancelled mid-run and removed cleanly (downloaded files are deleted and tracks reset for a fresh retry).

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

### 1. Clone the repo

```bash
git clone <repo-url>
cd PlaylistBuilder
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Edit `.env`:

```env
MUSIC_DIR=/path/to/your/music        # host path Navidrome scans
NAVIDROME_URL=http://your-host:4533  # your Navidrome instance URL
NAVIDROME_USER=admin
NAVIDROME_PASSWORD=your-password
SECRET_KEY=change-me-to-something-random
```

### 3. Start the app

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

1. Upload your file on the home page
2. Click **Import** next to the playlist you want
3. Watch progress on the job page — each track shows its status and source (SoundCloud, YouTube, or Already in library)
4. When complete, the playlist appears in Navidrome automatically

### Managing jobs

- **Cancel** — stops after the current track finishes downloading
- **Remove** — cancels, deletes any downloaded files, and resets tracks to pending so you can re-import cleanly

---

## Notes

- Tracks already in your Navidrome library (e.g. managed by Lidarr) are detected first and added to the playlist without re-downloading
- Downloads from SoundCloud/YouTube are lossy (MP3, M4A, Opus). Lidarr-managed tracks retain their original quality
- Cover art is embedded automatically from the download source
- The beets library (`config/beets/library.db`) tracks what has been imported. If you manually delete music files, remove the job through the UI rather than deleting files directly — this keeps the beets database consistent

---

## AI Disclosure

This project was built with the assistance of **Claude Code** (Anthropic). The architecture, all source code, Docker configuration, and documentation were generated and iterated through a conversational session with the AI. The human author directed requirements, made design decisions, and tested the result.
