"""Tier DESECHABLE (extraído de test_cash_register.py).

Flags periféricos del cajón físico (drawer_enabled/drawer_auto_open):
integración de hardware, no dinero/acceso. No corre en CI (verify_*.py).
Correr explícito:
    pytest tests/verify_cash_drawer.py
Si pasan 30 días sin correrlo, borrar sin discusión.
"""
import re as _re


def _login(client, user):
    with client.session_transaction() as sess:
        sess['user_id'] = user.id


def _csrf_headers(client):
    page = client.get('/orders/')
    m = _re.search(
        r'name="csrf-token" content="([^"]+)"', page.get_data(as_text=True))
    token = m.group(1) if m else ''
    return {'X-CSRFToken': token}


class TestCashDrawerFlags:
    def test_drawer_flags_default_off_and_persist(
            self, client, db, sample_restaurant, sample_user):
        _login(client, sample_user)
        headers = _csrf_headers(client)

        current = client.get('/cash-register/api/settings')
        data = current.get_json()['data']
        assert data['drawer_enabled'] is False
        assert data['drawer_auto_open'] is False

        # Subconjunto: solo cajón, el modo estricto no se toca.
        updated = client.put('/cash-register/api/settings', json={
            'drawer_enabled': True, 'drawer_auto_open': True,
        }, headers=headers)
        assert updated.status_code == 200
        payload = updated.get_json()['data']
        assert payload['drawer_enabled'] is True
        assert payload['drawer_auto_open'] is True
        assert payload['require_cash_shift'] is False

        drawer = client.get('/cash-register/api/drawer')
        assert drawer.status_code == 200
        assert drawer.get_json()['data'] == {
            'drawer_enabled': True, 'drawer_auto_open': True,
        }
