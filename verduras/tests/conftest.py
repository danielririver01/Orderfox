"""
Fixtures de tests del módulo Verduras.

Espeja la disciplina de tests/conftest.py de core: sqlite in-memory,
app session-scoped, DB function-scoped con create_all/drop_all.

Se corre con: pytest verduras/tests  (desde la raíz del monorepo).
No se coleciona en la suite de core (pytest.ini limita testpaths a tests/).
"""
import os
import sys
from pathlib import Path

import pytest

# Env ANTES de importar la factory (igual que core) + raíz en sys.path para
# resolver `app.models` y el paquete `verduras` sin importar el cwd.
_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test-secret-key-for-testing-only'
os.environ['SERVICE_API_KEY'] = 'test-service-api-key'

from app.models import db as _db
from verduras.app_factory import create_app


@pytest.fixture(scope='session')
def app():
    app = create_app()
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
    })
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.close()
        _db.drop_all()


@pytest.fixture(scope='function')
def db(app):
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        _db.session.close()
        _db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    return app.test_client()
