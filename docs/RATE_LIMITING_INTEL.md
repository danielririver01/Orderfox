# Sistema Inteligente de Rate Limiting para Pedidos

## Cambio de Enfoque

Se cambió el sistema de rate limiting de una estrategia punitiva simple a un sistema **inteligente que diferencia entre usuarios legítimos y spam**.

### Antes (Sistema Antiguo)
- ❌ Castigo duro: esperar 90 segundos entre pedidos
- ❌ No diferenciaba entre usuarios normales y spam
- ❌ Frustrante para usuarios que olvidan un producto

### Ahora (Sistema Inteligente)
- ✅ Límite normal: 1 pedido cada 12 segundos para usuarios legítimos
- ✅ Límite estricto: 1 pedido cada 30 segundos solo si detecta patrón de spam
- ✅ Análisis de patrones de comportamiento
- ✅ Mejor experiencia de usuario

---

## Cómo Funciona

### 1. **Análisis de Patrones Sospechosos**

El sistema detecta spam analizando:
- **Intentos fallidos recurrentes**: Si ve 3+ pedidos cancelados/expirados en 2 minutos desde la misma IP
- **Comportamiento repetido**: Si intenta hacer demasiados pedidos en muy poco tiempo

```python
def is_suspicious_pattern(restaurant_id, client_ip):
    # Busca 3+ intentos fallidos en los últimos 2 minutos
    # Si encuentra, considera que es spam potencial
```

### 2. **Rate Limiting Dinámico**

Según el patrón detectado, aplica el límite apropiado:

| Patrón | Límite | Intervalo Mínimo |
|--------|--------|------------------|
| **Usuario Normal** | 5 pedidos/minuto | 12 segundos |
| **Patrón Sospechoso** | 2 pedidos/minuto | 30 segundos |

### 3. **Mensaje Amable**

En lugar de "¿Olvidaste algo?", ahora:
- Permite el pedido rápidamente a usuarios normales
- Solo si detecta spam: "Por favor espera X segundos antes de hacer otro pedido."

---

## Archivos Modificados

### 📄 `app/utils/rate_limiter.py` (NUEVO)
Clase `OrderRateLimiter` con métodos:

```python
# Detecta si hay patrón de spam
is_suspicious_pattern(restaurant_id, client_ip)

# Obtiene el límite apropiado para esta IP
get_rate_limit_for_ip(restaurant_id, client_ip)

# Calcula tiempo de espera restante
get_remaining_time_to_retry(restaurant_id, client_ip)

# Decide si bloquear o permitir
should_block_request(restaurant_id, client_ip)

# Registra intentos de pedido para análisis
log_order_attempt(restaurant_id, order, client_ip)
```

### 📄 `app/__init__.py`
- Agregado: `from flask_limiter import Limiter`
- Agregado: Inicialización de `limiter` con estrategia de IP

### 📄 `app/routes/public.py`
- Reemplazado: Lógica antigua de rate limiting (90 segundos fijos)
- Con: Nueva lógica de `OrderRateLimiter.should_block_request()`
- Agregado: Logging de intentos con `OrderRateLimiter.log_order_attempt()`

### 📄 `requirements.txt`
- Agregado: `Flask-Limiter==3.5.0`

---

## Flujo de Validación

```
1. Usuario hace pedido
   ↓
2. Sistema obtiene IP del cliente
   ↓
3. Analiza patrones de comportamiento
   ├─ ¿3+ intentos fallidos recientes? → SPAM POTENCIAL
   └─ ¿Comportamiento normal? → USUARIO LEGÍTIMO
   ↓
4. Aplica límite apropiado
   ├─ Si SPAM: Espera 30 segundos mín
   └─ Si LEGÍTIMO: Espera 12 segundos mín
   ↓
5. Retorna respuesta
   └─ Si bloqueado: {"error": "Espera X segundos...", "retry_after": X}
```

---

## Configuración

### Límites Ajustables en `app/utils/rate_limiter.py`

```python
NORMAL_RATE = "5/minute"          # 5 pedidos/minuto para usuarios normales
STRICT_RATE = "2/minute"          # 2 pedidos/minuto para spam potencial
SUSPICIOUS_THRESHOLD = 3           # Intentos fallidos para considerar spam
REVIEW_WINDOW = 2                  # Minutos para revisar patrones
```

---

## Mejoras Futuras

Para sistemas de mayor escala:

1. **Redis para distributed rate limiting**
   ```python
   storage_uri="redis://localhost:6379"  # Reemplazar "memory://"
   ```

2. **Machine Learning** para detectar patrones más complejos
   - Análisis de fluctuaciones de tiempo
   - Detección de botnets
   - Análisis de geolocalización

3. **Dashboard de monitoreo**
   - IPs listadas en alto riesgo
   - Estadísticas de spam detectado
   - Alertas en tiempo real

---

## Testing

Para probar el nuevo sistema:

```bash
# Scenario 1: Usuario normal (debe permitir después de 12 segundos)
curl -X POST http://localhost:5000/menu/api/order \
  -H "Content-Type: application/json" \
  -d '{"cart": {...}, "restaurant_id": 1, "total": 100}'

# Scenario 2: Hacer 3 pedidos "fallidos" (expired), luego intentar otro
# Resultado: Debe bloquear con límite estricto de 30 segundos
```

---

## Notas de Implementación

- El sistema usa `request.remote_addr` para obtener la IP del cliente
- En producción con proxy/load balancer, usar: `request.headers.get('X-Forwarded-For')`
- Los datos se persisten en la BD (tabla `orders` con campo `notes` para IP)
- Escalable para múltiples restaurantes (tenant-aware)
