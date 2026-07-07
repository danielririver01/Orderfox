from datetime import date, datetime, timezone, timedelta
from sqlalchemy import func
from app.models import db, Order


class DashboardService:
    """Estadísticas y polling del dashboard. Compartido por web y API routes."""

    @staticmethod
    def _get_today_start():
        now = datetime.now(timezone.utc)
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

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
