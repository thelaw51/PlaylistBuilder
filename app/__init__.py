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
        db.create_all()

    from app.routes.library import library_bp
    from app.routes.jobs import jobs_bp
    app.register_blueprint(library_bp)
    app.register_blueprint(jobs_bp)

    return app
