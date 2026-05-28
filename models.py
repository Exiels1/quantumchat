from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy import UniqueConstraint
import json

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(30), unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    avatar        = db.Column(db.String(500), default=None)   # Cloudinary URL
    status        = db.Column(db.String(120), default="offline")
    bio           = db.Column(db.String(220), default=None)
    backup_codes  = db.Column(db.Text)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def set_backup_codes(self, codes):
        self.backup_codes = json.dumps([generate_password_hash(c) for c in codes])

    def consume_backup_code(self, code):
        if not self.backup_codes:
            return False
        hashes = json.loads(self.backup_codes)
        for i, h in enumerate(hashes):
            if check_password_hash(h, code):
                del hashes[i]
                self.backup_codes = json.dumps(hashes)
                return True
        return False

    @property
    def avatar_url(self):
        return self.avatar or None

    @property
    def initials(self):
        return self.username[0].upper()


class DirectThread(db.Model):
    __tablename__ = 'direct_thread'
    __table_args__ = (UniqueConstraint('a_id', 'b_id', name='uq_thread'),)
    id    = db.Column(db.Integer, primary_key=True)
    a_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    b_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    user_a = db.relationship('User', foreign_keys=[a_id])
    user_b = db.relationship('User', foreign_keys=[b_id])


class DirectMessage(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    thread_id  = db.Column(db.Integer, db.ForeignKey('direct_thread.id'), nullable=False)
    sender_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content    = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id])