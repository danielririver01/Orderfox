"""
Báscula digital del POS Verduras (Semana 4).

Diseño deliberado:
- La báscula es una AYUDA, nunca un requisito: el campo de cantidad manual
  del POS sigue siendo la fuente de verdad. Si la báscula falla (sin luz,
  puerto ocupado, cable suelto), el tendero teclea el peso y vende igual.
- El transporte (serial/USB) se INYECTA: el servicio se prueba completo con
  un transporte falso; pyserial solo se importa si la báscula está activada
  (dependencia opcional, `pip install pyserial`).
- Los parseadores son funciones puras (bytes → kg): fáciles de probar y de
  extender con nuevos protocolos sin tocar el transporte ni la ruta.

Unidades: TODO se normaliza a KILOGRAMOS (Decimal del servicio de ventas usa
kg con precisión de gramo para productos 'kg').
"""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Protocol

# Rango físico razonable para básculas de mesa/plataforma de verdulería.
MAX_WEIGHT_KG = 300.0


class ScaleError(Exception):
    """Base de errores de báscula."""


class ScaleDisabledError(ScaleError):
    """La báscula no está activada (SCALE_ENABLED=0)."""


class ScaleUnavailableError(ScaleError):
    """No se pudo hablar con la báscula (pyserial ausente, puerto ocupado,
    sin respuesta)."""


class ScaleReadError(ScaleError):
    """La báscula respondió pero el peso no es utilizable (cero, fuera de
    rango, frame ilegible)."""


# ── Parseadores (bytes → kg, o None si no se reconoce) ──────

_NUM_RE = re.compile(rb'\d+(?:[.,]\d+)?')


def parse_generic_ascii(raw: bytes) -> float | None:
    """ASCII con un número en el stream: 'S 1.234 kg', 'US 0,500 kg'.

    La coma se trata como separador decimal (locale es-CO de muchas
    básculas). Devuelve kg o None si no hay número legible.
    """
    if not raw:
        return None
    match = _NUM_RE.search(raw)
    if not match:
        return None
    try:
        return float(match.group().replace(b',', b'.'))
    except ValueError:  # pragma: no cover — la regex garantiza parseo
        return None


_DEC_RE = re.compile(rb'\d+[.,]\d+')
_TOLEDO_DIGITS_RE = re.compile(rb'\d{4,7}')


def parse_toledo(raw: bytes) -> float | None:
    """Frames tipo Toledo/Magenta (comunes en Colombia).

    Dos formatos aceptados:
    - 6 dígitos en GRAMOS: b'000123' → 0.123 kg.
    - Número con punto decimal en kg: b'| 12.345 kg' → 12.345.
    """
    if not raw:
        return None
    if b'.' in raw or b',' in raw:
        match = _DEC_RE.search(raw)
        if not match:
            return None
        try:
            return float(match.group().replace(b',', b'.'))
        except ValueError:  # pragma: no cover
            return None
    digits = _TOLEDO_DIGITS_RE.search(raw)
    if not digits:
        return None
    return int(digits.group()) / 1000.0


# Registro de protocolos soportados (config SCALE_PROTOCOL).
PARSERS: dict[str, Callable[[bytes], float | None]] = {
    'generic': parse_generic_ascii,
    'toledo': parse_toledo,
}


# ── Transporte ──────────────────────────────────────────────


class ScaleTransport(Protocol):
    """Contrato mínimo de transporte. read_line devuelve lo leído hasta
    \\n o hasta vencer el timeout (b'' si no llegó nada)."""

    def read_line(self, timeout_s: float) -> bytes: ...

    def close(self) -> None: ...


def _serial_transport(port: str, baudrate: int, timeout_s: float):
    """Transporte real (pyserial). Import perezoso: pyserial es dependencia
    opcional y solo se exige si la báscula está activada."""
    try:
        import serial  # pyserial — verificado en PyPI (v3.5)
    except ImportError as e:
        raise ScaleUnavailableError(
            'pyserial no está instalado. Instálalo con: pip install pyserial'
        ) from e
    try:
        ser = serial.Serial(port=port, baudrate=baudrate, timeout=timeout_s)
    except Exception as e:  # SerialException/OSError: puerto ocupado, ausente…
        raise ScaleUnavailableError(
            f'No se pudo abrir el puerto {port}: {e}') from e

    class _SerialTransport:
        def read_line(self, timeout_s: float) -> bytes:
            return ser.readline()  # respeta el timeout del puerto

        def close(self) -> None:
            ser.close()

    return _SerialTransport()


# Punto de inyección para tests (se reemplaza por un transporte falso).
_transport_factory: Callable[..., Any] = _serial_transport


# ── Lectura ─────────────────────────────────────────────────


def read_weight(
    transport: ScaleTransport | None = None,
    *,
    enabled: bool,
    protocol: str = 'generic',
    port: str = 'COM3',
    baudrate: int = 9600,
    timeout_s: float = 2.0,
) -> float:
    """Lee un peso en kg o lanza Scale*Error ante cualquier problema.

    El servicio NUNCA devuelve un peso dudoso: cero, fuera de rango o frame
    ilegible son errores (el frontend pide ingreso manual, jamás inventa).
    """
    if not enabled:
        raise ScaleDisabledError('La báscula no está activada')
    parser = PARSERS.get(protocol)
    if parser is None:
        raise ScaleError(f'Protocolo de báscula desconocido: {protocol}')

    own = transport is None
    if own:
        try:
            transport = _transport_factory(
                port=port, baudrate=baudrate, timeout_s=timeout_s)
        except ScaleUnavailableError:
            raise
        except Exception as e:
            raise ScaleUnavailableError(
                f'Puerto de báscula no disponible: {e}') from e
    try:
        raw = transport.read_line(timeout_s)
    except OSError as e:  # SerialException hereda de OSError
        raise ScaleUnavailableError(f'Error leyendo la báscula: {e}') from e
    finally:
        if own:
            transport.close()

    weight = parser(raw)
    if weight is None:
        raise ScaleReadError(
            'Lectura no reconocida — ingresa el peso manualmente')
    if weight <= 0:
        raise ScaleReadError(
            'La báscula está en cero — coloca el producto sobre la plataforma')
    if weight > MAX_WEIGHT_KG:
        raise ScaleReadError(f'Peso fuera de rango ({weight:g} kg)')
    return round(weight, 3)  # precisión de gramo (contrato con ventas)
