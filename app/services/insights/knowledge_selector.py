"""
Selector de conocimiento de industria para Copilot VZ (Fase 2).

Mapea el mensaje del usuario (y la intención clasificada) a UN documento de
best practices de `knowledge_base/`, que se inyecta como contexto adicional
en el prompt del LLM.

Diseño deliberadamente simple:
- Sin vector DB ni embeddings: con <50 documentos, un scoring por keywords +
  mapeo por intención alcanza la misma calidad con cero infraestructura.
- Máximo 1 documento por consulta (~600-800 tokens) para no saturar el
  presupuesto de 12K tokens del contexto.
- Los documentos viven en archivos .md editables sin tocar código.
"""

from functools import cache
from pathlib import Path

from flask import current_app

# Directorio de la base de conocimiento (raíz del proyecto).
KB_DIR = Path(__file__).resolve().parents[3] / 'knowledge_base'

# Tope de caracteres inyectados (~800 tokens a ~3.5 chars/token).
MAX_KNOWLEDGE_CHARS = 2600

DOCS = [
    {
        'key': 'menu_engineering',
        'file': 'menu_engineering.md',
        # Cuándo aplica: decisiones sobre carta/platos/productos.
        'keywords': [
            'menu', 'menú', 'carta', 'plato', 'platos', 'producto estrella',
            'rentabilidad de', 'que plato', 'qué plato', 'quitar', 'sacar del menu',
            'combo', 'combos', 'matriz', 'popularidad',
        ],
    },
    {
        'key': 'slow_days',
        'file': 'slow_days.md',
        # Cuándo aplica: días flojos, promociones, activaciones.
        'keywords': [
            'martes', 'miercoles', 'miércoles', 'dia muerto', 'día muerto',
            'dias flojos', 'días flojos', 'promocion', 'promoción', 'promo',
            '2x1', 'activacion', 'activación', 'bajar ventas entre semana',
        ],
    },
    {
        'key': 'food_cost',
        'file': 'food_cost.md',
        # Cuándo aplica: costos, mermas, proveedores, márgenes.
        'keywords': [
            'food cost', 'costo', 'costos', 'merma', 'mermas', 'insumo', 'insumos',
            'materia prima', 'proveedor', 'proveedores', 'desperdicio',
            'porcion', 'porción', 'porciones', 'receta', 'costear',
        ],
    },
    {
        'key': 'ticket_promedio',
        'file': 'ticket_promedio.md',
        # Cuándo aplica: vender más por pedido, capacitar personal, upselling.
        'keywords': [
            'ticket promedio', 'ticket', 'vender mas', 'vender más', 'cross selling',
            'cross-selling', 'upselling', 'mesero', 'meseros', 'cajero', 'cajeros',
            'capacitar', 'adicional', 'postre', 'aumentar venta',
        ],
    },
]

# Fallback por intención cuando ninguna keyword matchea.
INTENT_DOCS = {
    'profitability_analysis': 'food_cost',
    'recommendations': 'ticket_promedio',
    'sales_analysis': 'menu_engineering',
    'executive_report': None,
    'trend_analysis': None,
    'general_analysis': None,
}


@cache
def _load_doc(filename):
    """Lee un documento de KB. Cacheado en memoria (archivos pequeños)."""
    path = KB_DIR / filename
    try:
        return path.read_text(encoding='utf-8')
    except OSError as e:
        current_app.logger.warning(f"KB doc no legible ({filename}): {e}")
        return None


def select_knowledge(user_message, intent=None, max_chars=MAX_KNOWLEDGE_CHARS):
    """
    Retorna el texto del documento más relevante para el mensaje, o None.

    Prioridad: keyword match en el mensaje > mapeo por intención > None.
    Trunca el documento al tope de caracteres para proteger el presupuesto
    de tokens del contexto.
    """
    if not user_message and not intent:
        return None

    norm = (user_message or '').lower()
    best_key = None
    best_score = 0
    for doc in DOCS:
        score = sum(1 for kw in doc['keywords'] if kw in norm)
        if score > best_score:
            best_score = score
            best_key = doc['key']

    if not best_key:
        fallback = INTENT_DOCS.get(intent)
        best_key = fallback

    if not best_key:
        return None

    filename = next((d['file'] for d in DOCS if d['key'] == best_key), None)
    content = _load_doc(filename) if filename else None
    if not content:
        return None

    if len(content) > max_chars:
        # Cortar en el último salto de línea antes del tope (no partir palabras).
        cut = content.rfind('\n', 0, max_chars)
        content = content[:cut if cut > 0 else max_chars] + '\n\n[...]'
    return content


def clear_cache():
    """Invalida la caché de documentos (útil en tests)."""
    _load_doc.cache_clear()
