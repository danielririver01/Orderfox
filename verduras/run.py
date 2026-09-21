"""
Entrypoint de la app Verduras.

Ejecutar desde la raíz del monorepo (para que `app.models` de core resuelva):

    .venv/Scripts/python verduras/run.py

o desde verduras/ con el venv activado:

    python run.py
"""
import os
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from verduras.app_factory import create_app

app = create_app()

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=5100, debug=debug_mode)
