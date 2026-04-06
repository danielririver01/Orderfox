from datetime import datetime, timedelta, timezone
from app.models import db, Order

class OrderRateLimiter:
    """
    Sistema inteligente de rate limiting para pedidos (Anti-Bots).
    - Permite reintentos rápidos para humanos (sin bloqueo de 5-12s).
    - Protege contra ráfagas (max 3 pedidos por minuto).
    - Bloqueo administrativo de 10 minutos si se detecta spam.
    """
    
    MAX_ORDERS_PER_MINUTE = 3
    BAN_DURATION_MINUTES = 10
    
    @staticmethod
    def get_recent_orders_count(restaurant_id, client_ip, minutes=1):
        """Cuenta pedidos exitosos o pendientes de esta IP en el rango de tiempo."""
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return Order.query.filter(
            Order.restaurant_id == restaurant_id,
            Order.notes.ilike(f"%IP:{client_ip}%"),
            Order.created_at >= since,
            Order.status.in_(['pending', 'completed'])
        ).count()

    @staticmethod
    def is_ip_banned(restaurant_id, client_ip):
        """Verifica si la IP superó el límite recientemente y debe estar en 'penitencia'."""
        # Si en los últimos 10 minutos hubo más de 3 pedidos, está bloqueado
        recent_count = OrderRateLimiter.get_recent_orders_count(
            restaurant_id, client_ip, minutes=OrderRateLimiter.BAN_DURATION_MINUTES
        )
        return recent_count >= OrderRateLimiter.MAX_ORDERS_PER_MINUTE

    @staticmethod
    def should_block_request(restaurant_id, client_ip):
        """
        Determina si se debe bloquear la solicitud de un nuevo pedido.
        Nueva estrategia: Sin intervalos fijos cortos, solo protección contra ráfagas.
        
        Returns:
            tuple: (should_block: bool, message: str, wait_seconds: int or None)
        """
        # 1. Verificar si ya alcanzó el límite de ráfaga (3/min)
        orders_last_minute = OrderRateLimiter.get_recent_orders_count(restaurant_id, client_ip, minutes=1)
        
        if orders_last_minute >= OrderRateLimiter.MAX_ORDERS_PER_MINUTE:
            return True, "Parece que has realizado muchos pedidos seguidos. Por seguridad, por favor espera unos minutos.", 600

        # 2. Verificar si está en periodo de baneo (10 min)
        if OrderRateLimiter.is_ip_banned(restaurant_id, client_ip):
             return True, "Sistema de seguridad activado: Por favor espera unos minutos antes de intentar de nuevo.", 600

        return False, None, None
    
    @staticmethod
    def log_order_attempt(restaurant_id, order, client_ip):
        """Registra la IP en las notas del pedido para el seguimiento del rate limit."""
        if order.notes:
            order.notes += f" | IP:{client_ip}"
        else:
            order.notes = f"IP:{client_ip}"
