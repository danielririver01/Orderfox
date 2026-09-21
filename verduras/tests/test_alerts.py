"""
Tests de las alertas de rotación (Semana 5).

Cubren:
- set_min_stock: valores válidos, 0/negativo/lixo rechazados, None = opt-out.
- sales_velocity: None sin ventas, promedio sobre la ventana, excluye
  canceladas (misma semántica que el stock — fuente única de verdad).
- list_alerts: severidades out/low, productos sin umbral ignorados,
  velocidad y days_left, orden (out primero, luego urgencia, luego nombre),
  mensaje en lenguaje de verdulero (plural de 'unidad' incluido).
- API: x-api-key obligatorio, anti-IDOR (umbral de producto ajeno = 404).
- POS: el mapa de alertas llega en pos-data.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import Business
from verduras.services import alerts
from verduras.services import inventory as inventory_service
from verduras.services import sales as sales_service
from verduras.services.catalog import create_category, create_product

API_KEY = {'x-api-key': 'test-service-api-key'}


def _slug():
    _slug.n = getattr(_slug, 'n', 0) + 1
    return f'alerts-{_slug.n}'


@pytest.fixture()
def biz(db) -> Business:
    return Business.create_direct(vertical='verduras',
                                  name='Verduras Alertas', slug=_slug())


def _setup(biz, db, products=('Tomate', 'Banano')):
    cat = create_category(biz.id, 'General')
    created = {'cat': cat}
    for name in products:
        created[name] = create_product(biz.id, cat.id, name, 'kg', '1000')
    return created


def _lot(biz, product, qty, purchased_at=None):
    inventory_service.register_lot(biz.id, product.id, qty, str(Decimal(qty) * 1000),
                                   purchased_at=purchased_at)


def _sale(biz, product, qty, created_at=None):
    """Venta directa vía servicio; `created_at` de test viaja en `until`-style
    no aplica al crear: para backdatar se usa _backdate()."""
    sales_service.create_sale(
        biz.id, [{'product_id': product.id, 'quantity': qty}],
        sale_type='walk_in')


def _backdate_sale(db, product, days):
    """Retrocede created_at de la última venta del producto."""
    from verduras.models_sales import VerdurasSale
    sale = (VerdurasSale.query.filter_by(business_id=product.business_id)
            .order_by(VerdurasSale.id.desc()).first())
    sale.created_at = datetime.now(timezone.utc) - timedelta(days=days)
    db.session.commit()


# ═════════════════ set_min_stock ═════════════════


class TestSetMinStock:
    def test_set_valid_threshold(self, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        p = alerts.set_min_stock(biz.id, rows['Tomate'].id, '5')
        assert p.min_stock == Decimal('5.000')

    def test_decimal_threshold(self, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        p = alerts.set_min_stock(biz.id, rows['Tomate'].id, '2.500')
        assert p.min_stock == Decimal('2.500')

    def test_zero_rejected(self, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        with pytest.raises(inventory_service.VerdurasValidationError,
                           match='null'):
            alerts.set_min_stock(biz.id, rows['Tomate'].id, '0')

    def test_negative_rejected(self, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        with pytest.raises(inventory_service.VerdurasValidationError,
                           match='negativo'):
            alerts.set_min_stock(biz.id, rows['Tomate'].id, '-1')

    def test_clear_with_none(self, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        alerts.set_min_stock(biz.id, rows['Tomate'].id, '5')
        p = alerts.set_min_stock(biz.id, rows['Tomate'].id, None)
        assert p.min_stock is None

    def test_foreign_product_404(self, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        other = Business.create_direct(vertical='verduras', name='Otro',
                                       slug=_slug())
        with pytest.raises(inventory_service.VerdurasNotFoundError):
            alerts.set_min_stock(other.id, rows['Tomate'].id, '5')


# ═════════════════ sales_velocity ═════════════════


class TestVelocity:
    def test_none_without_sales(self, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        assert alerts.sales_velocity(biz.id, rows['Tomate'].id) is None

    def test_average_over_window(self, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        _lot(biz, rows['Tomate'], 10)
        _sale(biz, rows['Tomate'], '3.000')
        # 3 kg en 7 días → 0.428571... → 0.43 (2 decimales)
        assert alerts.sales_velocity(biz.id, rows['Tomate'].id) == Decimal('0.43')

    def test_excludes_cancelled(self, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        _lot(biz, rows['Tomate'], 10)
        sale, _ = sales_service.create_sale(
            biz.id, [{'product_id': rows['Tomate'].id, 'quantity': '5.000'}],
            sale_type='walk_in')
        sales_service.mark_cancelled(biz.id, sale.id)
        assert alerts.sales_velocity(biz.id, rows['Tomate'].id) is None

    def test_old_sales_outside_window_ignored(self, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        _lot(biz, rows['Tomate'], 20)
        _sale(biz, rows['Tomate'], '10.000')
        _backdate_sale(db, rows['Tomate'], 10)  # fuera de los 7 días
        assert alerts.sales_velocity(biz.id, rows['Tomate'].id) is None


# ═════════════════ list_alerts ═════════════════


class TestListAlerts:
    def test_no_threshold_no_alerts(self, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        _lot(biz, rows['Tomate'], 1)
        assert alerts.list_alerts(biz.id)['count'] == 0

    def test_stock_above_threshold_no_alert(self, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        _lot(biz, rows['Tomate'], 10)
        alerts.set_min_stock(biz.id, rows['Tomate'].id, '5')
        assert alerts.list_alerts(biz.id)['count'] == 0

    def test_low_alert_with_days_left(self, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        _lot(biz, rows['Tomate'], 10)
        _sale(biz, rows['Tomate'], '7.000')  # velocidad = 1/día
        alerts.set_min_stock(biz.id, rows['Tomate'].id, '5')
        data = alerts.list_alerts(biz.id)
        assert data['count'] == 1
        alert = data['alerts'][0]
        assert alert['severity'] == 'low'
        assert alert['stock'] == '3.000'
        assert alert['velocity_per_day'] == '1.00'
        assert alert['days_left'] == '3.0'
        assert alert['message'] == (
            'Te quedan 3 kg de Tomate — a este ritmo te dura ~3 días. '
            'Considera reponer.')

    def test_out_alert_no_days_left(self, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        _lot(biz, rows['Tomate'], 2)
        _sale(biz, rows['Tomate'], '2.000')  # stock 0
        alerts.set_min_stock(biz.id, rows['Tomate'].id, '5')
        alert = alerts.list_alerts(biz.id)['alerts'][0]
        assert alert['severity'] == 'out'
        assert alert['days_left'] is None
        assert alert['message'] == 'Te quedaste sin Tomate. Considera reponer.'

    def test_merma_counts_toward_stock(self, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        _lot(biz, rows['Tomate'], 10)
        inventory_service.register_merma(biz.id, rows['Tomate'].id, '8.000')
        alerts.set_min_stock(biz.id, rows['Tomate'].id, '5')
        alert = alerts.list_alerts(biz.id)['alerts'][0]
        # 10 − 0 vendido − 8 merma = 2 ≤ 5 → low (no agotado)
        assert alert['severity'] == 'low'
        assert alert['stock'] == '2.000'

    def test_order_out_first_then_urgency_then_name(self, db, biz):
        rows = _setup(biz, db, ('Banano', 'Tomate', 'Zanahoria'))
        for name in ('Banano', 'Tomate', 'Zanahoria'):
            alerts.set_min_stock(biz.id, rows[name].id, '5')
        _lot(biz, rows['Banano'], 2)
        _sale(biz, rows['Banano'], '3.000')    # stock −1 → OUT
        _lot(biz, rows['Tomate'], 8)
        _sale(biz, rows['Tomate'], '4.500')    # stock 3.5, vel 0.64 → ~5.5 días
        _lot(biz, rows['Zanahoria'], 8)
        _sale(biz, rows['Zanahoria'], '5.000')  # stock 3, vel 0.71 → ~4.2 días
        data = alerts.list_alerts(biz.id)
        names = [a['name'] for a in data['alerts']]
        # out primero; entre lows, el que se agota antes (4.2 < 5.5)
        assert names == ['Banano', 'Zanahoria', 'Tomate']
        assert data['alerts'][0]['severity'] == 'out'
        assert data['alerts'][1]['days_left'] == '4.2'

    def test_inactive_product_no_alert(self, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        _lot(biz, rows['Tomate'], 1)
        alerts.set_min_stock(biz.id, rows['Tomate'].id, '5')
        rows['Tomate'].is_active = False
        db.session.commit()
        assert alerts.list_alerts(biz.id)['count'] == 0

    def test_negative_stock_is_out(self, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        _lot(biz, rows['Tomate'], 1)
        _sale(biz, rows['Tomate'], '3.000')  # stock −2
        alerts.set_min_stock(biz.id, rows['Tomate'].id, '5')
        alert = alerts.list_alerts(biz.id)['alerts'][0]
        assert alert['severity'] == 'out'

    def test_unit_plural_in_message(self, db, biz):
        rows = _setup(biz, db, ('Banano',))
        # Producto por unidad: umbral 2, stock 2 (de unidades compradas)
        prod = create_product(biz.id, rows['cat'].id, 'Limón', 'unidad', '500')
        inventory_service.register_lot(biz.id, prod.id, '2', '1000')
        alerts.set_min_stock(biz.id, prod.id, '2')
        alert = alerts.list_alerts(biz.id)['alerts'][0]
        assert '2 unidades' in alert['message']


# ═════════════════ API ═════════════════


class TestAlertsAPI:
    def test_alerts_require_api_key(self, client, db, biz):
        res = client.get(f'/api/verduras/businesses/{biz.id}/inventory/alerts')
        assert res.status_code == 401

    def test_alerts_ok(self, client, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        _lot(biz, rows['Tomate'], 2)
        alerts.set_min_stock(biz.id, rows['Tomate'].id, '5')
        res = client.get(
            f'/api/verduras/businesses/{biz.id}/inventory/alerts',
            headers=API_KEY)
        assert res.status_code == 200
        data = res.get_json()['data']
        assert data['count'] == 1
        # lote 2, sin ventas → stock 2 ≤ 5 → low
        assert data['alerts'][0]['severity'] == 'low'

    def test_min_stock_requires_api_key(self, client, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        res = client.post(
            f'/api/verduras/businesses/{biz.id}/inventory/products/'
            f'{rows["Tomate"].id}/min-stock', json={'min_stock': '5'})
        assert res.status_code == 401

    def test_min_stock_set_and_clear(self, client, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        url = (f'/api/verduras/businesses/{biz.id}/inventory/products/'
               f'{rows["Tomate"].id}/min-stock')
        res = client.post(url, headers=API_KEY, json={'min_stock': '5'})
        assert res.get_json()['data']['min_stock'] == '5.000'
        res = client.post(url, headers=API_KEY, json={'min_stock': None})
        assert res.get_json()['data']['min_stock'] is None

    def test_min_stock_foreign_product_404(self, client, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        other = Business.create_direct(vertical='verduras', name='OtroX',
                                       slug=_slug())
        res = client.post(
            f'/api/verduras/businesses/{other.id}/inventory/products/'
            f'{rows["Tomate"].id}/min-stock',
            headers=API_KEY, json={'min_stock': '5'})
        assert res.status_code == 404

    def test_min_stock_validation_400(self, client, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        res = client.post(
            f'/api/verduras/businesses/{biz.id}/inventory/products/'
            f'{rows["Tomate"].id}/min-stock',
            headers=API_KEY, json={'min_stock': 'cero'})
        assert res.status_code == 400


# ═════════════════ POS ═════════════════


class TestPosAlerts:
    def _login(self, client, biz):
        from verduras.services.pos_auth import setup_pos_pin
        setup_pos_pin(biz.id, '4321')
        client.post('/pos/login', data={'slug': biz.slug, 'pin': '4321'})

    def test_pos_data_includes_alerts_map(self, client, db, biz):
        rows = _setup(biz, db, ('Tomate',))
        _lot(biz, rows['Tomate'], 2)
        alerts.set_min_stock(biz.id, rows['Tomate'].id, '5')
        self._login(client, biz)
        res = client.get(f'/pos/{biz.slug}')
        assert res.status_code == 200
        assert b'"alerts"' in res.data
        # Tomate (out) aparece con su id en el mapa
        assert str(rows['Tomate'].id).encode() in res.data
