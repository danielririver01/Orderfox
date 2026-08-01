"""Helpers de zona horaria.

Todas las fechas se almacenan en UTC (ver AGENTS.md). Para mostrar una fecha
al usuario del dashboard hay que convertirla a la hora local de Colombia
(UTC-5, sin horario de verano).
"""
from datetime import datetime, timedelta, timezone

# Colombia no usa horario de verano: UTC-5 fijo todo el año.
COLOMBIA_TZ = timezone(timedelta(hours=-5))


def to_colombia(value):
    """Convierte un datetime (UTC-aware o naive) a hora de Colombia (UTC-5).

    - Si ``value`` es ``None`` devuelve ``None``.
    - Si ``value`` no tiene tzinfo se asume que está en UTC (el valor crudo
      que devuelve la DB sin ``AwareDateTime``, p.ej. en SQLite/tests).
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(COLOMBIA_TZ)


def today_start_utc():
    """Inicio del día actual en Colombia (medianoche Bogotá) expresado en UTC.

    Las columnas de fecha guardan UTC (naive). Para filtrar "pedidos de hoy"
    hay que comparar contra la medianoche de Bogotá convertida a UTC:

        hoy 12:00 AM Bogotá == ayer 7:00 PM UTC (05:00 UTC del día actual).

    Devuelve un datetime naive en UTC, listo para usar en queries de SQLAlchemy.
    """
    now_col = datetime.now(COLOMBIA_TZ)
    start_col = now_col.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_col.astimezone(timezone.utc).replace(tzinfo=None)
