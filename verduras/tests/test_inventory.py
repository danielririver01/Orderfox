"""
Tests de inventario por lotes y merma (Semana 3).

Cobertura:
- Lotes: costo unitario derivado (jamás almacenado), validaciones.
- Costo promedio PONDERADO por cantidad (no promedio simple de lotes).
- Stock derivado integrado con las ventas reales de Semana 2:
  compras − ventas − merma, valor del stock en COP, canceladas fuera.
- Merma: pérdida COP congelada (snapshot contable), costo manual sin
  lotes, rechazo sin base de costo.
- Reporte: agregación por producto, % de pérdida y % sobre compras.
- API: auth x-api-key en todas las rutas (dato privado del negocio).
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models import Business
from verduras.models_inventory import VerdurasLot
from verduras.services.catalog import create_category, create_product
from verduras.services.inventory import (
    VerdurasNotFoundError,
    VerdurasValidationError,
    average_unit_cost,
    get_stock,
    list_merma,
    list_stock,
    merma_report,
    register_lot,
    register_merma,
)
from verduras.services.sales import create_sale

API_KEY = 'test-service-api-key'
AUTH = {'x-api-key': API_KEY}


def _slug():
    _slug.n = getattr(_slug, 'n', 0) + 1
    return f'inv-{_slug.n}'


@pytest.fixture()
def biz(db) -> Business:
    return Business.create_direct(
        vertical='verduras', name='Verduras La Central', slug=_slug())


@pytest.fixture()
def products(db, biz):
    cat = create_category(biz.id, 'Hortalizas')
    tomate = create_product(biz.id, cat.id, 'Tomate', 'kg', '3200.00')
    cat2 = create_category(biz.id, 'Frutas')
    banano = create_product(biz.id, cat2.id, 'Banano', 'unidad', '500.00')
    return SimpleNamespace(tomate=tomate, banano=banano)


# ═════════════════ Lotes ═════════════════


class TestLots:
    def test_unit_cost_is_derived_never_stored(self, db, biz, products):
        lot = register_lot(biz.id, products.tomate.id, '50', '90000')
        assert lot.quantity == Decimal('50.000')
        assert lot.total_cost == Decimal('90000.00')
        assert lot.unit_cost == Decimal('1800.00')  # 90000 / 50
        # En DB solo viven quantity y total_cost:
        raw = db.session.get(VerdurasLot, lot.id)
        assert raw.total_cost == Decimal('90000.00')

    def test_lot_fractional_quantity(self, db, biz, products):
        lot = register_lot(biz.id, products.tomate.id, '12.5', '25000')
        assert lot.unit_cost == Decimal('2000.00')

    def test_lot_foreign_product_rejected(self, db, biz, products):
        other = Business.create_direct(vertical='verduras',
                                       name='Otro', slug=_slug())
        with pytest.raises(VerdurasNotFoundError):
            register_lot(other.id, products.tomate.id, '10', '10000')

    def test_lot_invalid_inputs(self, db, biz, products):
        with pytest.raises(VerdurasValidationError, match='mayor a 0'):
            register_lot(biz.id, products.tomate.id, '0', '10000')
        with pytest.raises(VerdurasValidationError, match='gramo'):
            register_lot(biz.id, products.tomate.id, '0.0004', '10000')
        with pytest.raises(VerdurasValidationError, match='costo'):
            register_lot(biz.id, products.tomate.id, '10', '-5')
        with pytest.raises(VerdurasValidationError, match='inválida'):
            register_lot(biz.id, products.tomate.id, 'diez', '10000')

    def test_lot_with_explicit_date(self, db, biz, products):
        five_days_ago = (datetime.now(timezone.utc)
                         - timedelta(days=5)).isoformat()
        lot = register_lot(biz.id, products.tomate.id, '30', '45000',
                           purchased_at=five_days_ago)
        assert lot.purchased_at.date() < datetime.now(timezone.utc).date()


# ═════════════════ Costo promedio ponderado ═════════════════


class TestAverageCost:
    def test_weighted_by_quantity_not_simple(self, db, biz, products):
        """30kg a $1.500 + 20kg a $2.500 → 1.900 (el simple daría 2.000)."""
        register_lot(biz.id, products.tomate.id, '30', '45000')
        register_lot(biz.id, products.tomate.id, '20', '50000')
        assert average_unit_cost(biz.id, products.tomate.id) \
            == Decimal('1900.00')

    def test_no_lots_returns_none(self, db, biz, products):
        assert average_unit_cost(biz.id, products.tomate.id) is None

    def test_until_excludes_later_lots(self, db, biz, products):
        register_lot(biz.id, products.tomate.id, '30', '45000',
                     purchased_at=(datetime.now(timezone.utc)
                                   - timedelta(days=5)).isoformat())
        register_lot(biz.id, products.tomate.id, '20', '50000')
        cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        assert average_unit_cost(biz.id, products.tomate.id, until=cutoff) \
            == Decimal('1500.00')


# ═════════════════ Stock derivado ═════════════════


class TestStock:
    def test_stock_derives_from_movements(self, db, biz, products):
        """Ciclo completo: compro 50kg, vendo 5.5kg, pierdo 2kg → 42.500."""
        register_lot(biz.id, products.tomate.id, '50', '90000')
        create_sale(biz.id, [
            {'product_id': products.tomate.id, 'quantity': '5.500'}])
        register_merma(biz.id, products.tomate.id, '2', reason='danado')

        stock = get_stock(biz.id, products.tomate.id)
        assert stock['purchased'] == '50.000'
        assert stock['sold'] == '5.500'
        assert stock['merma'] == '2.000'
        assert stock['stock'] == '42.500'

    def test_stock_value_uses_weighted_cost(self, db, biz, products):
        register_lot(biz.id, products.tomate.id, '50', '90000')  # 1800/kg
        stock = get_stock(biz.id, products.tomate.id)
        assert stock['avg_unit_cost'] == '1800.00'
        assert stock['stock_value'] == '90000.00'  # 50kg × 1800

    def test_stock_negative_is_informative(self, db, biz, products):
        """Vender más de lo comprado NO se esconde: stock negativo visible."""
        register_lot(biz.id, products.tomate.id, '10', '18000')
        create_sale(biz.id, [
            {'product_id': products.tomate.id, 'quantity': '12'}])
        assert get_stock(biz.id, products.tomate.id)['stock'] == '-2.000'

    def test_cancelled_sales_do_not_reduce_stock(self, db, biz, products):
        register_lot(biz.id, products.tomate.id, '10', '18000')
        sale, _ = create_sale(biz.id, [
            {'product_id': products.tomate.id, 'quantity': '3'}])
        from verduras.services.sales import mark_cancelled
        mark_cancelled(biz.id, sale.id)
        assert get_stock(biz.id, products.tomate.id)['stock'] == '10.000'

    def test_no_lots_stock_value_none(self, db, biz, products):
        create_sale(biz.id, [
            {'product_id': products.tomate.id, 'quantity': '1'}])
        stock = get_stock(biz.id, products.tomate.id)
        assert stock['sold'] == '1.000'
        assert stock['avg_unit_cost'] is None
        assert stock['stock_value'] is None

    def test_foreign_product_is_not_found(self, db, biz, products):
        other = Business.create_direct(vertical='verduras',
                                       name='Otro', slug=_slug())
        with pytest.raises(VerdurasNotFoundError):
            get_stock(other.id, products.tomate.id)

    def test_list_stock_only_active(self, db, biz, products):
        register_lot(biz.id, products.tomate.id, '10', '10000')
        products.banano.is_active = False
        db.session.commit()
        rows = list_stock(biz.id)
        assert [r['name'] for r in rows] == ['Tomate']


# ═════════════════ Merma ═════════════════


class TestMerma:
    def test_loss_frozen_with_weighted_cost(self, db, biz, products):
        register_lot(biz.id, products.tomate.id, '50', '90000')  # 1800/kg
        merma = register_merma(biz.id, products.tomate.id, '2.5',
                               reason='danado')
        assert merma.cost_loss == Decimal('4500.00')  # 2.5 × 1800
        assert merma.reason == 'danado'

    def test_manual_cost_without_lots(self, db, biz, products):
        """Sin lotes, el verdulero pasa el costo que sabe."""
        merma = register_merma(biz.id, products.banano.id, '3',
                               reason='golpeado', unit_cost='400')
        assert merma.cost_loss == Decimal('1200.00')

    def test_without_lots_or_manual_rejected(self, db, biz, products):
        with pytest.raises(VerdurasValidationError, match='lotes'):
            register_merma(biz.id, products.tomate.id, '1')

    def test_invalid_reason_rejected(self, db, biz, products):
        with pytest.raises(VerdurasValidationError, match='Motivo'):
            register_merma(biz.id, products.tomate.id, '1', reason='robo')

    def test_snapshot_never_recalculated(self, db, biz, products):
        """La pérdida histórica no se re-escribe cuando llega un lote caro."""
        register_lot(biz.id, products.tomate.id, '10', '10000')  # 1000/kg
        merma = register_merma(biz.id, products.tomate.id, '1')
        assert merma.cost_loss == Decimal('1000.00')

        register_lot(biz.id, products.tomate.id, '10', '20000')  # avg 1500
        db.session.refresh(merma)
        assert merma.cost_loss == Decimal('1000.00')  # intacta

    def test_list_merma_filters_by_date(self, db, biz, products):
        register_lot(biz.id, products.tomate.id, '50', '90000')
        old = register_merma(biz.id, products.tomate.id, '1')
        recent = register_merma(biz.id, products.tomate.id, '2',
                                reason='vencido')
        old.registered_at = datetime.now(timezone.utc) - timedelta(days=7)
        db.session.commit()

        rows = list_merma(
            biz.id,
            day_from=(datetime.now(timezone.utc) - timedelta(days=2)).date()
            .isoformat(),
            day_to=datetime.now(timezone.utc).date().isoformat())
        assert [m.id for m in rows] == [recent.id]


# ═════════════════ Reporte ═════════════════


class TestReport:
    def test_report_aggregates_by_product(self, db, biz, products):
        register_lot(biz.id, products.tomate.id, '50', '90000')   # 1800/kg
        register_lot(biz.id, products.banano.id, '100', '40000')  # 400/un
        register_merma(biz.id, products.tomate.id, '1', reason='danado')
        register_merma(biz.id, products.tomate.id, '0.5', reason='vencido')
        register_merma(biz.id, products.banano.id, '2.5', reason='golpeado')

        today = datetime.now(timezone.utc).date()
        report = merma_report(
            biz.id, (today - timedelta(days=6)).isoformat(), today.isoformat())
        # tomate: 1.5kg × 1800 = 2700 · banano: 2.5un × 400 = 1000
        assert report['total_loss'] == '3700.00'
        top = report['items'][0]
        assert top['name'] == 'Tomate'
        assert top['quantity'] == '1.500'
        assert top['cost_loss'] == '2700.00'
        assert top['pct_of_loss'] == '73.0'  # 2700/3700
        assert report['merma_pct_of_purchases'] == '2.8'  # 3700/130000

    def test_report_no_purchases_pct_none(self, db, biz, products):
        # Lote de hace 10 días: el costo promedio existe, pero la compra
        # NO cae dentro del período del reporte → % sobre compras = None.
        register_lot(biz.id, products.tomate.id, '10', '10000',
                     purchased_at=(datetime.now(timezone.utc)
                                   - timedelta(days=10)).isoformat())
        register_merma(biz.id, products.tomate.id, '1')
        today = datetime.now(timezone.utc).date()
        report = merma_report(
            biz.id, (today - timedelta(days=1)).isoformat(),
            today.isoformat())
        assert report['total_loss'] == '1000.00'
        assert report['purchases_cost'] == '0.00'
        assert report['merma_pct_of_purchases'] is None

    def test_report_period_boundaries(self, db, biz, products):
        register_lot(biz.id, products.tomate.id, '50', '90000')
        old = register_merma(biz.id, products.tomate.id, '1')
        old.registered_at = datetime.now(timezone.utc) - timedelta(days=30)
        db.session.commit()

        today = datetime.now(timezone.utc).date()
        report = merma_report(
            biz.id, (today - timedelta(days=6)).isoformat(), today.isoformat())
        assert report['total_loss'] == '0.00'
        assert report['items'] == []

    def test_report_validates_period(self, db, biz, products):
        today = datetime.now(timezone.utc).date()
        with pytest.raises(VerdurasValidationError, match='requiere'):
            merma_report(biz.id, None, today.isoformat())
        with pytest.raises(VerdurasValidationError, match='anterior'):
            merma_report(biz.id, today.isoformat(),
                         (today - timedelta(days=1)).isoformat())


# ═════════════════ API ═════════════════


class TestInventoryAPI:
    def test_all_routes_require_api_key(self, client, db, biz, products):
        base = f'/api/verduras/businesses/{biz.id}/inventory'
        assert client.get(base).status_code == 401
        assert client.get(f'{base}/{products.tomate.id}').status_code == 401
        assert client.get(f'{base}/lots').status_code == 401
        assert client.post(f'{base}/lots', json={}).status_code == 401
        assert client.get(f'{base}/merma').status_code == 401
        assert client.post(f'{base}/merma', json={}).status_code == 401
        assert client.get(f'{base}/merma/report').status_code == 401

    def test_lot_flow_via_api(self, client, db, biz, products):
        res = client.post(
            f'/api/verduras/businesses/{biz.id}/inventory/lots', headers=AUTH,
            json={'product_id': products.tomate.id,
                  'quantity': '50', 'total_cost': '90000'})
        assert res.status_code == 201
        data = res.get_json()['data']
        assert data['unit_cost'] == '1800.00'

        res = client.get(
            f'/api/verduras/businesses/{biz.id}/inventory/lots', headers=AUTH)
        assert res.status_code == 200
        assert len(res.get_json()['data']['lots']) == 1

    def test_stock_and_merma_flow_via_api(self, client, db, biz, products):
        base = f'/api/verduras/businesses/{biz.id}/inventory'
        client.post(f'{base}/lots', headers=AUTH,
                    json={'product_id': products.tomate.id,
                          'quantity': '50', 'total_cost': '90000'})
        res = client.get(base, headers=AUTH)
        rows = res.get_json()['data']['stock']
        stock = next(s for s in rows
                     if s['product_id'] == products.tomate.id)
        assert stock['stock'] == '50.000'

        res = client.post(f'{base}/merma', headers=AUTH,
                          json={'product_id': products.tomate.id,
                                'quantity': '2', 'reason': 'danado'})
        assert res.status_code == 201
        assert res.get_json()['data']['cost_loss'] == '3600.00'

        res = client.get(f'{base}/{products.tomate.id}', headers=AUTH)
        assert res.get_json()['data']['stock'] == '48.000'

    def test_report_via_api(self, client, db, biz, products):
        base = f'/api/verduras/businesses/{biz.id}/inventory'
        client.post(f'{base}/lots', headers=AUTH,
                    json={'product_id': products.tomate.id,
                          'quantity': '50', 'total_cost': '90000'})
        client.post(f'{base}/merma', headers=AUTH,
                    json={'product_id': products.tomate.id,
                          'quantity': '2', 'reason': 'vencido'})
        today = datetime.now(timezone.utc).date()
        res = client.get(
            f'{base}/merma/report?date_from='
            f'{(today - timedelta(days=6)).isoformat()}&date_to='
            f'{today.isoformat()}', headers=AUTH)
        assert res.status_code == 200
        data = res.get_json()['data']
        assert data['total_loss'] == '3600.00'
        assert data['items'][0]['name'] == 'Tomate'

    def test_report_missing_params_400(self, client, db, biz):
        res = client.get(
            f'/api/verduras/businesses/{biz.id}/inventory/merma/report',
            headers=AUTH)
        assert res.status_code == 400

    def test_foreign_product_404_via_api(self, client, db, biz, products):
        other = Business.create_direct(vertical='verduras',
                                       name='Otro', slug=_slug())
        res = client.get(
            f'/api/verduras/businesses/{other.id}/inventory/'
            f'{products.tomate.id}', headers=AUTH)
        assert res.status_code == 404
