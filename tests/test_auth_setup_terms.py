"""Test del checkbox de aceptación de Términos en el registro (setup-account).

Cubre el requisito legal Ley 1581: la autorización previa, expresa e
informada del titular debe existir ANTES de crear la cuenta/restaurante.
"""


def _setup_session(client, user_id):
    with client.session_transaction() as s:
        s['user_id'] = user_id
        s['selected_plan'] = 'trial'


def _csrf_headers(client):
    """La ruta web exige CSRF (protect() manual). Registramos el token crudo
    en la sesión del test client y firmamos el mismo valor que envía el
    frontend (header X-CSRFToken), replicando Flask-WTF."""
    from flask import current_app
    from itsdangerous import URLSafeTimedSerializer

    raw = 'test-csrf-raw-token'
    with client.session_transaction() as s:
        s['csrf_token'] = raw
    ser = URLSafeTimedSerializer(current_app.secret_key, salt='wtf-csrf-token')
    return {'X-CSRFToken': ser.dumps(raw)}


def _valid_payload(extra=None):
    data = {
        'admin_name': 'Admin Test',
        'restaurant_name': 'Restaurante Test',
        'phone': '573001112233',
        'password': 'Test1234pass',
        'confirm_password': 'Test1234pass',
    }
    if extra:
        data.update(extra)
    return data


def test_setup_requires_accept_terms(app, db):
    """Sin marcar el checkbox el registro se rechaza con aviso."""
    from app.models import Restaurant, User

    u = User(email='test@velzia.co', username='testuser')
    u.set_password('Test1234pass')
    db.session.add(u)
    db.session.commit()

    client = app.test_client()
    _setup_session(client, u.id)
    headers = _csrf_headers(client)

    r = client.post('/setup-account', data=_valid_payload(),
                    headers=headers, follow_redirects=False)
    body = r.get_data(as_text=True)

    assert r.status_code == 200
    assert 'aceptar los Términos y Condiciones y la Política de Datos' in body
    # La cuenta NO debe haberse creado el restaurante aún.
    assert Restaurant.query.count() == 0


def test_setup_succeeds_with_accept_terms(app, db):
    """Con el checkbox marcado el flujo de trial continúa (crea restaurante)."""
    from app.models import Restaurant, User

    u = User(email='test2@velzia.co', username='testuser2')
    u.set_password('Test1234pass')
    db.session.add(u)
    db.session.commit()

    client = app.test_client()
    _setup_session(client, u.id)
    headers = _csrf_headers(client)

    r = client.post(
        '/setup-account',
        data=_valid_payload({'accept_terms': 'y'}),
        headers=headers,
        follow_redirects=False,
    )

    assert r.status_code == 302
    assert Restaurant.query.count() == 1
