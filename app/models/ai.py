"""
Modelos del módulo Copilot VZ (conversaciones, mensajes, eventos de negocio).

Incluye PlatformBenchmark: snapshots anónimos (medianas) para benchmarking
entre restaurantes con k-anonymity.
"""

import json
from datetime import datetime, timezone

from app.models import AwareDateTime, db


class CopilotConversation(db.Model):
    __tablename__ = 'copilot_conversations'

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    # Origen de la conversación: 'insights' (Copilot VZ) o 'cash_register' (Centro de Caja).
    source = db.Column(db.String(30), default='insights', nullable=False, index=True)
    title = db.Column(db.String(200), nullable=True)
    prompt_version = db.Column(db.String(10), default='v1.0')
    model = db.Column(db.String(50), default='deepseek-v4-flash')
    analysis_active = db.Column(db.Boolean, default=False, nullable=False)
    # Contador de seguimientos gratis dentro del bloque de análisis actual.
    # Se reinicia a 0 al pagar un token nuevo (mark_analysis_active) o al
    # limpiar analysis_active. El tope lo define COPILOT_MAX_FOLLOW_UPS.
    follow_up_count = db.Column(db.Integer, default=0, nullable=False)
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


class AILlmCall(db.Model):
    """
    Telemetría de costo por llamada al LLM (DeepSeek).

    Registro inmutable de cada invocación para separar el gasto real por
    fuente (insights vs cash_register) y por restaurante, y para decidir más
    adelante si Elite necesita un techo de uso justo. No afecta el flujo de
    negocio: es observabilidad.
    """

    __tablename__ = 'ai_llm_calls'

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(30), nullable=False, index=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('copilot_conversations.id', ondelete='SET NULL'),
                                nullable=True, index=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'),
                              nullable=False, index=True)
    model = db.Column(db.String(50), nullable=False)
    input_tokens_est = db.Column(db.Integer, nullable=False, default=0)
    output_tokens_est = db.Column(db.Integer, nullable=False, default=0)
    execution_ms = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc), index=True)

    conversation = db.relationship('CopilotConversation', backref=db.backref('llm_calls', lazy='dynamic'))

    def __repr__(self):
        return f'<AILlmCall {self.id} source={self.source} model={self.model}>'


class PlatformBenchmark(db.Model):
    """
    Snapshot de benchmarks ANONIMIZADOS de la plataforma (solo medianas).

    Un registro por cohorte ('global' o cuisine_type del restaurante).
    Se recalcula cada noche vía APScheduler. Solo se publica una cohorte si
    cumple k-anonymity (>= K_MIN restaurantes con datos suficientes), y se
    usan medianas para que ningún restaurante atípico distorsione el valor
    ni permita inferir datos de un competidor individual.

    El contenido real vive en metrics_json (dict con las métricas agregadas);
    las columnas escalares existen para consultas y depuración rápidas.
    """

    __tablename__ = 'platform_benchmarks'

    id = db.Column(db.Integer, primary_key=True)
    # Cohorte: 'global' o el cuisine_type del grupo de restaurantes.
    cohort = db.Column(db.String(30), nullable=False, unique=True, index=True)
    restaurant_count = db.Column(db.Integer, nullable=False, default=0)
    period_days = db.Column(db.Integer, nullable=False, default=30)
    metrics_json = db.Column(db.Text, nullable=False)
    computed_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<PlatformBenchmark {self.cohort} n={self.restaurant_count}>'

    @property
    def metrics(self):
        try:
            return json.loads(self.metrics_json)
        except (ValueError, TypeError):
            return {}
