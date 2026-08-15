import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.models import Order, OrderItem, Restaurant, TrialHistory, User, db
from app.services.theme_service import (
    BRAND_THEMES,
    DEFAULT_BRAND_COLOR,
    get_branding_permissions,
)
from app.utils.cover_bank import CUISINE_TYPES
from app.utils.image_handler import delete_image, save_image
from app.utils.timezone import COLOMBIA_TZ, today_start_utc

logger = logging.getLogger(__name__)


class DashboardService:
    """Estadísticas y polling del dashboard. Compartido por web y API routes."""

    @staticmethod
    def _get_today_start():
        """Inicio del día actual en hora de Colombia (medianoche Bogotá), en UTC."""
        return today_start_utc()

    @staticmethod
    def _get_date_range(range_type):
        """Return (start_date,) based on range_type. Supported: today, week, month."""
        now = datetime.now(timezone.utc)
        if range_type == 'month':
            return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif range_type == 'week':
            return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def get_today_overview(restaurant_id):
        """
        Return dict with today's order counts and sales.
        Active orders (pending/confirmed) — no date filter.
        Completed orders (delivered/cancelled) — filtered to today.
        Sales — confirmed + delivered today.
        """
        today_start = DashboardService._get_today_start()

        # Active orders: no date filter
        active_stats = db.session.query(
            Order.status, func.count(Order.id)
        ).filter(
            Order.restaurant_id == restaurant_id,
            Order.status.in_(['pending', 'confirmed'])
        ).group_by(Order.status).all()

        # Completed orders: today only
        completed_stats = db.session.query(
            Order.status, func.count(Order.id)
        ).filter(
            Order.restaurant_id == restaurant_id,
            Order.status.in_(['delivered', 'cancelled']),
            Order.created_at >= today_start
        ).group_by(Order.status).all()

        # Merge counts
        counts = {}
        for s, c in active_stats + completed_stats:
            counts[s] = counts.get(s, 0) + c

        # Today sales
        total_sales = db.session.query(func.sum(Order.total)).filter(
            Order.restaurant_id == restaurant_id,
            Order.created_at >= today_start,
            Order.status.in_(['confirmed', 'delivered'])
        ).scalar() or 0

        return {
            'today_orders': sum(counts.values()),
            'pending': counts.get('pending', 0),
            'confirmed': counts.get('confirmed', 0),
            'preparing': counts.get('preparing', 0),
            'delivered': counts.get('delivered', 0),
            'cancelled': counts.get('cancelled', 0),
            'today_sales_cop': int(total_sales),
        }

    @staticmethod
    def get_extended_stats(restaurant_id, range_type='today'):
        """
        Return extended stats for a date range.
        Returns total_orders, total_sales, avg_order_value, orders_by_status.
        """
        start_date = DashboardService._get_date_range(range_type)

        total_sales = db.session.query(func.sum(Order.total)).filter(
            Order.restaurant_id == restaurant_id,
            Order.created_at >= start_date,
            Order.status.in_(['confirmed', 'delivered'])
        ).scalar() or 0

        total_orders = Order.query.filter(
            Order.restaurant_id == restaurant_id,
            Order.created_at >= start_date
        ).count()

        orders_by_status = db.session.query(
            Order.status, func.count(Order.id)
        ).filter(
            Order.restaurant_id == restaurant_id,
            Order.created_at >= start_date
        ).group_by(Order.status).all()

        status_counts = {s: c for s, c in orders_by_status}
        avg_order_value = int(total_sales) / total_orders if total_orders > 0 else 0

        return {
            'total_orders': total_orders,
            'total_sales_cop': int(total_sales),
            'avg_order_value_cop': int(avg_order_value),
            'orders_by_status': status_counts,
        }

    @staticmethod
    def get_top_product_30d(restaurant_id):
        """Producto más vendido por ingresos en los últimos 30 días."""
        since_30d = (datetime.now(timezone.utc) - timedelta(days=30)).date()
        row = (
            db.session.query(
                OrderItem.product_name,
                func.sum(OrderItem.subtotal).label('revenue'),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .filter(
                OrderItem.restaurant_id == restaurant_id,
                Order.status != 'cancelled',
                func.date(Order.created_at) >= since_30d,
            )
            .group_by(OrderItem.product_name)
            .order_by(func.sum(OrderItem.subtotal).desc())
            .first()
        )
        if row:
            return {'name': row.product_name, 'revenue': int(row.revenue)}
        return None

    @staticmethod
    def get_order_polling(restaurant_id):
        """
        Return dict with last_id, pending_count, and recent pending orders.
        """
        last_id = db.session.query(func.max(Order.id)).filter(
            Order.restaurant_id == restaurant_id
        ).scalar() or 0

        pending_count = Order.query.filter(
            Order.restaurant_id == restaurant_id,
            Order.status == 'pending'
        ).count()

        recent_orders = Order.query.filter(
            Order.restaurant_id == restaurant_id,
            Order.status == 'pending'
        ).order_by(Order.created_at.desc()).limit(10).all()

        return {
            'last_id': last_id,
            'pending_count': pending_count,
            'new_orders': [
                {
                    'id': o.id,
                    'order_number': o.order_number,
                    'customer_name': o.customer_name,
                    'total': o.total,
                    'status': o.status,
                    'created_at': o.created_at.isoformat() if o.created_at else None,
                }
                for o in recent_orders
            ]
        }

    # ── Dashboard Inicio: narrativa + comparativa ─────────────────────────────

    @staticmethod
    def _delta_pct(current, previous):
        """Porcentaje de cambio seguro (nunca Infinity/NaN)."""
        if not previous or previous <= 0:
            return None
        return round(((current - previous) / previous) * 100)

    @staticmethod
    def get_comparative_stats(restaurant_id, range_type='today'):
        """
        Devuelve {current, previous, delta_pct, verdict} para Hoy vs Ayer
        o Mes vs Mes anterior.
        """
        now_utc = datetime.now(timezone.utc)

        if range_type == 'today':
            # Hoy: medianoche Colombia → UTC
            today_start = today_start_utc()
            yesterday_start = today_start - timedelta(days=1)

            current_sales = db.session.query(func.sum(Order.total)).filter(
                Order.restaurant_id == restaurant_id,
                Order.created_at >= today_start,
                Order.status.in_(['confirmed', 'delivered'])
            ).scalar() or 0

            current_orders = db.session.query(func.count(Order.id)).filter(
                Order.restaurant_id == restaurant_id,
                Order.created_at >= today_start,
                Order.status.in_(['confirmed', 'delivered'])
            ).scalar() or 0

            previous_sales = db.session.query(func.sum(Order.total)).filter(
                Order.restaurant_id == restaurant_id,
                Order.created_at >= yesterday_start,
                Order.created_at < today_start,
                Order.status.in_(['confirmed', 'delivered'])
            ).scalar() or 0

            previous_orders = db.session.query(func.count(Order.id)).filter(
                Order.restaurant_id == restaurant_id,
                Order.created_at >= yesterday_start,
                Order.created_at < today_start,
                Order.status.in_(['confirmed', 'delivered'])
            ).scalar() or 0

        else:  # month
            now_col = datetime.now(COLOMBIA_TZ)
            this_month_start_col = now_col.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            this_month_start_utc = this_month_start_col.astimezone(timezone.utc).replace(tzinfo=None)

            last_month_end_col = this_month_start_col - timedelta(days=1)
            last_month_start_col = last_month_end_col.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            last_month_start_utc = last_month_start_col.astimezone(timezone.utc).replace(tzinfo=None)
            last_month_end_utc = this_month_start_utc

            current_sales = db.session.query(func.sum(Order.total)).filter(
                Order.restaurant_id == restaurant_id,
                Order.created_at >= this_month_start_utc,
                Order.status.in_(['confirmed', 'delivered'])
            ).scalar() or 0

            current_orders = db.session.query(func.count(Order.id)).filter(
                Order.restaurant_id == restaurant_id,
                Order.created_at >= this_month_start_utc,
                Order.status.in_(['confirmed', 'delivered'])
            ).scalar() or 0

            previous_sales = db.session.query(func.sum(Order.total)).filter(
                Order.restaurant_id == restaurant_id,
                Order.created_at >= last_month_start_utc,
                Order.created_at < last_month_end_utc,
                Order.status.in_(['confirmed', 'delivered'])
            ).scalar() or 0

            previous_orders = db.session.query(func.count(Order.id)).filter(
                Order.restaurant_id == restaurant_id,
                Order.created_at >= last_month_start_utc,
                Order.created_at < last_month_end_utc,
                Order.status.in_(['confirmed', 'delivered'])
            ).scalar() or 0

        delta_pct = DashboardService._delta_pct(int(current_sales), int(previous_sales))

        # Veredicto textual
        cur = int(current_sales)
        prev = int(previous_sales)
        if cur > 0 and prev > 0:
            verdict = 'comparativa'
        elif cur > 0 and prev == 0:
            verdict = 'primeras_ventas'
        elif cur == 0 and prev > 0:
            verdict = 'sin_ventas_hoy'
        else:
            verdict = 'sin_datos'

        return {
            'current_sales': cur,
            'current_orders': int(current_orders),
            'previous_sales': prev,
            'previous_orders': int(previous_orders),
            'delta_pct': delta_pct,
            'verdict': verdict,
        }

    @staticmethod
    def get_home_narrative(restaurant_id, user):
        """
        Narrativa del hero: saludo + frase contextúa + plato estrella 30d.
        Sin cache en v1.
        """
        import time
        t0 = time.monotonic()

        now_col = datetime.now(COLOMBIA_TZ)
        hour = now_col.hour
        if 5 <= hour < 12:
            saludo = 'Buenos días'
        elif 12 <= hour < 18:
            saludo = 'Buenas tardes'
        else:
            saludo = 'Buenas noches'

        nombre = (user.username or '').strip() or None if user else None

        # Plato estrella 30 días
        since_30d = (datetime.now(timezone.utc) - timedelta(days=30)).date()
        top_row = (
            db.session.query(
                OrderItem.product_name,
                func.sum(OrderItem.quantity).label('qty'),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .filter(
                OrderItem.restaurant_id == restaurant_id,
                Order.status != 'cancelled',
                func.date(Order.created_at) >= since_30d,
            )
            .group_by(OrderItem.product_name)
            .order_by(func.sum(OrderItem.quantity).desc())
            .first()
        )

        elapsed_ms = round((time.monotonic() - t0) * 1000)
        logger.debug(
            'get_home_narrative restaurant=%d plato_estrella_ms=%d',
            restaurant_id, elapsed_ms
        )

        plato_estrella = top_row.product_name if top_row else None

        return {
            'saludo': saludo,
            'nombre': nombre,
            'plato_estrella': plato_estrella,
        }

    @staticmethod
    def get_recent_pending_limited(restaurant_id, limit=3):
        """
        Retorna (orders_list, total_pending) para la sección de atención.
        Cada order: {id, order_number, customer_name, total, table_name, elapsed}.
        """
        total_pending = Order.query.filter(
            Order.restaurant_id == restaurant_id,
            Order.status == 'pending'
        ).count()

        recent = Order.query.filter(
            Order.restaurant_id == restaurant_id,
            Order.status == 'pending'
        ).order_by(Order.created_at.desc()).limit(limit).all()

        now_utc = datetime.now(timezone.utc)
        orders = []
        for o in recent:
            elapsed = ''
            if o.created_at:
                diff = now_utc - (o.created_at if o.created_at.tzinfo else o.created_at.replace(tzinfo=timezone.utc))
                mins = int(diff.total_seconds() / 60)
                if mins < 1:
                    elapsed = 'ahora'
                elif mins < 60:
                    elapsed = f'hace {mins}m'
                else:
                    hours = mins // 60
                    elapsed = f'hace {hours}h'

            table_name = o.table.name if o.table else None
            orders.append({
                'id': o.id,
                'order_number': o.order_number,
                'customer_name': o.customer_name or 'Cliente',
                'total': o.total,
                'table_name': table_name,
                'elapsed': elapsed,
            })

        return orders, total_pending

    @staticmethod
    def toggle_status(restaurant, is_open):
        """Toggle restaurant open/closed."""
        restaurant.is_open = is_open
        db.session.commit()
        return restaurant.is_open

    @staticmethod
    def get_user(user_id):
        """Return User by ID or None."""
        return User.query.get(user_id)

    @staticmethod
    def get_expense_stats(user, start_date):
        """
        Query the velzia_expense table for total expenses by clerk_id.

        Returns int (0 on failure or no data).
        """
        try:
            query = db.text("""
                SELECT COALESCE(SUM(amount), 0) as total
                FROM velzia_expense
                WHERE userId = :clerk_id AND date >= :start_date
            """)
            result = db.session.execute(query, {
                'clerk_id': user.clerk_id,
                'start_date': start_date
            })
            row = result.fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    @staticmethod
    def delete_restaurant(restaurant, clerk_id=None):
        """
        Delete a restaurant and clear session on success.

        Orden crítico (Bug 2): primero se elimina el usuario en Clerk;
        SOLO si Clerk confirma se borra en DB. Si Clerk falla, no se toca
        la DB (no dejar la cuenta en estado intermedio).

        Returns (True, message_dict) or (False, error_dict).
        """
        if clerk_id:
            from app.services.auth_service import AuthService
            clerk_ok, clerk_error = AuthService.delete_clerk_user(clerk_id)
            if not clerk_ok:
                return False, {'message': clerk_error, 'clerk_error': True}

        try:
            db.session.delete(restaurant)
            db.session.commit()
            return True, {'message': 'Cuenta eliminada exitosamente'}
        except Exception:
            db.session.rollback()
            return False, {'message': 'Error al eliminar la cuenta'}

    @staticmethod
    def _can_apply_brand_color(restaurant, new_color):
        """
        Valida si un restaurante puede aplicar un brand_color según su plan.

        Reglas:
        - Élite / Trial (custom_allowed): cualquier hex válido pasa.
        - Crecimiento (themes_allowed, sin custom): solo hex de BRAND_THEMES.
        - Emprendedor (sin themes ni custom): solo el color por defecto.
        - Downgrade: si el restaurante ya tiene un color guardado (de un plan
          superior), se respeta — solo se bloquea el cambio a un color nuevo.
        """
        current = (restaurant.brand_color or '').strip().lower()
        new = new_color.strip().lower()

        # Respetar el color ya guardado (regla de downgrade): si es el mismo,
        # no es un cambio, se permite.
        if current and current == new:
            return True

        perms = get_branding_permissions(restaurant.plan_type)
        if perms['custom_allowed']:
            return True

        theme_hexes = [t['hex'].lower() for t in BRAND_THEMES]
        if perms['themes_allowed']:
            return new in theme_hexes

        # Emprendedor: solo el color por defecto.
        return new == DEFAULT_BRAND_COLOR.lower()

    @staticmethod
    def update_profile(restaurant, user, restaurant_name, whatsapp_phone, username,
                       cover_image=None, estimated_time=None, brand_color=None,
                       cuisine_type=None, delete_cover_image=False):
        """
        Update restaurant name, phone, user display name, and public menu
        branding fields (cover_image, estimated_time, brand_color, cuisine_type).

        Returns (True, None) on success or (False, error_message) on failure.
        Checks for name/phone conflicts.
        All new fields are optional (None = no tocar) → backward-compatible
        con call-sites existentes (web + API).
        """
        try:
            if restaurant_name != restaurant.name:
                existing = Restaurant.query.filter(
                    Restaurant.name == restaurant_name,
                    Restaurant.id != restaurant.id
                ).first()
                if existing:
                    return False, 'No se pudieron guardar los cambios. Verifica los datos e intenta de nuevo.'

            if whatsapp_phone != restaurant.whatsapp_phone:
                phone_in_trial = TrialHistory.query.filter(
                    TrialHistory.whatsapp_phone == whatsapp_phone
                ).first()
                phone_in_other = Restaurant.query.filter(
                    Restaurant.whatsapp_phone == whatsapp_phone,
                    Restaurant.id != restaurant.id,
                    Restaurant.has_used_trial == True
                ).first()
                if phone_in_trial or phone_in_other:
                    return False, 'No es posible usar este número. Intenta con otro.'

            # ── Menú público: validaciones antes de escribir ──
            if brand_color is not None and brand_color.strip():
                bc = brand_color.strip()
                if not re.fullmatch(r'#[0-9A-Fa-f]{6}', bc):
                    return False, 'El color de marca debe tener formato #RRGGBB.'
                if not DashboardService._can_apply_brand_color(restaurant, bc):
                    return False, 'Tu plan no permite ese color de marca. Mejora tu plan para personalizarlo.'
                restaurant.brand_color = bc
            elif brand_color is not None:
                restaurant.brand_color = None

            if cuisine_type is not None and cuisine_type.strip():
                ct = cuisine_type.strip()
                if ct not in CUISINE_TYPES:
                    return False, 'Tipo de cocina no válido.'
                restaurant.cuisine_type = ct

            if estimated_time is not None:
                try:
                    et = int(estimated_time)
                except (TypeError, ValueError):
                    et = -1
                if et < 0 or et > 600:
                    return False, 'El tiempo estimado debe ser entre 0 y 600 minutos.'
                restaurant.estimated_time = et if et > 0 else None

            # Portada: subir nueva, o borrar si se pide
            if cover_image and getattr(cover_image, 'filename', ''):
                new_url = save_image(cover_image, 'restaurants')
                if not new_url:
                    return False, 'No se pudo subir la portada. Usa una imagen JPG, PNG o WebP de menos de 10MB.'
                if restaurant.cover_image:
                    delete_image(restaurant.cover_image)
                restaurant.cover_image = new_url
            elif delete_cover_image:
                if restaurant.cover_image:
                    delete_image(restaurant.cover_image)
                restaurant.cover_image = None

            restaurant.name = restaurant_name
            restaurant.whatsapp_phone = whatsapp_phone
            user.username = username.strip() if username else user.username

            db.session.commit()
            return True, None
        except Exception:
            db.session.rollback()
            return False, 'No se pudieron guardar los cambios. Verifica los datos e intenta de nuevo.'

    @staticmethod
    def change_email(user, new_email, confirm_email, current_password=None):
        """
        Change user's email with validation.

        Returns (True, message) on success or (False, error_message, http_status).
        For Clerk users, password is not required.
        """
        if not new_email or not confirm_email:
            return False, 'Todos los campos son requeridos.', 400

        if new_email != confirm_email:
            return False, 'Los correos nuevos no coinciden.', 400

        if '@' not in new_email:
            return False, 'Ingresa un correo valido.', 400

        existing = User.query.filter(User.email == new_email, User.id != user.id).first()
        if existing:
            return False, 'Este correo ya esta registrado por otro usuario.', 400

        if not user.clerk_id:
            if not current_password:
                return False, 'Debes ingresar tu contraseña actual.', 400
            if not user.check_password(current_password):
                return False, 'La contraseña actual es incorrecta.', 400

        try:
            user.email = new_email
            db.session.commit()
            return True, '¡Correo actualizado con exito!', None
        except Exception:
            db.session.rollback()
            return False, 'Error al intentar cambiar el correo. Intenta de nuevo.', 500
