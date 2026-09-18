"""
employee_service.py — Lógica de negocio de empleados (sistema de roles v2.1.0).

Roles válidos: owner | cashier | waiter.
- El dueño (owner) es quien crea el restaurante: no tiene PIN.
- Los empleados (cashier/waiter) entran por PIN de 4 dígitos.

Reglas:
- El PIN nunca se guarda en texto plano (werkzeug generate_password_hash).
- `authenticate_employee` devuelve el usuario o None; la ruta distingue
  bloqueo activo para mostrar un mensaje claro (el error de PIN sigue
  siendo genérico, sin revelar qué falló).
- v2.1.4 fix: el bloqueo por fuerza bruta es INDIVIDUAL (antes, un empleado
  bloqueado impedía entrar a todos los del restaurante).
- `unlock_employee`: el dueño puede liberar el bloqueo desde Equipo.
- `deactivate_employee` desactiva sin borrar (is_active=False).
- El límite de empleados por plan se valida al CREAR (bajar de plan no borra
  empleados existentes, solo bloquea crear nuevos).
- v2.1.3: Protección contra fuerza bruta (bloqueo tras 5 intentos, 30 min).
- v2.1.3: PINs débiles rechazados (blacklist de 20 PINs obvios).
"""
import re
import secrets
from datetime import datetime, timezone, timedelta

from werkzeug.security import generate_password_hash, check_password_hash

from app.models import db, User, Restaurant
from app.utils.subscription import get_plan_limits

# Roles que pueden ser creados como empleado. El owner nunca se crea así.
EMPLOYEE_ROLES = ('cashier', 'waiter')
VALID_ROLES = ('owner', 'cashier', 'waiter')

# v2.1.3: PINs débiles que no deben aceptarse.
BLACKLISTED_PINS = {
    '0000', '1111', '2222', '3333', '4444',
    '5555', '6666', '7777', '8888', '9999',
    '1234', '4321', '1122', '1212', '2580',
    '0852', '1357', '7531', '1470', '0741',
}

# v2.1.3: Configuración de bloqueo.
MAX_PIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 30


class EmployeeValidationError(ValueError):
    """Error de negocio de empleados. El mensaje es seguro para mostrar."""


class EmployeeService:
    """Business logic de empleados. Compartida por rutas web y API."""

    # ── Helpers ─────────────────────────────────────────────

    @staticmethod
    def _validate_pin(pin):
        """El PIN debe ser exactamente 4 dígitos numéricos y no estar en la blacklist."""
        if not isinstance(pin, str) or not re.fullmatch(r'\d{4}', pin):
            raise EmployeeValidationError('El PIN debe tener exactamente 4 dígitos numéricos')
        if pin in BLACKLISTED_PINS:
            raise EmployeeValidationError('Este PIN es demasiado fácil de adivinar. Elige uno más seguro')

    @staticmethod
    def _hash_pin(pin):
        return generate_password_hash(pin)

    @staticmethod
    def _count_employees(restaurant_id):
        """Empleados = usuarios con PIN (cashier/waiter). El dueño no cuenta."""
        return User.query.filter(
            User.restaurant_id == restaurant_id,
            User.pin_hash.isnot(None),
        ).count()

    @staticmethod
    def employee_limit(restaurant):
        """Límite de empleados del plan. None = ilimitado."""
        return get_plan_limits(restaurant.plan_type).get('max_employees')

    # ── Creación ────────────────────────────────────────────

    @staticmethod
    def create_employee(restaurant, name, role, pin):
        """
        Crea un empleado (cashier/waiter) con PIN hasheado.

        Valida rol, PIN de 4 dígitos y el límite del plan. Nunca guarda el
        PIN en texto plano. Devuelve el User creado o lanza
        EmployeeValidationError.
        """
        if not name or not name.strip():
            raise EmployeeValidationError('El nombre del empleado es obligatorio')
        name = name.strip()

        if role not in EMPLOYEE_ROLES:
            raise EmployeeValidationError('El rol debe ser "cajero" o "mesero" (el dueño no se crea como empleado)')

        EmployeeService._validate_pin(pin)

        max_employees = EmployeeService.employee_limit(restaurant)
        if max_employees is not None:
            current = EmployeeService._count_employees(restaurant.id)
            if current >= max_employees:
                plan_name = get_plan_limits(restaurant.plan_type).get('name', restaurant.plan_type)
                plural = 's' if max_employees != 1 else ''
                raise EmployeeValidationError(
                    f'Tu plan {plan_name} permite máximo {max_employees} empleado{plural}. '
                    'Actualiza tu plan para agregar más.'
                )

        # email es NOT NULL + unique en el esquema. Los empleados no usan
        # email/password para entrar (solo PIN), así que se genera uno
        # sintético e irrepetible que nunca se usa para login.
        synthetic_email = f'emp-{restaurant.id}-{secrets.token_hex(4)}@empleado.velzia'

        employee = User(
            restaurant_id=restaurant.id,
            username=name,
            email=synthetic_email,
            # Password inutilizable (los empleados entran por PIN).
            password=generate_password_hash(secrets.token_hex(16)),
            role=role,
            pin_hash=EmployeeService._hash_pin(pin),
            is_active=True,
        )
        db.session.add(employee)
        db.session.commit()
        return employee

    # ── Autenticación por PIN ───────────────────────────────

    @staticmethod
    def is_employee_locked(user):
        """True si el empleado está dentro de su ventana de bloqueo por intentos."""
        if not user or not user.locked_until:
            return False
        locked_utc = (
            user.locked_until.replace(tzinfo=timezone.utc)
            if user.locked_until.tzinfo is None
            else user.locked_until
        )
        return locked_utc > datetime.now(timezone.utc)

    @staticmethod
    def authenticate_employee(slug, pin):
        """
        Valida PIN contra un empleado del restaurante.

        Devuelve el User si el PIN coincide y el empleado está activo, o None
        en cualquier otro caso (PIN incorrecto, restaurante inexistente,
        empleado inactivo) → mensaje genérico en la ruta.

        v2.1.3: Soporte para bloqueo por fuerza bruta.
        v2.1.4 (3 fixes de regresión):
        - El bloqueo es INDIVIDUAL: un empleado bloqueado o inactivo se salta
          y NO impide el login del resto (antes: return None abortaba todo).
        - Un login EXITOSO no castiga a los demás: si el PIN coincide con
          alguien, no se incrementa ningún contador (antes cada login exitoso
          de X sumaba +1 de intento fallido a todos los demás empleados,
          bloqueándolos con el uso normal del día).
        - Solo un intento que falla para TODOS los participantes activos
          cuenta como fallido (contra todos: el atacante no sabe a qué
          empleado ataca). Al llegar a 5 → bloqueo 30 min.
        """
        restaurant = Restaurant.query.filter_by(slug=slug).first()
        if not restaurant:
            return None

        candidates = User.query.filter(
            User.restaurant_id == restaurant.id,
            User.pin_hash.isnot(None),
        ).all()

        # Participantes válidos: activos y sin bloqueo vigente.
        participants = [
            c for c in candidates
            if c.is_active and not EmployeeService.is_employee_locked(c)
        ]

        matched = None
        for candidate in participants:
            if check_password_hash(candidate.pin_hash, pin):
                matched = candidate
                break

        if matched is not None:
            # PIN correcto: resetear contadores del que entró. Nadie más
            # recibe castigo (era un login legítimo, no un intento fallido).
            matched.failed_pin_attempts = 0
            matched.locked_until = None
            db.session.commit()
            return matched

        # Nadie coincidió: intento fallido real. Se cuenta contra todos los
        # participantes activos (no se sabe a qué empleado iba dirigido).
        now = datetime.now(timezone.utc)
        for candidate in participants:
            candidate.failed_pin_attempts = (candidate.failed_pin_attempts or 0) + 1
            if candidate.failed_pin_attempts >= MAX_PIN_ATTEMPTS:
                candidate.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
        db.session.commit()
        return None

    @staticmethod
    def unlock_employee(employee_id, restaurant):
        """
        Libera el bloqueo por fuerza bruta de un empleado (dueño).
        Devuelve (True, None) o (False, mensaje_error).
        """
        employee = User.query.filter_by(
            id=employee_id, restaurant_id=restaurant.id
        ).first()
        if not employee:
            return False, 'Empleado no encontrado'
        if employee.role == 'owner':
            return False, 'No puedes modificar al dueño'
        if employee.pin_hash is None:
            return False, 'Empleado no encontrado'

        employee.failed_pin_attempts = 0
        employee.locked_until = None
        db.session.commit()
        return True, None

    # ── Gestión ─────────────────────────────────────────────

    @staticmethod
    def deactivate_employee(employee_id, restaurant):
        """
        Desactiva un empleado (is_active=False) sin borrar el registro.
        Verifica que pertenezca al restaurante. Devuelve (True, None) o
        (False, mensaje_error).
        """
        employee = User.query.filter_by(
            id=employee_id, restaurant_id=restaurant.id
        ).first()
        if not employee or employee.pin_hash is None:
            return False, 'Empleado no encontrado'
        if employee.role == 'owner':
            return False, 'No puedes desactivar al dueño'

        employee.is_active = False
        db.session.commit()
        return True, None

    @staticmethod
    def reactivate_employee(employee_id, restaurant):
        """
        Reactiva un empleado desactivado. Devuelve (True, None) o
        (False, mensaje_error).
        """
        employee = User.query.filter_by(
            id=employee_id, restaurant_id=restaurant.id
        ).first()
        if not employee or employee.pin_hash is None:
            return False, 'Empleado no encontrado'
        if employee.role == 'owner':
            return False, 'No puedes modificar al dueño'

        employee.is_active = True
        db.session.commit()
        return True, None

    @staticmethod
    def update_employee_pin(employee_id, restaurant, new_pin):
        """
        Cambia el PIN de un empleado (validado a 4 dígitos y hasheado).
        Devuelve (True, None) o (False, mensaje_error).
        """
        EmployeeService._validate_pin(new_pin)

        employee = User.query.filter_by(
            id=employee_id, restaurant_id=restaurant.id
        ).first()
        if not employee or employee.pin_hash is None:
            return False, 'Empleado no encontrado'
        if employee.role == 'owner':
            return False, 'No puedes modificar al dueño'

        employee.pin_hash = EmployeeService._hash_pin(new_pin)
        db.session.commit()
        return True, None
