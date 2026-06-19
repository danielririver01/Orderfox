# ARCH-04: Flujo de Suscripción y Facturación

**Versión:** 1.0 | **Fecha:** 2026-06-16 | **Propietario:** Equipo Técnico

---

## 1. Ciclo de Vida de la Suscripción

```
Registro
   │
   ▼
┌───────────┐
│   TRIAL   │ (7 días gratis, todas las funcionalidades)
└─────┬─────┘
      │
      ├── Se compra plan ──────────→ ┌───────────┐
      │                              │  ACTIVE   │
      │                              └─────┬─────┘
      │                                    │
      └── No compra + expira trial ──→ ┌───────────┐
                                       │   GRACE   │ (14 días, solo lectura)
                                       │  PERIOD   │
                                       └─────┬─────┘
                                             │
                        ┌── Compra plan ─────┘
                        │
                        └── Expira grace ──→ ┌───────────┐
                                              │  EXPIRED  │ (sin acceso CRUD)
                                              └───────────┘
```

---

## 2. Estados

| Estado | ¿CRUD? | ¿API? | ¿Dashboard? | Duración |
|--------|--------|-------|-------------|----------|
| `trial` | ✅ | ✅ | ✅ | 7 días desde creación |
| `active` | ✅ | ✅ | ✅ | Hasta fecha de expiración |
| `grace_period` | ❌ | ❌ | ✅ (solo lectura) | 14 días post-expiración |
| `expired` | ❌ | ❌ | ⚠️ (limitado) | Indefinido |
| `inactive` | ❌ | ❌ | ❌ | Hasta reactivación manual |

---

## 3. Planes Disponibles

| Plan | Precio Mensual | Productos | Mesas QR | Modifiers | Tokens AI |
|------|---------------|-----------|----------|-----------|-----------|
| **Trial** | Gratis (7d) | Ilimitado | ✅ | ✅ | 100 |
| **Emprendedor** | 30.000 COP | 25 | ❌ | ❌ | 0 |
| **Crecimiento** | 40.000 COP | 100 | ✅ | ✅ | 0 |
| **Elite** | 50.000 COP | Ilimitado | ✅ | ✅ | Ilimitados |

### Límites por Plan

```python
PLAN_LIMITS = {
    'trial':       {'max_products': None, 'table_qr': True,  'modifiers': True,  'tokens': 100},
    'emprendedor': {'max_products': 25,   'table_qr': False, 'modifiers': False, 'tokens': 0},
    'crecimiento': {'max_products': 100,  'table_qr': True,  'modifiers': True,  'tokens': 0},
    'elite':       {'max_products': None, 'table_qr': True,  'modifiers': True,  'tokens': None},  # None = ilimitado
}
```

### Feature Checks

```python
check_feature_access(restaurant, 'table_qr')    # ¿Puede usar QR por mesa?
check_feature_access(restaurant, 'modifiers')   # ¿Puede tener modificadores?
```

---

## 4. Función Central: `get_subscription_status()`

Ubicación: `app/utils/subscription.py`

```python
def get_subscription_status(restaurant):
    """
    Calcula el estado actual de la suscripción.
    Retorna un diccionario con:
    - is_active: bool
    - status: str (active|expiring_soon|grace_period|expired|inactive)
    - message: str (mensaje en español)
    - formatted_expiration: str
    - badge_class: str (clases CSS)
    - badge_text: str
    - can_crud: bool
    """
```

### Lógica de Cálculo

```
1. Si restaurant.is_active == False
   → status = 'inactive', can_crud = False

2. Si restaurant.subscription_expires_at == None
   → status = 'expired', can_crud = False

3. Calcular días restantes:
   days_left = (expires_at - now_utc).days

4. Si days_left > 0:
   ├── days_left <= 7 → 'expiring_soon' (can_crud = True)
   └── days_left > 7  → 'active' (can_crud = True)

5. Si days_left <= 0:
   ├── days_since_expiry <= 14 → 'grace_period' (can_crud = False)
   └── days_since_expiry > 14  → 'expired' (can_crud = False)
```

---

## 5. Flujo de Pago (Mercado Pago)

### Suscripción Inicial

```
1. Usuario selecciona plan en /dashboard/subscription
2. Frontend envía solicitud a Mercado Pago:
   - preference con amount = precio del plan
   - external_reference = "{restaurant_id}:{plan_type}"
3. MP redirige a checkout
4. Usuario paga
5. MP envía webhook a /api/webhook/mp
6. Servidor:
   - Valida firma del webhook
   - Busca external_reference
   - Actualiza subscription_expires_at = now + 1 mes
   - Actualiza plan_type del restaurant
   - Renueva tokens AI si aplica
```

### Renovación

- No hay pagos recurrentes automáticos (el usuario debe renovar manualmente)
- Se puede renovar desde /dashboard/subscription antes de que expire

### Top-up de Tokens

```
1. Usuario selecciona pack (5K COP = 15 tokens, 10K COP = 35 tokens)
2. MP genera preference con external_reference = "token_topup:{user_id}:{pack_key}"
3. Usuario paga
4. Webhook recibe pago:
   - Verifica anti-duplicado por mp_payment_id
   - Agrega extra_tokens al AITokenWallet del usuario
   - Registra AITokenTransaction
```

---

## 6. Período de Gracia (14 días)

- Comienza automáticamente cuando `subscription_expires_at < now_utc`
- El usuario puede ver el dashboard pero NO crear/editar/eliminar contenido
- El bloqueo se implementa en `app/__init__.py` via `before_request`:

```python
@app.before_request
def block_grace_period_crud():
    """Bloquea POST/PUT/DELETE durante grace_period."""
    if request.endpoint and not request.path.startswith('/api/'):
        sub = get_subscription_status(current_restaurant)
        if sub['status'] == 'grace_period' and request.method in ('POST', 'PUT', 'DELETE'):
            flash(sub['message'], 'warning')
            return redirect(request.referrer or url_for('dashboard_bp.index'))
```

---

## 7. Sistema de Tokens AI

### Asignación Mensual

- Al crear/renovar suscripción: `plan_tokens = plan_limit`
- Elite: `plan_limit = NULL` (ilimitado, no se descuenta)
- Reset automático mensual vía calendario o renovación de plan

### Consumo

```python
def consume_token(user, amount=1, source='scanner_ia', description=''):
    wallet = user.token_wallet
    if wallet.is_elite:
        # Elite: no descuenta, solo registra
        log = AITokenTransaction(user_id=user.id, type='elite_scan', amount=0, ...)
    else:
        # Descuenta primero plan_tokens, luego extra_tokens
        if wallet.plan_tokens >= amount:
            wallet.plan_tokens -= amount
        else:
            remaining = amount - wallet.plan_tokens
            wallet.plan_tokens = 0
            wallet.extra_tokens -= remaining
        log = AITokenTransaction(user_id=user.id, type='consume', amount=-amount, ...)
```

---

## 8. Tareas Programadas

Ver `app/tasks.py`:

| Tarea | Horario | Acción |
|-------|---------|--------|
| `delete_inactive_accounts()` | Diario 3:00 AM | Elimina restaurantes inactivos >24h (cascade: users, orders, products) |
| `expire_pending_orders()` | Cada hora | Marca orders como 'expired' si pasaron expires_at |

---

## 9. Pruebas

```bash
# Suite de pruebas de suscripción
python test_subscription_utc.py
```

Escenarios validados:
- Sin suscripción
- Suscripción activa / por expirar
- Período de gracia (14 días)
- Expiración definitiva
- Independencia de zona horaria del servidor

---

## 10. Historial de Cambios

| Fecha | Versión | Cambio | Autor |
|-------|---------|--------|-------|
| 2026-06-16 | 1.0 | Versión inicial | Auditoría Documental |
