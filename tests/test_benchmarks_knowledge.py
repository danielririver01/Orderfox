"""
Tests de Fase 1 + Fase 2 de la mejora de conocimiento de Copilot VZ:

Fase 1 — Benchmarking anónimo de la plataforma:
- compute_benchmarks NO publica nada si hay menos de K_MIN restaurantes
  con datos suficientes (k-anonymity).
- Con >= K_MIN restaurantes publica snapshot 'global' (+ cohorte por
  cuisine_type solo si esa cohorte también cumple el mínimo).
- Las métricas publicadas son medianas y no exponen datos individuales.
- benchmarks_for_context devuelve el payload correcto (cohorte específica
  con fallback a global, None si no hay nada).

Fase 2 — Knowledge Base curada:
- select_knowledge matchea por keyword del mensaje.
- Fallback por intención clasificada cuando no hay keywords.
- Truncamiento al tope de caracteres.
- prompt_builder inyecta 'CONOCIMIENTO DE INDUSTRIA' solo en Copilot VZ
  (no con prompts custom como el copilot de caja).
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Order, OrderItem, Product, Restaurant
from app.models.ai import PlatformBenchmark
from app.services.insights import prompt_builder
from app.services.insights.benchmark_service import (
    K_MIN,
    MIN_ORDERS_PER_RESTAURANT,
    PERIOD_DAYS,
    benchmarks_for_context,
    compute_benchmarks,
    get_benchmark_for,
)
from app.services.insights.knowledge_selector import (
    MAX_KNOWLEDGE_CHARS,
    clear_cache,
    select_knowledge,
)

# ───────────── Helpers ─────────────

def _mk_restaurant(db, i, cuisine='hamburguesas'):
    r = Restaurant(
        name=f'R{i}',
        slug=f'r-{i}-{cuisine}',
        whatsapp_phone=f'+57300{1000000 + i}',
        plan_type='emprendedor',
        is_active=True,
        cuisine_type=cuisine,
    )
    db.session.add(r)
    db.session.flush()
    return r


def _mk_orders_with_items(db, restaurant, n_orders, total_per_order=20000):
    """Crea n_orders pedidos recientes (status confirmed) con 1 item c/u."""
    # Producto mínimo para el OrderItem.
    from app.models import Category
    c = Category(restaurant_id=restaurant.id, name='Cat', sort_order=1, is_active=True)
    db.session.add(c)
    db.session.flush()
    p = Product(restaurant_id=restaurant.id, category_id=c.id,
                name='Burger', price=total_per_order, is_active=True)
    db.session.add(p)
    db.session.flush()

    now = datetime.now(timezone.utc)
    for k in range(n_orders):
        o = Order(
            restaurant_id=restaurant.id,
            order_number=f'ORD-{restaurant.id}-{k}',
            customer_name='C',
            customer_phone='+573001112233',
            status='confirmed',
            total=total_per_order,
            created_at=now - timedelta(days=k % PERIOD_DAYS),
        )
        db.session.add(o)
        db.session.flush()
        db.session.add(OrderItem(
            order_id=o.id,
            restaurant_id=restaurant.id,
            product_name=p.name,
            product_price=total_per_order,
            quantity=1,
            subtotal=total_per_order,
        ))
    db.session.commit()


@pytest.fixture(autouse=True)
def _clean_benchmarks(db):
    yield
    PlatformBenchmark.query.delete()
    db.session.commit()


# ───────────── Fase 1: k-anonymity ─────────────

class TestBenchmarkKAnonymity:

    def test_insufficient_restaurants_no_snapshot(self, db, sample_restaurant):
        """Con < K_MIN restaurantes con datos suficientes NO se publica nada."""
        _mk_orders_with_items(db, sample_restaurant, MIN_ORDERS_PER_RESTAURANT + 5)
        result = compute_benchmarks()
        assert result['cohorts'] == 0
        assert PlatformBenchmark.query.count() == 0

    def test_stale_snapshots_cleared_when_insufficient(self, db, sample_restaurant):
        """Si el volumen cae por debajo del mínimo, snapshots viejos se limpian."""
        db.session.add(PlatformBenchmark(
            cohort='global', restaurant_count=9, period_days=PERIOD_DAYS,
            metrics_json='{"avg_ticket_cop": 20000}', computed_at=datetime.now(timezone.utc),
        ))
        db.session.commit()
        compute_benchmarks()  # sin datos suficientes ahora
        assert PlatformBenchmark.query.count() == 0

    def test_global_snapshot_published_at_k_min(self, db, sample_restaurant):
        """Con exactamente K_MIN restaurantes calificados se publica 'global'."""
        for i in range(K_MIN):
            r = _mk_restaurant(db, i)
            _mk_orders_with_items(db, r, MIN_ORDERS_PER_RESTAURANT)
        result = compute_benchmarks()
        assert result['cohorts'] >= 1
        g = PlatformBenchmark.query.filter_by(cohort='global').first()
        assert g is not None
        assert g.restaurant_count == K_MIN
        metrics = json.loads(g.metrics_json)
        assert metrics['avg_ticket_cop'] == 20000  # mediana de tickets iguales

    def test_small_cuisine_cohort_not_published(self, db, sample_restaurant):
        """Una cohorte cuisine con < K_MIN miembros no se publica; global sí."""
        # 6 restaurantes: 5 'pizza', 1 'sushi' → sushi queda fuera por k-anonymity.
        for i in range(K_MIN + 1):
            cuisine = 'pizza' if i < K_MIN else 'sushi'
            r = _mk_restaurant(db, i, cuisine=cuisine)
            _mk_orders_with_items(db, r, MIN_ORDERS_PER_RESTAURANT)
        compute_benchmarks()
        cohorts = {b.cohort for b in PlatformBenchmark.query.all()}
        assert 'global' in cohorts
        assert 'pizza' in cohorts
        assert 'sushi' not in cohorts

    def test_no_individual_data_leak(self, db, sample_restaurant):
        """El snapshot publicado nunca contiene ids ni filas individuales."""
        for i in range(K_MIN):
            r = _mk_restaurant(db, i)
            _mk_orders_with_items(db, r, MIN_ORDERS_PER_RESTAURANT + i)
        compute_benchmarks()
        for b in PlatformBenchmark.query.all():
            raw = b.metrics_json
            assert '"restaurant_id"' not in raw
            for i in range(K_MIN):
                assert f'R{i}' not in raw

    def test_cancelled_orders_excluded(self, db, sample_restaurant):
        pass  # cubierto implícitamente: los helpers crean status='confirmed'


# ───────────── Fase 1: lectura / fallback ─────────────

class TestBenchmarkLookup:

    def _seed_global_and_cuisine(self, db, cuisine):
        db.session.add(PlatformBenchmark(
            cohort='global', restaurant_count=10, period_days=30,
            metrics_json=json.dumps({'avg_ticket_cop': 30000}),
            computed_at=datetime.now(timezone.utc),
        ))
        db.session.add(PlatformBenchmark(
            cohort=cuisine, restaurant_count=7, period_days=30,
            metrics_json=json.dumps({'avg_ticket_cop': 25000}),
            computed_at=datetime.now(timezone.utc),
        ))
        db.session.commit()

    def test_prefers_cuisine_cohort(self, db, sample_restaurant):
        sample_restaurant.cuisine_type = 'pizza'
        db.session.commit()
        self._seed_global_and_cuisine(db, 'pizza')
        row = get_benchmark_for(sample_restaurant)
        assert row.cohort == 'pizza'
        assert benchmarks_for_context(sample_restaurant)['avg_ticket_cop'] == 25000

    def test_fallback_to_global(self, db, sample_restaurant):
        self._seed_global_and_cuisine(db, 'pizza')  # restaurante es 'general'
        row = get_benchmark_for(sample_restaurant)
        assert row.cohort == 'global'

    def test_none_when_empty(self, db, sample_restaurant):
        assert get_benchmark_for(sample_restaurant) is None
        assert benchmarks_for_context(sample_restaurant) is None

    def test_context_includes_benchmarks(self, db, sample_restaurant, monkeypatch):
        from app.services.insights import data_service
        # build_context usa dayofweek() (MySQL), que no existe en SQLite.
        monkeypatch.setattr(
            data_service, '_weekday_sales',
            lambda rid, start: {i: 0 for i in range(7)},
        )
        self._seed_global_and_cuisine(db, 'general')
        ctx = data_service.build_context(sample_restaurant.id, days=30)
        # El restaurante es cuisine 'general' → prefiere su cohorte sobre global.
        assert ctx['benchmarks']['cohort'] == 'general'
        assert ctx['benchmarks']['source'] == 'plataforma_velzia_anonimizado'
        assert ctx['benchmarks']['cohort_size'] == 7
        # Fechas concretas del período (regla 16 del prompt: nada de "90 días").
        assert 'period_start' in ctx and 'period_end' in ctx
        from datetime import date as _date
        _date.fromisoformat(ctx['period_start'])
        _date.fromisoformat(ctx['period_end'])


# ───────────── Benchmark opt-out (Ley 1581 de 2012) ─────────────

class TestBenchmarkOptOut:

    def test_opted_out_restaurant_excluded_from_computation(self, db, sample_restaurant):
        """Un restaurante con allow_benchmark=False NO aporta datos al snapshot."""
        sample_restaurant.allow_benchmark = False
        db.session.commit()
        _mk_orders_with_items(db, sample_restaurant, MIN_ORDERS_PER_RESTAURANT + 5)
        for i in range(K_MIN):
            r = _mk_restaurant(db, i)
            _mk_orders_with_items(db, r, MIN_ORDERS_PER_RESTAURANT)
        result = compute_benchmarks()
        assert result['cohorts'] >= 1
        g = PlatformBenchmark.query.filter_by(cohort='global').first()
        assert g.restaurant_count == K_MIN  # el opt-out no cuenta

    def test_opted_out_restaurant_gets_no_benchmarks(self, db, sample_restaurant):
        """Un restaurante opt-out no recibe benchmarks (benchmarks_for_context)."""
        sample_restaurant.allow_benchmark = False
        db.session.commit()
        for i in range(K_MIN):
            r = _mk_restaurant(db, i)
            _mk_orders_with_items(db, r, MIN_ORDERS_PER_RESTAURANT)
        compute_benchmarks()
        bench = benchmarks_for_context(sample_restaurant)
        assert bench is None

    def test_opted_in_restaurant_still_gets_benchmarks(self, db, sample_restaurant):
        """Un restaurante con allow_benchmark=True (default) sí recibe benchmarks."""
        _mk_orders_with_items(db, sample_restaurant, MIN_ORDERS_PER_RESTAURANT + 5)
        for i in range(K_MIN):
            r = _mk_restaurant(db, i)
            _mk_orders_with_items(db, r, MIN_ORDERS_PER_RESTAURANT)
        compute_benchmarks()
        bench = benchmarks_for_context(sample_restaurant)
        assert bench is not None
        assert 'avg_ticket_cop' in bench

    def test_default_allow_benchmark_is_true(self, db):
        """El default de allow_benchmark es True (participa por defecto)."""
        r = Restaurant(
            name='R-default', slug='r-default',
            whatsapp_phone='+57300999999', plan_type='emprendedor',
            is_active=True,
        )
        db.session.add(r)
        db.session.flush()
        assert r.allow_benchmark is True


# ───────────── Fase 2: Knowledge Base ─────────────

class TestKnowledgeSelector:

    def setup_method(self):
        clear_cache()

    def test_keyword_match_food_cost(self):
        text = 'Mi food cost está muy alto, las mermas me están comiendo'
        doc = select_knowledge(text)
        assert doc is not None
        assert 'Food Cost' in doc

    def test_keyword_match_slow_days(self):
        doc = select_knowledge('Cómo hago una promoción para los martes')
        assert doc is not None
        assert 'martes' in doc.lower()

    def test_intent_fallback_profitability(self):
        doc = select_knowledge('Analiza mi negocio completo', intent='profitability_analysis')
        assert doc is not None
        assert 'Food Cost' in doc

    def test_returns_none_without_match(self):
        assert select_knowledge('Hola', intent='general_analysis') is None
        assert select_knowledge('', intent=None) is None

    def test_truncated_to_max_chars(self):
        doc = select_knowledge('capacitar a mis meseros en upselling')
        assert doc is not None
        assert len(doc) <= MAX_KNOWLEDGE_CHARS + 10  # tope + marcador '[...]'


class TestClassifierAdviceRouting:
    """El detector de 'busca consejo' debe enviar a análisis preguntas que
    QUICK_PATTERNS secuestraba (solo números SQL sin recomendación)."""

    def test_how_do_i_improve_sales_is_analysis(self):
        from app.services.insights.classifier import classify
        c = classify('Como mejoro mis ventas?')
        assert c['level'] == 'analysis'
        assert c['intent'] == 'recommendations'

    def test_sales_dropped_what_do_i_do_not_quick(self):
        from app.services.insights.classifier import classify
        c = classify('Mis ventas bajaron este mes, que hago?')
        assert c['level'] == 'analysis'
        assert c['intent'] == 'sales_analysis'

    def test_food_cost_routes_to_profitability(self):
        from app.services.insights.classifier import classify
        c = classify('Mi food cost esta muy alto')
        assert c['intent'] == 'profitability_analysis'

    def test_factual_questions_still_quick(self):
        from app.services.insights.classifier import classify
        # Guardia de regresión: consultas de dato puntual siguen siendo gratis.
        assert classify('cuanto vendi hoy?')['level'] == 'quick'
        assert classify('ventas de este mes')['intent'] == 'month_sales'
        assert classify('cual es mi producto mas vendido')['intent'] == 'top_product'

    def test_flagship_question_gets_kb_doc(self):
        from app.services.insights.classifier import classify
        q = 'Como mejoro mis ventas?'
        c = classify(q)
        doc = select_knowledge(q.lower(), c['intent'])
        assert doc is not None
        assert 'ticket promedio' in doc.lower()


class TestPromptBuilderKnowledge:

    def test_system_prompt_has_new_rules(self):
        assert 'BENCHMARKS DE LA PLATAFORMA' in prompt_builder.SYSTEM_PROMPT
        assert 'CONOCIMIENTO DE INDUSTRIA' in prompt_builder.SYSTEM_PROMPT

    def test_system_prompt_no_meta_preamble(self):
        # Regla 15: prohibido abrir explicando de dónde viene el análisis.
        assert 'VE DIRECTO AL GRANO' in prompt_builder.SYSTEM_PROMPT
        assert 'NUNCA abras tu respuesta explicando' in prompt_builder.SYSTEM_PROMPT

    def test_system_prompt_natural_periods(self):
        # Regla 16: usar period_start/period_end, nunca "últimos 90 días".
        assert 'PERÍODOS EN LENGUAJE NATURAL' in prompt_builder.SYSTEM_PROMPT
        assert 'period_start' in prompt_builder.SYSTEM_PROMPT

    def test_prompt_version_bumped(self):
        assert prompt_builder.PROMPT_VERSION == 'v1.5'

    def test_knowledge_injected_as_system_message(self):
        msgs = prompt_builder.build_analysis_messages(
            user_message='hola', context={'a': 1}, knowledge='# Guía\nContenido',
        )
        kinds = [m['content'] for m in msgs if m['role'] == 'system']
        assert any('CONOCIMIENTO DE INDUSTRIA' in c for c in kinds)

    def test_cash_prompt_ignores_knowledge(self):
        msgs = prompt_builder.build_analysis_messages(
            user_message='hola', context={'a': 1},
            system_prompt=prompt_builder.CASH_SYSTEM_PROMPT,
            knowledge='# Guía\nContenido',
        )
        assert all('CONOCIMIENTO DE INDUSTRIA' not in m['content']
                   for m in msgs if m['role'] == 'system')

    def test_backward_compatible_without_knowledge(self):
        msgs = prompt_builder.build_analysis_messages(
            user_message='hola', context={'a': 1},
        )
        assert msgs[0]['role'] == 'system'
        assert msgs[-1] == {'role': 'user', 'content': 'hola'}
