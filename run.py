import os
import werkzeug.serving
werkzeug.serving.WSGIRequestHandler.server_version = ''
werkzeug.serving.WSGIRequestHandler.sys_version = ''

from app import create_app

app = create_app()

with app.app_context():
    try:
        from app.models import db
        db.create_all()
    except Exception as e:
        import sys
        print(f"ERROR: db.create_all() failed: {e}", file=sys.stderr)
        sys.stderr.flush()

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)
