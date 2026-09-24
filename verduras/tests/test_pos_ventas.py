"""
Ventas del Día v1: KPIs + desglose + curva + top5 (Tier GUARDIAN).

Todo número es real (ventas de hoy Bogotá, no canceladas). Sin cierre Z
en v1: esta suite fija que la página muestra resumen computable y que
los guards de sesión/anti-IDOR responden.
"""
import pytest

from app.models import Business
from verduras.services.catalog import create_category, create_product


def _slug():
    _slug.n = getattr(_slug, 'n', 0) + 1
    return f'vtas-{_slug.n}'


@pytest.fixture()
def biz(db) -> Business:
    return Business.create_direct(vertical='verduras',
                                  name='Verduras Ventas', slug=_slug())


@pytest.fixture()
def catalog_row(db, biz):
    from types import SimpleNamespace
    cat = create_category(biz.id, 'Hortalizas')
    tomate = create_product(biz.id, cat.id, 'Tomate', 'kg', '3200.00')
    return SimpleNamespace(cat=cat, tomate=tomate)


def _set_pin(biz, pin='4321'):
    from verduras.services.pos_auth import setup_pos_pin
    setup_pos_pin(biz.id, pin)


def _login(client, biz, pin='4321'):
    return client.post('/pos/login', data={'slug': biz.slug, 'pin': pin})


def _login_client(client, biz):
    _set_pin(biz)
    _login(client, biz)


def _sell(biz, product, qty='1', method='efectivo'):
    from verduras.services.sales import create_sale
    return create_sale(biz.id, [{'product_id': product.id,
                                 'quantity': qty}],
                       payment_method=method)


class TestVentasView:
    def test_requires_session(self, client, db, biz, catalog_row):
        res = client.get(f'/pos/{biz.slug}/ventas', follow_redirects=False)
        assert res.status_code == 302
        assert '/pos/login' in res.headers['Location']

    def test_foreign_slug_rejected(self, client, db, biz, catalog_row):
        other = Business.create_direct(vertical='verduras',
                                       name='Otro', slug=_slug())
        _set_pin(other)
        _login_client(client, biz)
        res = client.get(f'/pos/{other.slug}/ventas',
                         follow_redirects=False)
        assert res.status_code == 302
        assert '/pos/login' in res.headers['Location']

    def test_kpis_and_breakdown(self, client, db, biz, catalog_row):
        _sell(biz, catalog_row.tomate, '1', 'efectivo')
        _sell(biz, catalog_row.tomate, '2', 'tarjeta')
        _login_client(client, biz)
        res = client.get(f'/pos/{biz.slug}/ventas')
        html = res.get_data(as_text=True)
        assert res.status_code == 200
        # 3200 + 6400 = 9.600 total, 2 tickets.
        assert '9.600' in html
        assert 'Efectivo' in html
        assert 'Tarjeta' in html

    def test_cancelled_excluded(self, client, db, biz, catalog_row):
        from verduras.services.sales import mark_cancelled
        sale, _ = _sell(biz, catalog_row.tomate, '1', 'efectivo')
        mark_cancelled(biz.id, sale.id)
        _login_client(client, biz)
        res = client.get(f'/pos/{biz.slug}/ventas')
        html = res.get_data(as_text=True)
        assert 'Aún no hay ventas hoy' in html

    def test_top5_and_curve_with_data(self, client, db, biz, catalog_row):
        _sell(biz, catalog_row.tomate, '1', 'efectivo')
        _login_client(client, biz)
        res = client.get(f'/pos/{biz.slug}/ventas')
        html = res.get_data(as_text=True)
        assert 'Top 5 por kilos' in html
        assert 'Tomate' in html
        assert 'vtas-curve' in html

    def test_empty_state(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        res = client.get(f'/pos/{biz.slug}/ventas')
        html = res.get_data(as_text=True)
        assert res.status_code == 200
        assert 'Aún no hay ventas hoy' in html
        assert 'vtas-curve' not in html


class TestVentasDayFilter:
    def _ayer(self):
        from datetime import timedelta
        from verduras.services.caja import bogota_today
        return (bogota_today() - timedelta(days=1)).isoformat()

    def test_yesterday_shows_nothing_new(self, client, db, biz,
                                         catalog_row):
        _sell(biz, catalog_row.tomate, '1', 'efectivo')
        _login_client(client, biz)
        html = client.get(
            f'/pos/{biz.slug}/ventas?day={self._ayer()}').get_data(
            as_text=True)
        assert 'Aún no hay ventas hoy' in html

    def test_invalid_day_falls_back_to_today(self, client, db, biz,
                                            catalog_row):
        _sell(biz, catalog_row.tomate, '1', 'efectivo')
        _login_client(client, biz)
        res = client.get(f'/pos/{biz.slug}/ventas?day=no-es-fecha')
        assert res.status_code == 200
        assert '3.200' in res.get_data(as_text=True)

    def test_future_day_clamps_to_today(self, client, db, biz,
                                        catalog_row):
        _sell(biz, catalog_row.tomate, '1', 'efectivo')
        _login_client(client, biz)
        res = client.get(f'/pos/{biz.slug}/ventas?day=2999-01-01')
        assert res.status_code == 200
        assert '3.200' in res.get_data(as_text=True)

    def test_close_past_day(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/ventas/cierre',
                          json={'counted_cash': '0', 'day': self._ayer()})
        assert res.status_code == 201
        assert res.get_json()['data']['day'] == self._ayer()


class TestCierreZ:
    def test_close_computes_and_persists(self, client, db, biz,
                                         catalog_row):
        _sell(biz, catalog_row.tomate, '2', 'efectivo')  # 6400
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/ventas/cierre',
                          json={'counted_cash': '6000'})
        assert res.status_code == 201
        data = res.get_json()['data']
        assert data['cash_expected'] == '6400.00'
        assert data['counted_cash'] == '6000.00'
        assert data['difference'] == '-400.00'

    def test_duplicate_day_400(self, client, db, biz, catalog_row):
        _sell(biz, catalog_row.tomate, '1', 'efectivo')
        _login_client(client, biz)
        url = f'/pos/{biz.slug}/ventas/cierre'
        assert client.post(url, json={'counted_cash': '3200'}).status_code == 201
        res = client.post(url, json={'counted_cash': '3200'})
        assert res.status_code == 400
        assert 'ya tiene cierre' in res.get_json()['error']

    def test_invalid_counted_400(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/ventas/cierre',
                          json={'counted_cash': 'mucho'})
        assert res.status_code == 400

    def test_negative_counted_400(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/ventas/cierre',
                          json={'counted_cash': '-5'})
        assert res.status_code == 400

    def test_closed_badge_in_page(self, client, db, biz, catalog_row):
        _sell(biz, catalog_row.tomate, '1', 'efectivo')
        _login_client(client, biz)
        client.post(f'/pos/{biz.slug}/ventas/cierre',
                    json={'counted_cash': '3200'})
        html = client.get(f'/pos/{biz.slug}/ventas').get_data(as_text=True)
        assert 'Día cerrado' in html
        # El botón se va (por id, no por copy: el copy puede cambiar).
        assert 'id="vtas-cierre-open"' not in html

    def test_close_requires_session(self, client, db, biz, catalog_row):
        res = client.post(f'/pos/{biz.slug}/ventas/cierre',
                          json={'counted_cash': '1000'})
        assert res.status_code == 401


class TestLibroCaja:
    def _mov(self, client, biz, tipo, monto, motivo=''):
        return client.post(f'/pos/{biz.slug}/ventas/movimiento',
                           json={'tipo': tipo, 'monto': monto,
                                 'motivo': motivo})

    def test_ingreso_sube_esperado(self, client, db, biz, catalog_row):
        _sell(biz, catalog_row.tomate, '1', 'efectivo')  # 3200
        _login_client(client, biz)
        assert self._mov(client, biz, 'ingreso', '1000',
                         'fondo').status_code == 201
        res = client.post(f'/pos/{biz.slug}/ventas/cierre',
                          json={'counted_cash': '4200'})
        assert res.status_code == 201
        assert res.get_json()['data']['cash_expected'] == '4200.00'

    def test_retiro_baja_esperado(self, client, db, biz, catalog_row):
        _sell(biz, catalog_row.tomate, '1', 'efectivo')  # 3200
        _login_client(client, biz)
        assert self._mov(client, biz, 'retiro', '200',
                         'mercado').status_code == 201
        res = client.post(f'/pos/{biz.slug}/ventas/cierre',
                          json={'counted_cash': '3000'})
        assert res.status_code == 201
        assert res.get_json()['data']['cash_expected'] == '3000.00'

    def test_movimiento_invalido_400(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        assert self._mov(client, biz, 'regalo', '100').status_code == 400
        assert self._mov(client, biz, 'ingreso', 'cero').status_code == 400
        assert self._mov(client, biz, 'ingreso', '-5').status_code == 400

    def test_movimiento_requires_session(self, client, db, biz,
                                         catalog_row):
        res = client.post(f'/pos/{biz.slug}/ventas/movimiento',
                          json={'tipo': 'ingreso', 'monto': '100'})
        assert res.status_code == 401


class TestCierresHistory:
    def test_history_lists_signed_closes(self, client, db, biz,
                                         catalog_row):
        from verduras.services import caja as caja_service
        _sell(biz, catalog_row.tomate, '1', 'efectivo')
        caja_service.close_day(biz.id, '3200')
        _login_client(client, biz)
        html = client.get(f'/pos/{biz.slug}/ventas').get_data(as_text=True)
        assert 'Cierres anteriores' in html
        assert 'dif. $0' in html

    def test_history_hidden_without_closes(self, client, db, biz,
                                           catalog_row):
        _login_client(client, biz)
        html = client.get(f'/pos/{biz.slug}/ventas').get_data(as_text=True)
        assert 'Cierres anteriores' not in html
