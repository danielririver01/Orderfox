"""
Tests de los endpoints públicos /menu/api/reservations/* (Semana 3).

Cubre: config (enabled/anticipación), check, create (honeypot, rate limit,
validaciones) y arrival QR→reserva (multi-tenant safe).
"""
from datetime import datetime, timedelta

import pytest

from app.models import Reservation, Table
from app.services import reservation_service as rs


def _mañana():
    now = datetime.now(rs.COLOMBIA_TZ).replace(tzinfo=None)
    return (now + timedelta(days=1)).date()


@pytest.fixture
def settings_default(db, sample_restaurant):
    return rs.get_or_create_settings(sample_restaurant.id)


@pytest.fixture
def mesa(db, sample_restaurant):
    t = Table(restaurant_id=sample_restaurant.id, name='Mesa 1', capacity=4, is_active=True)
    db.session.add(t)
    db.session.commit()
    return t


def _payload(sample_restaurant, **overrides):
    base = {
        'restaurant_id': sample_restaurant.id,
        'fecha': _mañana().strftime('%Y-%m-%d'),
        'hora': '20:00',
        'personas': 2,
        'nombre': 'Carlos QR',
        'whatsapp': '3001234567',
    }
    base.update(overrides)
    return base


# ───────────── Config ─────────────

class TestConfig:

    def test_config_enabled(self, app, db, client, sample_restaurant, mesa, settings_default):
        resp = client.get(f'/menu/api/reservations/config?restaurant_id={sample_restaurant.id}')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['enabled'] is True
        assert data['min_notice_hours'] == 2
        assert data['max_party_size'] >= 1

    def test_config_por_slug(self, app, db, client, sample_restaurant, mesa, settings_default):
        resp = client.get(f'/menu/api/reservations/config?slug={sample_restaurant.slug}')
        assert resp.status_code == 200
        assert resp.get_json()['data']['enabled'] is True

    def test_config_disabled_sin_mesas(self, app, db, client, sample_restaurant, settings_default):
        """Sin mesas activas → enabled=False (el form no debe aparecer)."""
        resp = client.get(f'/menu/api/reservations/config?restaurant_id={sample_restaurant.id}')
        assert resp.get_json()['data']['enabled'] is False

    def test_config_disabled_por_settings(self, app, db, client, sample_restaurant, mesa, settings_default):
        rs.update_settings(sample_restaurant.id, {'reservations_enabled': False})
        resp = client.get(f'/menu/api/reservations/config?restaurant_id={sample_restaurant.id}')
        assert resp.get_json()['data']['enabled'] is False

    def test_config_restaurante_inexistente_404(self, db, client):
        resp = client.get('/menu/api/reservations/config?restaurant_id=999999')
        assert resp.status_code == 404


# ───────────── Check ─────────────

class TestCheck:

    def test_check_disponible(self, app, db, client, sample_restaurant, mesa, settings_default):
        resp = client.post('/menu/api/reservations/check', json=_payload(sample_restaurant))
        assert resp.status_code == 200
        assert resp.get_json()['data']['available'] is True

    def test_check_sin_disponibilidad(self, app, db, client, sample_restaurant, mesa, settings_default):
        db.session.add(Reservation(
            restaurant_id=sample_restaurant.id, table_id=mesa.id,
            customer_name='X', customer_whatsapp='3000000000',
            reservation_date=_mañana(), reservation_time=rs.parse_time('20:00'),
            party_size=2, status='confirmed'))
        db.session.commit()
        resp = client.post('/menu/api/reservations/check', json=_payload(sample_restaurant))
        assert resp.get_json()['data']['available'] is False

    def test_check_validacion_400(self, app, db, client, sample_restaurant, mesa, settings_default):
        resp = client.post('/menu/api/reservations/check',
                           json=_payload(sample_restaurant, personas=0))
        assert resp.status_code == 400


# ───────────── Create ─────────────

class TestCreate:

    def test_crea_201(self, app, db, client, sample_restaurant, mesa, settings_default, monkeypatch):
        import app.services.notification_service as ns
        monkeypatch.setattr(ns, 'notify_new_reservation', lambda r: None)

        resp = client.post('/menu/api/reservations', json=_payload(sample_restaurant))
        assert resp.status_code == 201
        body = resp.get_json()
        assert body['success'] is True
        assert Reservation.query.count() == 1

    def test_honeypot_403(self, app, db, client, sample_restaurant, mesa, settings_default):
        resp = client.post('/menu/api/reservations',
                           json=_payload(sample_restaurant, user_secondary_email='bot@spam.com'))
        assert resp.status_code == 403
        assert Reservation.query.count() == 0

    def test_sin_disponibilidad_409(self, app, db, client, sample_restaurant, mesa, settings_default):
        db.session.add(Reservation(
            restaurant_id=sample_restaurant.id, table_id=mesa.id,
            customer_name='X', customer_whatsapp='3000000000',
            reservation_date=_mañana(), reservation_time=rs.parse_time('20:00'),
            party_size=2, status='pending'))
        db.session.commit()
        resp = client.post('/menu/api/reservations', json=_payload(sample_restaurant, hora='20:30'))
        assert resp.status_code == 409
        assert resp.get_json()['error_code'] == 'NO_AVAILABILITY'

    def test_rate_limit_429(self, app, db, client, sample_restaurant, mesa, settings_default):
        """4ª solicitud en un minuto → 429 (mismo anti-spam que pedidos)."""
        import app.services.notification_service as ns
        monkey = pytest.MonkeyPatch()
        monkey.setattr(ns, 'notify_new_reservation', lambda r: None)
        try:
            for hora in ('12:00', '15:00', '18:00'):
                resp = client.post('/menu/api/reservations',
                                   json=_payload(sample_restaurant, hora=hora),
                                   environ_base={'REMOTE_ADDR': '5.6.7.8'})
                assert resp.status_code == 201, resp.get_json()
            resp = client.post('/menu/api/reservations',
                               json=_payload(sample_restaurant, hora='21:00'),
                               environ_base={'REMOTE_ADDR': '5.6.7.8'})
            assert resp.status_code == 429
        finally:
            monkey.undo()


# ───────────── Arrival (QR → reserva) ─────────────

class TestArrival:

    def _reserva_confirmada_hoy(self, db, sample_restaurant, mesa):
        hoy = datetime.now(rs.COLOMBIA_TZ).date()
        r = Reservation(
            restaurant_id=sample_restaurant.id, table_id=mesa.id,
            customer_name='Carlos Pérez', customer_whatsapp='3001111111',
            reservation_date=hoy, reservation_time=rs.parse_time('19:00'),
            party_size=4, status='confirmed')
        db.session.add(r)
        db.session.commit()
        return r

    def test_llegada_con_reserva(self, app, db, client, sample_restaurant, mesa, settings_default):
        r = self._reserva_confirmada_hoy(db, sample_restaurant, mesa)
        resp = client.post('/menu/api/reservations/arrival', json={
            'restaurant_id': sample_restaurant.id, 'table_id': mesa.id})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['has_reservation'] is True
        assert data['reservation']['customer_name'] == 'Carlos Pérez'
        db.session.expire(r)
        assert r.status == 'completed'  # marcada al llegar

    def test_llegada_sin_reserva(self, app, db, client, sample_restaurant, mesa, settings_default):
        resp = client.post('/menu/api/reservations/arrival', json={
            'restaurant_id': sample_restaurant.id, 'table_id': mesa.id})
        assert resp.status_code == 200
        assert resp.get_json()['data']['has_reservation'] is False

    def test_mesa_de_otro_restaurante_404(self, app, db, client, sample_restaurant, mesa, settings_default):
        from app.models import Restaurant
        otro = Restaurant(
            name='Vecino', slug='vecino-arrival', whatsapp_phone='+573007777777',
            plan_type='emprendedor', is_active=True, is_open=True,
            subscription_expires_at=datetime.now(rs.COLOMBIA_TZ) + timedelta(days=30),
            has_used_trial=False,
        )
        db.session.add(otro)
        db.session.commit()
        # Mesa pertenece a sample_restaurant, la consulta viene de "otro"
        resp = client.post('/menu/api/reservations/arrival', json={
            'restaurant_id': otro.id, 'table_id': mesa.id})
        assert resp.status_code == 404

    def test_sin_table_id_400(self, app, db, client, sample_restaurant, settings_default):
        resp = client.post('/menu/api/reservations/arrival',
                           json={'restaurant_id': sample_restaurant.id})
        assert resp.status_code == 400
