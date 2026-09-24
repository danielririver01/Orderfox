"""
Inventario y Precios v1: tabla + precio inline + crear (Tier GUARDIAN).

Cubre (Fase 1+2, sin roles — la sesión del POS autoriza):
- Sin sesión → login; slug ajeno → 401.
- Tabla con stock/precio/estado + KPIs reales.
- Precio inline persiste (con historial) y rechaza inválido.
- Crear producto (con categoría nueva al vuelo) y duplicado → 400.
"""
from types import SimpleNamespace

import pytest

from app.models import Business
from verduras.services.catalog import create_category, create_product

API_KEY = 'test-service-api-key'


def _slug():
    _slug.n = getattr(_slug, 'n', 0) + 1
    return f'inv-{_slug.n}'


@pytest.fixture()
def biz(db) -> Business:
    return Business.create_direct(vertical='verduras',
                                  name='Verduras Inv', slug=_slug())


@pytest.fixture()
def catalog_row(db, biz):
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


class TestInventoryView:
    def test_requires_session(self, client, db, biz, catalog_row):
        res = client.get(f'/pos/{biz.slug}/inventario',
                         follow_redirects=False)
        assert res.status_code == 302
        assert '/pos/login' in res.headers['Location']

    def test_foreign_slug_rejected(self, client, db, biz, catalog_row):
        other = Business.create_direct(vertical='verduras',
                                       name='Otro', slug=_slug())
        _set_pin(other)
        _login_client(client, biz)
        res = client.post(f'/pos/{other.slug}/inventario/precio',
                          json={'product_id': 1, 'price': '1000'})
        assert res.status_code == 401

    def test_table_with_kpis(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        res = client.get(f'/pos/{biz.slug}/inventario')
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert 'Tomate' in html
        assert 'Valor inventario' in html
        assert 'inv-price' in html


class TestInventoryPrice:
    def test_price_update_persists(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/inventario/precio', json={
            'product_id': catalog_row.tomate.id, 'price': '3500'})
        assert res.status_code == 200
        assert res.get_json()['data']['price'] == '3500.00'
        db.session.expire_all()
        assert str(catalog_row.tomate.current_price) == '3500.00'

    def test_price_invalid_400(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/inventario/precio', json={
            'product_id': catalog_row.tomate.id, 'price': 'abc'})
        assert res.status_code == 400


class TestInventoryCreate:
    def test_create_with_new_category(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/inventario/producto', json={
            'name': 'Papa', 'unit': 'kg', 'price': '1800',
            'category_name': 'Tubérculos'})
        assert res.status_code == 201
        data = res.get_json()['data']
        assert data['name'] == 'Papa'
        res = client.get(f'/pos/{biz.slug}/inventario')
        assert 'Papa' in res.get_data(as_text=True)

    def test_create_duplicate_400(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/inventario/producto', json={
            'name': 'Tomate', 'unit': 'kg', 'price': '1800',
            'category_id': catalog_row.cat.id})
        assert res.status_code == 400


class TestInventoryEdit:
    def test_edit_name_category_active(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        cat2 = create_category(biz.id, 'Frutas')
        db.session.commit()
        res = client.post(f'/pos/{biz.slug}/inventario/editar', json={
            'product_id': catalog_row.tomate.id, 'name': 'Tomate Cherry',
            'category_id': cat2.id, 'is_active': False})
        assert res.status_code == 200
        data = res.get_json()['data']
        assert data['name'] == 'Tomate Cherry'
        assert data['category_id'] == cat2.id
        assert data['is_active'] is False
        # La unidad NO se toca por esta vía aunque se envíe.
        assert data['unit'] == 'kg'

    def test_edit_duplicate_name_400(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        create_product(biz.id, catalog_row.cat.id, 'Papa', 'kg', '1800')
        res = client.post(f'/pos/{biz.slug}/inventario/editar', json={
            'product_id': catalog_row.tomate.id, 'name': 'Papa'})
        assert res.status_code == 400

    def test_edit_foreign_product_404(self, client, db, biz, catalog_row):
        other = Business.create_direct(vertical='verduras',
                                       name='Otro', slug=_slug())
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/inventario/editar', json={
            'product_id': 999999, 'name': 'X'})
        assert res.status_code == 404


class TestInventoryMovements:
    def test_lot_raises_stock(self, client, db, biz, catalog_row):
        from verduras.services.inventory import get_stock
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/inventario/lote', json={
            'product_id': catalog_row.tomate.id, 'quantity': '10',
            'total_cost': '30000'})
        assert res.status_code == 201
        db.session.expire_all()
        assert get_stock(biz.id, catalog_row.tomate.id)['stock'] == '10.000'

    def test_merma_lowers_stock(self, client, db, biz, catalog_row):
        from verduras.services.inventory import get_stock, register_lot
        register_lot(biz.id, catalog_row.tomate.id, '10', '30000')
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/inventario/merma', json={
            'product_id': catalog_row.tomate.id, 'quantity': '2',
            'reason': 'danado'})
        assert res.status_code == 201
        db.session.expire_all()
        assert get_stock(biz.id, catalog_row.tomate.id)['stock'] == '8.000'

    def test_lot_invalid_400(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/inventario/lote', json={
            'product_id': catalog_row.tomate.id, 'quantity': 'cero',
            'total_cost': '30000'})
        assert res.status_code == 400

    def test_merma_foreign_product_404(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/inventario/merma', json={
            'product_id': 999999, 'quantity': '1', 'reason': 'danado'})
        assert res.status_code == 404


class TestInventoryDelete:
    def test_delete_deactivates_keeps_history(self, client, db, biz,
                                              catalog_row):
        from verduras.services.sales import create_sale
        create_sale(biz.id, [{'product_id': catalog_row.tomate.id,
                              'quantity': '1'}])
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/inventario/eliminar',
                          json={'product_id': catalog_row.tomate.id})
        assert res.status_code == 200
        assert res.get_json()['data']['is_active'] is False
        # Sigue en la tabla con badge Inactivo (ya no se esconde), pero
        # fuera del POS. La venta vieja sigue intacta.
        html = client.get(f'/pos/{biz.slug}/inventario').get_data(
            as_text=True)
        assert 'inv-row' in html
        assert 'Inactivo' in html
        from verduras.models_sales import VerdurasSale
        assert VerdurasSale.query.filter_by(business_id=biz.id).count() == 1

    def test_delete_foreign_404(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/inventario/eliminar',
                          json={'product_id': 999999})
        assert res.status_code == 404


class TestInventoryRecreate:
    def test_recreate_after_delete_reactivates(self, client, db, biz,
                                              catalog_row):
        _login_client(client, biz)
        tid = catalog_row.tomate.id
        assert client.post(f'/pos/{biz.slug}/inventario/eliminar',
                           json={'product_id': tid}).status_code == 200
        res = client.post(f'/pos/{biz.slug}/inventario/producto', json={
            'name': 'Tomate', 'unit': 'kg', 'price': '3500',
            'category_id': catalog_row.cat.id})
        assert res.status_code == 201
        assert res.get_json()['data']['product_id'] == tid
        html = client.get(f'/pos/{biz.slug}/inventario').get_data(
            as_text=True)
        assert 'inv-row' in html  # vuelve a la tabla

    def test_recreate_other_unit_with_history_400(self, client, db, biz,
                                                 catalog_row):
        from verduras.services.inventory import register_lot
        register_lot(biz.id, catalog_row.tomate.id, '5', '15000')
        _login_client(client, biz)
        client.post(f'/pos/{biz.slug}/inventario/eliminar',
                    json={'product_id': catalog_row.tomate.id})
        res = client.post(f'/pos/{biz.slug}/inventario/producto', json={
            'name': 'Tomate', 'unit': 'unidad', 'price': '500',
            'category_id': catalog_row.cat.id})
        assert res.status_code == 400


class TestInventoryCategories:
    def test_rename_ok(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/inventario/categoria/renombrar',
                          json={'category_id': catalog_row.cat.id,
                                'name': 'Verduras Finas'})
        assert res.status_code == 200
        assert res.get_json()['data']['name'] == 'Verduras Finas'

    def test_delete_empty_ok(self, client, db, biz, catalog_row):
        from verduras.services.catalog import create_category
        vacia = create_category(biz.id, 'Vacía')
        db.session.commit()
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/inventario/categoria/eliminar',
                          json={'category_id': vacia.id})
        assert res.status_code == 200

    def test_delete_with_products_400(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/inventario/categoria/eliminar',
                          json={'category_id': catalog_row.cat.id})
        assert res.status_code == 400
        assert 'producto' in res.get_json()['error'].lower()


class TestInventoryAjuste:
    def test_ajuste_firmado_baja_stock(self, client, db, biz, catalog_row):
        from verduras.models_inventory import VerdurasAjuste
        from verduras.services.inventory import get_stock, register_lot
        register_lot(biz.id, catalog_row.tomate.id, '10', '30000')
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/inventario/ajuste', json={
            'product_id': catalog_row.tomate.id, 'counted': '7',
            'motivo': 'conteo'})
        assert res.status_code == 201
        data = res.get_json()['data']
        assert data['stock_before'] == '10.000'
        assert data['counted'] == '7.000'
        assert data['delta'] == '-3.000'
        assert data['motivo'] == 'conteo'
        db.session.expire_all()
        assert get_stock(biz.id, catalog_row.tomate.id)['stock'] == '7.000'
        assert VerdurasAjuste.query.filter_by(
            business_id=biz.id).count() == 1

    def test_ajuste_positivo_sube_stock(self, client, db, biz, catalog_row):
        from verduras.services.inventory import get_stock, register_lot
        register_lot(biz.id, catalog_row.tomate.id, '10', '30000')
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/inventario/ajuste', json={
            'product_id': catalog_row.tomate.id, 'counted': '12'})
        assert res.status_code == 201
        assert res.get_json()['data']['delta'] == '2.000'
        db.session.expire_all()
        assert get_stock(biz.id, catalog_row.tomate.id)['stock'] == '12.000'

    def test_ajuste_delta_cero_400(self, client, db, biz, catalog_row):
        from verduras.services.inventory import register_lot
        register_lot(biz.id, catalog_row.tomate.id, '10', '30000')
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/inventario/ajuste', json={
            'product_id': catalog_row.tomate.id, 'counted': '10'})
        assert res.status_code == 400

    def test_ajuste_foreign_404(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/inventario/ajuste', json={
            'product_id': 999999, 'counted': '5'})
        assert res.status_code == 404


class TestInventoryReactivate:
    def test_create_reactivated_flag(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        tid = catalog_row.tomate.id
        client.post(f'/pos/{biz.slug}/inventario/eliminar',
                    json={'product_id': tid})
        res = client.post(f'/pos/{biz.slug}/inventario/producto', json={
            'name': 'Tomate', 'unit': 'kg', 'price': '3500',
            'category_id': catalog_row.cat.id})
        assert res.status_code == 201
        data = res.get_json()['data']
        assert data['product_id'] == tid
        assert data['reactivated'] is True


class TestInventoryMoveOnDelete:
    def test_delete_moves_products(self, client, db, biz, catalog_row):
        from verduras.services.catalog import create_category
        dest = create_category(biz.id, 'Destino')
        db.session.commit()
        _login_client(client, biz)
        res = client.post(
            f'/pos/{biz.slug}/inventario/categoria/eliminar',
            json={'category_id': catalog_row.cat.id,
                  'move_to_category_id': dest.id})
        assert res.status_code == 200
        assert res.get_json()['data'] == {'deleted': True, 'moved': 1}
        db.session.expire_all()
        assert catalog_row.tomate.category_id == dest.id

    def test_delete_invalid_target_404(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        res = client.post(
            f'/pos/{biz.slug}/inventario/categoria/eliminar',
            json={'category_id': catalog_row.cat.id,
                  'move_to_category_id': 999999})
        assert res.status_code == 404


class TestInventoryActivity:
    def _movimiento(self, db, biz, catalog_row):
        from verduras.services.inventory import (
            register_ajuste, register_lot, register_merma)
        from verduras.services.sales import create_sale
        register_lot(biz.id, catalog_row.tomate.id, '10', '30000')
        create_sale(biz.id, [{'product_id': catalog_row.tomate.id,
                              'quantity': '1'}])
        register_merma(biz.id, catalog_row.tomate.id, '1')
        register_ajuste(biz.id, catalog_row.tomate.id, '9')
        db.session.expire_all()

    def test_feed_speaks_counter_language(self, client, db, biz,
                                          catalog_row):
        self._movimiento(db, biz, catalog_row)
        _login_client(client, biz)
        html = client.get(f'/pos/{biz.slug}/inventario').get_data(
            as_text=True)
        for text in ('Venta de Tomate', 'Compra de Tomate',
                     'Merma de Tomate', 'Ajuste de Tomate'):
            assert text in html
        # El código técnico vive silencioso (tooltip), no pintado.
        assert 'title="V-' in html
        assert '>V-20' not in html

    def test_feed_human_time(self, client, db, biz, catalog_row):
        self._movimiento(db, biz, catalog_row)
        _login_client(client, biz)
        html = client.get(f'/pos/{biz.slug}/inventario').get_data(
            as_text=True)
        assert 'Hoy, ' in html

    def test_feed_empty_honest(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        html = client.get(f'/pos/{biz.slug}/inventario').get_data(
            as_text=True)
        assert 'Aún no hay movimientos registrados' in html

    def test_feed_service_orders_and_signs(self, db, biz, catalog_row):
        from verduras.services.inventory import activity_feed
        self._movimiento(db, biz, catalog_row)
        feed = activity_feed(biz.id)
        kinds = [e['kind'] for e in feed]
        assert set(kinds) == {'venta', 'compra', 'merma', 'ajuste'}
        assert all(e['icon'] and e['when'] and e['ref'] for e in feed)


# ═════════════════ Paneles Copilot lectura + mínimo (Fase 3) ═════════


def _with_movement(db, biz, catalog_row):
    """Lote + venta para que haya actividad, margen y recomendación."""
    from verduras.services.inventory import register_lot
    from verduras.services.sales import create_sale
    register_lot(biz.id, catalog_row.tomate.id, '5', '3000.00')
    create_sale(biz.id, [{'product_id': catalog_row.tomate.id,
                          'quantity': '4'}])
    db.session.expire_all()


class TestInventoryPanels:
    def test_panels_with_data(self, client, db, biz, catalog_row):
        _with_movement(db, biz, catalog_row)
        _login_client(client, biz)
        res = client.get(f'/pos/{biz.slug}/inventario')
        html = res.get_data(as_text=True)
        assert res.status_code == 200
        assert 'Actividad reciente' in html
        assert 'Salud del Margen' in html
        assert 'Reponer' in html

    def test_panels_hidden_without_data(self, client, db, biz,
                                        catalog_row):
        _login_client(client, biz)
        res = client.get(f'/pos/{biz.slug}/inventario')
        html = res.get_data(as_text=True)
        assert 'Aún no hay movimientos registrados' in html
        assert 'Salud del Margen' not in html
        assert 'Reponer' not in html

    def test_minimum_update_persists(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/inventario/minimo', json={
            'product_id': catalog_row.tomate.id, 'min_stock': '5'})
        assert res.status_code == 200
        assert res.get_json()['data']['min_stock'] == '5.000'

    def test_minimum_invalid_400(self, client, db, biz, catalog_row):
        _login_client(client, biz)
        res = client.post(f'/pos/{biz.slug}/inventario/minimo', json={
            'product_id': catalog_row.tomate.id, 'min_stock': 'cero'})
        assert res.status_code == 400
