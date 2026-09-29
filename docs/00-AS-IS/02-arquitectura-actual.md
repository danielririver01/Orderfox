# 02 — Arquitectura actual (AS-IS)

**Commit de referencia:** `cd96aa763c086dea93e4aede46191b9add9067fa` · **Fecha:** 2026-09-29

> Describe **cómo está construido el sistema hoy**, no cómo debería estarlo.

---

## 1. Vista de componentes

```
                     ┌──────────────────────────────────────────┐
   Cliente final     │  Astro  (astro/)   puerto 4321 · Vercel  │
   (móvil, QR)  ───► │  · Landing pública  /                    │
                     │  · Menú digital     /[slug]/             │
                     └───────────────┬──────────────────────────┘
                                     │  fetch  /menu/api/*
                                     │  (proxy en dev · CORS en prod)
                                     ▼
 Dueño / empleado    ┌──────────────────────────────────────────┐
   (navegador)  ───► │  Flask  (app/)     puerto 5000           │
                     │  ┌────────────────────────────────────┐  │
                     │  │ routes/     25 blueprints · 200 URL │  │
                     │  ├────────────────────────────────────┤  │
                     │  │ services/   lógica de negocio       │  │
                     │  ├────────────────────────────────────┤  │
                     │  │ models/     27 tablas SQLAlchemy    │  │
                     │  └────────────────────────────────────┘  │
                     │  APScheduler: 7 tareas programadas       │
                     └───────┬──────────────────────┬───────────┘
                             │                      │
                             ▼                      ▼
                     ┌───────────────┐   ┌──────────────────────────┐
                     │ Base de datos │   │ Servicios externos       │
                     │ (motor único  │   │ Clerk · Mercado Pago     │
                     │  compartido)  │   │ Cloudinary · DeepSeek    │
                     └───────┬───────┘   │ Tavily · ntfy · Gmail    │
                             │           │ Unsplash · Gemini        │
                             ▼           │ Sentry/Better Stack      │
                     ┌───────────────┐   └──────────────────────────┘
                     │ Scanner IA    │
                     │ (repo EXTERNO)│  ← comparte la MISMA base de datos
                     │ Next.js+Prisma│
                     └───────────────┘
```

`[CÓDIGO]` El Scanner IA es un servicio Next.js/Prisma **fuera de este
repositorio** (`docker-compose.yml:37` lo construye desde `../Receipt-Scanner-AI`)
que recibe la misma `DATABASE_URL` (`docker-compose.yml:44`). La evidencia de que
efectivamente escribe en la misma base son las tablas `velzia_category`,
`velzia_expense` y `velzia_budget` (ver
[03-modelo-de-datos.md](03-modelo-de-datos.md#5-tablas-que-no-pertenecen-a-esta-aplicación)).

---

## 2. Estilo arquitectónico

`[CÓDIGO]` **Monolito Flask en capas, con un frontend público desacoplado.**

| Capa | Ubicación | Regla observada |
|---|---|---|
| Presentación (privada) | `app/template/` + `app/static/js/` | Jinja2 server-side + JS vanilla |
| Presentación (pública) | `astro/src/` | Astro SSR, consume la API de Flask |
| Rutas | `app/routes/` | Reciben la petición, llaman a un servicio, devuelven respuesta |
| Servicios | `app/services/` | Lógica de negocio |
| Modelos | `app/models/` | SQLAlchemy |
| Transversal | `app/utils/` | Decoradores, tiempo, límites, firmas |

`[CÓDIGO]` La regla *"las rutas no tienen lógica de negocio"* (`AGENTS.md`)
**no se cumple de forma uniforme**: hay 11 archivos de más de 500 líneas, entre
ellos `app/routes/employees.py` (640), `app/routes/dashboard.py` (626) y
`app/routes/auth.py` (561), que contienen lógica sustancial dentro de las rutas.

---

## 3. Application factory — orden de inicialización

`[CÓDIGO]` `app/__init__.py:27-465`, en este orden exacto:

1. `Flask(template_folder='template', static_folder='static')` — **`template`, no `templates`**
2. `app.config.from_object('settings.Config')`
3. `db`, `migrate`, `limiter`, `JWTManager`
4. Logging (`LOG_LEVEL`)
5. Sentry **solo si `SENTRY_DSN` está definido**, con `before_send` que redacta cabeceras y campos sensibles (`app/__init__.py:52-101`)
6. `WTF_CSRF_CHECK_DEFAULT = False` + CSRF manual (§5)
7. CORS con orígenes fijos (§6)
8. `ProxyFix(x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)`
9. WhiteNoise **solo si `not app.debug`**
10. **`scheduler.init_app(app)` + `scheduler.start()` + `init_tasks(scheduler)`** ← ver §7
11. Registro de los 25 blueprints
12. `before_request` `block_grace_period_crud` (§4)
13. `after_request` con cabeceras de caché y seguridad
14. Filtros de plantilla (`currency`, `local_time`) y `context_processor` global
15. Comando CLI `cleanup-accounts`
16. Manejadores 403 / 404 / 429 / 500

---

## 4. Autenticación y autorización

### 4.1 Tres mecanismos coexistentes

`[CÓDIGO]` `app/utils/auth.py:12-46` — el decorador `require_auth` acepta:

| Mecanismo | Señal | Sujeto |
|---|---|---|
| **JWT** | Cabecera `Authorization: Bearer …` | API móvil / Scanner IA |
| **Sesión de dueño** | `session['user_id']` | Dueño del restaurante |
| **Sesión de empleado** | `session['employee_id']` | Cajero o mesero (portal con PIN) |

`[CÓDIGO]` Además, **Clerk** es el proveedor de identidad externo para los
dueños: `POST /api/sync-clerk` (`app/routes/auth.py:30`) sincroniza el usuario de
Clerk con la tabla `users` (`clerk_id`). `users.password` sigue existiendo y
usándose (`check_password`, `app/models/core.py:141`).

`[INFERIDO]` Conviven un login propio con contraseña y un login federado con
Clerk. `[PENDIENTE]` ¿Es intencional mantener ambos, o el login propio es un
residuo? — ver [07-preguntas-pendientes.md](07-preguntas-pendientes.md) (D-03).

`[CÓDIGO]` Si `user_id` y `employee_id` coexisten en la misma sesión, **gana el
dueño** (`app/utils/restaurant.py:9-18`, comentario "v2.1.2").

### 4.2 Cadena de decoradores

`[CÓDIGO]` Orden previsto: `@require_auth` → `@require_active` → `@require_feature` / `@require_role`.

| Decorador | Qué verifica | Evidencia |
|---|---|---|
| `require_auth` | Hay identidad (JWT o sesión) | `app/utils/auth.py:12` |
| `require_active` | Restaurante existe, `is_active`, suscripción vigente o en gracia, o con créditos IA | `app/utils/auth.py:74` |
| `require_feature(f)` | El plan incluye la característica `f` | `app/utils/auth.py:131` |
| `require_role(*r)` | El usuario tiene uno de los roles y está activo | `app/utils/auth.py:223` |

`[CÓDIGO]` `require_active` **exime a cualquier endpoint cuyo nombre contenga
`subscription`** (`app/utils/auth.py:81`) para no bloquear la pantalla de
renovación. Es una coincidencia por cadena de texto, no una lista explícita.

> ⚠️ `require_active` contiene un `NameError` reproducible en la transición
> automática `cancellation_pending → dormant`. Ver
> [R-01](06-riesgos-y-deuda-tecnica.md#r-01).

### 4.3 Roles

`[CÓDIGO]` Tres roles en `users.role`: `owner` | `cashier` | `waiter`
(`app/models/core.py:122`). `EMPLOYEE_ROLES = ('cashier', 'waiter')`
(`app/services/employee_service.py:32`).

| Rol | Entrada | Credencial |
|---|---|---|
| `owner` | `/login` + Clerk | Contraseña / Clerk |
| `cashier` | `/empleado/<slug>` | **PIN** (`users.pin_hash`) |
| `waiter` | `/empleado/<slug>` | **PIN** |

`[CÓDIGO]` Protección contra fuerza bruta del PIN: `MAX_PIN_ATTEMPTS = 5`,
`LOCKOUT_MINUTES = 30` (`app/services/employee_service.py:44-45`), con contadores
`users.failed_pin_attempts` y `users.locked_until`.

### 4.4 Bloqueo global de escritura por suscripción vencida

`[CÓDIGO]` `app/__init__.py:262-273` — un `before_request` global intercepta
`POST/PUT/DELETE/PATCH` y los bloquea si `can_perform_crud(restaurant)` es falso.

**Excepciones (no se bloquean):** endpoints cuyo nombre contiene `auth.`,
`payment`, `public.` o `api_auth.`, y cualquier ruta bajo `/api/` o
`/insights/api/`.

`[INFERIDO]` Esto significa que **la API JSON no aplica el bloqueo por
suscripción vencida en este punto**; depende exclusivamente de que cada endpoint
lleve `@require_active`. `[PENDIENTE]` confirmar si es deliberado.

---

## 5. CSRF — implementación manual

`[CÓDIGO]` Flask-WTF 1.2.2 no respeta las exenciones por endpoint, así que el
proyecto desactiva la comprobación automática y la reimplementa:

- `settings.py:104` y `app/__init__.py:105`: `WTF_CSRF_CHECK_DEFAULT = False`
- `app/__init__.py:114`: prefijos exentos
  `('/api/', '/insights/api/', '/reclamar/', '/menu/api/')` **más** la ruta exacta `/webhook`
- `app/__init__.py:121-143`: `before_request` que llama a `csrf.protect()` para todo lo demás
- Si el token caducó, responde JSON 400 o redirige con un mensaje, en lugar de un 400 crudo

`[CÓDIGO]` Además hay dos exenciones por blueprint completo:
`csrf.exempt(api_email_bp)` y `csrf.exempt(rewards_bp)` (`app/__init__.py:260-261`),
un tercer mecanismo distinto para lo mismo.

---

## 6. CORS

`[CÓDIGO]` `app/__init__.py:173-196`. Orígenes **escritos en el código**:

| Patrón | Orígenes |
|---|---|
| `/api/*` | `localhost:3000`, `localhost:4321`, `localhost:5173`, `https://menu.velzia.shop`, `https://velzia.shop`, y `SCANNER_IA_URL` |
| `/menu/api/*` | `localhost:4321`, `localhost:3000`, `https://menu.velzia.shop`, `https://velzia.shop`, y `SCANNER_IA_URL` |

Ambos con `supports_credentials: True`.

`[CÓDIGO]` Los dominios de producción están **fijos en el código fuente**, no en
variables de entorno: añadir un dominio exige cambiar código y desplegar.

---

## 7. Tareas programadas (APScheduler)

`[EJECUTADO]` Al arrancar la aplicación, el log muestra las **7 tareas**:

| Job | Disparador | Qué hace | Evidencia |
|---|---|---|---|
| `manage_subscription_lifecycle` | cron 03:00 | Marca cuentas como `dormant` **sin borrar datos** | `app/tasks.py:266-273` |
| `expire_pending_orders` | cron cada hora :00 | `pending` → `expired` si venció `expires_at` | `app/tasks.py:276-282` |
| `scan_business_events` | cron cada hora :30 | Genera eventos de negocio para el Copilot | `app/tasks.py:285-291` |
| `expire_coupons` | cron cada hora :45 | Cupones `pending`/`reserved` vencidos → `expired` | `app/tasks.py:294-300` |
| `send_subscription_reminders` | cron 13:00 UTC (08:00 Colombia) | Correos de aviso de vencimiento | `app/tasks.py:304-311` |
| `compute_platform_benchmarks` | cron 04:15 | Medianas anónimas por cohorte | `app/tasks.py:314-321` |
| `send_reservation_reminders` | interval 30 min | Recordatorio ntfy de reservas confirmadas | `app/tasks.py:324-330` |

### Riesgo de ejecución múltiple

`[CÓDIGO]` `scheduler.start()` se invoca **dentro de `create_app()`**
(`app/__init__.py:208`), y `run.py:8` ejecuta `app = create_app()` a nivel de
módulo.

`[CÓDIGO]` `docker-compose.yml:19` arranca `gunicorn --workers 3 run:app` **y
además** `docker-compose.yml:22-34` levanta un contenedor
`orderfox-scheduler` que ejecuta `run_scheduler.py`, el cual también llama a
`create_app()`.

`[INFERIDO]` Con esa configuración **cada worker de gunicorn crea su propio
scheduler**, de modo que las 7 tareas quedarían programadas 3 veces (workers) + 1
(contenedor dedicado) = **4 veces**. No hay bloqueo distribuido ni `jobstore`
compartido: `app/extensions.py:7` usa `APScheduler()` con el almacén en memoria
por defecto.

`[PENDIENTE]` Confirmar el comportamiento observado en producción —
especialmente si los correos de recordatorio llegan duplicados. Ver
[R-04](06-riesgos-y-deuda-tecnica.md#r-04) y [07-preguntas-pendientes.md](07-preguntas-pendientes.md) (D-04).

---

## 8. Limitación de peticiones (rate limiting)

Hay **dos sistemas independientes**:

### 8.1 Flask-Limiter (global)

`[CÓDIGO]` `app/extensions.py:22-27`:
- Clave: IP remota
- Límite por defecto: `RATELIMIT_DEFAULT` o `"200 per day;50 per hour"`
- Almacenamiento: `RATELIMIT_STORAGE_URL` o **`memory://`**
- Exención: cabecera `x-api-key` igual a `SERVICE_API_KEY`
- `[CÓDIGO]` `app/__init__.py:22-24`: **cualquier usuario con sesión iniciada queda exento por completo** (`@limiter.request_filter`)

`[CÓDIGO]` Con `memory://`, el contador **es por proceso y se pierde al
reiniciar**; con 3 workers de gunicorn el límite efectivo es 3 veces el
configurado.

### 8.2 Rate limiter de negocio (`app/utils/rate_limiter.py`)

Basado en **consultas a la base de datos**, no en memoria:

| Clase | Regla |
|---|---|
| `OrderRateLimiter` | Máx. **3 pedidos/minuto** por IP+restaurante; ban de **10 minutos** |
| `ReservationRateLimiter` | Máx. **3 reservas/minuto** por IP+restaurante; ban de **10 minutos** |

`[CÓDIGO]` `OrderRateLimiter.get_recent_orders_count` filtra por
`status.in_(['pending', 'completed'])` (`app/utils/rate_limiter.py:25`).
`[CONTRADICCIÓN]` El estado `'completed'` **no existe** en la máquina de estados
de pedidos, que usa `pending | confirmed | delivered | cancelled | expired`
(`app/services/order_service.py:208-214`). El filtro por `'completed'` no puede
coincidir nunca. Ver [R-06](06-riesgos-y-deuda-tecnica.md#r-06).

---

## 9. Cabeceras de seguridad

`[EJECUTADO]` Respuesta real de `GET /login`:

| Cabecera | Valor observado |
|---|---|
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `X-XSS-Protection` | `0` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |
| `Content-Security-Policy` | presente (ver abajo) |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |
| `Cache-Control` | `no-cache, no-store, must-revalidate…` (excepto `/static`) |
| `Set-Cookie` | `HttpOnly; Path=/; SameSite=Lax` |

`[CÓDIGO]` La CSP (`app/__init__.py:293-308`) incluye **`'unsafe-inline'` y
`'unsafe-eval'` en `script-src`**, lo que reduce mucho su capacidad de mitigar
XSS. También lista dominios de Clerk **fijos en el código**
(`oriented-tortoise-50.clerk.accounts.dev`, `clerk.velzia.shop`).

`[CÓDIGO]` `settings.py:109`: `SESSION_COOKIE_SECURE = False` con el comentario
`# True en producción con HTTPS`. **No hay ningún mecanismo que lo cambie según
el entorno**: la cookie de sesión se envía sin la marca `Secure` también en
producción, salvo que se modifique el código.

`[EJECUTADO]` La cabecera `Server` se elimina en `after_request`
(`app/__init__.py:315`) pero el servidor de desarrollo de Werkzeug la vuelve a
añadir después; por eso `run.py` la parchea. Arrancando sin `run.py` se observó
`Server: Werkzeug/3.1.7 Python/3.11.2`.

---

## 10. Zona horaria

`[CÓDIGO]` Convención doble y **deliberada**:

| Dato | Almacenamiento | Evidencia |
|---|---|---|
| Todo en general | **UTC**, vía `AwareDateTime` | `app/models/core.py:10-36` |
| `reservations.reservation_date` / `reservation_time` | **Hora local de Colombia (naive)** | `app/models/reservations.py:4-12` |

`[CÓDIGO]` Motivo documentado en el propio código: convertir una reserva de las
8 p. m. a UTC la movería de día (01:00 UTC del día siguiente) y rompería el
calendario diario.

`[CÓDIGO]` `app/utils/timezone.py:10` fija `COLOMBIA_TZ = UTC-5` sin horario de
verano, y `today_start_utc()` calcula "hoy" desde la medianoche de Bogotá.

---

## 11. Frontend Astro

`[CÓDIGO]` `astro/astro.config.mjs`:

| Ajuste | Valor |
|---|---|
| `output` | `'server'` (SSR) |
| `adapter` | `@astrojs/vercel` |
| Puerto de desarrollo | `4321` |
| `vite.server.allowedHosts` | `true` — **acepta cualquier host** |
| Proxy de desarrollo | `/menu/api` → `http://localhost:5000` |

**Páginas:** `src/pages/index.astro` (landing) y `src/pages/[slug]/index.astro` (menú).
**Componentes:** 14 de landing, 8 de menú, 2 de carrito, 2 de checkout, 3 de UI.
**Librerías:** `api.ts`, `brand.ts`, `cart.ts`, `types.ts`, `urls.ts`.

`[CÓDIGO]` El puente Flask→Astro es una redirección: `GET /menu/<slug>` responde
`redirect(f"{ASTRO_BASE_URL}/{slug}/")` (`app/routes/public.py:26-44`).

`[EJECUTADO]` `GET /` responde **301** a `https://menu.velzia.shop/`.

`[CONTRADICCIÓN]` El destino por defecto de `/` difiere entre fuentes:
`settings.py:52` usa `'https://menu.velzia.shop/'` mientras `.env.example:73`
propone `LANDING_URL=https://velzia.shop/`.

---

## 12. Observabilidad

| Aspecto | Estado |
|---|---|
| Errores | `[CÓDIGO]` Sentry / Better Stack, **solo si `SENTRY_DSN` está definido** (`app/__init__.py:43`) |
| Redacción de datos sensibles | `[CÓDIGO]` `before_send` oculta cabeceras y campos como `password`, `token`, `api_key` (`app/__init__.py:52-92`) |
| Contexto | `[CÓDIGO]` etiquetas `restaurant_id`, `app_version`, `module` e identidad de usuario |
| Trazas de rendimiento | `[CÓDIGO]` `traces_sample_rate=0` — **desactivadas** |
| Logs | `[CÓDIGO]` `logging.basicConfig` con `LOG_LEVEL`. `LOG_FORMAT=json` se lee en `settings.py:124` pero **no se usa en ningún sitio**: el formato real no es JSON |
| Health check | `[CÓDIGO]` **No existe** ningún endpoint `/health` o `/healthz` en las 200 rutas |
| Telemetría de coste de IA | `[CÓDIGO]` tabla `ai_llm_calls` con tokens estimados y duración |

---

## 13. Decisiones de arquitectura observables

Decisiones deducidas del código. **Ninguna está confirmada por el propietario.**

| # | Decisión observada | Evidencia | Estado |
|---|---|---|---|
| A-01 | Monolito Flask en capas en lugar de microservicios | Estructura de `app/` | `[CÓDIGO]` |
| A-02 | Multi-inquilino por columna `restaurant_id` | 21/27 tablas | `[CÓDIGO]` |
| A-03 | Menú público desacoplado en Astro/Vercel, unido por redirección | `app/routes/public.py:26-44` | `[CÓDIGO]` |
| A-04 | Identidad delegada en Clerk, con login propio conservado | `app/routes/auth.py:30`, `app/models/core.py:141` | `[CÓDIGO]` + `[PENDIENTE]` |
| A-05 | Precios en **enteros** (pesos colombianos, sin decimales) | `app/models/core.py:173` (`price = db.Column(db.Integer)`) | `[CÓDIGO]` |
| A-06 | Todo en UTC salvo las reservas | `app/models/reservations.py:4-12` | `[CÓDIGO]` |
| A-07 | Las cuentas nunca se borran: pasan a `dormant` | `app/tasks.py:30-38` | `[CÓDIGO]` |
| A-08 | Scheduler integrado en el proceso web, no externo | `app/__init__.py:208` | `[CÓDIGO]` + riesgo `[R-04]` |
| A-09 | Base de datos compartida con el Scanner IA externo | `docker-compose.yml:44`, tablas `velzia_*` | `[CÓDIGO]` |
| A-10 | CSRF manual por incompatibilidad de Flask-WTF 1.2.2 | `app/__init__.py:104-143` | `[CÓDIGO]` |

`[PENDIENTE]` Estas diez decisiones deberían pasar a `docs/00-AS-IS/adr/` como
ADR formales una vez el propietario confirme cuáles fueron deliberadas y cuáles
son accidentales. Ver [adr/README.md](adr/README.md).
