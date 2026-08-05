"""
Tests del Copilot de Caja (Centro de Caja).

Cubre el flujo independiente de /insights:
- Creación/listado de conversaciones con source='cash_register' (aislamiento
  bidireccional con insights).
- Orquestador: grounding de datos por paid_at (coincide con get_summary),
  consumo de token SOLO en la primera consulta, follow-ups gratis.
- Validación de rango custom (400 + rollback del mensaje).
- Sin créditos → no_credits. IDOR → 404.
- Prompt de sistema propio (CASH_SYSTEM_PROMPT).
"""

import json
from datetime import datetime, timezone, timedelta

import pytest

from app.models import AITokenWallet, CopilotConversation, Order
from app.services.cash_register_service import CashRegisterService
from app.services.insights import prompt_builder


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def cash_wallet(db, sample_user):
    wallet = AITokenWallet(
        user_id=sample_user.id, plan_limit=50, plan_tokens=5,
        extra_tokens=0, tokens_used_month=0,
    )
    db.session.add(wallet)
    db.session.commit()
    return wallet


@pytest.fixture
def paid_order_factory(db, sample_restaurant):
    counter = {'n': 0}

    def _make(total, method, paid_at, amount_received=None):
        counter['n'] += 1
        o = Order(
            restaurant_id=sample_restaurant.id,
            order_number=f'CC-{counter["n"]:04d}',
            customer_name='Cliente Caja',
            status='delivered',
            total=total,
            payment_method=method,
            amount_received=amount_received,
            paid_at=paid_at,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db.session.add(o)
        db.session.commit()
        return o

    return _make


class _LLMCapture:
    """Captura los mensajes enviados al LLM y permite inyectar respuesta/error."""

    def __init__(self):
        self.calls = []
        self.return_value = '{"text": "Respuesta de prueba", "chart": null}'
        self.error = None

    def __call__(self, messages, temperature=0.35, max_tokens=2000):
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


class _Auth:
    """Login con sesión + headers CSRF (patrón de test_cash_register)."""

    import re as _re

    def _login(self, client, user):
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

    def _csrf_headers(self, client):
        page = client.get('/cash-register/')
        match = self._re.search(
            r'name="csrf-token" content="([^"]+)"', page.get_data(as_text=True))
        assert match, 'no se encontró el token CSRF en /cash-register/'
        return {'X-CSRFToken': match.group(1)}


# ── Rutas: conversaciones ──────────────────────────────────────────────────

class TestCashCopilotConversations(_Auth):
    """Creación y listado de conversaciones de caja (aislamiento de source)."""

    def test_create_conversation_uses_cash_source(self, client, db, sample_user):
        self._login(client, sample_user)
        resp = client.post('/cash-register/copilot/conversations', json={},
                           headers=self._csrf_headers(client))
        assert resp.status_code == 201
        body = resp.get_json()
        assert body['success'] is True
        assert body['data']['source'] == 'cash_register'
        conv = CopilotConversation.query.get(body['data']['id'])
        assert conv.source == 'cash_register'
        assert conv.user_id == sample_user.id

    def test_list_only_cash_conversations(self, client, db, sample_user,
                                          sample_restaurant):
        from app.services.insights import conversation_service as cs
        cs.create_conversation(sample_user.id, sample_restaurant.id,
                               title='Chat insights', source='insights')
        cash = cs.create_conversation(sample_user.id, sample_restaurant.id,
                                      title='Caja de hoy', source='cash_register')

        self._login(client, sample_user)
        resp = client.get('/cash-register/copilot/conversations')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        ids = {c['id'] for c in data}
        assert ids == {cash.id}
        assert data[0]['title'] == 'Caja de hoy'

    def test_cash_conversation_not_visible_in_insights(self, client, db,
                                                       sample_user,
                                                       sample_restaurant):
        from app.services.insights import conversation_service as cs
        cash = cs.create_conversation(sample_user.id, sample_restaurant.id,
                                      title='Caja', source='cash_register')

        self._login(client, sample_user)
        resp = client.get('/insights/api/conversations')
        assert resp.status_code == 200
        ids = {c['id'] for c in resp.get_json()['data']}
        assert cash.id not in ids

    def test_search_conversations_source_scoped(self, client, db, sample_user,
                                                sample_restaurant):
        from app.services.insights import conversation_service as cs
        cash = cs.create_conversation(sample_user.id, sample_restaurant.id,
                                      title='Caja de hoy', source='cash_register')
        cs.create_conversation(sample_user.id, sample_restaurant.id,
                               title='Caja en insights', source='insights')

        self._login(client, sample_user)
        resp = client.get('/cash-register/copilot/conversations?q=caja')
        assert resp.status_code == 200
        ids = {c['id'] for c in resp.get_json()['data']}
        assert ids == {cash.id}

    def test_create_conversation_requires_auth(self, client, db):
        resp = client.post('/cash-register/copilot/conversations', json={})
        # Sin sesión: redirige (302), 401 (JSON) o se bloquea por CSRF (400);
        # en ningún caso debe crear una conversación.
        assert resp.status_code in (302, 401, 400)
        assert CopilotConversation.query.count() == 0

    def test_get_conversation_returns_messages(self, client, db, sample_user,
                                               sample_restaurant):
        from app.services.insights import conversation_service as cs
        conv = cs.create_conversation(sample_user.id, sample_restaurant.id,
                                      title='Caja de hoy', source='cash_register')
        cs.add_message(conv.id, 'user', '¿Cuánto vendí hoy?')
        cs.add_message(conv.id, 'assistant', 'Vendiste $100.000 hoy.',
                       {'chart': {'type': 'bar', 'title': 'Ventas'}})

        self._login(client, sample_user)
        resp = client.get(f'/cash-register/copilot/conversations/{conv.id}')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['id'] == conv.id
        assert data['source'] == 'cash_register'
        assert len(data['messages']) == 2
        roles = [m['role'] for m in data['messages']]
        assert roles == ['user', 'assistant']
        assert data['messages'][1]['metadata']['chart']['title'] == 'Ventas'

    def test_get_conversation_rejects_insights_source(self, client, db,
                                                      sample_user,
                                                      sample_restaurant):
        from app.services.insights import conversation_service as cs
        conv = cs.create_conversation(sample_user.id, sample_restaurant.id,
                                      title='Chat insights', source='insights')

        self._login(client, sample_user)
        resp = client.get(f'/cash-register/copilot/conversations/{conv.id}')
        assert resp.status_code == 404

    def test_get_conversation_idor_404(self, client, db, sample_user,
                                       sample_restaurant):
        """Una conversación de otro usuario no debe ser alcanzable."""
        from app.services.insights import conversation_service as cs
        foreign = cs.create_conversation(
            9999, 9999, title='Ajeno', source='cash_register')

        self._login(client, sample_user)
        resp = client.get(f'/cash-register/copilot/conversations/{foreign.id}')
        assert resp.status_code == 404

    def test_get_conversation_empty_messages(self, client, db, sample_user,
                                             sample_restaurant):
        from app.services.insights import conversation_service as cs
        conv = cs.create_conversation(sample_user.id, sample_restaurant.id,
                                      title='Caja vacía', source='cash_register')

        self._login(client, sample_user)
        resp = client.get(f'/cash-register/copilot/conversations/{conv.id}')
        assert resp.status_code == 200
        assert resp.get_json()['data']['messages'] == []


# ── Orquestador: flujo de mensaje ──────────────────────────────────────────

class TestCashCopilotMessage(_Auth):
    """Envío de mensajes: grounding paid_at, tokens, errores, IDOR."""

    def _conv_id(self, client):
        resp = client.post('/cash-register/copilot/conversations', json={},
                           headers=self._csrf_headers(client))
        return resp.get_json()['data']['id']

    def _post_message(self, client, cid, payload):
        return client.post(
            f'/cash-register/copilot/conversations/{cid}/messages',
            json=payload, headers=self._csrf_headers(client))

    def _summary_sales(self, restaurant_id):
        start, end = CashRegisterService.resolve_range('today')
        return CashRegisterService.get_summary(restaurant_id, start, end)

    def test_grounding_matches_paid_at_summary(self, client, db, sample_user,
                                               sample_restaurant,
                                               cash_wallet, paid_order_factory,
                                               llm_capture):
        """El contexto enviado al LLM debe coincidir con get_summary (paid_at)."""
        now = datetime.now(timezone.utc)
        paid_order_factory(25000, 'cash', now, amount_received=30000)
        paid_order_factory(15000, 'nequi', now)

        self._login(client, sample_user)
        cid = self._conv_id(client)
        resp = self._post_message(
            client, cid,
            {'content': '¿Cómo vendí hoy?', 'period': {'range': 'today'}})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        assert body['type'] == 'analysis'
        assert body['content'] == 'Respuesta de prueba'
        assert body['metadata']['source'] == 'cash_register'
        assert body['metadata']['credits_used'] == 1

        # El LLM recibió contexto con los totales reales (paid_at).
        assert llm_capture.calls, 'el LLM debió ser invocado'
        system = llm_capture.calls[0][0]['content']
        expected = self._summary_sales(sample_restaurant.id)
        assert '"total_sales": 40000' in system
        assert f'"total_orders": {expected["total_orders"]}' in system
        assert '"cash": {"total": 25000' in system or '"total": 25000' in system

    def test_single_token_consumed_and_followup_free(self, client, db,
                                                     sample_user,
                                                     sample_restaurant,
                                                     cash_wallet,
                                                     paid_order_factory,
                                                     llm_capture):
        """1ª consulta consume 1 token; follow-up (analysis_active) es gratis."""
        now = datetime.now(timezone.utc)
        paid_order_factory(10000, 'cash', now, amount_received=10000)

        self._login(client, sample_user)
        cid = self._conv_id(client)

        first = self._post_message(
            client, cid, {'content': '¿Ventas?', 'period': {'range': 'today'}})
        assert first.status_code == 200
        wallet = AITokenWallet.query.filter_by(user_id=sample_user.id).first()
        assert wallet.plan_tokens == 4
        assert wallet.tokens_used_month == 1

        second = self._post_message(
            client, cid,
            {'content': '¿Y en efectivo?', 'period': {'range': 'today'}})
        assert second.status_code == 200
        assert second.get_json()['metadata']['credits_used'] == 0

        wallet = AITokenWallet.query.filter_by(user_id=sample_user.id).first()
        assert wallet.plan_tokens == 4
        assert wallet.tokens_used_month == 1

        conv = CopilotConversation.query.get(cid)
        assert conv.analysis_active is True

    def test_custom_range_missing_dates_400_rollback(self, client, db,
                                                     sample_user,
                                                     sample_restaurant,
                                                     cash_wallet, llm_capture):
        """Rango custom sin fechas → 400; el mensaje se descarta y no cobra."""
        self._login(client, sample_user)
        cid = self._conv_id(client)
        resp = self._post_message(
            client, cid,
            {'content': '¿Cómo fue?', 'period': {'range': 'custom'}})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body['success'] is False

        # El mensaje del usuario se elimina (rollback).
        conv = CopilotConversation.query.get(cid)
        assert conv.messages.count() == 0
        assert not llm_capture.calls, 'el LLM no debe invocarse'
        wallet = AITokenWallet.query.filter_by(user_id=sample_user.id).first()
        assert wallet.plan_tokens == 5

    def test_no_credits_response(self, client, db, sample_user, sample_restaurant):
        """Sin wallet/sin tokens → respuesta type=no_credits."""
        self._login(client, sample_user)
        cid = self._conv_id(client)
        resp = self._post_message(
            client, cid, {'content': '¿Ventas?', 'period': {'range': 'today'}})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        assert body['type'] == 'no_credits'
        assert body['error_code'] in ('NO_WALLET', 'INSUFFICIENT_TOKENS')

    def test_llm_error_rolls_back_message_and_clears_active(self, client, db,
                                                            sample_user,
                                                            sample_restaurant,
                                                            cash_wallet,
                                                            llm_capture):
        """Error del LLM → 502, mensaje eliminado, analysis_active limpio."""
        from app.services.insights.llm_service import LLMServiceError
        llm_capture.error = LLMServiceError('boom')
        self._login(client, sample_user)
        cid = self._conv_id(client)
        resp = self._post_message(
            client, cid, {'content': '¿Ventas?', 'period': {'range': 'today'}})
        assert resp.status_code == 502
        conv = CopilotConversation.query.get(cid)
        assert conv.messages.count() == 0
        assert conv.analysis_active is False

    def test_idor_other_user_conversation_404(self, client, db, sample_user,
                                              sample_restaurant):
        """Una conversación de otro restaurante/usuario no debe ser alcanzable."""
        from app.services.insights import conversation_service as cs
        foreign = cs.create_conversation(
            9999, 9999, title='Ajeno', source='cash_register')

        self._login(client, sample_user)
        resp = self._post_message(
            client, foreign.id,
            {'content': 'hola', 'period': {'range': 'today'}})
        assert resp.status_code == 404

    def test_empty_content_400(self, client, db, sample_user, sample_restaurant,
                               cash_wallet, llm_capture):
        self._login(client, sample_user)
        cid = self._conv_id(client)
        resp = self._post_message(
            client, cid, {'content': '   ', 'period': {'range': 'today'}})
        assert resp.status_code == 400


# ── Orquestador: prompt ────────────────────────────────────────────────────

class TestCashCopilotPrompt(_Auth):
    """El orquestador de caja usa su propio system prompt."""

    def _conv_id(self, client):
        resp = client.post('/cash-register/copilot/conversations', json={},
                           headers=self._csrf_headers(client))
        return resp.get_json()['data']['id']

    def test_cash_system_prompt_used(self, client, db, sample_user,
                                     sample_restaurant, cash_wallet,
                                     llm_capture):
        """El system message usa CASH_SYSTEM_PROMPT, no el de Copilot VZ."""
        self._login(client, sample_user)
        cid = self._conv_id(client)
        client.post(
            f'/cash-register/copilot/conversations/{cid}/messages',
            json={'content': '¿Ventas?', 'period': {'range': 'today'}},
            headers=self._csrf_headers(client))

        assert llm_capture.calls
        system = llm_capture.calls[0][0]['content']
        assert prompt_builder.CASH_SYSTEM_PROMPT.split('\n')[0] in system
        assert 'Centro de Caja' in system
        # No debe incluirse el prompt de insights (sistema de análisis).
        assert 'Clasificador' not in system

    def test_build_analysis_messages_system_prompt_param(self):
        """Backward-compat: sin param usa SYSTEM_PROMPT; con param usa el custom."""
        ctx = {'dato': 1}
        default = prompt_builder.build_analysis_messages('hola', ctx)
        assert prompt_builder.SYSTEM_PROMPT.split('\n')[0] in default[0]['content']

        custom = prompt_builder.build_analysis_messages(
            'hola', ctx, system_prompt=prompt_builder.CASH_SYSTEM_PROMPT)
        assert prompt_builder.CASH_SYSTEM_PROMPT.split('\n')[0] in custom[0]['content']
        assert prompt_builder.SYSTEM_PROMPT.split('\n')[0] not in custom[0]['content']
