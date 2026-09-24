"""
Tests de ventas por peso + pedidos WhatsApp (Semana 2).

Cobertura por capa:
- Servicio: precio/qty Decimal, snapshot, idempotencia (replay + carrera),
  numeración atómica, gates de delivery, transiciones, rate limiter,
  WhatsApp link y validación de teléfono.
- API: auth del POS, checkout público, scoping anti-IDOR y guards.
"""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Business
from verduras.models_sales import VerdurasSale
from verduras.services import sales as sales_svc
from verduras.services.catalog import create_category, create_product
from verduras.services.sales import (
    SaleRateLimiter,
    VerdurasNotFoundError,
    VerdurasValidationError,
    build_whatsapp_link,
    check_public_guards,
    create_sale,
    get_settings,
    mark_cancelled,
    mark_completed,
    update_settings,
)

API_KEY = 'test-service-api-key'
AUTH = {'x-api-key': API_KEY}


def _slug():
    _slug.n = getattr(_slug, 'n', 0) + 1
    return f'venta-{_slug.n}'


@pytest.fixture()
def biz(db) -> Business:
    return Business.create_direct(
        vertical='verduras', name='Verduras La Central', slug=_slug())


@pytest.fixture()
def products(db, biz):
    """Catálogo mínimo: dos por peso y uno por unidad."""
    cat = create_category(biz.id, 'Hortalizas')
    tomate = create_product(biz.id, cat.id, 'Tomate', 'kg', '3200.00')
    cebolla = create_product(biz.id, cat.id, 'Cebolla', 'kg', '2800.50')
    cat2 = create_category(biz.id, 'Frutas')
    banano = create_product(biz.id, cat2.id, 'Banano', 'unidad', '500.00')
    return SimpleNamespace(tomate=tomate, cebolla=cebolla, banano=banano)


def _sale(biz, products, **kw):
    """Venta por defecto: 500g tomate + 2 banano."""
    items = kw.pop('items', None) or [
        {'product_id': products.tomate.id, 'quantity': '0.500'},
        {'product_id': products.banano.id, 'quantity': '2'},
    ]
    return create_sale(biz.id, items, **kw)


# ═════════════════ Servicio: creación ═════════════════


class TestCreateSale:
    def test_weighted_sale_math(self, db, biz, products):
        sale, created = _sale(biz, products)
        assert created is True
        # 0.500 kg × 3200 = 1600 + 2 × 500 = 2600
        assert sale.total == Decimal('2600.00')
        assert len(sale.items) == 2
        first = sale.items[0]
        assert first.product_name == 'Tomate'
        assert first.unit == 'kg'
        assert first.quantity == Decimal('0.500')
        assert first.line_total == Decimal('1600.00')

    def test_price_comes_from_catalog_never_client(self, db, biz, products):
        """El cliente NO puede inyectar precio; se toma del catálogo."""
        sale, _ = _sale(biz, products, items=[
            {'product_id': products.tomate.id, 'quantity': '1',
             'price': '1'},  # intento de manipulación
        ])
        assert sale.total == Decimal('3200.00')

    def test_sale_number_sequence_daily(self, db, biz, products):
        today = datetime.now(timezone.utc).strftime('%Y%m%d')
        s1, _ = _sale(biz, products)
        s2, _ = _sale(biz, products)
        assert s1.sale_number == f'V-{today}-001'
        assert s2.sale_number == f'V-{today}-002'

    def test_counter_starts_at_one_per_business(self, db, biz, products):
        _, _ = _sale(biz, products)  # el contador de biz ya está en 001
        other = Business.create_direct(vertical='verduras',
                                       name='Otro', slug=_slug())
        cat = create_category(other.id, 'Hortalizas')
        prod = create_product(other.id, cat.id, 'Tomate', 'kg', '3200.00')
        sale, _ = create_sale(other.id, [
            {'product_id': prod.id, 'quantity': '1'}])
        assert sale.sale_number.endswith('-001')

    def test_idempotent_replay_returns_original(self, db, biz, products):
        s1, created1 = _sale(biz, products, idempotency_key='abc-123')
        s2, created2 = _sale(biz, products, idempotency_key='abc-123')
        assert created1 and not created2
        assert s1.id == s2.id
        assert VerdurasSale.query.count() == 1

    def test_idempotent_race_returns_winner(self, db, biz, products):
        """Carrera real: el pre-check no ve al ganador (aún no visible), el
        INSERT choca con el unique constraint y el servicio recupera la venta
        ganadora en el except (patrón create_order_idempotent de core)."""
        key = 'race-key'
        winner, _ = _sale(biz, products, idempotency_key=key)

        calls = {'n': 0}
        real_find = sales_svc.find_by_idempotency_key

        def find_like_concurrent(business_id, idem_key):
            calls['n'] += 1
            if calls['n'] == 1:
                return None  # pre-check: el ganador todavía no era visible
            return real_find(business_id, idem_key)  # recovery: ya visible

        conflict = IntegrityError(
            'INSERT INTO verduras_sales ...', None,
            Exception('uq_verduras_sales_business_idem'))
        with patch.object(sales_svc, 'find_by_idempotency_key',
                          side_effect=find_like_concurrent), \
                patch.object(sales_svc.db.session, 'commit',
                             side_effect=conflict):
            loser, created = create_sale(
                biz.id,
                [{'product_id': products.tomate.id, 'quantity': '1'}],
                idempotency_key=key)

        assert created is False
        assert loser.id == winner.id
        assert calls['n'] == 2  # pre-check + recovery

    def test_unknown_product_rejected(self, db, biz, products):
        with pytest.raises(VerdurasNotFoundError):
            _sale(biz, products, items=[
                {'product_id': 987654, 'quantity': '1'}])

    def test_foreign_product_rejected(self, db, biz, products):
        other = Business.create_direct(vertical='verduras',
                                       name='Otro', slug=_slug())
        with pytest.raises(VerdurasNotFoundError):
            create_sale(other.id, [
                {'product_id': products.tomate.id, 'quantity': '1'}])

    def test_empty_items_rejected(self, db, biz, products):
        with pytest.raises(VerdurasValidationError, match='items'):
            create_sale(biz.id, [])

    def test_invalid_sale_type_rejected(self, db, biz, products):
        with pytest.raises(VerdurasValidationError, match='Tipo de venta'):
            _sale(biz, products, sale_type='mayorista')

    def test_fractional_unit_rejected(self, db, biz, products):
        with pytest.raises(VerdurasValidationError, match='entera'):
            _sale(biz, products, items=[
                {'product_id': products.banano.id, 'quantity': '1.5'}])

    def test_gram_precision_ok(self, db, biz, products):
        sale, _ = _sale(biz, products, items=[
            {'product_id': products.tomate.id, 'quantity': '0.001'}])
        assert sale.total == Decimal('3.20')

    def test_sub_gram_rejected(self, db, biz, products):
        with pytest.raises(VerdurasValidationError, match='gramo'):
            _sale(biz, products, items=[
                {'product_id': products.tomate.id, 'quantity': '0.0004'}])

    def test_inactive_product_rejected(self, db, biz, products):
        products.tomate.is_active = False
        db.session.commit()
        with pytest.raises(VerdurasNotFoundError):
            _sale(biz, products, items=[
                {'product_id': products.tomate.id, 'quantity': '1'}])


# ═════════════════ Servicio: delivery gates ═════════════════


class TestDeliveryGates:
    def test_walk_in_ignores_closed(self, db, biz, products):
        update_settings(biz.id, {'is_open': False})
        sale, _ = _sale(biz, products, sale_type='walk_in')
        assert sale.status == 'pending'

    def test_delivery_closed_rejected(self, db, biz, products):
        update_settings(biz.id, {'is_open': False})
        with pytest.raises(VerdurasValidationError, match='cerrado'):
            _sale(biz, products, sale_type='delivery')

    def test_delivery_disabled_rejected(self, db, biz, products):
        update_settings(biz.id, {'delivery_enabled': False})
        with pytest.raises(VerdurasValidationError, match='Domicilios'):
            _sale(biz, products, sale_type='delivery')

    def test_delivery_open_ok(self, db, biz, products):
        update_settings(biz.id, {'is_open': True, 'delivery_enabled': True})
        sale, _ = _sale(biz, products, sale_type='delivery',
                        delivery_address='Calle 5 #3-21')
        assert sale.delivery_address == 'Calle 5 #3-21'


# ═════════════════ Servicio: transiciones ═════════════════


class TestTransitions:
    def test_complete_pending(self, db, biz, products):
        sale, _ = _sale(biz, products)
        done = mark_completed(biz.id, sale.id)
        assert done.status == 'completed'
        assert done.completed_at is not None

    def test_cancel_pending(self, db, biz, products):
        sale, _ = _sale(biz, products)
        cancelled = mark_cancelled(biz.id, sale.id)
        assert cancelled.status == 'cancelled'
        assert cancelled.cancelled_at is not None

    def test_complete_twice_is_idempotent(self, db, biz, products):
        sale, _ = _sale(biz, products)
        assert mark_completed(biz.id, sale.id).status == 'completed'
        assert mark_completed(biz.id, sale.id).status == 'completed'

    def test_cancel_completed_rejected(self, db, biz, products):
        sale, _ = _sale(biz, products)
        mark_completed(biz.id, sale.id)
        with pytest.raises(VerdurasValidationError, match='No se puede'):
            mark_cancelled(biz.id, sale.id)

    def test_cancelled_cannot_reopen(self, db, biz, products):
        sale, _ = _sale(biz, products)
        mark_cancelled(biz.id, sale.id)
        with pytest.raises(VerdurasValidationError, match='No se puede'):
            mark_completed(biz.id, sale.id)

    def test_foreign_sale_is_not_found(self, db, biz, products):
        sale, _ = _sale(biz, products)
        other = Business.create_direct(vertical='verduras',
                                       name='Otro2', slug=_slug())
        with pytest.raises(VerdurasNotFoundError):
            mark_completed(other.id, sale.id)


# ═════════════════ Rate limiter + guards ═════════════════


class TestRateLimiter:
    def test_first_three_pass_fourth_blocks(self, db, biz):
        ip = '1.2.3.4'
        for _ in range(3):
            blocked, _, _ = SaleRateLimiter.should_block(biz.id, ip)
            assert blocked is False
            db.session.add(VerdurasSale(
                business_id=biz.id, sale_number='V-X', total=100,
                status='pending', ip_address=ip))
            db.session.commit()
        blocked, _, wait = SaleRateLimiter.should_block(biz.id, ip)
        assert blocked is True and wait == 600

    def test_same_ip_other_business_not_affected(self, db, biz):
        other = Business.create_direct(vertical='verduras',
                                       name='Otro3', slug=_slug())
        for _ in range(3):
            db.session.add(VerdurasSale(
                business_id=biz.id, sale_number='V-X', total=100,
                status='pending', ip_address='5.6.7.8'))
        db.session.commit()
        blocked, _, _ = SaleRateLimiter.should_block(other.id, '5.6.7.8')
        assert blocked is False

    def test_cancelled_sales_do_not_count(self, db, biz):
        for _ in range(3):
            db.session.add(VerdurasSale(
                business_id=biz.id, sale_number='V-X', total=100,
                status='cancelled', ip_address='9.9.9.9'))
        db.session.commit()
        blocked, _, _ = SaleRateLimiter.should_block(biz.id, '9.9.9.9')
        assert blocked is False


class TestPublicGuards:
    def test_honeypot_blocks(self, db, biz):
        _, status = check_public_guards(
            {'user_secondary_email': 'bot@x.com'}, biz.id, '1.1.1.1')
        assert status == 403

    def test_fast_submit_blocks(self, db, biz):
        _, status = check_public_guards(
            {'_t0': datetime.now(timezone.utc).timestamp()}, biz.id, '1.1.1.1')
        assert status == 429

    def test_slow_submit_passes(self, db, biz):
        err, _ = check_public_guards(
            {'_t0': datetime.now(timezone.utc).timestamp() - 10}, biz.id, '1.1.1.1')
        assert err is None

    def test_missing_t0_passes(self, db, biz):
        # Cliente sin JS: sin _t0 no se puede medir; no bloquear.
        err, _ = check_public_guards({}, biz.id, '1.1.1.1')
        assert err is None


# ═════════════════ WhatsApp + settings ═════════════════


class TestWhatsappLink:
    def test_link_none_without_phone(self, db, biz, products):
        sale, _ = _sale(biz, products)
        assert build_whatsapp_link(biz.id, sale) is None

    def test_link_contains_summary(self, db, biz, products):
        update_settings(biz.id, {'whatsapp_phone': '+57 300 111 2233'})
        sale, _ = _sale(biz, products)
        link = build_whatsapp_link(biz.id, sale)
        assert link and link.startswith('https://wa.me/573001112233?text=')
        assert 'Pedido%20' in link and 'Total' in link

    def test_phone_normalization(self, db, biz):
        row = update_settings(biz.id, {'whatsapp_phone': '+57 300-111-2233'})
        assert row.whatsapp_phone == '573001112233'

    def test_invalid_phone_rejected(self, db, biz):
        with pytest.raises(VerdurasValidationError, match='válido'):
            update_settings(biz.id, {'whatsapp_phone': 'abc'})

    def test_settings_defaults_created_on_read(self, db, biz):
        row = get_settings(biz.id)
        assert row.is_open is True and row.delivery_enabled is True


# ═════════════════ API ═════════════════


class TestSalesAPI:
    def test_pos_walkin_requires_api_key(self, client, db, biz, products):
        res = client.post(f'/api/verduras/businesses/{biz.id}/sales',
                          json={'items': [
                              {'product_id': products.tomate.id,
                               'quantity': '1'}]})
        assert res.status_code == 401

    def test_pos_walkin_flow(self, client, db, biz, products):
        res = client.post(f'/api/verduras/businesses/{biz.id}/sales', headers=AUTH,
                          json={'items': [
                              {'product_id': products.tomate.id,
                               'quantity': '0.500'}]})
        assert res.status_code == 201
        data = res.get_json()['data']
        assert data['total'] == '1600.00'
        assert data['sale_number'].startswith('V-')
        assert 'whatsapp_link' in data

    def test_public_delivery_checkout(self, client, db, biz, products):
        update_settings(biz.id, {'is_open': True, 'delivery_enabled': True,
                                 'whatsapp_phone': '573001112233'})
        res = client.post(f'/api/verduras/businesses/{biz.id}/sales',
                          json={'sale_type': 'delivery',
                                'customer_name': 'Doña Marta',
                                'customer_phone': '3001112233',
                                'delivery_address': 'Cra 7 #12-34',
                                'idempotency_key': 'uuid-1',
                                '_t0': datetime.now(timezone.utc).timestamp() - 10,
                                'items': [
                                    {'product_id': products.cebolla.id,
                                     'quantity': '2.000'}]})
        assert res.status_code == 201
        data = res.get_json()['data']
        assert data['total'] == '5601.00'
        assert data['whatsapp_link'].startswith('https://wa.me/573001112233')

    def test_delivery_replay_flag(self, client, db, biz, products):
        payload = {'sale_type': 'delivery', 'idempotency_key': 'uuid-2',
                   '_t0': datetime.now(timezone.utc).timestamp() - 10,
                   'items': [{'product_id': products.tomate.id,
                              'quantity': '1'}]}
        r1 = client.post(f'/api/verduras/businesses/{biz.id}/sales', json=payload)
        r2 = client.post(f'/api/verduras/businesses/{biz.id}/sales', json=payload)
        assert r1.status_code == 201 and r2.status_code == 200
        assert r2.get_json()['replay'] is True
        assert r1.get_json()['data']['id'] == r2.get_json()['data']['id']

    def test_delivery_closed_400_via_validation(self, client, db, biz, products):
        update_settings(biz.id, {'is_open': False})
        res = client.post(f'/api/verduras/businesses/{biz.id}/sales',
                          json={'sale_type': 'delivery',
                                '_t0': datetime.now(timezone.utc).timestamp() - 10,
                                'items': [{'product_id': products.tomate.id,
                                           'quantity': '1'}]})
        assert res.status_code == 400

    def test_honeypot_403(self, client, db, biz, products):
        res = client.post(f'/api/verduras/businesses/{biz.id}/sales',
                          json={'sale_type': 'delivery',
                                'user_secondary_email': 'bot@x.com',
                                'items': [{'product_id': products.tomate.id,
                                           'quantity': '1'}]})
        assert res.status_code == 403

    def test_fast_submit_429(self, client, db, biz, products):
        res = client.post(f'/api/verduras/businesses/{biz.id}/sales',
                          json={'sale_type': 'delivery',
                                '_t0': datetime.now(timezone.utc).timestamp(),
                                'items': [{'product_id': products.tomate.id,
                                           'quantity': '1'}]})
        assert res.status_code == 429

    def test_list_and_filter(self, client, db, biz, products):
        client.post(f'/api/verduras/businesses/{biz.id}/sales', headers=AUTH,
                    json={'items': [{'product_id': products.tomate.id,
                                     'quantity': '1'}]})
        res = client.get(f'/api/verduras/businesses/{biz.id}/sales',
                         headers=AUTH)
        assert res.status_code == 200
        assert len(res.get_json()['data']['sales']) == 1

        res = client.get(f'/api/verduras/businesses/{biz.id}/sales'
                         '?status=completed', headers=AUTH)
        assert res.get_json()['data']['sales'] == []

    def test_list_requires_api_key(self, client, db, biz, products):
        res = client.get(f'/api/verduras/businesses/{biz.id}/sales')
        assert res.status_code == 401

    def test_complete_flow(self, client, db, biz, products):
        sale_id = client.post(f'/api/verduras/businesses/{biz.id}/sales',
                              headers=AUTH,
                              json={'items': [{'product_id': products.tomate.id,
                                               'quantity': '1'}]}
                              ).get_json()['data']['id']
        res = client.post(
            f'/api/verduras/businesses/{biz.id}/sales/{sale_id}/complete',
            headers=AUTH)
        assert res.status_code == 200
        assert res.get_json()['data']['status'] == 'completed'

    def test_detail_scoped_and_auth(self, client, db, biz, products):
        sale_id = client.post(f'/api/verduras/businesses/{biz.id}/sales',
                              headers=AUTH,
                              json={'items': [{'product_id': products.tomate.id,
                                               'quantity': '1'}]}
                              ).get_json()['data']['id']
        assert client.get(
            f'/api/verduras/businesses/{biz.id}/sales/{sale_id}'
        ).status_code == 401
        assert client.get(
            f'/api/verduras/businesses/{biz.id}/sales/{sale_id}',
            headers=AUTH).status_code == 200

    def test_settings_roundtrip(self, client, db, biz):
        res = client.get(f'/api/verduras/businesses/{biz.id}/settings',
                         headers=AUTH)
        assert res.status_code == 200
        assert res.get_json()['data']['is_open'] is True

        res = client.post(f'/api/verduras/businesses/{biz.id}/settings',
                          headers=AUTH,
                          json={'whatsapp_phone': '573001112233',
                                'is_open': 'false'})
        assert res.get_json()['data']['is_open'] is False

    def test_settings_requires_api_key(self, client, db, biz):
        assert client.get(
            f'/api/verduras/businesses/{biz.id}/settings').status_code == 401

    def test_restaurant_mirror_409_on_sales(self, client, db):
        from app.models import Restaurant
        r = Restaurant(name='Rest', slug=_slug(), whatsapp_phone='+573001112233')
        db.session.add(r)
        db.session.flush()
        res = client.get(f'/api/verduras/businesses/{r.id}/sales')
        assert res.status_code == 409


# ═════════════════ Método de pago (POS rediseñado v1, guardian) ═════════


class TestSalePaymentMethod:
    def test_valid_method_saved(self, db, biz, products):
        sale, _ = _sale(biz, products, payment_method='transferencia')
        assert sale.payment_method == 'transferencia'

    def test_invalid_method_rejected(self, db, biz, products):
        with pytest.raises(VerdurasValidationError, match='pago'):
            _sale(biz, products, payment_method='trueque')

    def test_default_none_for_old_sales(self, db, biz, products):
        sale, _ = _sale(biz, products)
        assert sale.payment_method is None


class TestSaleCashTender:
    def test_change_computed(self, db, biz, products):
        sale, _ = _sale(biz, products, payment_method='efectivo',
                        amount_received='50000')
        # 2600 total, recibe 50000 → vueltas 47400.
        assert sale.amount_received == Decimal('50000.00')
        assert sale.change_due == Decimal('47400.00')

    def test_short_payment_rejected(self, db, biz, products):
        with pytest.raises(VerdurasValidationError, match='Faltan'):
            _sale(biz, products, payment_method='efectivo',
                  amount_received='1000')

    def test_invalid_received_rejected(self, db, biz, products):
        with pytest.raises(VerdurasValidationError, match='inválido'):
            _sale(biz, products, payment_method='efectivo',
                  amount_received='mucho')

    def test_non_cash_ignores_received(self, db, biz, products):
        sale, _ = _sale(biz, products, payment_method='tarjeta',
                        amount_received='50000')
        assert sale.amount_received is None
        assert sale.change_due is None
