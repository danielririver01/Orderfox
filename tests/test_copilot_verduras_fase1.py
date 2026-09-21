"""
Tests FASE 1 — Copilot VZ Verdulería: inventario, merma, rentabilidad,
reposición (lee MODELOS de lots/merma, no el service del módulo).

Cubre:
- Stock derivado (compras − ventas − merma) con estados y cobertura.
- Merma del mes con pérdida congelada y % sobre compras.
- Márgenes con costo ponderado; sin lotes → without_cost (jamás inventado).
- Reposición calculada con fórmula visible.
- Quick intents nuevos + intent de análisis restock/waste via classifier.
- Contexto con inventory/merma/margins/quiet_products.
- Hook HTTP: quick de stock y merma responden con datos reales.
"""

from datetime import datetime, timedelta, timezone

import pytest
from werkzeug.security import generate_password_hash

import verduras.models  # noqa: F401
import verduras.models_inventory  # noqa: F401
import verduras.models_sales  # noqa: F401
from app.models import Business, CopilotConversation, User, db
from app.services.insights import (
    classifier,
    data_service_verduras as vd,
    prompt_builder,
)
from verduras.models import VerdurasCategory, VerdurasProduct
from verduras.models_inventory import VerdurasLot, VerdurasMerma
from verduras.models_sales import VerdurasSale, VerdurasSaleItem


BID = 1_000_000


@pytest.fixture
def negocio(db):
    b = Business(id=BID, vertical='verduras', name='La Huerta',
                 slug='la-huerta', is_active=True)
    db.session.add(b)
    db.session.commit()
    return b


@pytest.fixture
def datos(db, negocio):
    """Tomate ($4.000/kg, lote 50kg a $160.000) + papa ($2.000/kg,
    lote 100kg a $150.000) + aguacate ($6.000/kg, lote 10kg a $30.000)
    + cilantro ($1.000/un, lote 5un a $5.000) + yuca (sin nada)."""
    cat = VerdurasCategory(business_id=BID, name='Hortalizas')
    db.session.add(cat)
    db.session.flush()
    now = datetime.now(timezone.utc)

    def prod(name, unit, price):
        p = VerdurasProduct(business_id=BID, category_id=cat.id, name=name,
                            unit=unit, current_price=price, is_active=True)
        db.session.add(p)
        db.session.flush()
        return p

    tomate = prod('Tomate', 'kg', 4000)
    papa = prod('Papa', 'kg', 2000)
    aguacate = prod('Aguacate', 'kg', 6000)
    cilantro = prod('Cilantro', 'unidad', 1000)
    yuca = prod('Yuca', 'kg', 2500)

    def lot(p, qty, cost, days_ago=0):
        db.session.add(VerdurasLot(
            business_id=BID, product_id=p.id, quantity=qty,
            total_cost=cost, purchased_at=now - timedelta(days=days_ago)))

    lot(tomate, 50, 160000)      # $3.200/kg ponderado
    lot(papa, 100, 150000)       # $1.500/kg ponderado
    lot(aguacate, 10, 30000)     # $3.000/kg
    lot(cilantro, 5, 5000)       # $1.000/un

    n = {'n': 0}

    def sale(items, total, days_ago=0, phone='+573001'):
        n['n'] += 1
        s = VerdurasSale(
            business_id=BID, sale_number=f'V-F1-{n["n"]:03d}', total=total,
            status='completed', customer_phone=phone,
            created_at=now - timedelta(days=days_ago))
        db.session.add(s)
        db.session.flush()
        for p, qty, price in items:
            db.session.add(VerdurasSaleItem(
                sale_id=s.id, product_id=p.id, product_name=p.name,
                unit=p.unit, unit_price=price, quantity=qty,
                line_total=round(float(qty) * float(price), 2)))
        return s

    sale([(tomate, 2, 4000)], 8000, days_ago=0)             # hoy
    sale([(papa, 5, 2000)], 10000, days_ago=1)             # ayer
    sale([(tomate, 1, 4000)], 4000, days_ago=20)           # hace 20d
    sale([(aguacate, 4, 6000)], 24000, days_ago=1)         # ayer
    sale([(aguacate, 5, 6000)], 30000, days_ago=2)         # anteayer
    sale([(cilantro, 4, 1000)], 4000, days_ago=1)          # ayer

    db.session.add(VerdurasMerma(
        business_id=BID, product_id=tomate.id, quantity=2,
        reason='danado', cost_loss=6400,  # 2kg × $3.200 ponderado
        registered_at=now - timedelta(days=5)))
    db.session.add(VerdurasMerma(
        business_id=BID, product_id=papa.id, quantity=1,
        reason='vencido', cost_loss=1500,  # 1kg × $1.500 ponderado
        registered_at=now - timedelta(days=3)))
    db.session.commit()
    return {'tomate': tomate, 'papa': papa, 'aguacate': aguacate,
            'cilantro': cilantro, 'yuca': yuca}


# ── Inventario ───────────────────────────────────────────────────────────────

class TestStock:
    def test_derivado_compras_menos_ventas_menos_merma(self, datos):
        s = vd._stock_of(BID, datos['tomate'])
        assert float(s['stock']) == 50 - 3 - 2
        assert float(s['avg_unit_cost']) == 3200

    def test_estados(self, datos):
        by_name = {i['name']: i for i in vd.stock_status(BID)['items']}
        assert by_name['Aguacate']['status'] == 'bajo'   # stock 1, cobertura ~1.6d
        assert by_name['Yuca']['status'] == 'sin_compras'
        assert by_name['Tomate']['status'] == 'ok'
        assert by_name['Cilantro']['stock'] == 1

    def test_texto_con_alertas(self, datos):
        text = vd.stock_status(BID)['text']
        assert 'AGOTADO' in text or 'BAJO' in text
        assert 'Aguacate' in text

    def test_quiet_products(self, datos):
        # Ventana 14d: solo Yuca está quieta (tomate vendió hoy).
        assert {q['name'] for q in vd.quiet_products(BID)} == {'Yuca'}

    def test_quiet_ventana_30_dias(self, datos):
        quiet = {q['name'] for q in vd.quiet_products(BID, days=30)}
        assert 'Yuca' in quiet and 'Tomate' not in quiet


# ── Merma ────────────────────────────────────────────────────────────────────

class TestMerma:
    def test_reporte_mes(self, datos):
        r = vd.merma_month(BID)
        assert r['total_loss'] == 7900
        assert r['items'][0]['name'] == 'Tomate'
        assert 'Merma de este mes: $7.900' in r['text']

    def test_mes_sin_merma(self, db, negocio):
        r = vd.merma_month(BID)
        assert r['total_loss'] == 0 and r['items'] == []
        assert 'no registraste merma' in r['text']


# ── Rentabilidad y reposición ────────────────────────────────────────────────

class TestMargenReposicion:
    def test_margenes_con_ponderado(self, datos):
        m = vd.margins(BID, 30)
        by_name = {i['name']: i for i in m['items']}
        # Tomate: 3kg × $4.000 = $12.000 − 3 × $3.200 = $2.400 (20%)
        assert by_name['Tomate']['margin'] == 2400
        assert by_name['Tomate']['margin_pct'] == 20.0
        # Papa: 5kg × $2.000 = $10.000 − 5 × $1.500 = $2.500 (25%)
        assert by_name['Papa']['margin'] == 2500
        assert m['totals']['margin'] == 2400 + 2500 + 27000 + 0
        assert 'Rentabilidad' in m['text']

    def test_sin_lotes_sin_margen(self, db, negocio, datos):
        m = vd.margins(BID, 30)
        assert 'Yuca' not in [i['name'] for i in m['items']]
        # Yuca no vendió: tampoco va a without_cost (solo venden sin costo)
        assert m['without_cost'] == []

    def test_reposicion_formula_visible(self, datos):
        r = vd.restock_suggestions(BID, cover_days=7)
        assert r['items'][0]['name'] == 'Aguacate'  # menor cobertura primero
        ag = r['items'][0]
        assert ag['suggested'] > 0
        # 9kg/14d × 7d − 1kg = 3.5kg
        assert ag['suggested'] == pytest.approx(3.5)
        assert 'Para cubrir 7 días' in r['text']


# ── Quick, classifier, contexto, hook ────────────────────────────────────────

class TestIntegracion:
    def test_quick_nuevos(self, datos):
        assert 'Estado de inventario' in vd.handle_quick(BID, 'stock_status')['text']
        assert '$7.900' in vd.handle_quick(BID, 'merma_month')['text']

    def test_classifier(self):
        assert classifier.classify('¿qué tengo en stock?')['intent'] == 'stock_status'
        assert classifier.classify('¿qué tengo en stock?')['level'] == 'quick'
        assert classifier.classify('¿cuánta merma tuve este mes?')['intent'] == 'merma_month'
        assert classifier.classify('¿qué debo reponer primero?')['intent'] == 'restock'
        assert classifier.classify('¿qué debo reponer primero?')['level'] == 'analysis'
        assert classifier.classify('¿cuál es mi margen por producto?')['intent'] in (
            'profitability_analysis', 'restock', 'general_analysis')

    def test_contexto_trae_fase1(self, datos):
        ctx = vd.build_context(BID, days=30)
        assert set(ctx['inventory']) >= {'items', 'total_value', 'low', 'out'}
        assert 'Aguacate' in ctx['inventory']['low']
        assert ctx['merma']['month_loss'] == 7900
        assert ctx['margins']['totals']['margin'] > 0
        assert 'Yuca' in ctx['quiet_products']

    def test_prompt_v18(self):
        assert prompt_builder.PROMPT_VERSION == 'v1.8'
        msgs = prompt_builder.build_analysis_messages(
            '¿qué repongo?', {'vertical': 'verduras'}, history=[],
            vertical='verduras', business_name='La Huerta')
        assert 'REPOSICIÓN' in msgs[0]['content']

    def test_hook_http_stock_y_merma(self, client, db, datos):
        u = User(restaurant_id=None, username='verdulero1',
                 email='v1@test.com', password='x', clerk_id='clk_f1')
        db.session.add(u)
        db.session.flush()
        conv = CopilotConversation(user_id=u.id, restaurant_id=None,
                                   business_id=BID)
        db.session.add(conv)
        db.session.commit()
        with client.session_transaction() as sess:
            sess['user_id'] = u.id
        r1 = client.post(f'/insights/api/conversations/{conv.id}/messages',
                         json={'content': '¿qué se me está acabando?'})
        assert r1.get_json()['type'] == 'quick'
        assert 'Aguacate' in r1.get_json()['content']
        r2 = client.post(f'/insights/api/conversations/{conv.id}/messages',
                         json={'content': '¿cuánta merma tuve este mes?'})
        assert '$7.900' in r2.get_json()['content']
