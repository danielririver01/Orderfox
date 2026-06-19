# GUIDE-04: Integración con Scanner IA

**Versión:** 1.0 | **Fecha:** 2026-06-16 | **Propietario:** Equipo Técnico

---

## 1. Descripción General

Scanner IA es un servicio externo de inteligencia artificial que consume tokens del sistema de wallets para procesar escaneos de menús. La comunicación es server-to-server usando JWT de Clerk o API Key.

---

## 2. Autenticación

### Opción 1: JWT de Clerk (Recomendada)

Scanner IA genera un JWT firmado usando `CLERK_SECRET_KEY`:

```
Header: Authorization: Bearer <jwt_token>
```

El servidor valida:
1. Firma del JWT contra JWKS endpoint de Clerk
2. Extrae `sub` (clerk_id) del payload
3. Busca `User.clerk_id` en BD local

```python
# TokenService.verify_clerk_jwt() en app/services/token_service.py
payload = jwt.decode(token, jwks_data, algorithms=['RS256'])
clerk_id = payload.get('sub')
user = User.query.filter_by(clerk_id=clerk_id).first()
```

### Opción 2: API Key (Server-to-Server)

Para operaciones internas o cuando no hay un usuario específico:

```
Header: x-api-key: <SERVICE_API_KEY>
```

- Bypass completo de rate limiting
- Bypass de autenticación de usuario
- El usuario se identifica por `?clerk_id=` o `?userId=` en query params

---

## 3. Endpoints

### GET /api/tokens/status

Estado actual del wallet.

**Headers:** `Authorization: Bearer <jwt>` o `x-api-key: <key>`

**Respuesta:**
```json
{
  "is_elite": false,
  "plan_limit": 100,
  "plan_tokens": 85,
  "extra_tokens": 15,
  "total_available": 100,
  "can_scan": true
}
```

### POST /api/tokens/consume

Consumir 1 token por escaneo.

**Headers:** `Authorization: Bearer <jwt>` o `x-api-key: <key>`
**CSRF:** Exento (`@csrf.exempt`)

**Respuesta 200:**
```json
{
  "success": true,
  "message": "Token consumido exitosamente"
}
```

**Respuesta 403 (sin tokens):**
```json
{
  "success": false,
  "error_code": "INSUFFICIENT_TOKENS",
  "message": "No tienes tokens disponibles para escanear."
}
```

---

## 4. Flujo de Consumo

```
Scanner IA                          Orderfox API
     │                                    │
     │   POST /api/tokens/consume         │
     │   Authorization: Bearer <jwt>      │
     ├───────────────────────────────────►│
     │                                    │
     │   1. Verificar JWT (Clerk JWKS)    │
     │   2. Buscar usuario por clerk_id    │
     │   3. Verificar wallet.can_scan()    │
     │   4. Descontar token:              │
     │      ├─ plan_tokens primero        │
     │      └─ extra_tokens después       │
     │   5. Registrar AITokenTransaction   │
     │                                    │
     │   ◄── 200 {"success": true}        │
     │         o                          │
     │   ◄── 403 {"error_code": "..."}    │
```

### Reglas de Consumo

| Tipo de Usuario | ¿Descuenta? | ¿Registra? |
|----------------|-------------|------------|
| Elite | ❌ (ilimitado) | ✅ (como `elite_scan`) |
| Emprendedor/Crecimiento | ✅ (plan → extra) | ✅ (como `consume`) |

---

## 5. Auto-Healing de Base de Datos

Cuando Scanner IA envía un `clerk_id` que no existe en la BD, el sistema intenta vincular automáticamente por email:

```python
# En _get_user_from_request() de app/routes/tokens.py
if email:
    user = User.query.filter_by(email=email).first()
    if user:
        user.clerk_id = clerk_id  # Vincular
        db.session.commit()
```

Esto permite que usuarios creados antes de la migración a Clerk se vinculen automáticamente en su primer escaneo.

---

## 6. Top-Up de Tokens

Los usuarios pueden comprar tokens adicionales desde el dashboard:

| Pack | Precio | Tokens |
|------|--------|--------|
| 5K | 5.000 COP | 15 |
| 10K | 10.000 COP | 35 |

Flujo:
1. `POST /api/tokens/topup/initiate` → crea preferencia en Mercado Pago
2. Usuario paga en checkout de MP
3. MP redirige a `/api/tokens/topup/callback`
4. `TokenService.credit_topup_purchase()` acredita tokens (anti-duplicado por `mp_payment_id`)

---

## 7. Anti-Duplicados

El sistema previene acreditaciones dobles del mismo pago:

```python
already = AITokenTransaction.query.filter_by(
    mp_payment_id=mp_payment_id,
    type='topup_purchase'
).first()
if already:
    return already, None  # No es error, solo saltar
```

---

## 8. Configuración

| Variable | Propósito | Default |
|----------|-----------|---------|
| `SCANNER_IA_URL` | URL base del servicio Scanner IA | `http://localhost:3000` |
| `SERVICE_API_KEY` | API Key para comunicación S2S | — |
| `CLERK_SECRET_KEY` | Para validar JWT de Clerk | — |
| `CLERK_JWT_ISSUER` | Emisor del JWT | `https://oriented-tortoise-50.clerk.accounts.dev` |

---

## 9. Historial de Cambios

| Fecha | Versión | Cambio | Autor |
|-------|---------|--------|-------|
| 2026-06-16 | 1.0 | Versión inicial | Auditoría Documental |
