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
        from sqlalchemy import text
        db.create_all()
        with db.engine.connect() as conn:
            try:
                conn.execute(text("ALTER TABLE import_job ADD COLUMN navidrome_name VARCHAR(500)"))
                conn.commit()
            except Exception:
                pass  # column already exists

    from app.routes.library import library_bp
    from app.routes.jobs import jobs_bp
    app.register_blueprint(library_bp)
    app.register_blueprint(jobs_bp)

    return app
