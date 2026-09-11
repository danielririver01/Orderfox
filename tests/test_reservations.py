"""
Tests del dominio de reservas (v1.5, feature/reservas).

Cubre:
- Matemática de disponibilidad: sin doble booking en ningún escenario
  (overlap parcial, mismo horario, mesas paralelas, buffer de limpieza).
- Creación (público): validaciones, config del restaurante, auto-rechazo
  cuando no hay mesas (409), rate limiting por IP.
- Transiciones de estado: confirm / reject (con motivo) / complete / no_show,
  incluyendo seguridad multi-restaurante (no ver la reserva del vecino).
- QR → reserva: link_qr_to_reservation marca 'completed'.
- Recordatorios: ventana, idempotencia (flag reminder_sent).

Convención de fechas en los tests: usar SIEMPRE fechas relativas a mañana
(hora Colombia) para que la suite no caduque con el paso del tiempo.
"""
from datetime import datetime, timedelta

import pytest

from app import create_app  # noqa: F401  (app fixture vive en conftest)
from app.models import Reservation, Table, db
from app.services import reservation_service as rs
from app.services.reservation_service import ReservationServiceError

# ───────────── Helpers / fixtures ─────────────

def _mañana():
    """Mañana en hora Colombia (naive) — las reservas viven en hora local."""
    now = datetime.now(rs.COLOMBIA_TZ).replace(tzinfo=None)
    return (now + timedelta(days=1)).date()


@pytest.fixture
def settings_default(db, sample_restaurant):
    return rs.get_or_create_settings(sample_restaurant.id)


@pytest.fixture
def mesa4(db, sample_restaurant):
    t = Table(restaurant_id=sample_restaurant.id, name='Mesa 1', capacity=4, is_active=True)
    db.session.add(t)
    db.session.commit()
    return t


@pytest.fixture
def mesa8(db, sample_restaurant):
    t = Table(restaurant_id=sample_restaurant.id, name='Terraza', capacity=8, is_active=True)
    db.session.add(t)
    db.session.commit()
    return t


def _crear_reserva(restaurant_id, table_id, fecha, hora, status='pending'):
    r = Reservation(
        restaurant_id=restaurant_id,
        table_id=table_id,
        customer_name='Cliente Existente',
        customer_whatsapp='+573001111111',
        reservation_date=fecha,
        reservation_time=hora,
        party_size=2,
        status=status,
    )
    db.session.add(r)
    db.session.commit()
    return r


# ───────────── Matemática de disponibilidad ─────────────

class TestAvailability:

    def test_mesa_libre_cuando_no_hay_reservas(self, db, sample_restaurant, mesa4, settings_default):
        table, _ = rs.check_availability(sample_restaurant.id, _mañana(), rs.parse_time('20:00'), 2)
        assert table is not None and table.id == mesa4.id

    def test_overlap_total_bloquea(self, db, sample_restaurant, mesa4, settings_default):
        """Reserva confirmada 8pm bloquea otra reserva 8pm."""
        _crear_reserva(sample_restaurant.id, mesa4.id, _mañana(), rs.parse_time('20:00'))
        table, _ = rs.check_availability(sample_restaurant.id, _mañana(), rs.parse_time('20:00'), 2)
        assert table is None

    def test_overlap_parcial_bloquea(self, db, sample_restaurant, mesa4, settings_default):
        """Duración 90 + buffer 15: reserva 8pm bloquea hasta 9:45pm. 9pm debe fallar."""
        _crear_reserva(sample_restaurant.id, mesa4.id, _mañana(), rs.parse_time('20:00'), status='confirmed')
        table, _ = rs.check_availability(sample_restaurant.id, _mañana(), rs.parse_time('21:00'), 2)
        assert table is None

    def test_horario_posterior_a_ventana_disponible(self, db, sample_restaurant, mesa4, settings_default):
        """Con config default (90+15), a las 9:45pm la mesa ya está libre."""
        _crear_reserva(sample_restaurant.id, mesa4.id, _mañana(), rs.parse_time('20:00'), status='confirmed')
        table, _ = rs.check_availability(sample_restaurant.id, _mañana(), rs.parse_time('21:45'), 2)
        assert table is not None

    def test_pendiente_tambien_bloquea(self, db, sample_restaurant, mesa4, settings_default):
        """Dos pendientes sobre la misma mesa = doble booking. La pending bloquea."""
        _crear_reserva(sample_restaurant.id, mesa4.id, _mañana(), rs.parse_time('20:00'), status='pending')
        table, _ = rs.check_availability(sample_restaurant.id, _mañana(), rs.parse_time('20:00'), 2)
        assert table is None

    def test_rechazada_y_no_show_no_bloquean(self, db, sample_restaurant, mesa4, settings_default):
        for status in ('rejected', 'no_show', 'completed'):
            _crear_reserva(sample_restaurant.id, mesa4.id, _mañana(), rs.parse_time('20:00'), status=status)
        table, _ = rs.check_availability(sample_restaurant.id, _mañana(), rs.parse_time('20:00'), 2)
        assert table is not None

    def test_otra_mesa_para_el_mismo_horario(self, db, sample_restaurant, mesa4, mesa8, settings_default):
        """Mesa 1 ocupada → best-fit encuentra Terraza."""
        _crear_reserva(sample_restaurant.id, mesa4.id, _mañana(), rs.parse_time('20:00'))
        table, _ = rs.check_availability(sample_restaurant.id, _mañana(), rs.parse_time('20:00'), 2)
        assert table is not None and table.id == mesa8.id

    def test_best_fit_no_quema_mesa_grande(self, db, sample_restaurant, mesa4, mesa8, settings_default):
        """Grupo de 2 → prefiere la de 4 aunque exista la de 8."""
        table, _ = rs.check_availability(sample_restaurant.id, _mañana(), rs.parse_time('20:00'), 2)
        assert table.id == mesa4.id

    def test_grupo_grande_salta_mesa_pequena(self, db, sample_restaurant, mesa4, mesa8, settings_default):
        """Grupo de 6 no cabe en la de 4 → usa Terraza."""
        table, _ = rs.check_availability(sample_restaurant.id, _mañana(), rs.parse_time('20:00'), 6)
        assert table.id == mesa8.id

    def test_grupo_mas_grande_que_todas_las_mesas(self, db, sample_restaurant, mesa4, settings_default):
        table, _ = rs.check_availability(sample_restaurant.id, _mañana(), rs.parse_time('20:00'), 50)
        assert table is None

    def test_capacity_null_se_trata_como_4(self, db, sample_restaurant, settings_default):
        t = Table(restaurant_id=sample_restaurant.id, name='Sin capacidad', capacity=None, is_active=True)
        db.session.add(t)
        db.session.commit()
        # 4 personas caben (default), 5 no
        table, _ = rs.check_availability(sample_restaurant.id, _mañana(), rs.parse_time('20:00'), 4)
        assert table is not None
        table, _ = rs.check_availability(sample_restaurant.id, _mañana(), rs.parse_time('21:00'), 5)
        assert table is None

    def test_mesa_inactiva_no_es_candidata(self, db, sample_restaurant, settings_default):
        t = Table(restaurant_id=sample_restaurant.id, name='Rota', capacity=4, is_active=False)
        db.session.add(t)
        db.session.commit()
        table, _ = rs.check_availability(sample_restaurant.id, _mañana(), rs.parse_time('20:00'), 2)
        assert table is None

    def test_reserva_de_otro_restaurante_no_bloquea(self, db, sample_restaurant, mesa4, settings_default):
        from app.models import Restaurant
        otro = Restaurant(
            name='Otro', slug='otro-reservas-test', whatsapp_phone='+573009999999',
            plan_type='emprendedor', is_active=True, is_open=True,
            subscription_expires_at=datetime.now(rs.COLOMBIA_TZ) + timedelta(days=30),
            has_used_trial=False,
        )
        db.session.add(otro)
        db.session.commit()
        _crear_reserva(otro.id, mesa4.id, _mañana(), rs.parse_time('20:00'))
        table, _ = rs.check_availability(sample_restaurant.id, _mañana(), rs.parse_time('20:00'), 2)
        assert table is not None

    def test_config_custom_cambia_la_ventana(self, db, sample_restaurant, mesa4, settings_default):
        """Duración 60 + buffer 0: reserva 8pm libera a las 9pm exactas."""
        rs.update_settings(sample_restaurant.id, {'service_duration_min': 60, 'cleanup_buffer_min': 0})
        _crear_reserva(sample_restaurant.id, mesa4.id, _mañana(), rs.parse_time('20:00'), status='confirmed')
        table, _ = rs.check_availability(sample_restaurant.id, _mañana(), rs.parse_time('21:00'), 2)
        assert table is not None  # ventana [20:00, 21:00) — 21:00 ya es libre


# ───────────── Creación de reservas (público) ─────────────

class TestCreateReservation:

    def test_crea_pendiente_con_mesa_asignada(self, db, sample_restaurant, mesa4, settings_default):
        r = rs.create_reservation(sample_restaurant.id, fecha=_mañana(), hora='20:00',
                                  party_size=2, customer_name='Carlos Pérez',
                                  customer_whatsapp='300 123-4567')
        assert r.status == 'pending'
        assert r.table_id == mesa4.id
        assert r.customer_whatsapp == '300123-4567'.replace('-', '')  # saneado

    def test_validaciones_basicas(self, db, sample_restaurant, mesa4, settings_default):
        with pytest.raises(ReservationServiceError):
            rs.create_reservation(sample_restaurant.id, fecha=_mañana(), hora='20:00',
                                  party_size=2, customer_name='  ', customer_whatsapp='3001234567')
        with pytest.raises(ReservationServiceError):
            rs.create_reservation(sample_restaurant.id, fecha=_mañana(), hora='20:00',
                                  party_size=2, customer_name='X', customer_whatsapp='abc')
        with pytest.raises(ReservationServiceError):
            rs.create_reservation(sample_restaurant.id, fecha=_mañana(), hora='25:00',
                                  party_size=2, customer_name='X', customer_whatsapp='3001234567')
        with pytest.raises(ReservationServiceError):
            rs.create_reservation(sample_restaurant.id, fecha=_mañana(), hora='20:00',
                                  party_size=0, customer_name='X', customer_whatsapp='3001234567')

    def test_fecha_pasada_rechazada(self, db, sample_restaurant, mesa4, settings_default):
        ayer = (datetime.now(rs.COLOMBIA_TZ) - timedelta(days=1)).strftime('%Y-%m-%d')
        with pytest.raises(ReservationServiceError) as e:
            rs.create_reservation(sample_restaurant.id, fecha=ayer, hora='20:00',
                                  party_size=2, customer_name='X', customer_whatsapp='3001234567')
        assert 'pasada' in str(e.value)

    def test_anticipacion_minima(self, db, sample_restaurant, mesa4, settings_default):
        """min_notice_hours=2: reservar en 30 minutos debe fallar."""
        en_media_hora = (datetime.now(rs.COLOMBIA_TZ) + timedelta(minutes=30))
        with pytest.raises(ReservationServiceError) as e:
            rs.create_reservation(sample_restaurant.id, fecha=en_media_hora.strftime('%Y-%m-%d'),
                                  hora=en_media_hora.strftime('%H:%M'),
                                  party_size=2, customer_name='X', customer_whatsapp='3001234567')
        assert 'anticipación' in str(e.value)

    def test_anticipacion_maxima(self, db, sample_restaurant, mesa4, settings_default):
        lejano = (datetime.now(rs.COLOMBIA_TZ) + timedelta(days=31)).strftime('%Y-%m-%d')
        with pytest.raises(ReservationServiceError) as e:
            rs.create_reservation(sample_restaurant.id, fecha=lejano, hora='20:00',
                                  party_size=2, customer_name='X', customer_whatsapp='3001234567')
        assert '30 días' in str(e.value)

    def test_auto_rechazo_sin_disponibilidad_409(self, db, sample_restaurant, mesa4, settings_default):
        """Regla del plan: sin mesa → NO se crea reserva, error 409 NO_AVAILABILITY."""
        _crear_reserva(sample_restaurant.id, mesa4.id, _mañana(), rs.parse_time('20:00'))
        with pytest.raises(ReservationServiceError) as e:
            rs.create_reservation(sample_restaurant.id, fecha=_mañana(), hora='20:30',
                                  party_size=2, customer_name='Y', customer_whatsapp='3001234567')
        assert e.value.code == 'NO_AVAILABILITY'
        assert e.value.http_status == 409
        assert Reservation.query.count() == 1  # solo la original

    def test_reservas_disabled_409(self, db, sample_restaurant, mesa4, settings_default):
        rs.update_settings(sample_restaurant.id, {'reservations_enabled': False})
        with pytest.raises(ReservationServiceError) as e:
            rs.create_reservation(sample_restaurant.id, fecha=_mañana(), hora='20:00',
                                  party_size=2, customer_name='X', customer_whatsapp='3001234567')
        assert e.value.code == 'RESERVATIONS_DISABLED'

    def test_nota_se_sanea(self, db, sample_restaurant, mesa4, settings_default):
        r = rs.create_reservation(sample_restaurant.id, fecha=_mañana(), hora='20:00',
                                  party_size=2, customer_name='X',
                                  customer_whatsapp='3001234567', customer_note='cumpleaños  ' + 'x' * 600)
        assert r.customer_note.startswith('cumpleaños')
        assert len(r.customer_note) == 500  # truncada al límite


# ───────────── Transiciones de estado ─────────────

class TestTransitions:

    def _reserva(self, db, sample_restaurant, mesa4, status='pending'):
        return _crear_reserva(sample_restaurant.id, mesa4.id, _mañana(), rs.parse_time('20:00'), status=status)

    def test_confirm(self, db, sample_restaurant, mesa4, settings_default):
        r = self._reserva(db, sample_restaurant, mesa4)
        out = rs.confirm_reservation(r.id, sample_restaurant.id)
        assert out.status == 'confirmed' and out.confirmed_at is not None

    def test_confirm_solo_pendientes(self, db, sample_restaurant, mesa4, settings_default):
        r = self._reserva(db, sample_restaurant, mesa4, status='confirmed')
        with pytest.raises(ReservationServiceError):
            rs.confirm_reservation(r.id, sample_restaurant.id)

    def test_reject_con_y_sin_motivo(self, db, sample_restaurant, mesa4, settings_default):
        r = self._reserva(db, sample_restaurant, mesa4)
        out = rs.reject_reservation(r.id, sample_restaurant.id, motivo=' No hay espacio ')
        assert out.status == 'rejected'
        assert out.rejection_reason == 'No hay espacio'
        assert out.rejected_at is not None

        r2 = self._reserva(db, sample_restaurant, mesa4)
        out2 = rs.reject_reservation(r2.id, sample_restaurant.id)
        assert out2.rejection_reason is None

    def test_reject_libera_la_mesa(self, db, sample_restaurant, mesa4, settings_default):
        """Al rechazar, el horario vuelve a estar disponible."""
        r = self._reserva(db, sample_restaurant, mesa4)
        rs.reject_reservation(r.id, sample_restaurant.id)
        table, _ = rs.check_availability(sample_restaurant.id, _mañana(), rs.parse_time('20:00'), 2)
        assert table is not None

    def test_reject_no_permite_rechazar_completada(self, db, sample_restaurant, mesa4, settings_default):
        r = self._reserva(db, sample_restaurant, mesa4, status='completed')
        with pytest.raises(ReservationServiceError):
            rs.reject_reservation(r.id, sample_restaurant.id)

    def test_complete_y_no_show_solo_confirmadas(self, db, sample_restaurant, mesa4, settings_default):
        r = self._reserva(db, sample_restaurant, mesa4)
        with pytest.raises(ReservationServiceError):
            rs.complete_reservation(r.id, sample_restaurant.id)
        with pytest.raises(ReservationServiceError):
            rs.mark_no_show(r.id, sample_restaurant.id)
        rs.confirm_reservation(r.id, sample_restaurant.id)
        assert rs.complete_reservation(r.id, sample_restaurant.id).status == 'completed'

        r2 = self._reserva(db, sample_restaurant, mesa4)
        rs.confirm_reservation(r2.id, sample_restaurant.id)
        assert rs.mark_no_show(r2.id, sample_restaurant.id).status == 'no_show'

    def test_404_reserva_de_otro_restaurante(self, db, sample_restaurant, mesa4, settings_default):
        from app.models import Restaurant
        otro = Restaurant(
            name='Vecino', slug='vecino-reservas-test', whatsapp_phone='+573008888888',
            plan_type='emprendedor', is_active=True, is_open=True,
            subscription_expires_at=datetime.now(rs.COLOMBIA_TZ) + timedelta(days=30),
            has_used_trial=False,
        )
        db.session.add(otro)
        db.session.commit()
        r = _crear_reserva(sample_restaurant.id, mesa4.id, _mañana(), rs.parse_time('20:00'))
        with pytest.raises(ReservationServiceError) as e:
            rs.confirm_reservation(r.id, otro.id)
        assert e.value.http_status == 404


# ───────────── QR → reserva ─────────────

class TestQrLink:

    def test_qr_confirma_reserva_del_dia(self, db, sample_restaurant, mesa4, settings_default):
        hoy = datetime.now(rs.COLOMBIA_TZ).date()
        r = _crear_reserva(sample_restaurant.id, mesa4.id, hoy, rs.parse_time('12:00'), status='confirmed')
        out = rs.link_qr_to_reservation(sample_restaurant.id, mesa4.id)
        assert out is not None and out.id == r.id
        assert out.status == 'completed'

    def test_qr_sin_reserva_devuelve_none(self, db, sample_restaurant, mesa4, settings_default):
        assert rs.link_qr_to_reservation(sample_restaurant.id, mesa4.id) is None

    def test_qr_ignora_pendientes(self, db, sample_restaurant, mesa4, settings_default):
        hoy = datetime.now(rs.COLOMBIA_TZ).date()
        _crear_reserva(sample_restaurant.id, mesa4.id, hoy, rs.parse_time('12:00'), status='pending')
        assert rs.link_qr_to_reservation(sample_restaurant.id, mesa4.id) is None


# ───────────── Recordatorios ─────────────

class TestReminders:

    def test_recordatorio_en_ventana(self, db, sample_restaurant, mesa4, settings_default, monkeypatch):
        """Reserva confirmada en 1h (ventana default 2h) → se envía y marca flag."""
        enviado = []
        import app.services.notification_service as ns
        monkeypatch.setattr(ns, 'notify_reservation_reminder',
                            lambda restaurant, res: enviado.append(res.id))

        en_una_hora = datetime.now(rs.COLOMBIA_TZ) + timedelta(hours=1)
        r = Reservation(
            restaurant_id=sample_restaurant.id, table_id=mesa4.id,
            customer_name='Carlos', customer_whatsapp='+573001111111',
            reservation_date=en_una_hora.date(),
            reservation_time=en_una_hora.time().replace(microsecond=0),
            party_size=2, status='confirmed', reminder_sent=False,
        )
        db.session.add(r)
        db.session.commit()

        sent = rs.send_reservation_reminders()
        assert sent == 1
        assert enviado == [r.id]
        db.session.expire(r)
        assert r.reminder_sent is True

    def test_recordatorio_idempotente(self, db, sample_restaurant, mesa4, settings_default, monkeypatch):
        """Dos corridas seguidas no duplican el envío."""
        import app.services.notification_service as ns
        llamados = []
        monkeypatch.setattr(ns, 'notify_reservation_reminder',
                            lambda restaurant, res: llamados.append(res.id))

        en_una_hora = datetime.now(rs.COLOMBIA_TZ) + timedelta(hours=1)
        r = Reservation(
            restaurant_id=sample_restaurant.id, table_id=mesa4.id,
            customer_name='Ana', customer_whatsapp='+573002222222',
            reservation_date=en_una_hora.date(),
            reservation_time=en_una_hora.time().replace(microsecond=0),
            party_size=2, status='confirmed',
        )
        db.session.add(r)
        db.session.commit()

        assert rs.send_reservation_reminders() == 1
        assert rs.send_reservation_reminders() == 0
        assert llamados == [r.id]

    def test_recordatorio_fuera_de_ventana(self, db, sample_restaurant, mesa4, settings_default, monkeypatch):
        """Reserva en 5 horas (ventana 2h) → no se envía todavía."""
        import app.services.notification_service as ns
        monkeypatch.setattr(ns, 'notify_reservation_reminder', lambda *a, **k: None)

        en_cinco_horas = datetime.now(rs.COLOMBIA_TZ) + timedelta(hours=5)
        db.session.add(Reservation(
            restaurant_id=sample_restaurant.id, table_id=mesa4.id,
            customer_name='Luis', customer_whatsapp='+573003333333',
            reservation_date=en_cinco_horas.date(),
            reservation_time=en_cinco_horas.time().replace(microsecond=0),
            party_size=2, status='confirmed',
        ))
        db.session.commit()
        assert rs.send_reservation_reminders() == 0

    def test_recordatorio_deshabilitado(self, db, sample_restaurant, mesa4, settings_default, monkeypatch):
        import app.services.notification_service as ns
        monkeypatch.setattr(ns, 'notify_reservation_reminder', lambda *a, **k: None)
        rs.update_settings(sample_restaurant.id, {'reminder_enabled': False})

        en_una_hora = datetime.now(rs.COLOMBIA_TZ) + timedelta(hours=1)
        db.session.add(Reservation(
            restaurant_id=sample_restaurant.id, table_id=mesa4.id,
            customer_name='Marta', customer_whatsapp='+573004444444',
            reservation_date=en_una_hora.date(),
            reservation_time=en_una_hora.time().replace(microsecond=0),
            party_size=2, status='confirmed',
        ))
        db.session.commit()
        assert rs.send_reservation_reminders() == 0


# ───────────── Config con saneamiento ─────────────

class TestSettings:

    def test_defaults(self, db, sample_restaurant, settings_default):
        assert settings_default.service_duration_min == 90
        assert settings_default.cleanup_buffer_min == 15
        assert settings_default.min_notice_hours == 2
        assert settings_default.max_advance_days == 30
        assert settings_default.reservations_enabled is True

    def test_update_y_rangos(self, db, sample_restaurant, settings_default):
        rs.update_settings(sample_restaurant.id, {'service_duration_min': 120})
        assert settings_default.service_duration_min == 120
        with pytest.raises(ReservationServiceError):
            rs.update_settings(sample_restaurant.id, {'service_duration_min': 10})
        with pytest.raises(ReservationServiceError):
            rs.update_settings(sample_restaurant.id, {'cleanup_buffer_min': 999})
        with pytest.raises(ReservationServiceError):
            rs.update_settings(sample_restaurant.id, {'max_advance_days': 'no-es-numero'})

    def test_singleton_por_restaurante(self, db, sample_restaurant, settings_default):
        again = rs.get_or_create_settings(sample_restaurant.id)
        assert again.id == settings_default.id


# ───────────── API pública (HTTP) ─────────────

class TestPublicAPI:

    def test_check_disponible(self, app, db, client, sample_restaurant, mesa4, settings_default):
        resp = client.post(f'/api/reservations/{sample_restaurant.slug}/check', json={
            'fecha': _mañana().strftime('%Y-%m-%d'), 'hora': '20:00', 'personas': 2})
        assert resp.status_code == 200
        assert resp.get_json()['data']['available'] is True

    def test_check_sin_disponibilidad(self, app, db, client, sample_restaurant, mesa4, settings_default):
        _crear_reserva(sample_restaurant.id, mesa4.id, _mañana(), rs.parse_time('20:00'))
        resp = client.post(f'/api/reservations/{sample_restaurant.slug}/check', json={
            'fecha': _mañana().strftime('%Y-%m-%d'), 'hora': '20:00', 'personas': 2})
        assert resp.get_json()['data']['available'] is False

    def test_crear_reserva_201(self, app, db, client, sample_restaurant, mesa4, settings_default, monkeypatch):
        import app.routes.api_reservations as route_mod
        monkeypatch.setattr(route_mod, 'notify_new_reservation', lambda r: None)

        resp = client.post(f'/api/reservations/{sample_restaurant.slug}', json={
            'fecha': _mañana().strftime('%Y-%m-%d'), 'hora': '20:00', 'personas': 2,
            'nombre': 'Carlos Pérez', 'whatsapp': '3001234567', 'nota': 'cumpleaños'})
        assert resp.status_code == 201
        body = resp.get_json()
        assert body['success'] is True
        assert Reservation.query.count() == 1

    def test_crear_sin_disponibilidad_409(self, app, db, client, sample_restaurant, mesa4, settings_default):
        _crear_reserva(sample_restaurant.id, mesa4.id, _mañana(), rs.parse_time('20:00'))
        resp = client.post(f'/api/reservations/{sample_restaurant.slug}', json={
            'fecha': _mañana().strftime('%Y-%m-%d'), 'hora': '20:00', 'personas': 2,
            'nombre': 'Y', 'whatsapp': '3001234567'})
        assert resp.status_code == 409
        assert resp.get_json()['error_code'] == 'NO_AVAILABILITY'

    def test_slug_inexistente_404(self, db, client):
        resp = client.post('/api/reservations/no-existe', json={})
        assert resp.status_code == 404

    def test_rate_limit_429(self, app, db, client, sample_restaurant, mesa4, settings_default):
        """4ª solicitud en un minuto desde la misma IP → 429."""
        payload = {'fecha': _mañana().strftime('%Y-%m-%d'), 'hora': '20:00',
                   'personas': 2, 'nombre': 'RL', 'whatsapp': '3001234567'}
        # horas separadas >105 min (duración 90 + buffer 15) para que cada
        # solicitud encuentre la mesa libre y devuelva 201 (no 409)
        for i, hora in enumerate(('12:00', '15:00', '18:00')):
            resp = client.post(f'/api/reservations/{sample_restaurant.slug}',
                               json={**payload, 'hora': hora},
                               environ_base={'REMOTE_ADDR': '1.2.3.4'})
            assert resp.status_code == 201, f'intento {i}: {resp.get_json()}'
        resp = client.post(f'/api/reservations/{sample_restaurant.slug}',
                           json={**payload, 'hora': '21:00'},
                           environ_base={'REMOTE_ADDR': '1.2.3.4'})
        assert resp.status_code == 429


# ───────────── API del restaurante (HTTP, sesión) ─────────────

@pytest.fixture
def auth_client(app, sample_user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = sample_user.id
        sess['username'] = sample_user.username
    return client


class TestRestaurantAPI:

    def test_listar_requiere_auth(self, client):
        assert client.get('/api/reservations').status_code in (301, 302, 401)

    def test_listar(self, auth_client, db, sample_restaurant, mesa4, settings_default):
        _crear_reserva(sample_restaurant.id, mesa4.id, _mañana(), rs.parse_time('20:00'))
        resp = auth_client.get('/api/reservations')
        assert resp.status_code == 200
        data = resp.get_json()['data']['reservations']
        assert len(data) == 1
        assert data[0]['customer_name'] == 'Cliente Existente'
        assert data[0]['table_name'] == 'Mesa 1'

    def test_confirm_via_api(self, auth_client, db, sample_restaurant, mesa4, settings_default, monkeypatch):
        import app.routes.api_reservations as route_mod
        monkeypatch.setattr(route_mod, 'notify_reservation_confirmed', lambda r: None)
        r = _crear_reserva(sample_restaurant.id, mesa4.id, _mañana(), rs.parse_time('20:00'))
        resp = auth_client.patch(f'/api/reservations/{r.id}/confirm')
        assert resp.status_code == 200
        db.session.expire(r)
        assert r.status == 'confirmed'

    def test_reject_via_api_con_motivo(self, auth_client, db, sample_restaurant, mesa4, settings_default, monkeypatch):
        import app.routes.api_reservations as route_mod
        monkeypatch.setattr(route_mod, 'notify_reservation_rejected', lambda r: None)
        r = _crear_reserva(sample_restaurant.id, mesa4.id, _mañana(), rs.parse_time('20:00'))
        resp = auth_client.patch(f'/api/reservations/{r.id}/reject', json={'motivo': 'Cerramos temprano'})
        assert resp.status_code == 200
        db.session.expire(r)
        assert r.status == 'rejected'
        assert r.rejection_reason == 'Cerramos temprano'

    def test_calendar(self, auth_client, db, sample_restaurant, mesa4, settings_default):
        _crear_reserva(sample_restaurant.id, mesa4.id, _mañana(), rs.parse_time('20:00'), status='confirmed')
        resp = auth_client.get(f'/api/reservations/calendar?fecha={_mañana().strftime("%Y-%m-%d")}')
        assert resp.status_code == 200
        rows = resp.get_json()['data']['rows']
        assert len(rows) == 1
        assert rows[0]['table_name'] == 'Mesa 1'
        assert rows[0]['reservations'][0]['start'] == '20:00'
        assert rows[0]['reservations'][0]['end'] == '21:45'

    def test_settings_get_y_patch(self, auth_client, settings_default):
        resp = auth_client.get('/api/reservations/settings')
        assert resp.status_code == 200
        assert resp.get_json()['data']['service_duration_min'] == 90

        resp = auth_client.patch('/api/reservations/settings', json={'service_duration_min': 60})
        assert resp.status_code == 200
        assert resp.get_json()['data']['service_duration_min'] == 60

        # Config inválida → 400
        resp = auth_client.patch('/api/reservations/settings', json={'service_duration_min': 9999})
        assert resp.status_code == 400
