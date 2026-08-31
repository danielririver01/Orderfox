# Política de Autenticación

**Versión:** 2.0 | **Fecha:** 2026-08-22 | **Propietario:** Equipo Técnico
> Estado verificado contra el código actual (commit `7994803` + ciclo de vida `dormant`).

---

## 1. Filosofía: La Base de Datos es la Fuente de Verdad

El sistema **nunca** otorga acceso sin un registro correspondiente en la base de datos local. Clerk es el proveedor de identidad OAuth, pero la base de datos local (`User`, `Restaurant`) es el sistema de registro autoritativo. La sesión Flask (cookie) y el JWT (API) son dos caras del mismo acceso.

---

## 2. Mecanismos de Autenticación (3)

| Mecanismo | Token | Uso |
|-----------|-------|-----|
| **Sesión** | Cookie Flask (`user_id` o `employee_id`) | Dashboard web del dueño / portal de empleado (PIN) |
| **JWT** | `Authorization: Bearer <token>` (24h, firmado por Clerk vía PyJWT 2.13) | API móvil / externa |
| **Clerk OAuth** | Redirect + callback | Login social web |

---

## 3. Flujos

### 3.1 Clerk OAuth (Web dueño)
1. Login vía Clerk (redirect) → callback recibe `clerk_id` + perfil.
2. `auth_service.sync_or_create_user(clerk_id, email, username)` busca `User.clerk_id`.
   - **Existe** → inicia sesión, redirige al dashboard.
   - **No existe** → auto-crea usuario (ver §4) y envía a `/auth/setup-account`.
3. Si el JWT de Clerk no valida → `401` (`unauthorized`).

### 3.2 JWT (API)
1. `verify_jwt_in_request()` (flask-jwt-extended) valida firma.
2. `get_jwt_identity()` → `user_id` → se busca `User` local.
   - Existe + restaurante → acceso.
   - No existe → `401` `USER_NOT_REGISTERED`.
3. `SERVICE_API_KEY` (header `x-api-key`, p.ej. Scanner IA) exime rate limits y some checks.

### 3.3 Sesión (Dashboard Web)
- Cookie de sesión segura; `require_auth` verifica `user_id` o `employee_id` en sesión.
- El dueño entra con `user_id`; el empleado con `employee_id` (portal PIN, ver §5).

---

## 4. Auto-Creación de Usuario y Trial

`auth_service.sync_or_create_user` / `create_restaurant_for_user`:
1. Recibe `clerk_id`, `email`, `username` (y opcionalmente `selected_plan` desde `PreRegistration`).
2. Crea `User` (`clerk_id`, `email`, `username`, password hash = clerk_id).
3. Crea `Restaurant` + asocia `User` (role `owner`).
4. Plan y duración:
   - **Trial:** `plan_type='trial'`, `subscription_expires_at = now + 60 días`, `has_used_trial=True`, registro en `TrialHistory` (email + whatsapp).
   - **De pago:** `plan_type` según `PreRegistration.selected_plan` (`emprendedor`/`crecimiento`/`elite`).
5. Crea `AITokenWallet` con `plan_limit=100` si es trial (None si es plan de pago).

### Reglas del Trial
- **Duración:** **60 días** (no 7). Hard-coded en `auth_service.create_restaurant_for_user`.
- **Unicidad:** un trial por email + whatsapp (`TrialHistory` + `Restaurant.has_used_trial`). `check_trial_eligibility()` bloquea si ya usó uno → error `TRIAL_ALREADY_USED`.
- **Grace period post-expiración:** `GRACE_PERIOD_DAYS = 5` en `app/utils/subscription.py` (⚠️ docs legales dicen 14; pendiente homogeneizar).

---

## 5. Empleados (Portal PIN)

Los empleados son filas de `User` con `role` en `{cashier, waiter}` y `pin_hash` (PIN de 4 dígitos), asociadas al `Restaurant` del dueño. **No** tienen cuenta Clerk ni JWT.

- **Login:** `POST /empleado/<slug>` con PIN (sin `@require_auth`). Valida `pin_hash`; en éxito setea `employee_id` en sesión.
- **Portal:**-opera la caja registradora (`cash_register.py`).
- **Gestión (solo dueño):** `/equipo/...` protegido por `@require_role('owner')`: crear (con PIN), desactivar, reactivar, cambiar PIN.
- **Protección anti-fuerza-bruta:** el commit `7994803` añadió límites de intentos en login/PIN (ver `app/__init__.py` y `auth.py`).

---

## 6. Estados de Cuenta y Acceso

`app/utils/subscription.py → get_subscription_status(restaurant)`:

| Estado | Significado | Acceso |
|--------|-------------|--------|
| `active` | Suscripción vigente | CRUD completo |
| `trial` | Período de prueba (60 días) | CRUD completo |
| `expiring_soon_*` | <7 días para vencer (neutral/warning/urgent) | CRUD completo + banner |
| `grace_period` | Hasta `GRACE_PERIOD_DAYS` tras expiración | Solo lectura (sin CRUD) |
| `expired` | Pasó grace period, aún `is_active` | Solo dashboard (sin CRUD) |
| `dormant` | Marcado por lifecycle (3 AM) tras >grace o >30d inactivo | **Sin CRUD**; datos preservados; reactivable en 1 clic |
| `inactive` | Suspensión admin manual (`is_active=False`, no dormant) | Solo login |
| `no_subscription` | Sin `subscription_expires_at` | Solo dashboard |
| `not_found` | Sin restaurante | Setup |

`require_active` permite CRUD durante `grace_period` (`include_grace_period=True`); bloquea en `expired`/`dormant`/`inactive` y redirige a `dashboard.subscription`. Para `dormant` muestra banner de reactivación.

---

## 7. Códigos de Error / Respuestas

| Código / clave | Significado | HTTP |
|----------------|-------------|------|
| `USER_NOT_REGISTERED` | Clerk OK pero sin `User` local | 401 |
| `unauthorized` | Sesión/JWT inválido o expirado | 401 |
| `TRIAL_ALREADY_USED` | Email/whatsapp ya usó trial | 403/402 |
| `SUBSCRIPTION_EXPIRED` / `GRACE_PERIOD` | Sin acceso por suscripción | 402/403 |
| `FEATURE_NOT_AVAILABLE` | Plan no incluye feature | 403 |
| `TOKEN_INSUFFICIENT` | Sin tokens AI suficientes | 402 |
| `dormant: true` | Cuenta inactiva, reactivar | 402 (JSON) |
| `INVALID_CREDENTIALS` | Email/password incorrectos (auth local) | 401 |

---

## 8. Decoradores (unificados en `app/utils/auth.py`)

Reemplazan a los viejos `@login_required`/`@active_required`/`@flexible_*` de `jwt_auth.py`:

| Decorator | Verifica |
|-----------|----------|
| `require_auth` | Login (sesión `user_id`/`employee_id` O JWT Bearer) |
| `require_active` | Login + cuenta activa (maneja `dormant`/`grace_period`/`expired`; excluye endpoint `subscription`) |
| `require_feature(name)` | `require_auth` + feature habilitada por plan |
| `require_role(*roles)` / `require_role_check` | `require_auth` + rol de empleado/dueño |
| Helpers `jwt_auth.py` | `get_current_user_jwt()` / `get_current_restaurant_jwt()` (extracción cruda) |

---

## 9. Historial de Cambios

| Fecha | Versión | Cambio | Autor |
|-------|---------|--------|-------|
| 2026-06-16 | 1.0 | Versión inicial | Auditoría Documental |
| 2026-08-22 | 2.0 | Trial 60 días (no 7); empleados como `User`+PIN (roles cashier/waiter) con portal `/empleado/<slug>` y anti-fuerza-bruta; decoradores unificados en `auth.py`; estados `dormant` y `expiring_soon_*`; `TRIAL_ALREADY_USED`; PyJWT 2.13 | Agente |
