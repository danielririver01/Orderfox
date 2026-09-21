"""
Tests del hook FASE 0 — message_handler con tenant verdulero, vía HTTP real.

Cubre:
- POST /insights/api/conversations/<id>/messages con conversación
  (restaurant_id=NULL, business_id=verduras) responde con datos de
  VerdurasSale (Nivel 1 quick, gratis, con gráfica).
- El guard de alcance NO bloquea al mencionar el nombre propio del negocio.
- Nivel 2 (análisis) usa el adapter verdulero + sección VERDULERÍA del
  prompt, consume 1 token y omite telemetría/web-search sin romper.
"""

from datetime import datetime, timezone

import pytest
from werkzeug.security import generate_password_hash

import verduras.models  # noqa: F401
import verduras.models_sales  # noqa: F401
from app.models import (
    AITokenWallet,
    Business,
    CopilotConversation,
    User,
    db,
)
from verduras.models import VerdurasCategory, VerdurasProduct
from verduras.models_sales import VerdurasSale, VerdurasSaleItem


BID = 1_000_000


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


def _login(client, user):
    with client.session_transaction() as sess:
        sess['user_id'] = user.id


def _post(client, cid, content):
    return client.post(
        f'/insights/api/conversations/{cid}/messages',
        json={'content': content},
    )


class TestHookVerduras:
    def test_quick_responde_con_ventas_verduleria(
        self, client, verduras_user, verduras_venta_hoy, verduras_conv,
    ):
        _login(client, verduras_user)
        resp = _post(client, verduras_conv.id, '¿cuánto vendí hoy?')
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
        _login(client, verduras_user)
        # 'de La Huerta' dispara el patrón débil del guard; como es el nombre
        # propio (own_ids) debe pasar. Sin el fix sería scope_guard.
        resp = _post(client, verduras_conv.id, 'ventas de hoy de La Huerta')
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
        _login(client, verduras_user)
        resp = _post(client, conv.id, '¿cuánto vendí hoy?')
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
        _login(client, verduras_user)
        resp = _post(client, verduras_conv.id, 'analiza mis ventas')
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
