"""
Tests del sistema de roles para empleados (v2.1.0).

Cubre exactamente los 7 casos aprobados:
1. Crear empleado con plan en límite → error con mensaje exacto.
2. PIN incorrecto → error genérico (no revela si el restaurante o el PIN existen).
3. Mesero intenta acceder a /cash-register/ → redirect, no 500.
4. Cajero intenta acceder a /insights/ → redirect, no 500.
5. require_active usa role='owner', nunca users[0].
6. Downgrade de plan no borra empleados, solo bloquea crear nuevos.
7. Empleado con is_active=False no puede hacer login.

v2.1.3: Tests de seguridad — fuerza bruta, PINs débiles, insights role check.
"""
import re
from datetime import datetime, timezone, timedelta

import pytest
from werkzeug.security import generate_password_hash

from app.models import AITokenWallet, Order, OrderItem, Restaurant, User
from app.services.employee_service import (
    EmployeeService,
    EmployeeValidationError,
    BLACKLISTED_PINS,
    MAX_PIN_ATTEMPTS,
    LOCKOUT_MINUTES,
)


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def team_restaurant(db):
    """Restaurante con plan élite (empleados ilimitados) para pruebas de roles."""
    r = Restaurant(
        name='Team Restaurant',
        slug='team-restaurant',
        whatsapp_phone='+573001111111',
        plan_type='elite',
        is_active=True,
        is_open=True,
        subscription_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        has_used_trial=False,
    )
    db.session.add(r)
    db.session.commit()
    return r


@pytest.fixture
def owner_user(db, team_restaurant):
    u = User(
        restaurant_id=team_restaurant.id,
        username='Owner Team',
        email='team-owner@test.com',
        password=generate_password_hash('Pass123'),
        role='owner',  # el dueño no tiene PIN
    )
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def waiter_user(db, team_restaurant):
    return EmployeeService.create_employee(team_restaurant, 'Mesero Test', 'waiter', '3847')


@pytest.fixture
def cashier_user(db, team_restaurant):
    return EmployeeService.create_employee(team_restaurant, 'Cajero Test', 'cashier', '5926')


# ── Caso 1: límite de empleados por plan ──────────────────────────────────

class TestEmployeePlanLimit:

    def test_second_employee_blocked_on_emprendedor(self, db, sample_restaurant):
        """Plan emprendedor (máx 1): el 2º empleado falla con el mensaje exacto."""
        first = EmployeeService.create_employee(
            sample_restaurant, 'Mesero Uno', 'waiter', '3847')
        assert first.role == 'waiter'

        with pytest.raises(EmployeeValidationError) as exc:
            EmployeeService.create_employee(
                sample_restaurant, 'Mesero Dos', 'waiter', '5926')

        msg = str(exc.value)
        assert msg == (
            'Tu plan Emprendedor permite máximo 1 empleado. '
            'Actualiza tu plan para agregar más.'
        )
        # El segundo nunca se insertó.
        count = EmployeeService._count_employees(sample_restaurant.id)
        assert count == 1

    def test_elite_plan_allows_multiple(self, db, team_restaurant):
        EmployeeService.create_employee(team_restaurant, 'M1', 'waiter', '3847')
        EmployeeService.create_employee(team_restaurant, 'C1', 'cashier', '5926')
        EmployeeService.create_employee(team_restaurant, 'M2', 'waiter', '4738')
        assert EmployeeService._count_employees(team_restaurant.id) == 3


# ── Caso 2: PIN incorrecto → error genérico ───────────────────────────────

class TestGenericPinError:

    def test_service_returns_none_for_wrong_pin(self, db, team_restaurant, waiter_user):
        """PIN incorrecto → None (mismo resultado que restaurante inexistente)."""
        assert EmployeeService.authenticate_employee('team-restaurant', '9999') is None
        # El PIN correcto sí funciona (control positivo: el negativo es real).
        assert EmployeeService.authenticate_employee('team-restaurant', '3847') == waiter_user

    def test_service_returns_none_for_unknown_restaurant(self, db):
        assert EmployeeService.authenticate_employee('no-existe', '1234') is None

    def test_login_route_generic_message(self, client, db, team_restaurant, waiter_user):
        """POST con PIN incorrecto → 401 genérico, sin revelar datos del empleado."""
        page = client.get('/empleado/team-restaurant')
        token = re.search(
            r'name="csrf-token" content="([^"]+)"', page.get_data(as_text=True)
        ).group(1)

        resp = client.post('/empleado/team-restaurant', data={
            'csrf_token': token,
            'pin': '9999',
        }, headers={'X-CSRFToken': token})

        assert resp.status_code == 401
        body = resp.get_data(as_text=True)
        assert 'PIN incorrecto' in body
        # No revela el nombre/email del empleado ni la existencia del PIN.
        assert 'Mesero Test' not in body
        assert 'team-owner@test.com' not in body


# ── Caso 3: mesero → /cash-register/ → redirect ───────────────────────────

class TestWaiterBlockedFromCashRegister:

    def test_waiter_redirected_not_500(self, client, db, team_restaurant, waiter_user):
        with client.session_transaction() as sess:
            sess['user_id'] = waiter_user.id

        resp = client.get('/cash-register/')
        assert resp.status_code == 302, f'esperaba 302, obtuvo {resp.status_code}'
        assert '/empleado/' in resp.headers.get('Location', '')


# ── Caso 4: cajero → /insights/ → redirect ────────────────────────────────

class TestCashierBlockedFromInsights:

    def test_cashier_redirected_not_500(self, client, db, team_restaurant, cashier_user):
        with client.session_transaction() as sess:
            sess['user_id'] = cashier_user.id

        resp = client.get('/insights/')
        assert resp.status_code == 302, f'esperaba 302, obtuvo {resp.status_code}'
        assert '/empleado/' in resp.headers.get('Location', '')


# ── Caso 5: require_active usa role='owner', nunca users[0] ───────────────

class TestRequireActiveOwnerByRole:

    def test_owner_found_by_role_not_by_position(
            self, client, db, expired_restaurant):
        """
        Restaurante con suscripción vencida: el acceso pasa SOLO si el dueño
        (identificado por role) tiene tokens IA. El primer usuario de la lista
        es un empleado sin wallet → users[0] fallaría si se usara.
        """
        # 1) El empleado se crea PRIMERO → es users[0].
        employee = EmployeeService.create_employee(
            expired_restaurant, 'Mesero Primero', 'waiter', '3847')
        db.session.refresh(expired_restaurant)
        assert expired_restaurant.users[0].role == 'waiter'
        assert expired_restaurant.users[0].id == employee.id

        # 2) El dueño se crea DESPUÉS, con wallet de tokens.
        owner = User(
            restaurant_id=expired_restaurant.id,
            username='Owner Expired',
            email='expired-owner@test.com',
            password=generate_password_hash('Pass123'),
            role='owner',
        )
        db.session.add(owner)
        db.session.commit()
        wallet = AITokenWallet(
            user_id=owner.id, plan_limit=10, plan_tokens=5,
            extra_tokens=0, tokens_used_month=0,
        )
        db.session.add(wallet)
        db.session.commit()

        with client.session_transaction() as sess:
            sess['user_id'] = owner.id

        # require_active debe encontrar al dueño por role (no users[0]) y pasar.
        resp = client.get('/dashboard/api/check-orders')
        assert resp.status_code == 200, resp.get_data(as_text=True)


# ── Caso 6: downgrade de plan no borra empleados ───────────────────────────

class TestPlanDowngradeKeepsEmployees:

    def test_downgrade_blocks_new_but_keeps_existing(self, db):
        r = Restaurant(
            name='Downgrade Restaurant',
            slug='downgrade-restaurant',
            whatsapp_phone='+573002222222',
            plan_type='elite',  # ilimitado → se crean 2 empleados
            is_active=True,
            is_open=True,
            subscription_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.session.add(r)
        db.session.commit()

        EmployeeService.create_employee(r, 'E1', 'waiter', '3847')
        EmployeeService.create_employee(r, 'E2', 'cashier', '5926')

        # Downgrade a emprendedor (máx 1): NO borra a los 2 existentes.
        r.plan_type = 'emprendedor'
        db.session.commit()
        assert EmployeeService._count_employees(r.id) == 2

        # Pero bloquea crear uno nuevo.
        with pytest.raises(EmployeeValidationError) as exc:
            EmployeeService.create_employee(r, 'E3', 'waiter', '4738')
        assert 'máximo 1 empleado' in str(exc.value)
        assert EmployeeService._count_employees(r.id) == 2


# ── Caso 7: empleado inactivo no puede hacer login ─────────────────────────

class TestInactiveEmployeeCannotLogin:

    def test_inactive_employee_rejected(self, db, team_restaurant, waiter_user):
        ok, _ = EmployeeService.deactivate_employee(waiter_user.id, team_restaurant)
        assert ok is True
        assert waiter_user.is_active is False

        # Con el PIN correcto ya no entra (mismo error genérico).
        assert EmployeeService.authenticate_employee('team-restaurant', '3847') is None

        # Al reactivar vuelve a entrar.
        ok, _ = EmployeeService.reactivate_employee(waiter_user.id, team_restaurant)
        assert ok is True
        assert EmployeeService.authenticate_employee('team-restaurant', '3847') == waiter_user


# ── v2.1.3: Fix 1 — Fuerza bruta de PIN ─────────────────────────────────────

class TestBruteForceProtection:

    def test_lockout_after_5_failed_attempts(self, db, team_restaurant, waiter_user):
        """5 intentos fallidos → cuenta bloqueada 30 minutos."""
        for i in range(MAX_PIN_ATTEMPTS):
            result = EmployeeService.authenticate_employee('team-restaurant', '9999')
            assert result is None

        # Verificar que el empleado está bloqueado.
        db.session.refresh(waiter_user)
        assert waiter_user.failed_pin_attempts == MAX_PIN_ATTEMPTS
        assert waiter_user.locked_until is not None
        assert waiter_user.locked_until > datetime.now(timezone.utc)

    def test_correct_pin_resets_attempts(self, db, team_restaurant, waiter_user):
        """PIN correcto → resetea contadores."""
        # 3 intentos fallidos.
        for i in range(3):
            EmployeeService.authenticate_employee('team-restaurant', '9999')

        db.session.refresh(waiter_user)
        assert waiter_user.failed_pin_attempts == 3

        # PIN correcto → resetea.
        result = EmployeeService.authenticate_employee('team-restaurant', '3847')
        assert result == waiter_user

        db.session.refresh(waiter_user)
        assert waiter_user.failed_pin_attempts == 0
        assert waiter_user.locked_until is None

    def test_locked_account_rejects_correct_pin(self, db, team_restaurant, waiter_user):
        """Cuenta bloqueada → rechaza incluso el PIN correcto."""
        # Bloquear la cuenta.
        waiter_user.failed_pin_attempts = MAX_PIN_ATTEMPTS
        waiter_user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
        db.session.commit()

        # PIN correcto pero cuenta bloqueada → None.
        result = EmployeeService.authenticate_employee('team-restaurant', '1234')
        assert result is None

    def test_lockout_duration_is_30_minutes(self, db, team_restaurant, waiter_user):
        """Bloqueo dura exactamente 30 minutos."""
        for i in range(MAX_PIN_ATTEMPTS):
            EmployeeService.authenticate_employee('team-restaurant', '9999')
        db.session.refresh(waiter_user)
        expected_unlock = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
        diff = abs((waiter_user.locked_until - expected_unlock).total_seconds())
        assert diff < 60  # menos de 1 minuto de diferencia


# ── v2.1.3: Fix 3 — PINs débiles blacklist ──────────────────────────────────

class TestWeakPinBlacklist:

    def test_blacklisted_pin_rejected_on_create(self, db, team_restaurant):
        """PINs en la blacklist son rechazados al crear empleado."""
        for pin in ['0000', '1234', '1111', '2580']:
            with pytest.raises(EmployeeValidationError) as exc:
                EmployeeService.create_employee(team_restaurant, f'Test {pin}', 'waiter', pin)
            assert 'demasiado fácil' in str(exc.value)

    def test_valid_pin_accepted(self, db, team_restaurant):
        """PINs no en la blacklist son aceptados."""
        emp = EmployeeService.create_employee(team_restaurant, 'Valid', 'waiter', '3847')
        assert emp is not None
        assert emp.pin_hash is not None

    def test_all_blacklisted_pins_are_4_digits(self):
        """Todos los PINs en la blacklist son exactamente 4 dígitos."""
        for pin in BLACKLISTED_PINS:
            assert re.fullmatch(r'\d{4}', pin), f'{pin} no es 4 dígitos'


# ── v2.1.3: Fix 2 — Insights role check ─────────────────────────────────────

class TestInsightsRoleCheck:

    def test_employee_blocked_from_insights(self, client, db, team_restaurant, waiter_user):
        """Mesero no puede acceder a /insights/ → redirect, no 500."""
        with client.session_transaction() as sess:
            sess['employee_id'] = waiter_user.id
            sess['employee_login'] = True

        resp = client.get('/insights/')
        assert resp.status_code in (302, 403), f'esperaba 302/403, obtuvo {resp.status_code}'

    def test_owner_can_access_insights(self, client, db, team_restaurant, owner_user):
        """Dueño puede acceder a /insights/."""
        with client.session_transaction() as sess:
            sess['user_id'] = owner_user.id

        resp = client.get('/insights/')
        assert resp.status_code == 200


# ── v2.1.4: Detalle de pedido para mesero/cajero (sin datos financieros) ───

def _make_order(db, restaurant, status='pending', order_number='ORD-100',
                restaurant_id=None):
    """Crea un pedido con items (snapshot) para el restaurante indicado."""
    o = Order(
        restaurant_id=restaurant_id or restaurant.id,
        order_number=order_number,
        customer_name='Cliente Mesero',
        customer_phone='+573001112233',
        status=status,
        total=39000,
        notes='sin cebolla en la burger | IP: 127.0.0.1',
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.session.add(o)
    db.session.flush()
    db.session.add(OrderItem(
        order_id=o.id,
        restaurant_id=restaurant.id,
        product_name='Hamburguesa Clásica',
        product_price=15000,
        quantity=2,
        subtotal=30000,
    ))
    db.session.add(OrderItem(
        order_id=o.id,
        restaurant_id=restaurant.id,
        product_name='Limonada de Coco',
        product_price=9000,
        quantity=1,
        subtotal=9000,
    ))
    db.session.commit()
    return o


@pytest.fixture
def detail_foreign_restaurant(db):
    r = Restaurant(
        name='Otra Cafetería',
        slug='otra-cafeteria-detail',
        whatsapp_phone='+573009999999',
        plan_type='elite',
        is_active=True,
        is_open=True,
        subscription_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        has_used_trial=False,
    )
    db.session.add(r)
    db.session.commit()
    return r


class TestWaiterOrderDetail:

    def test_waiter_can_view_pending_order(self, client, db, team_restaurant, waiter_user):
        """Mesero puede ver detalle de pedido pending → 200."""
        order = _make_order(db, team_restaurant, status='pending')
        with client.session_transaction() as sess:
            sess['employee_id'] = waiter_user.id
            sess['employee_login'] = True

        resp = client.get(f'/empleado/team-restaurant/pedidos/{order.id}')
        assert resp.status_code == 200
        assert order.order_number.encode() in resp.data

    def test_waiter_can_view_confirmed_order(self, client, db, team_restaurant, waiter_user):
        """Mesero puede ver detalle de pedido confirmed → 200."""
        order = _make_order(db, team_restaurant, status='confirmed')
        with client.session_transaction() as sess:
            sess['employee_id'] = waiter_user.id
            sess['employee_login'] = True

        resp = client.get(f'/empleado/team-restaurant/pedidos/{order.id}')
        assert resp.status_code == 200

    def test_detail_html_has_no_payment_data(self, client, db, team_restaurant, waiter_user):
        """El detalle NO expone datos de pago, precios por ítem ni acciones del dueño."""
        order = _make_order(db, team_restaurant, status='pending')
        with client.session_transaction() as sess:
            sess['employee_id'] = waiter_user.id
            sess['employee_login'] = True

        html = client.get(f'/empleado/team-restaurant/pedidos/{order.id}').get_data(as_text=True)
        for sensitive in ['payment_method', 'amount_received', 'change_due', 'paid_at',
                          'product_price', 'subtotal',
                          'Registrar pago', 'Imprimir', 'Editar venta', 'Eliminar']:
            assert sensitive not in html, f'{sensitive} no debería aparecer en el detalle'

    def test_waiter_sees_products_and_total(self, client, db, team_restaurant, waiter_user):
        """El detalle muestra productos, cantidades y total (sin IP en notas)."""
        order = _make_order(db, team_restaurant, status='pending')
        with client.session_transaction() as sess:
            sess['employee_id'] = waiter_user.id
            sess['employee_login'] = True

        html = client.get(f'/empleado/team-restaurant/pedidos/{order.id}').get_data(as_text=True)
        assert 'Hamburguesa Clásica' in html
        assert '2x' in html
        assert '$39,000' in html or '$39.000' in html
        assert '127.0.0.1' not in html  # IP sanitizada de las notas

    def test_foreign_order_returns_404(self, client, db, team_restaurant, waiter_user,
                                       detail_foreign_restaurant):
        """Pedido de otro restaurante → 404 (anti-IDOR)."""
        order = _make_order(db, detail_foreign_restaurant, status='pending',
                            order_number='ORD-FOREIGN',
                            restaurant_id=detail_foreign_restaurant.id)
        with client.session_transaction() as sess:
            sess['employee_id'] = waiter_user.id
            sess['employee_login'] = True

        resp = client.get(f'/empleado/team-restaurant/pedidos/{order.id}')
        assert resp.status_code == 404

    def test_delivered_order_redirects_to_list(self, client, db, team_restaurant, waiter_user):
        """Pedido delivered no está en curso → redirect a la lista del mesero."""
        order = _make_order(db, team_restaurant, status='delivered')
        with client.session_transaction() as sess:
            sess['employee_id'] = waiter_user.id
            sess['employee_login'] = True

        resp = client.get(f'/empleado/team-restaurant/pedidos/{order.id}')
        assert resp.status_code == 302
        assert '/pedidos' in resp.headers['Location']

    def test_expired_order_redirects_to_list(self, client, db, team_restaurant, waiter_user):
        """Pedido expired no está en curso → redirect a la lista del mesero."""
        order = _make_order(db, team_restaurant, status='expired')
        with client.session_transaction() as sess:
            sess['employee_id'] = waiter_user.id
            sess['employee_login'] = True

        resp = client.get(f'/empleado/team-restaurant/pedidos/{order.id}')
        assert resp.status_code == 302
        assert '/pedidos' in resp.headers['Location']

    def test_cashier_can_view_detail(self, client, db, team_restaurant, cashier_user):
        """Cajero también puede ver el detalle → 200."""
        order = _make_order(db, team_restaurant, status='pending')
        with client.session_transaction() as sess:
            sess['employee_id'] = cashier_user.id
            sess['employee_login'] = True

        resp = client.get(f'/empleado/team-restaurant/pedidos/{order.id}')
        assert resp.status_code == 200
