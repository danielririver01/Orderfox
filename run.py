import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    # Entrará en modo debug solo si FLASK_DEBUG=True en el entorno
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode)
