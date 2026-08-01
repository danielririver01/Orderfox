from datetime import date, datetime, timezone, timedelta
from sqlalchemy import func
from app.models import db, Order, Restaurant, User, TrialHistory
from app.utils.timezone import today_start_utc


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
    def delete_restaurant(restaurant):
        """
        Delete a restaurant and clear session on success.

        Returns (True, message_dict) or (False, error_dict).
        """
        try:
            db.session.delete(restaurant)
            db.session.commit()
            return True, {'message': 'Cuenta eliminada exitosamente'}
        except Exception:
            db.session.rollback()
            return False, {'message': 'Error al eliminar la cuenta'}

    @staticmethod
    def update_profile(restaurant, user, restaurant_name, whatsapp_phone, username):
        """
        Update restaurant name, phone, and user display name.

        Returns (True, None) on success or (False, error_message) on failure.
        Checks for name/phone conflicts.
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
        except Exception as e:
            db.session.rollback()
            return False, 'Error al intentar cambiar el correo. Intenta de nuevo.', 500
