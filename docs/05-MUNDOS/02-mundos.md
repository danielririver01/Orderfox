# 02 — Mundos

Un **mundo** es un vertical del SaaS con frontend propio. El sistema de
Mundos es cómo Velzia pasa de "app de restaurantes" a "plataforma de
negocios de barrio" sin duplicar identidad, billing ni suscripciones.

## Registro de verticales (`app/utils/verticals.py`)

El selector post-registro se construye SOLO desde `VERTICALS`. Agregar el
3er/4º mundo es añadir una entrada + su ruta de setup. Nada de
condicionales regados por `auth.py`.

| Mundo | slug | Estado | Setup |
|-------|------|--------|-------|
| Restaurante | `restaurant` | ✅ Activo | `auth.setup_account` |
| Verdurería | `verduras` | ✅ Activo | `auth.register_verduras` |
| Farmacia | `farmacia` | 🔜 Próximamente | — (sin link) |

> **Decisión de producto (2026-09-22): Delivery NO es mundo del core
> Velzia.** Su tarjeta se eliminó del selector a propósito; su destino se
> definirá después. No re-agregar sin confirmación del dueño (nota durable
> en `verticals.py`).

Cada entrada: `slug` (va a `businesses.vertical` / sesión), `nombre`,
`icono` (material-symbols), `descripcion`, `setup_route`, `enabled`.

## Selector y Hub (una sola superficie)

- **Ruta:** `auth.register_vertical` con dos modos:
  - **Modo registro** (sin tenant): elige tu primer mundo.
  - **Modo hub** (con tenant): "Tus mundos" — tarjetas con chip de estado
    + agregar según plan.
- `dashboard.mundos` (`/dashboard/mundos`) es solo un redirect de
  compatibilidad hacia el selector (para bookmarks, switcher y enlaces
  antiguos).
- **`post_login_target()`**: destino único tras login — con mundo →
  selector en modo hub; sin mundo → selector en modo registro.
- **`build_user_worlds(user)`**: única fuente de la lista de mundos. La
  consumen el selector, el World Switcher y el modo hub. Cada mundo trae
  `chip_label`/`chip_color` (vía `subscription_chip()`, única fuente del
  mapeo estado → chip), `message` y `entry_url`.
  - Restaurante → `dashboard.index`.
  - Verduras → `dashboard.mundos_pos` (handoff SSO al POS). `None` =
    vertical con mundo creado pero sin frontend aún.
- **`user_has_tenant(user)`**: condición de acceso explícita del selector
  (restaurante por `restaurant_id` o vertical directo como owner).

## Handoff Mundos → POS (dueño salta sin PIN)

Ruta core: `GET /dashboard/mundos/pos/<slug>` (`app/routes/dashboard.py`).

1. Verifica sesión de dueño + que el mundo sea suyo (404 genérico si no,
   para no revelar slugs ajenos) y que esté activo (si está pausado,
   redirige al selector con flash).
2. Emite el token vía `verduras.services.pos_auth.mint_pos_sso_token`:
   un solo uso, expira en 5 min (`SSO_TTL_MINUTES`), solo uno vivo a la
   vez (mintear reemplaza el anterior), nunca se loguea.
3. Redirige a `{VERDURAS_BASE_URL}/pos/sso/<slug>/<token>`; el módulo lo
   consume (comparación en tiempo constante), lo limpia y abre la sesión
   del POS. Mensajes genéricos: no revela si falló slug, token o
   expiración; el token expirado también se limpia.

Tests: `tests/test_mundos_pos_sso.py`, `verduras/tests/test_pos_sso.py`.

## Registro multi-vertical (un solo funnel)

Función: `register_verduras_business()` en
`app/services/business_registration.py`.

- **El trial es del SaaS completo, no del mundo.** `TrialHistory`
  (email/teléfono) se comparte entre verticales — nadie lo cobra dos veces
  cambiando de vertical. Si el dueño ya tiene ciclo (trial o plan pago),
  `start_user_trial()` es no-op: un solo reloj para todos sus mundos.
- **Cupo de mundos por plan** (`can_activate_vertical()`): el dueño de
  restaurante SÍ puede agregar verdulería; el guard es el cupo, no el tipo
  de cuenta.
- Planes válidos: `trial` (60 días, `TRIAL_DAYS`), `emprendedor`,
  `crecimiento`, `elite`. Con plan pago el Business nace inactivo hasta
  registrar el pago (mismo patrón que restaurantes).
- El WhatsApp se pide **una sola vez** aquí y viaja al módulo por
  `businesses.whatsapp_phone` (el setup del POS lo pre-llena, editable).
- Emite `pos_setup_token` (un solo uso) para el onboarding del POS en el
  módulo (PIN + WhatsApp); el enlace muere al usarse.
- Slug único generado desde el nombre (`generate_and_ensure_slug`).

Tests: `tests/test_business_registration.py`,
`tests/test_register_vertical.py`, `tests/test_world_quota.py`.

## Billing y ciclo de vida multi-mundo

- El billing SaaS vive en el **User** de core (`app/services/user_billing.py`):
  cancelar es de la CUENTA — deja de renovar en TODOS los mundos del dueño.
- Cada Business directo tiene su propio `plan_type`,
  `subscription_expires_at`, `subscription_state` y `dormant_at`
  (los verticales directos no tienen fila en `restaurants`; si el ciclo no
  viviera en `businesses`, quedarían fuera de trial → activo → gracia → dormant).
- El módulo **pregunta, no decide**: `ensure_business_active()` consulta
  `get_business_subscription_status()` de core y levanta
  `BusinessInactiveError` si no puede operar hoy.
- Datos siempre preservados: gracia/vencido/dormant bloquean operar, nunca
  borran (misma política SaaS de core).

Tests: `tests/test_user_billing.py`, `tests/test_business_subscription.py`,
`tests/test_worlds_hub.py`, `tests/test_account_deletion.py`.
