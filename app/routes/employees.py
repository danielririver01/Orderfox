"""
routes/employees.py — Blueprints del sistema de roles (v2.1.0).

Dos blueprints independientes:

1. `employees_bp` (url_prefix /dashboard):
   Gestión del equipo por el DUEÑO.
   - GET  /dashboard/equipo                    → lista de empleados
   - POST /dashboard/equipo/crear              → crear empleado (cashier/waiter)
   - POST /dashboard/equipo/<id>/desactivar    → desactivar (is_active=False)
   - POST /dashboard/equipo/<id>/reactivar     → reactivar
   - POST /dashboard/equipo/<id>/cambiar-pin   → cambiar PIN

2. `employee_portal_bp` (url_prefix /empleado):
   Portal del empleado, SIN sidebar ni acceso al dashboard.
   - GET/POST /empleado/<slug>          → login por PIN (sin @require_auth)
   - GET      /empleado/<slug>/pedidos  → pantalla mesero (role=waiter)
   - GET/POST /empleado/<slug>/pedidos/nuevo → POS del empleado (waiter/cashier)
   - POST     /empleado/<slug>/pedidos/<id>/cancelar → cancelar pending (waiter/cashier)
   - GET/POST /empleado/<slug>/pedidos/<id>/editar → editar pending (waiter/cashier)
   - GET      /empleado/<slug>/caja     → pantalla cajero (role=cashier)
   - GET      /empleado/logout          → cerrar sesión

Las acciones del mesero (cambiar estado) y del cajero (registrar pago) reusan
los endpoints existentes de /orders/* protegidos por @require_role.
"""
import json

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.models import db, Order, Restaurant, User
from app.services.cash_register_service import CashRegisterService
from app.services.employee_service import (
    EMPLOYEE_ROLES,
    EmployeeService,
    EmployeeValidationError,
)
from app.services.order_service import OrderService, PaymentValidationError
from app.utils.auth import require_active, require_auth, require_role
from app.utils.restaurant import get_current_restaurant
from app.utils.subscription import check_feature_access, get_plan_limits
from app.extensions import limiter

employees_bp = Blueprint('employees', __name__, url_prefix='/dashboard')
employee_portal_bp = Blueprint('employee_portal', __name__, url_prefix='/empleado')


# ── Gestión del equipo (dueño) ──────────────────────────────────────────────


@employees_bp.route('/equipo')
@require_auth
@require_active
@require_role('owner')
def team():
    """Lista de empleados del restaurante + estado del límite del plan."""
    restaurant = get_current_restaurant()
    if not restaurant:
        abort(404)

    employees = User.query.filter(
        User.restaurant_id == restaurant.id,
        User.pin_hash.isnot(None),
    ).order_by(User.is_active.desc(), User.id.asc()).all()

    plan_limits = get_plan_limits(restaurant.plan_type)
    max_employees = plan_limits.get('max_employees')
    current_count = len(employees)

    return render_template(
        'dashboard/team.html',
        restaurant=restaurant,
        employees=employees,
        current_count=current_count,
        max_employees=max_employees,
        plan_name=plan_limits.get('name', restaurant.plan_type),
        limit_reached=(
            max_employees is not None and current_count >= max_employees
        ),
    )


@employees_bp.route('/equipo/crear', methods=['POST'])
@require_auth
@require_active
@require_role('owner')
def create_employee():
    """Crear empleado (cashier/waiter) con PIN de 4 dígitos."""
    restaurant = get_current_restaurant()
    if not restaurant:
        abort(404)

    # employee_name (campo renombrado en team.html para evitar el autofill del
    # navegador); se acepta 'name' como fallback por compatibilidad.
    name = (request.form.get('employee_name') or request.form.get('name') or '').strip()
    role = request.form.get('role', '').strip()
    pin = request.form.get('pin', '').strip()

    try:
        employee = EmployeeService.create_employee(restaurant, name, role, pin)
        flash(
            f'Empleado "{employee.username}" agregado como '
            f'{"cajero" if role == "cashier" else "mesero"}.',
            'success',
        )
    except EmployeeValidationError as e:
        flash(str(e), 'error')

    return redirect(url_for('employees.team'))


@employees_bp.route('/equipo/<int:employee_id>/desactivar', methods=['POST'])
@require_auth
@require_active
@require_role('owner')
def deactivate_employee(employee_id):
    """Desactiva un empleado sin borrarlo."""
    restaurant = get_current_restaurant()
    if not restaurant:
        abort(404)

    success, error = EmployeeService.deactivate_employee(employee_id, restaurant)
    if success:
        flash('Empleado desactivado. Ya no puede entrar con su PIN.', 'success')
    else:
        flash(error, 'error')

    return redirect(url_for('employees.team'))


@employees_bp.route('/equipo/<int:employee_id>/reactivar', methods=['POST'])
@require_auth
@require_active
@require_role('owner')
def reactivate_employee(employee_id):
    """Reactiva un empleado desactivado."""
    restaurant = get_current_restaurant()
    if not restaurant:
        abort(404)

    success, error = EmployeeService.reactivate_employee(employee_id, restaurant)
    if success:
        flash('Empleado reactivado. Ya puede entrar con su PIN.', 'success')
    else:
        flash(error, 'error')

    return redirect(url_for('employees.team'))


@employees_bp.route('/equipo/<int:employee_id>/cambiar-pin', methods=['POST'])
@require_auth
@require_active
@require_role('owner')
def change_employee_pin(employee_id):
    """Cambia el PIN de un empleado (validado a 4 dígitos)."""
    restaurant = get_current_restaurant()
    if not restaurant:
        abort(404)

    new_pin = request.form.get('pin', '').strip()
    try:
        success, error = EmployeeService.update_employee_pin(
            employee_id, restaurant, new_pin
        )
    except EmployeeValidationError as e:
        success, error = False, str(e)

    if success:
        flash('PIN actualizado correctamente.', 'success')
    else:
        flash(error, 'error')

    return redirect(url_for('employees.team'))


# ── Portal del empleado (PIN) ───────────────────────────────────────────────


def _get_restaurant_by_slug(slug):
    return Restaurant.query.filter_by(slug=slug).first()


def _portal_user():
    """Usuario en sesión si es un empleado (tiene PIN), si no None.

    Lee session['employee_id'] (clave propia del portal), nunca user_id
    (que pertenece al dueño)."""
    employee_id = session.get('employee_id')
    user = User.query.get(employee_id) if employee_id else None
    if user and user.pin_hash is not None:
        return user
    return None


@employee_portal_bp.route('/<slug>', methods=['GET', 'POST'])
@limiter.limit("5 per minute; 20 per hour")
def login(slug):
    """Login del empleado por PIN. Sin @require_auth (acceso público)."""
    restaurant = _get_restaurant_by_slug(slug)
    if not restaurant:
        abort(404)

    # Ya logueado como empleado de este restaurante → ir a su pantalla.
    current = _portal_user()
    if current and current.restaurant_id == restaurant.id:
        if current.role == 'cashier':
            return redirect(url_for('employee_portal.cashier', slug=slug))
        return redirect(url_for('employee_portal.waiter', slug=slug))

    if request.method == 'POST':
        pin = request.form.get('pin', '').strip()
        user = EmployeeService.authenticate_employee(slug, pin)
        if not user:
            # Error genérico: no revela si el PIN, empleado o restaurante falla.
            flash('PIN incorrecto. Inténtalo de nuevo.', 'error')
            return render_template(
                'employees/login.html', restaurant=restaurant
            ), 401

        # Sesión del empleado en clave propia. v2.1.2: última acción de login
        # gana — si en este navegador había sesión del dueño (user_id), el
        # empleado la toma al entrar con PIN. Sin session.clear().
        session.pop('user_id', None)
        session.pop('username', None)
        session['employee_id'] = user.id
        session['employee_login'] = True
        session['employee_slug'] = slug

        if user.role == 'cashier':
            return redirect(url_for('employee_portal.cashier', slug=slug))
        return redirect(url_for('employee_portal.waiter', slug=slug))

    return render_template('employees/login.html', restaurant=restaurant)


@employee_portal_bp.route('/<slug>/pedidos')
@require_auth
@require_active
@require_role('waiter')
def waiter(slug):
    """Pantalla del mesero: pedidos activos del día (sin sidebar)."""
    restaurant = _get_restaurant_by_slug(slug)
    if not restaurant:
        abort(404)

    user = _portal_user()
    if not user or user.restaurant_id != restaurant.id:
        flash('Sesión no válida para este restaurante.', 'error')
        return redirect(url_for('employee_portal.login', slug=slug))

    active_orders = OrderService.get_active_orders_query(
        restaurant.id
    ).order_by(Order.created_at.asc()).all()

    # "Marcar entregado" está gated por plan (has_status_management) en
    # orders.change_status; aquí solo controlamos si el botón se muestra.
    can_deliver = check_feature_access(restaurant, 'has_status_management')

    return render_template(
        'employees/waiter.html',
        restaurant=restaurant,
        orders=active_orders,
        user=user,
        can_deliver=can_deliver,
    )


@employee_portal_bp.route('/<slug>/pedidos/nuevo', methods=['GET', 'POST'])
@require_auth
@require_active
@require_role('waiter', 'cashier')
def order_create(slug):
    """
    POS del empleado (sin sidebar): crear pedidos desde el portal.

    Misma lógica de creación que orders.create (OrderService) pero SIN tocar
    ninguna ruta del dueño. El pedido nace en estado 'pending'; el pago lo
    registra el cajero desde su pantalla.
    """
    restaurant = _get_restaurant_by_slug(slug)
    if not restaurant:
        abort(404)

    user = _portal_user()
    if not user or user.restaurant_id != restaurant.id:
        flash('Sesión no válida para este restaurante.', 'error')
        return redirect(url_for('employee_portal.login', slug=slug))

    if request.method == 'POST':
        data = request.form
        try:
            items_data = json.loads(data.get('items', '[]'))
        except (TypeError, ValueError):
            items_data = []

        if not items_data:
            flash('Selecciona al menos un producto para crear el pedido.', 'error')
            return redirect(
                url_for('employee_portal.order_create', slug=slug)
            )

        order_data = {
            'customer_name': data.get('customer_name', '').strip(),
            'customer_phone': data.get('customer_phone', '').strip(),
            'notes': data.get('notes', '').strip(),
            'pending_expiry_hours': restaurant.pending_expiry_hours or 24,
        }

        try:
            order = OrderService.create_order(restaurant.id, order_data)
        except ValueError as e:
            flash(str(e), 'error')
            return redirect(
                url_for('employee_portal.order_create', slug=slug)
            )
        try:
            total, _ = OrderService.add_items_to_order(
                order, items_data, restaurant.id
            )
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'error')
            return redirect(url_for('employee_portal.order_create', slug=slug))

        db.session.commit()
        from app.services.notification_service import notify_new_order
        notify_new_order(order.id)

        flash(f'Pedido {order.order_number} creado (${total:,}).', 'success')
        return redirect(url_for('employee_portal.waiter', slug=slug))

    products = OrderService.get_active_products(restaurant.id)
    return render_template(
        'employees/order_create_pos.html',
        restaurant=restaurant,
        products=products,
        user=user,
    )


def _employee_can_modify_order(order):
    """Regla de oro del portal: mesero/cajero solo tocan pedidos pending
    SIN pago registrado. Todo lo demás (confirmed/delivered/pagado) es del
    dueño. Validación de backend — nunca confiar solo en el frontend."""
    return order.status == 'pending' and order.paid_at is None


@employee_portal_bp.route('/<slug>/pedidos/<int:order_id>/cancelar', methods=['POST'])
@require_auth
@require_active
@require_role('waiter', 'cashier')
def cancel_order(slug, order_id):
    """Cancelar un pedido pending desde el portal del empleado.

    Ruta SEPARADA de orders.cancel (del dueño). El empleado solo puede
    cancelar pedidos en estado pending y sin pago.
    """
    restaurant = _get_restaurant_by_slug(slug)
    if not restaurant:
        abort(404)

    user = _portal_user()
    if not user or user.restaurant_id != restaurant.id:
        flash('Sesión no válida para este restaurante.', 'error')
        return redirect(url_for('employee_portal.login', slug=slug))

    order = OrderService.get_order_for_restaurant(restaurant.id, order_id)
    if not order:
        abort(404)

    if not _employee_can_modify_order(order):
        flash('Este pedido ya no se puede cancelar', 'error')
        return redirect(url_for('employee_portal.waiter', slug=slug))

    ok, error = OrderService.cancel_order(order)
    if not ok:
        flash(error, 'error')
    else:
        flash(f'Pedido {order.order_number} cancelado.', 'success')

    return redirect(url_for('employee_portal.waiter', slug=slug))


@employee_portal_bp.route('/<slug>/pedidos/<int:order_id>/editar', methods=['GET', 'POST'])
@require_auth
@require_active
@require_role('waiter', 'cashier')
def order_edit(slug, order_id):
    """Editar items de un pedido pending desde el portal del empleado.

    Solo productos/cantidades (sin mesa, sin estado, sin pago — eso es del
    dueño). Validación de estado pending en backend antes de guardar.
    """
    restaurant = _get_restaurant_by_slug(slug)
    if not restaurant:
        abort(404)

    user = _portal_user()
    if not user or user.restaurant_id != restaurant.id:
        flash('Sesión no válida para este restaurante.', 'error')
        return redirect(url_for('employee_portal.login', slug=slug))

    order = OrderService.get_order_for_restaurant(restaurant.id, order_id)
    if not order:
        abort(404)

    if not _employee_can_modify_order(order):
        flash('Este pedido ya no se puede editar', 'error')
        return redirect(url_for('employee_portal.waiter', slug=slug))

    if request.method == 'POST':
        data = request.form
        try:
            items_data = json.loads(data.get('items', '[]'))
        except (TypeError, ValueError):
            items_data = []

        if not items_data:
            flash('Selecciona al menos un producto para guardar el pedido.', 'error')
            return redirect(
                url_for('employee_portal.order_edit', slug=slug, order_id=order_id)
            )

        # Re-validar pending aquí (el pedido pudo cambiar entre el GET y el POST).
        if not _employee_can_modify_order(order):
            flash('Este pedido ya no se puede editar', 'error')
            return redirect(url_for('employee_portal.waiter', slug=slug))

        try:
            total, _ = OrderService.update_order_items(
                order, items_data, restaurant.id
            )
        except (ValueError, PaymentValidationError) as e:
            db.session.rollback()
            flash(str(e), 'error')
            return redirect(
                url_for('employee_portal.order_edit', slug=slug, order_id=order_id)
            )

        flash(f'Pedido {order.order_number} actualizado (${total:,}).', 'success')
        return redirect(url_for('employee_portal.waiter', slug=slug))

    products = OrderService.get_active_products(restaurant.id)
    # Precargar el carrito con los items actuales del pedido.
    name_to_id = {p.name: p.id for p in products}
    order_items_json = json.dumps([
        {'product_id': name_to_id[item.product_name], 'quantity': item.quantity}
        for item in order.items if item.product_name in name_to_id
    ])
    return render_template(
        'employees/order_edit_pos.html',
        restaurant=restaurant,
        products=products,
        order=order,
        order_items_json=order_items_json,
        user=user,
    )


@employee_portal_bp.route('/<slug>/caja')
@require_auth
@require_active
@require_role('cashier')
def cashier(slug):
    """Pantalla del cajero: pedidos por cobrar + total del día (sin reportes)."""
    restaurant = _get_restaurant_by_slug(slug)
    if not restaurant:
        abort(404)

    user = _portal_user()
    if not user or user.restaurant_id != restaurant.id:
        flash('Sesión no válida para este restaurante.', 'error')
        return redirect(url_for('employee_portal.login', slug=slug))

    # Pedidos activos sin pago (listos para cobrar).
    pending_orders = CashRegisterService.get_pending(restaurant.id)

    # Total del día: SOLO el número, sin desglose histórico ni reportes.
    start, end = CashRegisterService.resolve_range('today')
    summary = CashRegisterService.get_summary(restaurant.id, start, end)
    day_total = summary['total_sales']
    day_orders = summary['total_orders']

    return render_template(
        'employees/cashier.html',
        restaurant=restaurant,
        orders=pending_orders,
        day_total=day_total,
        day_orders=day_orders,
        user=user,
    )


@employee_portal_bp.route('/logout')
def logout():
    """Cierra SOLO la sesión del empleado; no toca la sesión del dueño (user_id)."""
    slug = session.pop('employee_slug', None)
    session.pop('employee_id', None)
    session.pop('employee_login', None)
    flash('Sesión del empleado cerrada.', 'info')
    if slug:
        return redirect(url_for('employee_portal.login', slug=slug))
    return redirect(url_for('auth.login'))
