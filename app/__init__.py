import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL', 'sqlite:////data/playlist_builder.db'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

    db.init_app(app)

    with app.app_context():
        from app.models import Library, Playlist, Track, ImportJob  # noqa: F401
        from sqlalchemy import or_
        from datetime import datetime
        db.create_all()

        # Ensure the singleton global library exists
        if not db.session.get(Library, 1):
            db.session.add(Library(id=1, name='App Library'))
            db.session.commit()

        # Mark any jobs left running from a previous process as failed so they
        # don't appear frozen. Mid-flight tracks are set to failed so the
        # existing "Retry failed" button can re-queue them.
        stuck_jobs = ImportJob.query.filter_by(status='running').all()
        for job in stuck_jobs:
            Track.query.filter(
                Track.playlist_id == job.playlist_id,
                or_(Track.status == 'downloading', Track.status == 'tagging'),
            ).update(
                {'status': 'failed', 'error_msg': 'Interrupted by server restart'},
                synchronize_session=False,
            )
            job.tracks_failed = Track.query.filter_by(
                playlist_id=job.playlist_id, status='failed'
            ).count()
            job.status = 'failed'
            job.completed_at = datetime.utcnow()
        if stuck_jobs:
            db.session.commit()

    from app.routes.library import library_bp
    from app.routes.jobs import jobs_bp
    app.register_blueprint(library_bp)
    app.register_blueprint(jobs_bp)

    from app.services import worker as _worker
    _worker.purge_old_jobs(app)
    _worker.start_maintenance(app)

    return app
