"""
tenant_router.py — Resuelve qué adapter de datos usa una conversación (FASE 0).

Un solo Copilot VZ, un router delgado: si el tenant de la conversación es un
Business del vertical 'verduras' (activo), se usa data_service_verduras con
business_id; en cualquier otro caso, data_service con restaurant_id.

Sin migraciones: lee Business por ID. El hook vive en message_handler
(una sola resolución por mensaje) — ver propuesta FASE 0.
"""

from app.models import Business, db


def resolve(conv):
    """Devuelve (adapter, tenant_id, vertical, display_name) para la conversación.

    - adapter: módulo con la interfaz de data_service (quick/contexto/stage).
    - tenant_id: business_id (verduras) o restaurant_id (restaurante).
    - vertical: 'verduras' | 'restaurant'.
    - display_name: nombre del negocio para el prompt (o None).
    """
    from app.services.insights import data_service, data_service_verduras

    tenant_id = getattr(conv, 'business_id', None) or conv.restaurant_id
    biz = db.session.get(Business, tenant_id) if tenant_id else None
    if biz is not None and biz.vertical == 'verduras' and biz.is_active:
        return data_service_verduras, biz.id, 'verduras', biz.name
    return data_service, conv.restaurant_id, 'restaurant', None
