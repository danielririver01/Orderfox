"""
Tests del catálogo Verduras (Semana 1).

Cobertura por capa:
- Servicio: unidades, precios Decimal, unicidad, historial (baseline + append),
  anti-IDOR y categorías duplicadas.
- API: status codes, auth x-api-key en mutaciones, scoping por business y
  payload JSON.
"""
import pytest

from app.models import Business, Restaurant
from verduras.services.catalog import (
    VerdurasNotFoundError,
    VerdurasValidationError,
    create_category,
    create_product,
    list_categories,
    update_price,
)

API_KEY = 'test-service-api-key'
AUTH = {'x-api-key': API_KEY}


def _slug():
    _slug.n = getattr(_slug, 'n', 0) + 1
    return f'verduras-{_slug.n}'


@pytest.fixture()
def biz(db) -> Business:
    """Business del vertical verduras (banda >= 1_000_000)."""
    return Business.create_direct(
        vertical='verduras', name='Verduras La Central', slug=_slug())


@pytest.fixture()
def category(db, biz):
    return create_category(biz.id, 'Hortalizas')


def _product(db, biz, category, name='Tomate', unit='kg', price='3200.00'):
    return create_product(biz.id, category.id, name, unit, price)


# ═════════════════ Servicio ═════════════════


class TestCategoryService:
    def test_create_and_list(self, db, biz, category):
        cats = list_categories(biz.id)
        assert [c.name for c in cats] == ['Hortalizas']

    def test_duplicate_rejected(self, db, biz, category):
        with pytest.raises(VerdurasValidationError, match='ya existe'):
            create_category(biz.id, 'Hortalizas')

    def test_same_name_other_business_allowed(self, db, biz, category):
        other = Business.create_direct(
            vertical='verduras', name='Verduras El Progreso', slug=_slug())
        cat2 = create_category(other.id, 'Hortalizas')
        assert cat2.business_id == other.id

    def test_blank_name_rejected(self, db, biz):
        with pytest.raises(VerdurasValidationError):
            create_category(biz.id, '   ')


class TestProductService:
    def test_create_with_baseline_history(self, db, biz, category):
        p = _product(db, biz, category)
        assert p.unit == 'kg'
        assert str(p.current_price) == '3200.00'
        assert len(p.price_history) == 1
        assert str(p.price_history[0].price) == '3200.00'
        assert p.price_history[0].source == 'manual'

    def test_units_valid(self, db, biz, category):
        for unit, expected in (('kg', 'kg'), ('LB', 'lb'),
                               ('Unidad', 'unidad')):
            p = _product(db, biz, category, name=f'P-{unit}', unit=unit)
            assert p.unit == expected

    def test_unit_invalid(self, db, biz, category):
        with pytest.raises(VerdurasValidationError, match='Unidad inválida'):
            _product(db, biz, category, name='Oro', unit='gramo')

    def test_price_formats(self, db, biz, category):
        p = _product(db, biz, category, name='Cebolla', price='3200.555')
        assert str(p.current_price) == '3200.56'  # ROUND_HALF_UP

    def test_price_zero_or_negative_rejected(self, db, biz, category):
        for bad in ('0', '-5', '0.00'):
            with pytest.raises(VerdurasValidationError):
                _product(db, biz, category, name=f'X-{bad}', price=bad)

    def test_price_garbage_rejected(self, db, biz, category):
        with pytest.raises(VerdurasValidationError):
            _product(db, biz, category, name='Yuca', price='caro')

    def test_duplicate_name_rejected(self, db, biz, category):
        _product(db, biz, category, name='Tomate')
        with pytest.raises(VerdurasValidationError, match='ya existe'):
            _product(db, biz, category, name='Tomate')

    def test_category_of_other_business_rejected(self, db, biz, category):
        other = Business.create_direct(
            vertical='verduras', name='Otra', slug=_slug())
        with pytest.raises(VerdurasNotFoundError):
            _product(db, other, category)  # categoría ajena


class TestPriceHistory:
    def test_update_price_appends_history(self, db, biz, category):
        p = _product(db, biz, category)
        updated = update_price(biz.id, p.id, '3500')
        assert str(updated.current_price) == '3500.00'
        assert len(updated.price_history) == 2
        newest, baseline = updated.price_history  # orden DESC: el vigente primero
        assert str(baseline.price) == '3200.00'
        assert str(newest.price) == '3500.00'

    def test_same_price_rejected(self, db, biz, category):
        p = _product(db, biz, category)
        with pytest.raises(VerdurasValidationError, match='no hay cambio'):
            update_price(biz.id, p.id, '3200.00')

    def test_history_ordering_desc(self, db, biz, category):
        p = _product(db, biz, category)
        update_price(biz.id, p.id, '3500')
        update_price(biz.id, p.id, '3700')
        prices = [str(h.price) for h in p.price_history]
        assert prices == ['3700.00', '3500.00', '3200.00']

    def test_update_foreign_product_is_not_found(self, db, biz, category):
        p = _product(db, biz, category)
        other = Business.create_direct(
            vertical='verduras', name='Otro', slug=_slug())
        with pytest.raises(VerdurasNotFoundError):
            update_price(other.id, p.id, '9999')


# ═════════════════ API ═════════════════


class TestCatalogAPI:
    def test_create_category_requires_api_key(self, client, db, biz):
        res = client.post(f'/api/verduras/businesses/{biz.id}/categories',
                          json={'name': 'Frutas'})
        assert res.status_code == 401
        assert res.get_json()['error_code'] == 'unauthorized'

    def test_category_flow(self, client, db, biz):
        res = client.post(f'/api/verduras/businesses/{biz.id}/categories',
                          json={'name': 'Frutas'}, headers=AUTH)
        assert res.status_code == 201

        res = client.get(f'/api/verduras/businesses/{biz.id}/categories')
        assert res.status_code == 200
        assert [c['name'] for c in res.get_json()['data']['categories']] == ['Frutas']

    def test_product_flow_and_price_change(self, client, db, biz):
        cat_id = client.post(f'/api/verduras/businesses/{biz.id}/categories',
                             json={'name': 'Hortalizas'}, headers=AUTH
                             ).get_json()['data']['id']

        res = client.post(f'/api/verduras/businesses/{biz.id}/products',
                          json={'category_id': cat_id, 'name': 'Tomate',
                                'unit': 'kg', 'price': '3200.00'},
                          headers=AUTH)
        assert res.status_code == 201
        product_id = res.get_json()['data']['id']

        # Cambio de precio diario
        res = client.post(
            f'/api/verduras/businesses/{biz.id}/products/{product_id}/price',
            json={'price': '3500', 'note': 'subió en la central'},
            headers=AUTH)
        assert res.status_code == 200
        data = res.get_json()['data']
        assert data['current_price'] == '3500.00'
        assert len(data['price_history']) == 2

        # GET detalle incluye historial
        res = client.get(
            f'/api/verduras/businesses/{biz.id}/products/{product_id}')
        assert res.get_json()['data']['price_history'][0]['price'] == '3500.00'

    def test_mutation_without_key_401(self, client, db, biz, category):
        res = client.post(f'/api/verduras/businesses/{biz.id}/products',
                          json={'category_id': category.id, 'name': 'Pera',
                                'unit': 'kg', 'price': '1000'})
        assert res.status_code == 401

    def test_reads_public(self, client, db, biz, category):
        _product(db, biz, category)
        res = client.get(f'/api/verduras/businesses/{biz.id}/products')
        assert res.status_code == 200
        assert res.get_json()['data']['products'][0]['name'] == 'Tomate'

    def test_restaurant_mirror_is_409(self, client, db):
        r = Restaurant(name='Rest', slug=_slug(), whatsapp_phone='+573001112233')
        db.session.add(r)
        db.session.flush()
        res = client.get(f'/api/verduras/businesses/{r.id}/products')
        assert res.status_code == 409

    def test_unknown_business_is_404(self, client, db):
        # db requerido: garantiza create_all para la consulta de esta función.
        res = client.get('/api/verduras/businesses/987654321/products')
        assert res.status_code == 404
