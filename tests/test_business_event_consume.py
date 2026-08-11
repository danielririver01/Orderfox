"""
Tests del flujo de consumo de BusinessEvents en Copilot VZ.

Cubre:
- POST /insights/api/events/<id>/consume ejecuta el análisis automáticamente:
  el usuario que pulsó "Analizar" en el dashboard no debe responder un saludo
  para obtener el análisis (fix del botón "Analizar").
- Timeline resultante: saludo template (assistant) → usuario automático
  ("Analiza mi negocio") → análisis (assistant).
- El evento queda marcado como consumido y vinculado a la conversación.
- El primer análisis cobra 1 token (source 'copilot_vz').
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.models import (
    AITokenTransaction,
    AITokenWallet,
    Category,
    CopilotBusinessEvent,
    CopilotConversation,
    Order,
    Product,
)
from app.services.insights import conversation_service as cs


@pytest.fixture(autouse=True)
def _mock_data_context(monkeypatch):
    """build_context usa dayofweek() (MySQL), que no existe en SQLite."""
    def _fake_build_context(restaurant_id, days=90):
        return {
            'period_days': days,
            'currency': 'COP',
            'overall': {'total': 10000, 'orders': 1, 'avg_ticket': 10000},
            'active_days': 1,
            'daily_series': [{'date': '2026-08-06', 'total': 10000, 'orders': 1}],
            'top_products_by_revenue': [{'name': 'Producto 1', 'revenue': 10000}],
            'top_products_by_quantity': [{'name': 'Producto 1', 'qty': 1}],
            'sales_by_weekday': {i: 0 for i in range(7)},
            'catalog': {'total': 1, 'active': 1},
        }

    monkeypatch.setattr(
        'app.services.insights.data_service.build_context', _fake_build_context)


@pytest.fixture(autouse=True)
def _disable_achievements(monkeypatch):
    """El logro 'primer_analisis' otorga +5 tokens; se neutraliza para aislar
    la lógica de consumo que aquí se prueba."""
    monkeypatch.setattr(
        'app.services.insights.message_handler.eval_achievement',
        lambda *a, **k: None)


@pytest.fixture
def wallet(db, sample_user):
    w = AITokenWallet(
        user_id=sample_user.id, plan_limit=50, plan_tokens=5,
        extra_tokens=0, tokens_used_month=0,
    )
    db.session.add(w)
    db.session.commit()
    return w


@pytest.fixture
def sale_factory(db):
    """Crea categoría + producto + pedido para que el restaurante llegue a Nivel 2+."""
    counter = {'n': 0}

    def _make(restaurant):
        counter['n'] += 1
        cat = Category(
            restaurant_id=restaurant.id, name='Categoría', sort_order=1,
            is_active=True,
        )
        db.session.add(cat)
        db.session.flush()
        p = Product(
            restaurant_id=restaurant.id, category_id=cat.id,
            name=f'Producto {counter["n"]}', price=5000, is_active=True,
        )
        o = Order(
            restaurant_id=restaurant.id,
            order_number=f'IN-{counter["n"]:04d}',
            customer_name='Cliente Copilot',
            status='delivered',
            total=10000,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db.session.add_all([cat, p, o])
        db.session.commit()
        return o

    return _make


class _LLMCapture:
    """Captura los mensajes enviados al LLM y permite inyectar respuesta/error."""

    def __init__(self):
        self.calls = []
        self.return_value = '{"text": "Análisis de prueba", "chart": null}'
        self.error = None

    def __call__(self, messages, temperature=0.35, max_tokens=2000, **kwargs):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return self.return_value


@pytest.fixture
def llm_capture(monkeypatch):
    cap = _LLMCapture()
    monkeypatch.setattr(
        'app.services.insights.llm_service.chat', cap)
    return cap


@pytest.fixture
def business_event(db, sample_restaurant):
    ev = CopilotBusinessEvent(
        restaurant_id=sample_restaurant.id,
        kind='first_sales',
        priority=10,
        title='¡Ya tienes tus primeras ventas! 🎉',
        preview='Ya tienes suficientes datos registrados para que pueda ayudarte.',
        template_key='first_sales',
        active=True,
    )
    db.session.add(ev)
    db.session.commit()
    return ev


class _Auth:
    """Login con sesión (rutas /insights/api exentas de CSRF)."""

    def _login(self, client, user):
        with client.session_transaction() as sess:
            sess['user_id'] = user.id


class TestConsumeEvent(_Auth):

    def test_consume_runs_auto_analysis(
            self, client, db, sample_user, sample_restaurant, wallet,
            sale_factory, business_event, llm_capture):
        sale_factory(sample_restaurant)
        self._login(client, sample_user)

        resp = client.post(f'/insights/api/events/{business_event.id}/consume')
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = resp.get_json()
        assert body['success'] is True
        assert body['redirect'].endswith(f'#conv={business_event.conversation_id}')

        db.session.refresh(business_event)
        assert business_event.active is False
        assert business_event.conversation_id is not None

        conv = CopilotConversation.query.get(business_event.conversation_id)
        assert conv is not None
        msgs = cs.get_messages(conv.id)
        assert [m.role for m in msgs] == ['assistant', 'user', 'assistant']
        assert 'business_event' in (msgs[0].metadata_json or '')
        assert msgs[1].content == 'Analiza mi negocio'
        assert msgs[2].content == 'Análisis de prueba'

        # El análisis automático consume 1 token (source 'copilot_vz').
        tx = AITokenTransaction.query.filter_by(
            user_id=sample_user.id, type='consume',
        ).order_by(AITokenTransaction.id.desc()).first()
        assert tx is not None
        assert tx.source == 'copilot_vz'
        assert tx.amount == -1

    def test_consume_reuses_event_conversation(
            self, client, db, sample_user, sample_restaurant, wallet,
            sale_factory, business_event, llm_capture):
        """Dos eventos consecutivos reusan la misma conversación."""
        sale_factory(sample_restaurant)
        self._login(client, sample_user)

        resp1 = client.post(f'/insights/api/events/{business_event.id}/consume')
        assert resp1.status_code == 200
        conv_id = resp1.get_json()['conversation_id']

        ev2 = CopilotBusinessEvent(
            restaurant_id=sample_restaurant.id,
            kind='record_week',
            priority=70,
            title='¡Semana récord! 📈',
            preview='Esta semana tus ventas alcanzaron un récord.',
            template_key='record_week',
            template_data=json.dumps({'revenue': '200.000', 'pct': 30}),
            active=True,
        )
        db.session.add(ev2)
        db.session.commit()

        resp2 = client.post(f'/insights/api/events/{ev2.id}/consume')
        assert resp2.status_code == 200
        assert resp2.get_json()['conversation_id'] == conv_id

    def test_consume_returns_redirect_even_if_llm_fails(
            self, client, db, sample_user, sample_restaurant, wallet,
            sale_factory, business_event, llm_capture):
        """Fallo del LLM → el evento igual se consume y redirige (no se atasca)."""
        sale_factory(sample_restaurant)
        llm_capture.error = RuntimeError('DeepSeek caído')
        self._login(client, sample_user)

        resp = client.post(f'/insights/api/events/{business_event.id}/consume')
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert resp.get_json()['success'] is True

        db.session.refresh(business_event)
        assert business_event.active is False
