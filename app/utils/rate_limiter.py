from datetime import datetime, timedelta, timezone
from app.models import db, Order
from flask import session

class OrderRateLimiter:
    """
    Sistema inteligente de rate limiting para pedidos.
    Diferencia entre usuarios legítimos y spam basándose en:
    - Frecuencia de pedidos
    - Patrones de comportamiento
    - Historial de pedidos del usuario
    """
    
    # Límites configurables
    NORMAL_RATE = "5/minute"  # 5 pedidos por minuto para usuarios legítimos
    STRICT_RATE = "2/minute"  # 2 pedidos por minuto si mostramos patrones sospechosos
    SUSPICIOUS_THRESHOLD = 3  # Intentos fallidos antes de considerar spam
    REVIEW_WINDOW = 2  # Minutos para revisar patrones
    
    @staticmethod
    def is_suspicious_pattern(restaurant_id, client_ip):
        """
        Analiza si la IP tiene patrón de spam.
        Retorna True si detecta comportamiento sospechoso.
        
        Patrones a detectar:
        - Múltiples intentos fallidos en corto tiempo
        - Pedidos vacíos o con errores recurrentes
        - Intentos de bypass del sistema
        """
        review_start = datetime.now(timezone.utc) - timedelta(minutes=OrderRateLimiter.REVIEW_WINDOW)
        
        # Buscar intentos fallidos recientes (orders con status 'expired' o errores)
        failed_attempts = Order.query.filter(
            Order.restaurant_id == restaurant_id,
            Order.created_at >= review_start,
            Order.notes.ilike(f"%IP:{client_ip}%"),
            Order.status.in_(['expired', 'cancelled'])
        ).count()
        
        return failed_attempts >= OrderRateLimiter.SUSPICIOUS_THRESHOLD
    
    @staticmethod
    def get_rate_limit_for_ip(restaurant_id, client_ip):
        """
        Retorna el límite de rate appropriate para esta IP.
        
        Returns:
            str: Límite en formato "N/period" ej: "5/minute"
        """
        if OrderRateLimiter.is_suspicious_pattern(restaurant_id, client_ip):
            return OrderRateLimiter.STRICT_RATE
        return OrderRateLimiter.NORMAL_RATE
    
    @staticmethod
    def get_remaining_time_to_retry(restaurant_id, client_ip):
        """
        Calcula cuánto tiempo debe esperar el usuario antes de hacer otro pedido.
        Retorna None si puede hacer otro pedido ahora.
        Retorna segundos si debe esperar.
        """
        # Obtener el último pedido de esta IP en los últimos 2 minutos
        two_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=2)
        
        last_order = Order.query.filter(
            Order.restaurant_id == restaurant_id,
            Order.notes.ilike(f"%IP:{client_ip}%"),
            Order.created_at >= two_minutes_ago
        ).order_by(Order.created_at.desc()).first()
        
        if not last_order:
            return None
        
        # Determinar límite actual
        is_suspicious = OrderRateLimiter.is_suspicious_pattern(restaurant_id, client_ip)
        
        if is_suspicious:
            # Límite estricto: 1 pedido cada 30 segundos
            min_interval = 30
        else:
            # Límite normal: 1 pedido cada 12 segundos
            min_interval = 12
        
        time_since_last = (datetime.now(timezone.utc) - last_order.created_at).total_seconds()
        remaining = min_interval - time_since_last
        
        return max(0, int(remaining)) if remaining > 0 else None
    
    @staticmethod
    def should_block_request(restaurant_id, client_ip):
        """
        Determina si se debe bloquear la solicitud de hacer un nuevo pedido.
        
        Returns:
            tuple: (should_block: bool, message: str, wait_seconds: int or None)
        """
        remaining = OrderRateLimiter.get_remaining_time_to_retry(restaurant_id, client_ip)
        
        if remaining and remaining > 0:
            return True, f"Por favor espera {remaining} segundos antes de hacer otro pedido.", remaining
        
        return False, None, None
    
    @staticmethod
    def log_order_attempt(restaurant_id, order, client_ip):
        """
        Registra información del intento de pedido en las notas para análisis.
        """
        if order.notes:
            order.notes += f" | IP:{client_ip}"
        else:
            order.notes = f"IP:{client_ip}"
