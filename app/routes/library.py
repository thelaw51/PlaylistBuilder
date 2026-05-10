import os
import tempfile
from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import func
from werkzeug.utils import secure_filename

from app import db
from app.models import ImportJob, Library, Playlist, Track
from app.services import parser, worker

library_bp = Blueprint("library", __name__)

_LIBRARY_ID = 1


@library_bp.route("/")
def index():
    sort = request.args.get("sort", "name")
    if sort == "tracks":
        playlists = (
            Playlist.query.filter_by(library_id=_LIBRARY_ID)
            .outerjoin(Track, Track.playlist_id == Playlist.id)
            .group_by(Playlist.id)
            .order_by(func.count(Track.id).desc())
            .all()
        )
    else:
        playlists = Playlist.query.filter_by(library_id=_LIBRARY_ID).order_by(Playlist.name).all()
    lib = db.session.get(Library, _LIBRARY_ID)
    return render_template("index.html", playlists=playlists, sort=sort, lib=lib)


@library_bp.route("/library", methods=["POST"])
def upload():
    f = request.files.get("library_file")
    if not f or not f.filename:
        flash("No file selected.", "error")
        return redirect(url_for("library.index"))

    ext = os.path.splitext(f.filename.lower())[1]
    if ext not in (".xml", ".txt"):
        flash("Please upload an iTunes Library XML (.xml) or playlist export (.txt) file.", "error")
        return redirect(url_for("library.index"))

    filename = secure_filename(f.filename)
    safe_stem = os.path.splitext(filename)[0]

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext)
    try:
        os.close(tmp_fd)
        f.save(tmp_path)

        if ext == ".xml":
            count = parser.parse_library(tmp_path)
            label = f"{count} playlist(s)"
        else:
            playlist_name = safe_stem or filename
            count = parser.parse_playlist_txt(tmp_path, playlist_name)
            label = f'playlist "{playlist_name}"'

        # Update the library's timestamp to reflect the latest upload
        lib = db.session.get(Library, _LIBRARY_ID)
        lib.updated_at = datetime.utcnow()
        db.session.commit()

        flash(f"Imported {label} from {filename}.", "success")
        return redirect(url_for("library.index"))
    except Exception as exc:
        db.session.rollback()
        flash(f"Failed to parse file: {exc}", "error")
        return redirect(url_for("library.index"))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@library_bp.route("/playlist/<int:pl_id>/import", methods=["POST"])
def import_playlist(pl_id: int):
    Playlist.query.filter_by(id=pl_id, library_id=_LIBRARY_ID).first_or_404()

    active = ImportJob.query.filter_by(playlist_id=pl_id, status="running").first()
    if active:
        return redirect(url_for("jobs.show", job_id=active.id))

    navidrome_name = request.form.get("navidrome_name", "").strip() or None
    job = ImportJob(playlist_id=pl_id, navidrome_name=navidrome_name)
    db.session.add(job)
    db.session.commit()

    worker.start_job(current_app._get_current_object(), job.id)

    if request.headers.get("HX-Request"):
        return render_template("_playlist_queued.html", job=job)
    return redirect(url_for("jobs.show", job_id=job.id))


@library_bp.route("/import-selected", methods=["POST"])
def import_selected():
    pl_ids = request.form.getlist("pl", type=int)
    for pl_id in pl_ids:
        playlist = Playlist.query.filter_by(id=pl_id, library_id=_LIBRARY_ID).first()
        if not playlist:
            continue
        if ImportJob.query.filter_by(playlist_id=pl_id, status="running").first():
            continue
        job = ImportJob(playlist_id=pl_id)
        db.session.add(job)
        db.session.commit()
        worker.start_job(current_app._get_current_object(), job.id)
    return redirect(url_for("jobs.list_jobs"))
