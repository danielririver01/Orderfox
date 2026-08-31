"""
Tests del cierre del agujero de costos de Copilot VZ (v1.4.0).

Cubre:
- Consumo de tokens: 1ª consulta cobra 1 token, follow-ups gratis hasta el
  tope (COPILOT_MAX_FOLLOW_UPS), el N+1 abre un bloque nuevo (cobra y resetea).
- Sin tokens en el tope → no_credits sin descuento adicional.
- `reserve_follow_up` atómico (UPDATE condicional, sin TOCTOU).
- Elite exento del tope de seguimientos, pero NO del truncamiento de historial.
- Truncamiento de historial a COPILOT_MAX_HISTORY_MESSAGES (todos los planes).
- Telemetría AILlmCall (source, conversation, restaurant, tokens estimados).
- Origen del consumo: AITokenTransaction.source ('copilot_vz' vs default 'scanner_ia').
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import (
    AILlmCall,
    AITokenTransaction,
    AITokenWallet,
    Category,
    CopilotConversation,
    Order,
    Product,
    Restaurant,
    User,
)
from app.services.insights import conversation_service as cs
from app.services.insights import prompt_builder
from app.services.token_service import TokenService


@pytest.fixture(autouse=True)
def _mock_data_context(monkeypatch):
    """build_context usa dayofweek() (MySQL), que no existe en SQLite.

    Estos tests verifican el tope de seguimientos, tokens y truncamiento de
    historial, no el contenido real del contexto de datos, así que se inyecta
    un dict mínimo válido para el prompt del LLM.
    """
    def _fake_build_context(restaurant_id, days=60):
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
    """El logro 'primer_analisis' otorga +5 tokens extra al primer análisis.

    Es un efecto colateral ajeno al tope de seguimientos; se neutraliza para
    aislar la lógica de consumo/cap que aquí se prueba (patrón de
    MAIL_SUPPRESS_SEND en conftest).
    """
    monkeypatch.setattr(
        'app.services.insights.message_handler.eval_achievement',
        lambda *a, **k: None)


# ── Fixtures ───────────────────────────────────────────────────────────────

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
        self.return_value = '{"text": "Respuesta de prueba", "chart": null}'
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


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


@pytest.fixture
def fake_deepseek(monkeypatch):
    """Parchea requests.post para simular DeepSeek con telemetría de usage."""
    payload = {
        'choices': [{'message': {
            'content': '{"text": "Análisis de prueba", "chart": null}'}}],
        'usage': {'prompt_tokens': 120, 'completion_tokens': 40},
    }

    def _post(*args, **kwargs):
        return _FakeResp(payload)

    monkeypatch.setattr('app.services.insights.llm_service.requests.post', _post)


@pytest.fixture
def elite_restaurant(db):
    r = Restaurant(
        name='Test Elite', slug='test-elite', whatsapp_phone='+573007777777',
        plan_type='elite', is_active=True, is_open=True,
        subscription_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        has_used_trial=False,
    )
    db.session.add(r)
    db.session.commit()
    return r


@pytest.fixture
def elite_user(db, elite_restaurant):
    u = User(
        restaurant_id=elite_restaurant.id,
        username='admin-elite', email='elite@test.com',
        password='not-used', clerk_id='clerk_elite_1',
    )
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def elite_wallet(db, elite_user):
    w = AITokenWallet(
        user_id=elite_user.id, plan_limit=3000, plan_tokens=5,
        extra_tokens=0, tokens_used_month=0,
    )
    db.session.add(w)
    db.session.commit()
    return w


class _Auth:
    """Login con sesión (rutas /insights/api exentas de CSRF)."""

    def _login(self, client, user):
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

    def _conv_id(self, client):
        resp = client.post('/insights/api/conversations', json={})
        assert resp.status_code == 201, resp.get_data(as_text=True)
        return resp.get_json()['data']['id']

    def _post_message(self, client, cid, content):
        return client.post(
            f'/insights/api/conversations/{cid}/messages',
            json={'content': content},
        )


# ── Consumo de tokens y tope de follow-ups (API) ───────────────────────────

class TestFollowUpCap(_Auth):
    """1 token por bloque; follow-ups gratis hasta el tope."""

    def test_first_message_consumes_one_token(self, client, db, sample_user,
                                              sample_restaurant, wallet,
                                              sale_factory, llm_capture):
        sale_factory(sample_restaurant)
        self._login(client, sample_user)
        cid = self._conv_id(client)

        resp = self._post_message(client, cid, '¿Por qué bajaron mis ventas?')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        assert body['type'] == 'analysis'
        assert body['metadata']['credits_used'] == 1

        w = AITokenWallet.query.filter_by(user_id=sample_user.id).first()
        assert w.plan_tokens == 4
        assert w.tokens_used_month == 1

    def test_follow_ups_free_until_cap_then_charges_and_resets(
            self, client, app, db, sample_user, sample_restaurant, wallet,
            sale_factory, llm_capture, monkeypatch):
        monkeypatch.setitem(app.config, 'COPILOT_MAX_FOLLOW_UPS', 2)
        sale_factory(sample_restaurant)
        self._login(client, sample_user)
        cid = self._conv_id(client)

        # 1er mensaje: consume 1 token (5 → 4).
        first = self._post_message(client, cid, '¿Por qué bajaron mis ventas?')
        assert first.status_code == 200
        assert first.get_json()['metadata']['credits_used'] == 1

        # Follow-ups 1..N (tope=2): gratis.
        for i in range(2):
            resp = self._post_message(client, cid, f'¿Por qué cayeron mis ventas? {i}')
            assert resp.status_code == 200
            assert resp.get_json()['metadata']['credits_used'] == 0

        w = AITokenWallet.query.filter_by(user_id=sample_user.id).first()
        assert w.plan_tokens == 4
        assert w.tokens_used_month == 1

        db.session.expire_all()
        conv = CopilotConversation.query.get(cid)
        assert conv.follow_up_count == 2

        # N+1: consume token nuevo y resetea el contador (bloque nuevo).
        charged = self._post_message(client, cid, '¿Cuál es la tendencia de mis ventas?')
        assert charged.status_code == 200
        assert charged.get_json()['metadata']['credits_used'] == 1
        w = AITokenWallet.query.filter_by(user_id=sample_user.id).first()
        assert w.plan_tokens == 3
        assert w.tokens_used_month == 2

        db.session.expire_all()
        conv = CopilotConversation.query.get(cid)
        assert conv.follow_up_count == 0

        # Siguiente follow-up vuelve a ser gratis (nuevo bloque).
        free_again = self._post_message(client, cid, '¿Qué recomiendas para mejorar?')
        assert free_again.status_code == 200
        assert free_again.get_json()['metadata']['credits_used'] == 0
        w = AITokenWallet.query.filter_by(user_id=sample_user.id).first()
        assert w.plan_tokens == 3

    def test_no_credits_at_cap_returns_no_credits(self, client, app, db,
                                                  sample_user, sample_restaurant,
                                                  sale_factory, llm_capture,
                                                  monkeypatch):
        monkeypatch.setitem(app.config, 'COPILOT_MAX_FOLLOW_UPS', 1)
        w = AITokenWallet(
            user_id=sample_user.id, plan_limit=50, plan_tokens=1,
            extra_tokens=0, tokens_used_month=0,
        )
        db.session.add(w)
        db.session.commit()
        sale_factory(sample_restaurant)
        self._login(client, sample_user)
        cid = self._conv_id(client)

        first = self._post_message(client, cid, '¿Por qué bajaron mis ventas?')
        assert first.status_code == 200
        assert first.get_json()['metadata']['credits_used'] == 1
        assert AITokenWallet.query.filter_by(user_id=sample_user.id).first().plan_tokens == 0

        # Follow-up gratis dentro del tope (tope=1).
        free = self._post_message(client, cid, '¿Por qué cayeron mis ventas?')
        assert free.status_code == 200
        assert free.get_json()['metadata']['credits_used'] == 0

        # Siguiente: tope alcanzado y sin tokens → no_credits, sin descuento.
        blocked = self._post_message(client, cid, '¿Cuál es la tendencia?')
        assert blocked.status_code == 200
        body = blocked.get_json()
        assert body['success'] is True
        assert body['type'] == 'no_credits'
        assert body['error_code'] == 'INSUFFICIENT_TOKENS'
        assert AITokenWallet.query.filter_by(user_id=sample_user.id).first().plan_tokens == 0

    def test_regeneration_does_not_increment_counter(self, client, app, db,
                                                     sample_user, sample_restaurant,
                                                     wallet, sale_factory,
                                                     llm_capture, monkeypatch):
        """Editar/regenerar (replace_tail) no cuenta como follow-up ni cobra."""
        monkeypatch.setitem(app.config, 'COPILOT_MAX_FOLLOW_UPS', 1)
        sale_factory(sample_restaurant)
        self._login(client, sample_user)
        cid = self._conv_id(client)

        first = self._post_message(client, cid, '¿Por qué bajaron mis ventas?')
        assert first.status_code == 200
        assert first.get_json()['metadata']['credits_used'] == 1
        user_msg_id = first.get_json()['message_id']

        # Regenerar se indica con message_id + replace_tail: no debe cobrar
        # ni incrementar el contador (no penaliza corregir una pregunta).
        resp = client.post(
            f'/insights/api/conversations/{cid}/messages',
            json={'message_id': user_msg_id, 'replace_tail': True},
        )
        assert resp.status_code == 200
        assert resp.get_json()['metadata']['credits_used'] == 0

        db.session.expire_all()
        conv = CopilotConversation.query.get(cid)
        assert conv.follow_up_count == 0


# ── Origen del consumo de tokens ───────────────────────────────────────────

class TestTokenSource:
    """AITokenTransaction.source distingue copilot_vz de scanner_ia."""

    def test_insights_consumption_uses_copilot_vz_source(
            self, client, db, sample_user, sample_restaurant, wallet,
            sale_factory, llm_capture):
        sale_factory(sample_restaurant)
        auth = _Auth()
        auth._login(client, sample_user)
        cid = auth._conv_id(client)
        resp = auth._post_message(client, cid, '¿Por qué bajaron mis ventas?')
        assert resp.status_code == 200

        tx = AITokenTransaction.query.filter_by(
            user_id=sample_user.id, type='consume',
        ).order_by(AITokenTransaction.id.desc()).first()
        assert tx is not None
        assert tx.source == 'copilot_vz'
        assert tx.amount == -1

    def test_default_source_is_scanner_ia(self, db, sample_user, wallet):
        """Backward-compat: consume_token() sin source registra 'scanner_ia'."""
        ok, err = TokenService.consume_token(sample_user)
        assert ok and err is None
        tx = AITokenTransaction.query.filter_by(
            user_id=sample_user.id, type='consume',
        ).order_by(AITokenTransaction.id.desc()).first()
        assert tx.source == 'scanner_ia'


# ── Truncamiento de historial (todos los planes) ───────────────────────────

class TestHistoryTruncation(_Auth):
    """COPILOT_MAX_HISTORY_MESSAGES acota el historial enviado al LLM."""

    def test_llm_call_history_truncated_to_config(self, client, app, db,
                                                  sample_user, sample_restaurant,
                                                  wallet, sale_factory,
                                                  llm_capture, monkeypatch):
        monkeypatch.setitem(app.config, 'COPILOT_MAX_FOLLOW_UPS', 50)
        monkeypatch.setitem(app.config, 'COPILOT_MAX_HISTORY_MESSAGES', 4)
        sale_factory(sample_restaurant)
        self._login(client, sample_user)
        cid = self._conv_id(client)

        for i in range(1, 10):
            resp = self._post_message(client, cid, f'msg {i}')
            assert resp.status_code == 200, resp.get_data(as_text=True)

        assert llm_capture.calls
        last_call = llm_capture.calls[-1]
        # system + ≤ max_history historial + mensaje actual.
        assert len(last_call) <= 6
        assert last_call[-1]['content'] == 'msg 9'
        history = last_call[1:-1]
        assert len(history) <= 4
        contents = [m['content'] for m in history]
        assert 'msg 8' in contents
        assert 'msg 7' in contents
        assert 'msg 1' not in contents

    def test_build_analysis_messages_uses_config_default(self, app, db,
                                                         sample_user,
                                                         sample_restaurant,
                                                         monkeypatch):
        from app.models import CopilotMessage

        monkeypatch.setitem(app.config, 'COPILOT_MAX_HISTORY_MESSAGES', 3)
        conv = cs.create_conversation(sample_user.id, sample_restaurant.id)
        for i in range(8):
            m = CopilotMessage(conversation_id=conv.id, role='user',
                               content=f'hist {i}')
            db.session.add(m)
        db.session.commit()

        history = cs.get_messages(conv.id)
        messages = prompt_builder.build_analysis_messages(
            'pregunta actual', {'dummy': 1}, history=history,
        )
        contents = [m['content'] for m in messages if m['role'] != 'system']
        assert contents[-1] == 'pregunta actual'
        assert len(contents) - 1 == 3  # solo los últimos 3 de historial
        assert 'hist 7' in contents
        assert 'hist 0' not in contents


# ── Telemetría de costo (AILlmCall) ────────────────────────────────────────

class TestLLMCallTelemetry(_Auth):
    """Cada llamada al LLM queda registrada en ai_llm_calls."""

    def test_telemetry_recorded_for_insights(self, client, db, sample_user,
                                             sample_restaurant, wallet,
                                             sale_factory, fake_deepseek):
        sale_factory(sample_restaurant)
        self._login(client, sample_user)
        cid = self._conv_id(client)
        resp = self._post_message(client, cid, '¿Por qué bajaron mis ventas?')
        assert resp.status_code == 200
        assert resp.get_json()['type'] == 'analysis'

        row = AILlmCall.query.filter_by(conversation_id=cid).first()
        assert row is not None
        assert row.source == 'insights'
        assert row.conversation_id == cid
        assert row.restaurant_id == sample_restaurant.id
        assert row.model == 'deepseek-v4-flash'
        assert row.input_tokens_est == 120
        assert row.output_tokens_est == 40

    def test_telemetry_is_silent_on_error(self, client, app, db, sample_user,
                                          sample_restaurant, wallet,
                                          sale_factory, fake_deepseek,
                                          monkeypatch):
        """Si falla el registro de telemetría, la llamada no se rompe."""
        sale_factory(sample_restaurant)

        class _ExplodingLlmCall:
            def __init__(self, **kwargs):
                raise RuntimeError('registro de telemetría caído')

        monkeypatch.setattr(
            'app.services.insights.llm_service.AILlmCall',
            _ExplodingLlmCall)
        self._login(client, sample_user)
        cid = self._conv_id(client)
        resp = self._post_message(client, cid, '¿Por qué bajaron mis ventas?')
        assert resp.status_code == 200
        assert resp.get_json()['type'] == 'analysis'
        assert AILlmCall.query.filter_by(conversation_id=cid).first() is None


# ── Elite: exento del tope, no del truncamiento ────────────────────────────

class TestElite(_Auth):
    """Elite conserva follow-ups gratis; el truncamiento aplica igual."""

    def test_elite_follow_ups_never_charged(self, client, db, elite_user,
                                            elite_restaurant, elite_wallet,
                                            sale_factory, llm_capture):
        sale_factory(elite_restaurant)
        self._login(client, elite_user)
        cid = self._conv_id(client)

        first = self._post_message(client, cid, '¿Por qué bajaron mis ventas?')
        assert first.status_code == 200
        assert first.get_json()['metadata']['credits_used'] == 1
        assert AITokenWallet.query.filter_by(user_id=elite_user.id).first().plan_tokens == 4

        # 10 follow-ups: todos gratis, el contador no se toca.
        for i in range(10):
            resp = self._post_message(client, cid, f'¿Por qué cayeron mis ventas? {i}')
            assert resp.status_code == 200
            assert resp.get_json()['metadata']['credits_used'] == 0

        w = AITokenWallet.query.filter_by(user_id=elite_user.id).first()
        assert w.plan_tokens == 4
        assert w.tokens_used_month == 1

        db.session.expire_all()
        conv = CopilotConversation.query.get(cid)
        assert conv.follow_up_count == 0

    def test_elite_history_still_truncated(self, client, app, db, elite_user,
                                           elite_restaurant, elite_wallet,
                                           sale_factory, llm_capture,
                                           monkeypatch):
        monkeypatch.setitem(app.config, 'COPILOT_MAX_HISTORY_MESSAGES', 3)
        monkeypatch.setitem(app.config, 'COPILOT_MAX_FOLLOW_UPS', 50)
        sale_factory(elite_restaurant)
        self._login(client, elite_user)
        cid = self._conv_id(client)

        for i in range(1, 8):
            resp = self._post_message(client, cid, f'msg {i}')
            assert resp.status_code == 200, resp.get_data(as_text=True)

        last_call = llm_capture.calls[-1]
        assert last_call[-1]['content'] == 'msg 7'
        history = last_call[1:-1]
        assert len(history) <= 3
        contents = [m['content'] for m in history]
        assert 'msg 1' not in contents


# ── reserve_follow_up: atomicidad ──────────────────────────────────────────

class TestReserveFollowUp:
    """reserve_follow_up usa un UPDATE condicional atómico.

    Se prueba de forma determinista (sin hilos): con SQLite en memoria
    (StaticPool, conexión única) una carrera real con threads sería flaky,
    pero el contrato observable de la atomicidad es que N reservas con tope M
    solo dejan pasar M — exactamente lo que aquí se verifica.
    """

    def test_conditional_update_only_one_passes_at_cap(self, db, sample_user,
                                                       sample_restaurant):
        conv = cs.create_conversation(sample_user.id, sample_restaurant.id)
        assert cs.reserve_follow_up(conv.id, 1) is True
        assert cs.reserve_follow_up(conv.id, 1) is False

        db.session.expire_all()
        conv = CopilotConversation.query.get(conv.id)
        assert conv.follow_up_count == 1

    def test_increments_until_max(self, db, sample_user, sample_restaurant):
        conv = cs.create_conversation(sample_user.id, sample_restaurant.id)
        for _ in range(3):
            assert cs.reserve_follow_up(conv.id, 3) is True
        assert cs.reserve_follow_up(conv.id, 3) is False

        db.session.expire_all()
        conv = CopilotConversation.query.get(conv.id)
        assert conv.follow_up_count == 3

    def test_mark_analysis_active_resets_counter(self, db, sample_user,
                                                 sample_restaurant):
        conv = cs.create_conversation(sample_user.id, sample_restaurant.id)
        cs.reserve_follow_up(conv.id, 99)
        cs.reserve_follow_up(conv.id, 99)
        cs.mark_analysis_active(conv.id)

        db.session.expire_all()
        conv = CopilotConversation.query.get(conv.id)
        assert conv.analysis_active is True
        assert conv.follow_up_count == 0

    def test_clear_analysis_active_resets_counter(self, db, sample_user,
                                                  sample_restaurant):
        conv = cs.create_conversation(sample_user.id, sample_restaurant.id)
        cs.mark_analysis_active(conv.id)
        cs.reserve_follow_up(conv.id, 99)
        cs.clear_analysis_active(conv.id)

        db.session.expire_all()
        conv = CopilotConversation.query.get(conv.id)
        assert conv.analysis_active is False
        assert conv.follow_up_count == 0
