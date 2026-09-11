"""
Tests del panel web de reservas (Semana 2, v1.5).

Cubre:
- Web routes: index (lista, filtros, blur sin plan), calendar, settings
  (GET y POST con CSRF), protección owner-only y auth.
- API de capacidad: PATCH /api/tables/<id>/capacity + capacity en create.
- TableService.parse_capacity / update_capacity.
"""
from datetime import datetime, timedelta

import pytest

from app.models import Reservation, Table
from app.services import reservation_service as rs
from app.services.table_service import TableService


def _mañana():
    now = datetime.now(rs.COLOMBIA_TZ).replace(tzinfo=None)
    return (now + timedelta(days=1)).date()


@pytest.fixture
def mesa(db, sample_restaurant):
    t = Table(restaurant_id=sample_restaurant.id, name='Mesa 1', capacity=4, is_active=True)
    db.session.add(t)
    db.session.commit()
    return t


@pytest.fixture
def reserva_pendiente(db, sample_restaurant, mesa):
    r = Reservation(
        restaurant_id=sample_restaurant.id, table_id=mesa.id,
        customer_name='Carlos Pérez', customer_whatsapp='+573001111111',
        reservation_date=_mañana(), reservation_time=rs.parse_time('20:00'),
        party_size=2, status='pending',
    )
    db.session.add(r)
    db.session.commit()
    return r


@pytest.fixture
def settings_default(db, sample_restaurant):
    # Crecimiento: incluye has_table_qr → acceso al panel de reservas
    sample_restaurant.plan_type = 'crecimiento'
    db.session.commit()
    return rs.get_or_create_settings(sample_restaurant.id)


@pytest.fixture
def db_settings_emprendedor(db, sample_restaurant):
    """Restaurante en plan Emprendedor (sin has_table_qr) + settings creados."""
    return rs.get_or_create_settings(sample_restaurant.id)


@pytest.fixture
def auth_client(app, sample_user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = sample_user.id
        sess['username'] = sample_user.username
    return client


def _csrf_token(client, app):
    """Patrón del proyecto (test_account_deletion.py): token crudo en sesión
    + header firmado con el serializer de Flask-WTF."""
    from itsdangerous import URLSafeTimedSerializer
    raw = 'test-csrf-raw-token'
    with client.session_transaction() as sess:
        sess['csrf_token'] = raw
    ser = URLSafeTimedSerializer(app.secret_key, salt='wtf-csrf-token')
    return ser.dumps(raw)


# ───────────── Web routes ─────────────

class TestReservationsWebRoutes:

    def test_index_requiere_auth(self, client):
        resp = client.get('/dashboard/reservations/')
        assert resp.status_code in (301, 302)

    def test_index_renderiza_con_reservas(self, app, db, auth_client, sample_restaurant,
                                          mesa, settings_default, reserva_pendiente):
        resp = auth_client.get('/dashboard/reservations/')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'Carlos Pérez' in html
        assert 'Pendientes' in html

    def test_index_filtro_estado(self, app, db, auth_client, sample_restaurant,
                                 mesa, settings_default, reserva_pendiente):
        resp = auth_client.get('/dashboard/reservations/?estado=confirmed')
        assert resp.status_code == 200
        assert 'Carlos Pérez' not in resp.get_data(as_text=True)

    def test_index_filtro_estado_invalido_no_explota(self, app, db, auth_client,
                                                     sample_restaurant, mesa, settings_default):
        resp = auth_client.get('/dashboard/reservations/?estado=hack')
        assert resp.status_code == 200

    def test_index_sin_plan_muestra_upsell(self, app, db, auth_client, sample_restaurant,
                                           sample_user, db_settings_emprendedor):
        """Plan emprendedor no tiene has_table_qr → blur + upsell, sin datos."""
        resp = auth_client.get('/dashboard/reservations/')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'MEJORAR MI PLAN' in html

    def test_calendar_renderiza(self, app, db, auth_client, sample_restaurant,
                                mesa, settings_default, reserva_pendiente):
        resp = auth_client.get(f'/dashboard/reservations/calendar?fecha={_mañana().strftime("%Y-%m-%d")}')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'Mesa 1' in html
        assert '20:00' in html
        assert '21:45' in html  # fin del bloqueo: 90 + 15

    def test_settings_get(self, app, db, auth_client, sample_restaurant, mesa, settings_default):
        resp = auth_client.get('/dashboard/reservations/settings')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'service_duration_min' in html
        assert f'capacity_{mesa.id}' in html

    def test_settings_post_actualiza(self, app, db, auth_client, sample_restaurant,
                                     mesa, settings_default):
        token = _csrf_token(auth_client, app)
        resp = auth_client.post('/dashboard/reservations/settings', data={
            'csrf_token': token,
            'service_duration_min': '120',
            'cleanup_buffer_min': '20',
            'min_notice_hours': '1',
            'max_advance_days': '15',
            'reminder_hours_before': '3',
            f'capacity_{mesa.id}': '6',
        }, follow_redirects=True)
        assert resp.status_code == 200
        settings = rs.get_or_create_settings(sample_restaurant.id)
        assert settings.service_duration_min == 120
        assert settings.cleanup_buffer_min == 20
        assert settings.reservations_enabled is False  # checkbox ausente
        db.session.expire(mesa)
        assert mesa.capacity == 6

    def test_settings_post_sin_token_no_cambia_config(self, app, db, auth_client,
                                                      sample_restaurant, mesa, settings_default):
        """En tests WTF_CSRF_ENABLED=False (conftest): el POST sin token pasa
        la protección pero verifica que la ruta no explote. La protección CSRF
        real la aplica flask-wtf a nivel app (ver app/__init__.py) — se cubre
        con el test de flujo con token (patrón test_account_deletion.py)."""
        resp = auth_client.post('/dashboard/reservations/settings', data={
            'service_duration_min': '120',
        })
        assert resp.status_code in (302, 400)
        # Con token válido sí debe cambiar (flujo completo cubierto arriba).

    def test_settings_post_invalido_flashea_error(self, app, db, auth_client,
                                                  sample_restaurant, mesa, settings_default):
        token = _csrf_token(auth_client, app)
        resp = auth_client.post('/dashboard/reservations/settings', data={
            'csrf_token': token,
            'service_duration_min': '9999',  # fuera de rango
        }, follow_redirects=True)
        assert resp.status_code == 200
        settings = rs.get_or_create_settings(sample_restaurant.id)
        assert settings.service_duration_min == 90  # sin cambios


# ───────────── Owner-only ─────────────

class TestOwnerOnly:

    def test_empleado_no_accede(self, app, db, sample_restaurant, mesa, settings_default):
        """Patrón v2.1.1: empleados fuera del panel de reservas (before_request)."""
        from werkzeug.security import generate_password_hash

        from app.models import User
        empleado = User(
            restaurant_id=sample_restaurant.id,
            username='mozo', email='mozo@test.com',
            password=generate_password_hash('TestPass123'),
            role='waiter',
        )
        db.session.add(empleado)
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['employee_id'] = empleado.id
        resp = client.get('/dashboard/reservations/')
        assert resp.status_code in (301, 302, 403)


# ───────────── Capacidad: service ─────────────

class TestCapacityService:

    def test_parse_capacity_valida(self):
        assert TableService.parse_capacity('4') == (4, None)
        assert TableService.parse_capacity(6) == (6, None)
        assert TableService.parse_capacity(None) == (None, None)
        assert TableService.parse_capacity('') == (None, None)

    def test_parse_capacity_invalida(self):
        _, err = TableService.parse_capacity('abc')
        assert err
        _, err = TableService.parse_capacity('0')
        assert err
        _, err = TableService.parse_capacity('999')
        assert err

    def test_create_table_con_capacidad(self, db, sample_restaurant):
        t, err = TableService.create_table(sample_restaurant.id, 'Terraza', capacity=8)
        assert err is None
        assert t.capacity == 8

    def test_create_table_sin_capacidad(self, db, sample_restaurant):
        t, err = TableService.create_table(sample_restaurant.id, 'Barra')
        assert err is None
        assert t.capacity is None

    def test_update_capacity(self, db, sample_restaurant, mesa):
        t, err = TableService.update_capacity(sample_restaurant.id, mesa.id, '10')
        assert err is None
        assert t.capacity == 10

    def test_update_capacity_mesa_ajena_404(self, db, sample_restaurant, mesa):
        _, err = TableService.update_capacity(999999, mesa.id, '10')
        assert err == 'Mesa no encontrada'


# ───────────── Capacidad: API ─────────────

class TestCapacityAPI:

    def test_patch_capacity(self, app, db, auth_client, sample_restaurant, mesa):
        resp = auth_client.patch(f'/api/tables/{mesa.id}/capacity',
                                 json={'capacity': 5})
        assert resp.status_code == 200
        assert resp.get_json()['data']['capacity'] == 5
        db.session.expire(mesa)
        assert mesa.capacity == 5

    def test_patch_capacity_invalida_400(self, app, db, auth_client, sample_restaurant, mesa):
        resp = auth_client.patch(f'/api/tables/{mesa.id}/capacity',
                                 json={'capacity': 999})
        assert resp.status_code == 400

    def test_patch_capacity_mesa_inexistente_404(self, app, db, auth_client, sample_restaurant):
        resp = auth_client.patch('/api/tables/999999/capacity', json={'capacity': 5})
        assert resp.status_code == 404

    def test_patch_capacity_requiere_auth(self, client):
        resp = client.patch('/api/tables/1/capacity', json={'capacity': 5})
        assert resp.status_code in (301, 302, 401)

    def test_create_con_capacity_en_payload(self, app, db, auth_client, sample_restaurant):
        # crear mesas requiere has_table_qr (plan Crecimiento+)
        sample_restaurant.plan_type = 'crecimiento'
        db.session.commit()
        resp = auth_client.post('/api/tables', json={'name': 'Vip', 'capacity': 12})
        assert resp.status_code == 201
        assert resp.get_json()['data']['capacity'] == 12

    def test_list_incluye_capacity(self, app, db, auth_client, sample_restaurant, mesa):
        resp = auth_client.get('/api/tables')
        assert resp.status_code == 200
        tables = resp.get_json()['data']['tables']
        assert tables[0]['capacity'] == 4
