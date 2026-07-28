"""
Modelos del módulo Copilot VZ (conversaciones, mensajes, eventos de negocio).
"""

from datetime import datetime, timezone
from app.models import db, AwareDateTime


class CopilotConversation(db.Model):
    __tablename__ = 'copilot_conversations'

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(200), nullable=True)
    prompt_version = db.Column(db.String(10), default='v1.0')
    model = db.Column(db.String(50), default='deepseek-chat')
    analysis_active = db.Column(db.Boolean, default=False, nullable=False)
    pinned = db.Column(db.Boolean, default=False, nullable=False)
    metadata_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    restaurant = db.relationship('Restaurant', backref=db.backref('copilot_conversations', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('copilot_conversations', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<CopilotConversation {self.id} title={self.title}>'


class CopilotMessage(db.Model):
    __tablename__ = 'copilot_messages'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('copilot_conversations.id', ondelete='CASCADE'), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    metadata_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))

    conversation = db.relationship('CopilotConversation', backref=db.backref('messages', lazy='dynamic', cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<CopilotMessage {self.id} [{self.role}]>'
    

class CopilotBusinessEvent(db.Model):
    __tablename__ = 'copilot_business_events'

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=False, index=True)
    kind = db.Column(db.String(50), nullable=False, index=True)
    priority = db.Column(db.SmallInteger, default=0, nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    preview = db.Column(db.String(300), nullable=False)
    template_key = db.Column(db.String(50), nullable=False)
    template_data = db.Column(db.Text, nullable=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('copilot_conversations.id', ondelete='SET NULL'), nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))
    consumed_at = db.Column(AwareDateTime, nullable=True)
    dismissed_at = db.Column(AwareDateTime, nullable=True)

    restaurant = db.relationship('Restaurant', backref=db.backref('copilot_events', lazy='dynamic', cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<CopilotBusinessEvent {self.id} kind={self.kind} p={self.priority}>'
