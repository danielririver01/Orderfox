"""VLZ-11 · Cookies de sesión configurables por entorno.

SESSION_COOKIE_SECURE debe ser True en producción y False en local, con
anulación explícita por variable de entorno. settings.Config evalúa su
class-body al importarse, así que cada caso re-importa el módulo con el
entorno parcheado y lo restaura al salir.
"""
import importlib
import os

import pytest

import settings

_CLAVES = ('SESSION_COOKIE_SECURE', 'SESSION_COOKIE_SAMESITE', 'FLASK_DEBUG')


@pytest.fixture
def config_bajo_entorno():
    """Re-importa settings.Config bajo un entorno dado y lo restaura."""
    snapshot = {clave: os.environ.get(clave) for clave in _CLAVES}

    def _cargar(**env):
        for clave in _CLAVES:
            if clave in env:
                os.environ[clave] = str(env[clave])
            else:
                os.environ.pop(clave, None)
        importlib.reload(settings)
        return settings.Config

    yield _cargar

    for clave, valor in snapshot.items():
        if valor is None:
            os.environ.pop(clave, None)
        else:
            os.environ[clave] = valor
    importlib.reload(settings)


def test_produccion_secure_por_defecto(config_bajo_entorno):
    cfg = config_bajo_entorno(FLASK_DEBUG='False', SESSION_COOKIE_SECURE='',
                              SESSION_COOKIE_SAMESITE='')
    assert cfg.SESSION_COOKIE_SECURE is True


def test_local_debug_sin_secure(config_bajo_entorno):
    cfg = config_bajo_entorno(FLASK_DEBUG='True', SESSION_COOKIE_SECURE='')
    assert cfg.SESSION_COOKIE_SECURE is False


def test_override_apaga_secure_en_produccion(config_bajo_entorno):
    cfg = config_bajo_entorno(FLASK_DEBUG='False', SESSION_COOKIE_SECURE='false')
    assert cfg.SESSION_COOKIE_SECURE is False


def test_override_activa_secure_en_local(config_bajo_entorno):
    cfg = config_bajo_entorno(FLASK_DEBUG='True', SESSION_COOKIE_SECURE='true')
    assert cfg.SESSION_COOKIE_SECURE is True


def test_samesite_por_defecto_es_lax(config_bajo_entorno):
    cfg = config_bajo_entorno(FLASK_DEBUG='False', SESSION_COOKIE_SAMESITE='')
    assert cfg.SESSION_COOKIE_SAMESITE == 'Lax'


def test_samesite_estricto_por_entorno(config_bajo_entorno):
    cfg = config_bajo_entorno(FLASK_DEBUG='False', SESSION_COOKIE_SAMESITE='strict')
    assert cfg.SESSION_COOKIE_SAMESITE == 'Strict'


def test_samesite_invalido_cae_a_lax(config_bajo_entorno):
    cfg = config_bajo_entorno(FLASK_DEBUG='False', SESSION_COOKIE_SAMESITE='banana')
    assert cfg.SESSION_COOKIE_SAMESITE == 'Lax'


def test_httponly_siempre_activa(config_bajo_entorno):
    cfg = config_bajo_entorno(FLASK_DEBUG='False')
    assert cfg.SESSION_COOKIE_HTTPONLY is True
