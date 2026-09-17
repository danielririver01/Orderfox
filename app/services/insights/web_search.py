"""
web_search.py — Capa de búsqueda web para Copilot VZ.

Usa Tavily para responder preguntas con contexto externo en tiempo real.
El resto del sistema no necesita saber qué proveedor de búsqueda se usa.

Flujo:
    message_handler.py → is_web_search_query() → search() → prompt_builder
"""

import re
from datetime import datetime, timezone

from flask import current_app


class WebSearchError(Exception):
    """Error en la búsqueda web (API key faltante, rate limit, etc.)."""
    pass


# ── Patrones de detección de queries que requieren búsqueda web ──────────────
# Si el clasificador detecta "analysis" pero la query necesita contexto externo,
# este módulo decide si vale la pena gastar una query de Tavily.

_WEB_SEARCH_PATTERNS = [
    # Precios de mercado
    re.compile(r'precio.*(hoy|actual|mercado|colombia|mayorista|plaza|proveedor)', re.IGNORECASE),
    re.compile(r'cu[aá]nto cuesta', re.IGNORECASE),
    re.compile(r'cu[aá]nto est[aá]', re.IGNORECASE),
    re.compile(r'cu[aá]nto vale', re.IGNORECASE),
    re.compile(r'cu[aá]nto cobr', re.IGNORECASE),
    re.compile(r'valor.*(hoy|actual|mercado|colombia|del?)', re.IGNORECASE),
    re.compile(r'costo.*(actual|hoy|mercado|referencia|del?)', re.IGNORECASE),
    re.compile(r'price|pricing', re.IGNORECASE),

    # Tendencias e industria
    re.compile(r'tendencia.*(gastronom|restaurante|industria|food|2025|2026)', re.IGNORECASE),
    re.compile(r'qu[eé].*(pasa|est[aá] pasando|est[aá] tendiendo).*(restaurante|gastronom|sector|industria)', re.IGNORECASE),
    re.compile(r'novel(?:dades|ty).*(restaurante|gastronom|food|industry)', re.IGNORECASE),

    # Contexto económico
    re.compile(r'(inflaci[oó]n|d[oó]lar|IPC|arancel|tasa de cambio|econom[ií]a)', re.IGNORECASE),
    re.compile(r'qu[eé].*(pasa|pasando).*(econom[ií]a|pa[ií]s|colombia)', re.IGNORECASE),

    # Competencia externa (general, no datos privados)
    re.compile(r'competencia.*(precio|estrategia|tendencia|restaurante)', re.IGNORECASE),
    re.compile(r'qu[eé].*(hace|est[aá] haciendo).*(starbucks|mcdonald|burger king|pedidos ya|rappi)', re.IGNORECASE),

    # Noticias
    re.compile(r'noticias?.*(restaurante|gastronom|sector|industria|food)', re.IGNORECASE),
    re.compile(r'qu[eé].*(dice|dicen|opinan).*(prensa|medios|noticias).*(restaurante|gastronom)', re.IGNORECASE),

    # Proveedores y supply chain
    re.compile(r'(proveedor|mayorista|distribuidor).*(precio|costo|mejor)', re.IGNORECASE),
    re.compile(r'd[oó]nde.*(comprar|conseguir).*(ingrediente|insumo|materia prima)', re.IGNORECASE),

    # Estrategias externas
    re.compile(r'estrategia.*(marketing|ventas|fidelizaci[oó]n).*(restaurante|gastronom)', re.IGNORECASE),
    re.compile(r'qu[eé].*(funciona|est[aá] funcionando).*(restaurante|restaurant|food)', re.IGNORECASE),
]

# Patrones que NUNCA deben activar búsqueda web (ya tenemos los datos internos)
_WEB_SEARCH_EXCLUSIONS = [
    re.compile(r'mis ventas|mi venta|cu[aá]nto vend[ií]', re.IGNORECASE),
    re.compile(r'mi ticket|ticket promedio|cu[aá]nto factur', re.IGNORECASE),
    re.compile(r'mi producto|producto(s)?.*(m[aá]s vendido|m[aá]s popular)', re.IGNORECASE),
    re.compile(r'mi men[uú]|qu[eé] tengo|cat[aá]logo', re.IGNORECASE),
    re.compile(r'mis pedidos?|pedido(s)?.*(hoy|ayer|semana|mes)', re.IGNORECASE),
    re.compile(r'mis clientes?|cu[aá]ntos clientes?', re.IGNORECASE),
    re.compile(r'mi negocio|mi restaurante', re.IGNORECASE),
    re.compile(r'mi caja|efectivo.*cobrado|pagos?.*(hoy|ayer)', re.IGNORECASE),
]


def is_web_search_query(text: str) -> bool:
    """
    Detecta si la consulta requiere información de internet.
    Complementa al classifier.py existente.

    Returns:
        True si la query necesita contexto externo de la web.
    """
    # Si alguna exclusión coincide, no buscar
    for pattern in _WEB_SEARCH_EXCLUSIONS:
        if pattern.search(text):
            return False

    # Si algún patrón de búsqueda coincide, sí buscar
    for pattern in _WEB_SEARCH_PATTERNS:
        if pattern.search(text):
            return True

    return False


def search(query: str, max_results: int = 3) -> list[dict]:
    """
    Busca en internet y retorna resultados limpios para inyectar al prompt.

    Args:
        query: texto de búsqueda
        max_results: número máximo de resultados (default 3)

    Returns:
        list of {'title': str, 'url': str, 'content': str}

    Raises:
        WebSearchError si la API key no está o falla la búsqueda.
    """
    api_key = current_app.config.get('TAVILY_API_KEY', '')
    if not api_key:
        raise WebSearchError('TAVILY_API_KEY no está configurada')

    try:
        from tavily import TavilyClient
    except ImportError:
        raise WebSearchError('tavily-python no está instalado. Ejecuta: pip install tavily-python')

    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query,
            search_depth='basic',
            max_results=max_results,
            include_answer=False,
        )
        results = []
        for r in response.get('results', []):
            results.append({
                'title': r.get('title', ''),
                'url': r.get('url', ''),
                'content': r.get('content', ''),
            })
        return results
    except WebSearchError:
        raise
    except Exception as e:
        raise WebSearchError(f'Error en Tavily API: {e}')


def check_and_reset_monthly_counter(restaurant) -> bool:
    """
    Verifica si el restaurante está dentro del límite mensual de búsquedas.
    Resetea el contador si es un mes nuevo.

    Args:
        restaurant: instancia de Restaurant

    Returns:
        True si puede hacer la búsqueda (dentro del límite).
    """
    from app.models import db

    limit = current_app.config.get('TAVILY_MONTHLY_LIMIT', 1000)
    now = datetime.now(timezone.utc)

    # Si nunca se ha buscado, inicializar
    if restaurant.web_search_month_reset is None:
        restaurant.web_search_month_reset = now
        restaurant.web_search_queries_this_month = 0
        db.session.commit()
        return True

    reset_date = restaurant.web_search_month_reset
    if reset_date.tzinfo is None:
        reset_date = reset_date.replace(tzinfo=timezone.utc)

    # Si es un mes nuevo (o más), resetear contador
    if now.year > reset_date.year or (now.year == reset_date.year and now.month > reset_date.month):
        restaurant.web_search_queries_this_month = 0
        restaurant.web_search_month_reset = now
        db.session.commit()

    # Verificar límite
    if restaurant.web_search_queries_this_month >= limit:
        return False

    return True


def increment_monthly_counter(restaurant) -> None:
    """
    Incrementa el contador mensual de queries de búsqueda web.
    Se llama después de una búsqueda exitosa.
    """
    from app.models import db

    restaurant.web_search_queries_this_month = (
        restaurant.web_search_queries_this_month + 1
    )
    db.session.commit()
