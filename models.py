from app import db
from datetime import datetime
from sqlalchemy import Text

class Call(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), nullable=False)
    call_sid = db.Column(db.String(100), unique=True)
    stream_sid = db.Column(db.String(100), unique=True)
    status = db.Column(db.String(20), default='initiated')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime)
    
class ConversationTurn(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    call_id = db.Column(db.Integer, db.ForeignKey('call.id'), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # 'user' or 'assistant'
    content = db.Column(Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    call = db.relationship('Call', backref=db.backref('conversation_turns', lazy=True))
