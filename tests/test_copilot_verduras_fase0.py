"""
Tests FASE 0 — Copilot VZ para Verdulería (solo Ventas).

Cubre:
- Adapter data_service_verduras: quick (N1), contexto (N2), stage, charts.
- tenant_router: Business verduras → adapter verduras; resto → restaurante.
- prompt_builder v1.7: sección VERDULERÍA solo con vertical='verduras'.
- Reglas FASE 0: canceladas excluidas, teléfonos vacíos no cuentan como
  clientes, kg solo suma líneas en kg, fechas normalizadas en SQLite.

Los imports de verduras.* registran sus tablas en el metadata compartido
para que conftest (create_all) las cree en sqlite:///:memory:.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from werkzeug.security import generate_password_hash

import verduras.models  # noqa: F401  (registra verduras_* en el metadata)
import verduras.models_sales  # noqa: F401
from app.models import AITokenWallet, Business, CopilotConversation, Restaurant, User, db
from app.services.insights import (
    chart_service,
    data_service,
    data_service_verduras as vd,
    prompt_builder,
    tenant_router,
)
from verduras.models import VerdurasCategory, VerdurasPriceHistory, VerdurasProduct
from verduras.models_sales import VerdurasSale, VerdurasSaleItem


BID = 1_000_000


@pytest.fixture
def business(db):
    b = Business(id=BID, vertical='verduras', name='La Huerta',
                 slug='la-huerta', is_active=True)
    db.session.add(b)
    db.session.commit()
    return b


@pytest.fixture
def catalogo(db, business):
    cat = VerdurasCategory(business_id=business.id, name='Hortalizas')
    db.session.add(cat)
    db.session.flush()
    tomate = VerdurasProduct(
        business_id=business.id, category_id=cat.id, name='Tomate',
        unit='kg', current_price=3200, is_active=True,
    )
    papa = VerdurasProduct(
        business_id=business.id, category_id=cat.id, name='Papa',
        unit='kg', current_price=1800, is_active=True,
    )
    cebolla = VerdurasProduct(
        business_id=business.id, category_id=cat.id, name='Cebolla',
        unit='unidad', current_price=800, is_active=True,
    )
    db.session.add_all([tomate, papa, cebolla])
    db.session.flush()
    db.session.add(VerdurasPriceHistory(
        product_id=tomate.id, price=3000,
        effective_from=datetime.now(timezone.utc) - timedelta(days=5),
        source='manual',
    ))
    db.session.commit()
    return {'tomate': tomate, 'papa': papa, 'cebolla': cebolla}


def _sale(db, business_id, items, total, when, phone='', status='completed',
          number='V-1'):
    s = VerdurasSale(
        business_id=business_id, sale_number=number, total=total,
        status=status, customer_phone=phone, created_at=when,
    )
    db.session.add(s)
    db.session.flush()
    for prod, qty, price in items:
        db.session.add(VerdurasSaleItem(
            sale_id=s.id, product_id=prod.id, product_name=prod.name,
            unit=prod.unit, unit_price=price, quantity=qty,
            line_total=round(float(qty) * float(price), 2),
        ))
    db.session.commit()
    return s


@pytest.fixture
def ventas(db, business, catalogo):
    now = datetime.now(timezone.utc)
    c = catalogo
    # Hoy: 2 kg tomate ($6.400) + 1 cebolla unidad ($800) = $7.200
    _sale(db, business.id, [(c['tomate'], 2, 3200), (c['cebolla'], 1, 800)],
          7200, now, phone='+573001', number='V-001')
    # Ayer: 5 kg papa ($9.000)
    _sale(db, business.id, [(c['papa'], 5, 1800)], 9000,
          now - timedelta(days=1), phone='+573002', number='V-002')
    # Hace 10 días: 1 kg tomate ($3.200), teléfono vacío
    _sale(db, business.id, [(c['tomate'], 1, 3200)], 3200,
          now - timedelta(days=10), phone='', number='V-003')
    # Hace 40 días (mes anterior): 3 kg papa ($5.400)
    _sale(db, business.id, [(c['papa'], 3, 1800)], 5400,
          now - timedelta(days=40), phone='+573003', number='V-004')
    # Cancelada hoy: NO debe contar ($10.000)
    _sale(db, business.id, [(c['tomate'], 3, 3200)], 10000,
          now, phone='+573009', status='cancelled', number='V-005')
    return business


# ── Nivel 1: consultas rápidas ───────────────────────────────────────────────

class TestQuick:
    def test_sales_today(self, ventas):
        r = vd.sales_for_date(BID, 0)
        assert r['summary']['total'] == 7200
        assert r['summary']['orders'] == 1
        assert 'Hoy vendiste $7.200' in r['text']

    def test_sales_yesterday(self, ventas):
        r = vd.sales_for_date(BID, 1)
        assert r['summary']['total'] == 9000
        assert 'Ayer' in r['text']

    def test_cancelled_excluded(self, ventas):
        assert vd.sales_for_date(BID, 0)['summary']['total'] == 7200

    def test_top_products_units(self, ventas):
        r = vd.top_products(BID, 60, 5)
        assert r['items'][0]['name'] == 'Papa'  # 9000+5400 por ingresos
        assert r['items'][0]['revenue'] == 14400
        assert r['items'][0]['unit'] == 'kg'
        cebolla = [i for i in r['items'] if i['name'] == 'Cebolla'][0]
        assert cebolla['unit'] == 'unidad'
        assert 'kg' in r['text'] or 'unidad' in r['text']

    def test_handle_quick_parity(self, ventas):
        assert 'ventas' in vd.handle_quick(BID, 'orders_today')['text']
        assert 'ticket promedio' in vd.handle_quick(BID, 'avg_ticket')['text'].lower()
        assert 'Mes anterior' in vd.handle_quick(BID, 'compare_months')['text']
        assert 'esta semana' in vd.handle_quick(BID, 'week_sales')['text']
        assert vd.handle_quick(BID, 'month_sales')['summary']['orders'] == 3

    def test_new_customers_ignores_empty_phone(self, ventas):
        assert vd.new_customers(BID, 0)['count'] == 1  # solo +573001
        assert vd.new_customers(BID, 10)['count'] == 0  # teléfono '' no cuenta

    def test_empty_result_detection(self, db, business):
        assert vd.is_empty_quick_result(vd.sales_for_date(BID, 0)) is True
        assert vd.is_empty_quick_result({'items': []}) is True

    def test_window_labels(self):
        assert vd.window_label_from_days(1) == 'Hoy'
        assert vd.window_label_from_days(7) == 'esta semana'


# ── Nivel 2: contexto ────────────────────────────────────────────────────────

class TestContext:
    def test_keys_mirror_restaurant(self, ventas):
        ctx = vd.build_context(BID, days=60)
        for key in ('period_days', 'period_start', 'period_end', 'currency',
                    'overall', 'active_days', 'daily_series',
                    'top_products_by_revenue', 'top_products_by_quantity',
                    'sales_by_weekday', 'catalog'):
            assert key in ctx
        assert ctx['vertical'] == 'verduras'
        assert ctx['overall']['total'] == 7200 + 9000 + 3200 + 5400  # 60 días
        assert ctx['catalog'] == {'total': 3, 'active': 3}

    def test_catalog_items_have_price_and_unit(self, ventas):
        ctx = vd.build_context(BID, days=7, include_catalog=True)
        by_name = {i['name']: i for i in ctx['catalog_items']}
        assert by_name['Tomate']['price'] == 3200
        assert by_name['Tomate']['unit'] == 'kg'
        assert by_name['Cebolla']['unit'] == 'unidad'

    def test_daily_series_dates_normalized(self, ventas):
        series = vd.daily_series_since(BID, vd._today_utc() - timedelta(days=60))
        assert series, 'debe haber serie con ventas'
        for d, total in series:
            assert hasattr(d, 'weekday'), f'{d!r} no es date (SQLite devuelve str)'
            assert isinstance(total, int)

    def test_weekday_sums_match(self, ventas):
        ctx = vd.build_context(BID, days=60)
        assert sum(ctx['sales_by_weekday'].values()) == ctx['overall']['total']

    def test_stage_levels(self, db, business, catalogo):
        assert vd.get_data_stage(BID)['level'] == 1  # catálogo sin ventas
        now = datetime.now(timezone.utc)
        _sale(db, BID, [(catalogo['tomate'], 1, 3200)], 3200, now, number='V-100')
        assert vd.get_data_stage(BID)['level'] == 2
        for n in range(19):
            _sale(db, BID, [(catalogo['papa'], 1, 1800)], 1800, now,
                  number=f'V-2{n:02d}')
        assert vd.get_data_stage(BID)['level'] == 3
        assert vd.has_sales(BID) is True
        assert vd.has_sales(BID, days=1) is True

    def test_stage_zero_without_catalog(self, db):
        b2 = Business(id=BID + 1, vertical='verduras', name='Vacía',
                      slug='vacia', is_active=True)
        db.session.add(b2)
        db.session.commit()
        assert vd.get_data_stage(b2.id) == {'level': 0, 'products': 0, 'orders': 0}
        assert vd.has_sales(b2.id) is False

    def test_projection_math(self, ventas):
        p = vd.projection_uplift(BID, days=60)
        assert p['addon_price'] == 800  # cebolla, la más económica
        assert p['extra_revenue'] == int(p['orders'] * 0.25 * 800)
        assert p['projected_revenue'] == p['revenue'] + p['extra_revenue']

    def test_empty_states_verduleria(self):
        for kind in ('no_catalog', 'no_sales_yet', 'chart_empty'):
            s = vd.build_empty_state(kind)
            assert s['text'] and s['suggestions']
        w = vd.build_empty_state('no_data_window', window_label='Hoy')
        assert 'Hoy' in w['text']
        assert 'verduler' in vd.build_empty_state('no_catalog')['text'].lower()

    def test_suggestions_shape(self, ventas):
        stage = vd.get_data_stage(BID)
        welcome = vd.welcome_suggestions(BID, stage)
        assert 1 <= len(welcome) <= 4
        chips = vd.followup_suggestions(
            {'level': 'quick', 'intent': 'sales_today', 'window': 1}, stage=stage)
        assert len(chips) == 3 and all('label' in c for c in chips)


# ── Router + prompt + charts ─────────────────────────────────────────────────

class TestRouterPromptCharts:
    def test_router_verduras(self, business):
        conv = SimpleNamespace(business_id=None, restaurant_id=BID)
        ds, tid, vertical, name = tenant_router.resolve(conv)
        assert ds is vd and tid == BID and vertical == 'verduras'
        assert name == 'La Huerta'

    def test_router_restaurant_and_unknown(self, db, sample_restaurant):
        conv = SimpleNamespace(business_id=None, restaurant_id=sample_restaurant.id)
        ds, tid, vertical, _ = tenant_router.resolve(conv)
        assert ds is data_service and vertical == 'restaurant'
        conv2 = SimpleNamespace(business_id=None, restaurant_id=999999)
        assert tenant_router.resolve(conv2)[0] is data_service

    def test_prompt_version_and_section(self):
        assert prompt_builder.PROMPT_VERSION == 'v1.8'
        msgs = prompt_builder.build_analysis_messages(
            '¿cuánto vendí hoy?', {'vertical': 'verduras'}, history=[],
            vertical='verduras', business_name='La Huerta')
        system = msgs[0]['content']
        assert 'verdulería' in system
        assert 'CONTEXTO DEL NEGOCIO' in system
        assert 'La Huerta' in system
        msgs_r = prompt_builder.build_analysis_messages(
            '¿cuánto vendí hoy?', {'overall': {}}, history=[])
        assert 'CONTEXTO DEL RESTAURANTE' in msgs_r[0]['content']
        assert 'verdulería' not in msgs_r[0]['content']

    def test_charts_with_verduras_adapter(self, ventas):
        week = vd.handle_quick(BID, 'week_sales')
        chart = chart_service.chart_for_intent(BID, 'week_sales', week, ds=vd)
        assert chart['type'] == 'line' and len(chart['labels']) == 7
        assert sum(chart['datasets'][0]['data']) == week['summary']['total']
        top = vd.handle_quick(BID, 'top_product')  # ventana 30d: Tomate $9.600
        bar = chart_service.chart_for_intent(BID, 'top_product', top, ds=vd)
        assert bar['labels'][0] == 'Tomate'
        chips = chart_service.followup_suggestions(
            {'level': 'quick', 'intent': 'sales_today', 'window': 1},
            stage={'level': 3}, restaurant_id=BID, ds=vd)
        assert len(chips) == 3


# ── Fusionado desde test_copilot_verduras_hook.py ────────────────────────────
# Hook HTTP FASE 0: message_handler con tenant verdulero vía HTTP real.
# Reutiliza BID de este archivo (mismo valor 1_000_000).

@pytest.fixture
def verduras_business(db):
    b = Business(id=BID, vertical='verduras', name='La Huerta',
                 slug='la-huerta', is_active=True)
    db.session.add(b)
    db.session.commit()
    return b


@pytest.fixture
def verduras_venta_hoy(db, verduras_business):
    cat = VerdurasCategory(business_id=BID, name='Hortalizas')
    db.session.add(cat)
    db.session.flush()
    tomate = VerdurasProduct(
        business_id=BID, category_id=cat.id, name='Tomate',
        unit='kg', current_price=3200, is_active=True,
    )
    db.session.add(tomate)
    db.session.flush()
    now = datetime.now(timezone.utc)
    sale = VerdurasSale(
        business_id=BID, sale_number='V-001', total=6400,
        status='completed', customer_phone='+573001', created_at=now,
    )
    db.session.add(sale)
    db.session.flush()
    db.session.add(VerdurasSaleItem(
        sale_id=sale.id, product_id=tomate.id, product_name='Tomate',
        unit='kg', unit_price=3200, quantity=2, line_total=6400,
    ))
    db.session.commit()
    return sale


@pytest.fixture
def verduras_user(db):
    u = User(
        restaurant_id=None,
        username='verdulero',
        email='verdulero@test.com',
        password=generate_password_hash('TestPass123'),
        clerk_id='clerk_verduras_1',
    )
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def verduras_wallet(db, verduras_user):
    w = AITokenWallet(
        user_id=verduras_user.id, plan_limit=50, plan_tokens=5,
        extra_tokens=0, tokens_used_month=0,
    )
    db.session.add(w)
    db.session.commit()
    return w


@pytest.fixture
def verduras_conv(db, verduras_user, verduras_business):
    c = CopilotConversation(
        user_id=verduras_user.id, restaurant_id=None, business_id=BID,
    )
    db.session.add(c)
    db.session.commit()
    return c


def _hook_login(client, user):
    with client.session_transaction() as sess:
        sess['user_id'] = user.id


def _hook_post(client, cid, content):
    return client.post(
        f'/insights/api/conversations/{cid}/messages',
        json={'content': content},
    )


class TestHookVerduras:
    def test_quick_responde_con_ventas_verduleria(
        self, client, verduras_user, verduras_venta_hoy, verduras_conv,
    ):
        _hook_login(client, verduras_user)
        resp = _hook_post(client, verduras_conv.id, '¿cuánto vendí hoy?')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['type'] == 'quick'
        assert 'Hoy vendiste $6.400' in data['content']
        assert data['metadata']['credits_used'] == 0
        assert data['chart'] is not None  # serie 7 días desde ventas reales

    def test_mencionar_negocio_propio_no_bloquea(
        self, client, verduras_user, verduras_venta_hoy, verduras_conv,
    ):
        _hook_login(client, verduras_user)
        # 'de La Huerta' dispara el patrón débil del guard; como es el nombre
        # propio (own_ids) debe pasar. Sin el fix sería scope_guard.
        resp = _hook_post(client, verduras_conv.id, 'ventas de hoy de La Huerta')
        data = resp.get_json()
        assert data['type'] == 'quick'  # no scope_guard

    def test_empty_state_verduleria_sin_ventas(
        self, client, db, verduras_user, verduras_business,
    ):
        cat = VerdurasCategory(business_id=BID, name='Hortalizas')
        db.session.add(cat)
        db.session.flush()
        db.session.add(VerdurasProduct(
            business_id=BID, category_id=cat.id, name='Tomate',
            unit='kg', current_price=3200, is_active=True,
        ))
        conv = CopilotConversation(
            user_id=verduras_user.id, restaurant_id=None, business_id=BID,
        )
        db.session.add(conv)
        db.session.commit()
        _hook_login(client, verduras_user)
        resp = _hook_post(client, conv.id, '¿cuánto vendí hoy?')
        data = resp.get_json()
        assert data['is_empty_state'] is True
        assert 'primeras ventas' in data['message']['content']

    def test_analysis_usa_adapter_y_prompt_verduleria(
        self, client, verduras_user, verduras_wallet, verduras_venta_hoy,
        verduras_conv, monkeypatch,
    ):
        captured = {}

        def _fake_chat(messages, **kwargs):
            captured['system'] = messages[0]['content']
            captured['restaurant_id'] = kwargs.get('restaurant_id')
            return '{"text": "Análisis de prueba", "chart": null}'

        monkeypatch.setattr(
            'app.services.insights.llm_service.chat', _fake_chat)
        monkeypatch.setattr(
            'app.services.insights.message_handler.eval_achievement',
            lambda *a, **k: None)
        _hook_login(client, verduras_user)
        resp = _hook_post(client, verduras_conv.id, 'analiza mis ventas')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['type'] == 'analysis'
        assert data['content'] == 'Análisis de prueba'
        assert data['metadata']['credits_used'] == 1
        # Prompt con sección del vertical y sin telemetría con FK rota.
        assert 'verdulería' in captured['system']
        assert captured['restaurant_id'] is None
        # El token se consumió del wallet.
        assert db.session.get(AITokenWallet, verduras_wallet.id).tokens_used_month == 1
