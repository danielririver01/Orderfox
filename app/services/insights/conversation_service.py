"""
conversation_service.py — Persistencia de Copilot VZ.

Operaciones CRUD sobre CopilotConversation y CopilotMessage. Mantiene
la integridad de tenant (un usuario solo accede a sus propias
conversaciones) y genera títulos cuando corresponde.
"""

import json
from datetime import datetime, timezone

from sqlalchemy import exists

from app import db
from app.models import CopilotConversation, CopilotMessage


def list_conversations(user_id, limit=50):
    return (
        CopilotConversation.query
        .filter_by(user_id=user_id)
        .order_by(
            CopilotConversation.pinned.desc(),
            CopilotConversation.updated_at.desc(),
        )
        .limit(limit)
        .all()
    )


def get_conversation(conversation_id, user_id):
    return CopilotConversation.query.filter_by(id=conversation_id, user_id=user_id).first()


def create_conversation(user_id, restaurant_id, title=None, prompt_version='v1.0', model='deepseek-chat'):
    conv = CopilotConversation(
        user_id=user_id,
        restaurant_id=restaurant_id,
        title=title,
        prompt_version=prompt_version,
        model=model,
    )
    db.session.add(conv)
    db.session.commit()
    return conv


def get_messages(conversation_id):
    return (
        CopilotMessage.query
        .filter_by(conversation_id=conversation_id)
        .order_by(CopilotMessage.created_at.asc())
        .all()
    )


def add_message(conversation_id, role, content, metadata=None):
    msg = CopilotMessage(
        conversation_id=conversation_id,
        role=role,
        content=content,
        metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata is not None else None,
    )
    db.session.add(msg)
    # Refresca updated_at de la conversación.
    conv = CopilotConversation.query.get(conversation_id)
    if conv:
        conv.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return msg


def delete_conversation(conversation_id, user_id):
    conv = get_conversation(conversation_id, user_id)
    if not conv:
        return False
    db.session.delete(conv)
    db.session.commit()
    return True


def set_title(conversation_id, title):
    conv = CopilotConversation.query.get(conversation_id)
    if not conv:
        return
    conv.title = title
    db.session.commit()


def set_pinned(conversation_id, pinned):
    conv = CopilotConversation.query.get(conversation_id)
    if not conv:
        return
    conv.pinned = bool(pinned)
    db.session.commit()


def count_pinned(user_id):
    return CopilotConversation.query.filter_by(user_id=user_id, pinned=True).count()


def find_draft(user_id):
    """Devuelve una conversación sin mensajes (borrador) del usuario, o None."""
    return (
        CopilotConversation.query
        .filter_by(user_id=user_id)
        .filter(~exists().where(CopilotMessage.conversation_id == CopilotConversation.id))
        .order_by(CopilotConversation.updated_at.desc())
        .first()
    )


MAX_PINNED = 3


def mark_analysis_active(conversation_id):
    conv = CopilotConversation.query.get(conversation_id)
    if conv:
        conv.analysis_active = True
        db.session.commit()


def make_title_from_message(text, limit=60):
    """Título por defecto (Nivel 1 o fallback): recorta el primer mensaje."""
    clean = ' '.join(str(text).split())
    if len(clean) <= limit:
        return clean
    return clean[:limit].rstrip() + '…'


def safe_get_message(message_id, conversation_id):
    """Retorna un mensaje por ID y conversación, o None."""
    return CopilotMessage.query.filter_by(id=message_id, conversation_id=conversation_id).first()


def update_message_content(message_id, content):
    """Actualiza el contenido de un mensaje (edición de mensaje enviado)."""
    msg = CopilotMessage.query.get(message_id)
    if not msg:
        return
    msg.content = content
    db.session.commit()


def delete_messages_after(conversation_id, after_message_id):
    """Borra todos los mensajes creados después de `after_message_id`.

    Usado al editar un mensaje (nueva rama) o al regenerar una respuesta:
    se elimina la cola de la conversación a partir del mensaje indicado.
    """
    target = CopilotMessage.query.get(after_message_id)
    if not target:
        return
    tail = (
        CopilotMessage.query
        .filter_by(conversation_id=conversation_id)
        .filter(CopilotMessage.id > after_message_id)
        .all()
    )
    for m in tail:
        db.session.delete(m)
    db.session.commit()
