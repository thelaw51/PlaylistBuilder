"""Background job runner. One thread per import job; deduplication via _active_jobs."""

import logging
import os
import threading
from datetime import datetime

from app import db
from app.models import ImportJob, Playlist, Track
from app.services import downloader, navidrome, tagger

logger = logging.getLogger(__name__)

_active_jobs: set[int] = set()
_cancelled_jobs: set[int] = set()
_lock = threading.Lock()


def start_job(app, job_id: int) -> None:
    """Spawn a daemon thread to run *job_id*, unless it is already running."""
    with _lock:
        if job_id in _active_jobs:
            return
        _active_jobs.add(job_id)

    thread = threading.Thread(target=_run_job, args=(app, job_id), daemon=True)
    thread.start()


def cancel_job(app, job_id: int) -> None:
    """Signal a running job to stop after the current track finishes."""
    with _lock:
        if job_id not in _active_jobs:
            return
        _cancelled_jobs.add(job_id)

    with app.app_context():
        job = db.session.get(ImportJob, job_id)
        if job and job.status == 'running':
            job.status = 'cancelled'
            job.completed_at = datetime.utcnow()
            db.session.commit()


def _run_job(app, job_id: int) -> None:
    with app.app_context():
        try:
            _execute(job_id)
        except Exception:
            logger.exception('Unhandled error in job %s', job_id)
        finally:
            with _lock:
                _active_jobs.discard(job_id)
                _cancelled_jobs.discard(job_id)


def _execute(job_id: int) -> None:
    job = db.session.get(ImportJob, job_id)
    if not job:
        return

    job.status = 'running'
    job.started_at = datetime.utcnow()
    db.session.commit()

    tracks = Track.query.filter_by(playlist_id=job.playlist_id, status='pending').all()
    job.tracks_total = len(tracks)
    db.session.commit()

    for track in tracks:
        with _lock:
            cancelled = job_id in _cancelled_jobs
        if cancelled:
            break
        _process_track(job, track)

    if job.status != 'cancelled':
        _sync_to_navidrome(job)
        job.status = 'done'
        job.completed_at = datetime.utcnow()
        db.session.commit()


def _process_track(job: ImportJob, track: Track) -> None:
    track.status = 'downloading'
    track.updated_at = datetime.utcnow()
    db.session.commit()

    try:
        # Check Navidrome first — if Lidarr already has this track, skip the
        # download entirely and mark it as done so it lands in the playlist.
        try:
            existing_id = navidrome.find_track_id(track.title, track.artist or '')
        except Exception:
            existing_id = None

        if existing_id:
            track.source = 'navidrome'
            track.status = 'done'
            job.tracks_done += 1
            track.updated_at = datetime.utcnow()
            db.session.commit()
            return

        local_path, source, dl_error = downloader.download_track(
            track.title, track.artist or '', track.album or ''
        )

        if not local_path:
            _fail(job, track, dl_error or 'Not found on SoundCloud or YouTube')
            return

        track.source = source
        track.local_path = local_path
        track.status = 'tagging'
        track.updated_at = datetime.utcnow()
        db.session.commit()

        success, error = tagger.import_file(local_path)

        if success:
            if os.path.exists(local_path):
                # Beets returned 0 but left the file in place — it silently
                # skipped the import (e.g. unrecognised format or bad tags).
                os.remove(local_path)
                _fail(job, track, 'beets did not move the file (check tags/format)')
            else:
                # File is gone — beets successfully moved it to /music.
                track.status = 'done'
                job.tracks_done += 1
        else:
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except OSError:
                    pass
            _fail(job, track, error or 'beets import failed')

    except Exception as exc:
        _fail(job, track, str(exc)[:500])

    track.updated_at = datetime.utcnow()
    db.session.commit()


def _fail(job: ImportJob, track: Track, reason: str) -> None:
    track.status = 'failed'
    track.error_msg = reason
    job.tracks_failed += 1


def cleanup_tracks(app, playlist_id: int) -> None:
    """Remove any downloaded files for a playlist and reset all tracks to pending.

    Called before deleting a job so a fresh re-import starts from scratch.
    Tracks that came from Navidrome (already in Lidarr library) are reset
    without attempting file deletion since we never downloaded them.
    """
    with app.app_context():
        done_tracks = Track.query.filter_by(
            playlist_id=playlist_id, status='done'
        ).filter(Track.source != 'navidrome').all()

        for track in done_tracks:
            tagger.remove_from_library(track.title, track.artist or '')

        Track.query.filter_by(playlist_id=playlist_id).update(
            {
                'status': 'pending',
                'source': None,
                'local_path': None,
                'error_msg': None,
                'updated_at': datetime.utcnow(),
            },
            synchronize_session=False,
        )
        db.session.commit()


def _sync_to_navidrome(job: ImportJob) -> None:
    """Trigger a Navidrome scan, wait for it, then create/update the playlist."""
    playlist = db.session.get(Playlist, job.playlist_id)
    if not playlist:
        return

    done_tracks = Track.query.filter_by(playlist_id=job.playlist_id, status='done').all()
    if not done_tracks:
        return

    try:
        navidrome.trigger_scan()
        navidrome.wait_for_scan()
    except Exception:
        logger.exception('Navidrome scan failed for job %s', job.id)
        return

    song_ids: list[str] = []
    for track in done_tracks:
        nid = navidrome.find_track_id(track.title, track.artist or '')
        if nid:
            song_ids.append(nid)

    if song_ids:
        try:
            navidrome.create_or_update_playlist(playlist.name, song_ids)
        except Exception:
            logger.exception('Navidrome playlist creation failed for job %s', job.id)
