"""
Regresiones de los tres fallos de una línea encontrados en el diagnóstico
AS-IS (VLZ-1, VLZ-2, VLZ-22).

Los tres eran el mismo tipo de error: un nombre que el módulo nunca importó, o
un valor por defecto que nunca se aplica. Ninguno tenía cobertura, y el CI
pasaba porque `flake8` corría con `--exit-zero` (VLZ-5, ya corregido).

Estas pruebas recorren justo esas rutas para que no vuelvan.
"""

from datetime import datetime, timedelta, timezone

from app.models import Restaurant, User


class TestRequireActiveTransicionDormant:
    """VLZ-1 — `app/utils/auth.py` usaba datetime, timezone y db sin importarlos.

    La rama que fallaba: restaurante con `cancellation_pending` cuya
    suscripción ya venció y agotó los 5 días de gracia. Al entrar al panel,
    `require_active` intenta pasarlo a `dormant` y reventaba con NameError,
    devolviendo un 500 en lugar de la pantalla de reactivación.
    """

    def _restaurante_cancelado_y_vencido(self, db):
        r = Restaurant(
            name='Cancelado', slug='cancelado-vencido',
            whatsapp_phone='+573009998877', is_active=True,
            plan_type='emprendedor', subscription_state='cancellation_pending',
            subscription_expires_at=datetime.now(timezone.utc) - timedelta(days=90),
        )
        db.session.add(r)
        db.session.commit()
        u = User(restaurant_id=r.id, username='duenoc', email='c@test.co',
                 password='x', role='owner')
        db.session.add(u)
        db.session.commit()
        return r, u

    def test_no_revienta_con_nameerror(self, db, client):
        r, u = self._restaurante_cancelado_y_vencido(db)
        with client.session_transaction() as s:
            s['user_id'] = u.id

        resp = client.get('/dashboard/')

        assert resp.status_code != 500, (
            'La transición cancellation_pending -> dormant volvió a romperse'
        )

    def test_la_cuenta_queda_dormant(self, db, client):
        r, u = self._restaurante_cancelado_y_vencido(db)
        rid = r.id
        with client.session_transaction() as s:
            s['user_id'] = u.id

        client.get('/dashboard/')

        db.session.expire_all()
        actualizado = db.session.get(Restaurant, rid)
        assert actualizado.subscription_state == 'dormant'
        assert actualizado.is_active is False
        assert actualizado.dormant_at is not None


class TestCancelarCuentaPorApi:
    """VLZ-2 — `app/routes/api_dashboard.py` usaba `db` sin importarlo.

    Doble fallo: el NameError saltaba en el commit, lo capturaba el
    `except Exception` y el propio manejador volvía a fallar en el rollback.
    Resultado: 500 y la cancelación sin guardar.
    """

    def test_devuelve_exito_y_no_500(self, db, client, sample_restaurant, sample_user):
        with client.session_transaction() as s:
            s['user_id'] = sample_user.id

        resp = client.post('/api/dashboard/cancel-account',
                           json={'confirmation': 'CANCELAR'})

        assert resp.status_code == 200, f'Esperaba 200, llegó {resp.status_code}'
        assert resp.get_json()['success'] is True

    def test_la_cancelacion_se_persiste(self, db, client, sample_restaurant, sample_user):
        rid = sample_restaurant.id
        with client.session_transaction() as s:
            s['user_id'] = sample_user.id

        client.post('/api/dashboard/cancel-account', json={'confirmation': 'CANCELAR'})

        db.session.expire_all()
        actualizado = db.session.get(Restaurant, rid)
        assert actualizado.subscription_state == 'cancellation_pending'
        assert actualizado.cancellation_requested_at is not None

    def test_sigue_exigiendo_la_confirmacion(self, db, client, sample_restaurant, sample_user):
        with client.session_transaction() as s:
            s['user_id'] = sample_user.id

        resp = client.post('/api/dashboard/cancel-account', json={'confirmation': 'nope'})

        assert resp.status_code == 400


class TestRedireccionDelMenuPublico:
    """VLZ-22 — `config.get(clave, defecto)` con claves que valen None.

    `ASTRO_BASE_URL` existe en la configuración con valor None cuando falta su
    variable de entorno, así que el segundo argumento de `get` nunca se
    aplicaba y la redirección salía como `None/<slug>/`: todos los QR de las
    mesas acababan en un 404.
    """

    def test_sin_astro_base_url_no_aparece_none_en_la_url(
        self, app, db, client, sample_restaurant
    ):
        app.config['ASTRO_BASE_URL'] = None
        app.config['BASE_URL'] = None

        resp = client.get(f'/menu/{sample_restaurant.slug}')

        assert resp.status_code == 302
        assert 'None' not in resp.headers['Location'], (
            f"La cascada de respaldo volvió a fallar: {resp.headers['Location']}"
        )
        assert resp.headers['Location'].rstrip('/').endswith(sample_restaurant.slug)

    def test_usa_base_url_cuando_falta_astro_base_url(
        self, app, db, client, sample_restaurant
    ):
        app.config['ASTRO_BASE_URL'] = None
        app.config['BASE_URL'] = 'https://respaldo.example'

        resp = client.get(f'/menu/{sample_restaurant.slug}')

        assert resp.headers['Location'] == (
            f'https://respaldo.example/{sample_restaurant.slug}/'
        )

    def test_astro_base_url_tiene_prioridad(self, app, db, client, sample_restaurant):
        app.config['ASTRO_BASE_URL'] = 'https://menu.example'
        app.config['BASE_URL'] = 'https://respaldo.example'

        resp = client.get(f'/menu/{sample_restaurant.slug}')

        assert resp.headers['Location'] == (
            f'https://menu.example/{sample_restaurant.slug}/'
        )
