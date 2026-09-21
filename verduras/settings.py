"""
Settings del módulo Verduras (app Flask separada dentro del monorepo).

Carga el MISMO .env de la raíz del repo: la conexión a la DB es compartida
con velzia core (DATABASE_URL) — es el canal de integración del puente
Business ↔ Restaurant. El SECRET_KEY es el mismo porque en desarrollo las
sesiones pueden viajar entre apps; en producción cada app debe tener el suyo.

Puerto de desarrollo: 5100 (core corre en 5000, Astro en 4321).
"""
import os

from dotenv import load_dotenv

# El .env vive en la raíz del monorepo (un nivel arriba de verduras/).
_ROOT_ENV = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(_ROOT_ENV)


class Config:
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError(
            "SECRET_KEY no está configurada. "
            "Establece SECRET_KEY en el archivo .env de la raíz del monorepo."
        )

    # DB compartida con velzia core (contrato del puente Business ↔ Restaurant).
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'postgresql+psycopg2://localhost/orderfox'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Módulo
    MODULE_NAME = 'verduras'
    MODULE_VERSION = '0.3.0'
    # Origen de la API de core (para llamadas HTTP cuando la DB compartida
    # no aplique, p.ej. core desplegado por separado). Por defecto, local.
    CORE_API_BASE_URL = os.environ.get('CORE_API_BASE_URL') or 'http://localhost:5000'

    # API key server-to-server (header x-api-key), mismo patrón que core.
    # Protege las mutaciones del catálogo (POST /api/verduras/*).
    SERVICE_API_KEY = os.environ.get('SERVICE_API_KEY')

    # Ambiente (permite distinguir en logs/metrics)
    ENV = os.environ.get('FLASK_ENV', 'development')
