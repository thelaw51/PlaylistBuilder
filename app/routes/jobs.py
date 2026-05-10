from flask import Blueprint, current_app, redirect, render_template, url_for

from app import db
from app.models import ImportJob, Track
from app.services import worker

jobs_bp = Blueprint('jobs', __name__)


@jobs_bp.route('/jobs')
def list_jobs():
    jobs = ImportJob.query.order_by(ImportJob.created_at.desc()).all()
    return render_template('jobs.html', jobs=jobs)


@jobs_bp.route('/jobs/list')
def list_partial():
    """HTMX polling target — returns the jobs list partial."""
    jobs = ImportJob.query.order_by(ImportJob.created_at.desc()).all()
    return render_template('_jobs_list.html', jobs=jobs)


@jobs_bp.route('/jobs/<int:job_id>')
def show(job_id: int):
    job = db.session.get(ImportJob, job_id)
    if not job:
        return redirect(url_for('library.index'))
    tracks = Track.query.filter_by(playlist_id=job.playlist_id).order_by(Track.id).all()
    return render_template('job.html', job=job, tracks=tracks)


@jobs_bp.route('/jobs/<int:job_id>/progress')
def progress(job_id: int):
    """HTMX polling target — returns the progress partial."""
    job = db.session.get(ImportJob, job_id)
    if not job:
        return '', 404
    tracks = Track.query.filter_by(playlist_id=job.playlist_id).order_by(Track.id).all()
    return render_template('_progress.html', job=job, tracks=tracks)


@jobs_bp.route('/jobs/<int:job_id>/cancel', methods=['POST'])
def cancel(job_id: int):
    job = db.session.get(ImportJob, job_id)
    if job and job.status == 'running':
        worker.cancel_job(current_app._get_current_object(), job_id)
    return redirect(url_for('jobs.show', job_id=job_id))


@jobs_bp.route('/jobs/<int:job_id>/delete', methods=['POST'])
def delete(job_id: int):
    """Remove a job, delete any downloaded files, and reset tracks to pending."""
    job = db.session.get(ImportJob, job_id)
    if job and job.status != 'running':
        playlist_id = job.playlist_id
        db.session.delete(job)
        db.session.commit()
        worker.cleanup_tracks(current_app._get_current_object(), playlist_id)
    return redirect(url_for('jobs.list_jobs'))


@jobs_bp.route('/jobs/<int:job_id>/retry', methods=['POST'])
def retry(job_id: int):
    """Reset failed tracks to pending and start a new import job."""
    job = db.session.get(ImportJob, job_id)
    if not job or job.status == 'running':
        return redirect(url_for('jobs.show', job_id=job_id))

    active = ImportJob.query.filter_by(playlist_id=job.playlist_id, status='running').first()
    if active:
        return redirect(url_for('jobs.show', job_id=active.id))

    Track.query.filter_by(playlist_id=job.playlist_id, status='failed').update(
        {'status': 'pending', 'source': None, 'local_path': None, 'error_msg': None},
        synchronize_session=False,
    )
    db.session.commit()

    new_job = ImportJob(playlist_id=job.playlist_id)
    db.session.add(new_job)
    db.session.commit()

    worker.start_job(current_app._get_current_object(), new_job.id)
    return redirect(url_for('jobs.show', job_id=new_job.id))
