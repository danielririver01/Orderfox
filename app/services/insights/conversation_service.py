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


def list_conversations(user_id, source='insights', limit=200):
    return (
        CopilotConversation.query
        .filter_by(user_id=user_id, source=source)
        .order_by(
            CopilotConversation.pinned.desc(),
            CopilotConversation.updated_at.desc(),
        )
        .limit(limit)
        .all()
    )


def search_conversations(user_id, query, source='insights', limit=50):
    """Filtra las conversaciones del usuario por texto.

    Busca coincidencias (case-insensitive) en el título de la conversación
    y en el contenido de sus mensajes (primer mensaje, título derivado, etc.).
    Devuelve las conversaciones ordenadas igual que list_conversations.
    """
    from sqlalchemy import or_

    q = f"%{query.strip().lower()}%"
    if not query or not query.strip():
        return list_conversations(user_id, source=source, limit=limit)

    # Subquery: conversaciones que tienen algún mensaje cuyo contenido
    # coincide con la búsqueda.
    convs_with_msg = (
        db.session.query(CopilotMessage.conversation_id)
        .filter(CopilotMessage.content.ilike(q))
        .subquery()
    )

    return (
        CopilotConversation.query
        .filter(
            CopilotConversation.user_id == user_id,
            CopilotConversation.source == source,
            or_(
                CopilotConversation.title.ilike(q),
                CopilotConversation.id.in_(convs_with_msg),
            ),
        )
        .order_by(
            CopilotConversation.pinned.desc(),
            CopilotConversation.updated_at.desc(),
        )
        .limit(limit)
        .all()
    )


def get_conversation(conversation_id, user_id):
    return CopilotConversation.query.filter_by(id=conversation_id, user_id=user_id).first()


def create_conversation(user_id, restaurant_id, title=None, prompt_version='v1.0', model='deepseek-v4-flash', source='insights'):
    conv = CopilotConversation(
        user_id=user_id,
        restaurant_id=restaurant_id,
        title=title,
        prompt_version=prompt_version,
        model=model,
        source=source,
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
    # UPDATE directo — evita el error MySQL 1020 ("record has changed since last read")
    # que ocurre cuando dos requests concurrentes modifican la misma conversación.
    CopilotConversation.query.filter_by(id=conversation_id).update(
        {'updated_at': datetime.now(timezone.utc)}
    )
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
    CopilotConversation.query.filter_by(id=conversation_id).update(
        {'title': title, 'updated_at': datetime.now(timezone.utc)}
    )
    db.session.commit()


def set_pinned(conversation_id, pinned):
    CopilotConversation.query.filter_by(id=conversation_id).update(
        {'pinned': bool(pinned), 'updated_at': datetime.now(timezone.utc)}
    )
    db.session.commit()


def count_pinned(user_id, source='insights'):
    return CopilotConversation.query.filter_by(user_id=user_id, pinned=True, source=source).count()


def find_draft(user_id, source='insights'):
    """Devuelve una conversación sin mensajes (borrador) del usuario, o None."""
    return (
        CopilotConversation.query
        .filter_by(user_id=user_id, source=source)
        .filter(~exists().where(CopilotMessage.conversation_id == CopilotConversation.id))
        .order_by(CopilotConversation.updated_at.desc())
        .first()
    )


MAX_PINNED = 3


def mark_analysis_active(conversation_id):
    """Marca la conversación como análisis activo e inicia un bloque nuevo.

    Se llama tras pagar un token (primer mensaje o al llegar al tope de
    seguimientos): reinicia el contador de follow-ups a 0.
    """
    CopilotConversation.query.filter_by(id=conversation_id).update(
        {'analysis_active': True, 'follow_up_count': 0,
         'updated_at': datetime.now(timezone.utc)}
    )
    db.session.commit()


def clear_analysis_active(conversation_id):
    """Limpia analysis_active y resetea el contador de follow-ups."""
    CopilotConversation.query.filter_by(id=conversation_id).update(
        {'analysis_active': False, 'follow_up_count': 0,
         'updated_at': datetime.now(timezone.utc)}
    )
    db.session.commit()


def reserve_follow_up(conversation_id, max_count):
    """Reserva un follow-up gratis de forma atómica si queda espacio en el tope.

    UPDATE condicional (follow_up_count < max_count) en una sola sentencia:
    sin TOCTOU entre leer y escribir. Devuelve True si el turno quedó
    reservado como seguimiento gratis, False si se llegó al tope (ese turno
    deberá consumir un token nuevo para abrir un bloque).
    """
    result = (
        CopilotConversation.query
        .filter(
            CopilotConversation.id == conversation_id,
            CopilotConversation.follow_up_count < max_count,
        )
        .update(
            {CopilotConversation.follow_up_count: CopilotConversation.follow_up_count + 1},
            synchronize_session=False,
        )
    )
    db.session.commit()
    return result > 0


def delete_message(message_id):
    """Elimina un mensaje (rollback de un turno que falló)."""
    msg = CopilotMessage.query.get(message_id)
    if not msg:
        return False
    db.session.delete(msg)
    db.session.commit()
    return True


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
