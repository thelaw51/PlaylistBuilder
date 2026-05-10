from datetime import datetime
from app import db


class Library(db.Model):
    __tablename__ = 'library'

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    playlists = db.relationship('Playlist', backref='library', lazy=True)


class Playlist(db.Model):
    __tablename__ = 'playlist'

    id = db.Column(db.Integer, primary_key=True)
    library_id = db.Column(db.Integer, db.ForeignKey('library.id'), nullable=False)
    name = db.Column(db.String(500), nullable=False)
    itunes_id = db.Column(db.String(100), nullable=False)

    tracks = db.relationship('Track', backref='playlist', lazy=True)
    jobs = db.relationship('ImportJob', backref='playlist', lazy=True)


class Track(db.Model):
    __tablename__ = 'track'

    id = db.Column(db.Integer, primary_key=True)
    playlist_id = db.Column(db.Integer, db.ForeignKey('playlist.id'), nullable=False)
    itunes_id = db.Column(db.String(100))
    title = db.Column(db.String(500), nullable=False)
    artist = db.Column(db.String(500))
    album = db.Column(db.String(500))
    duration_ms = db.Column(db.Integer)
    # pending | downloading | tagging | done | failed
    status = db.Column(db.String(50), default='pending', nullable=False)
    source = db.Column(db.String(50))        # 'soundcloud' | 'youtube'
    local_path = db.Column(db.String(2000))
    error_msg = db.Column(db.String(2000))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)


class ImportJob(db.Model):
    __tablename__ = 'import_job'

    id = db.Column(db.Integer, primary_key=True)
    playlist_id = db.Column(db.Integer, db.ForeignKey('playlist.id'), nullable=False)
    # pending | running | done | failed
    status = db.Column(db.String(50), default='pending', nullable=False)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    tracks_total = db.Column(db.Integer, default=0)
    tracks_done = db.Column(db.Integer, default=0)
    tracks_failed = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
