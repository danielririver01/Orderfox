# Changelog

Todas las fechas en UTC.

---

## [Sin release] - rama `feature/verduras` — puente multi-vertical

> Trabajo en rama `feature/verduras`, no mergeado a `main`. El tag
> `v1.6.0` sigue siendo la última versión estable del monolito. Requiere
> `flask db upgrade` al aplicar.

### Añadido

#### Puente multi-vertical `Business` ↔ `Restaurant` (estrategia expand-contract)
- Nuevo modelo `Business` en `app/models/business.py`: raíz del tenant
  multi-vertical con columna `vertical` ('restaurant' | 'delivery' | ...).
- Backfill alineado por ID: migración `a1f6e3d2b4c5_add_businesses_table`
  crea `businesses` e inserta un Business por cada Restaurant existente
  **con el mismo ID**, así las FKs `restaurant_id` vigentes siguen válidas
  sin migración masiva.
- Listeners ORM (mismo flush, sin sesión anidada): `after_insert` crea el
  espejo, `before_update` sincroniza name/slug/is_active, `before_delete`
  borra el espejo (sin FK → cascada manual).
- `Business.create_direct(vertical, name, slug)`: verticales sin Restaurant
  espejo (delivery, etc.) con banda de IDs reservada `>= 1.000.000` para no
  chocar con los espejos (los espejos usan el autoincrement de
  `restaurants`). Rechaza `vertical='restaurant'`.
- Alias `Tenant = Business` en `app/models/__init__.py` + `__all__` explícito.
  Código NUEVO habla de `Business`/`Tenant` y `business_id`; código viejo
  sigue intacto.
- Tests `tests/test_business_bridge.py` (11 casos): invariante 1:1, sync,
  borrado, banda de IDs, unicidad de slug y backfill validado sobre SQLite.
- Relación `Business.restaurant_profile` (viewonly, por ID compartido).

#### Módulo vertical `verduras/` — primera app de submódulo (monorepo, Opción A)
- Nueva app Flask separada en `verduras/`: propia factory (`verduras.app_factory.create_app`),
  settings propios (leen el `.env` de la raíz), blueprints y suite de tests
  independiente (sqlite in-memory, corre con `pytest verduras/tests`, no se
  coleciona en la suite de core).
- Contrato con core: comparte la DB y re-exporta `app.models.db` como su `db`
  (nunca instancia otra); toda FK nueva del módulo apunta a `business_id`,
  nunca a `restaurants`. El acceso a `Business` pasa por el punto único
  `verduras/services/context.py` (`require_business` valida existencia,
  vertical y estado activo).
- Endpoints iniciales: `GET /`, `GET /health`, `GET /health/core-bridge`,
  `GET /api/businesses`, `GET /api/businesses/<id>` (404 si no existe, 409 si
  es de otro vertical). Entrypoint: `python verduras/run.py` (puerto 5100).
- `verduras/extensions.py` inicializa Migrate con directorio de migraciones
  PROPIO del módulo (aún inexistente): un `flask db` accidental desde verduras
  falla ruidoso en vez de ejecutar las migraciones de core.
- Tests `verduras/tests/test_skeleton.py` (14 casos): endpoints, filtro por
  vertical, servicio de contexto y puente activo en el proceso del módulo.
- `verduras/README.md`: contrato completo core↔módulo y guía de extracción
  futura (git subtree split).

#### Módulo verduras — Semana 1: catálogo + precios por peso (v0.2.0)
- Models `verduras/models.py`: `verduras_categories`, `verduras_products`
  (precio por kg/lb/unidad, foto) y `verduras_price_history` (curva histórica
  de precios). Todas con FK a `businesses.id` — primeras tablas nacidas bajo
  el contrato del puente; prefijo `verduras_` obligatorio.
- Servicio `verduras/services/catalog.py`: precios Decimal(12,2) con
  ROUND_HALF_UP y > 0, unidades normalizadas (kg|lb|unidad), unicidad
  por business, anti-IDOR (pedir recurso de otro business = 404), y
  `update_price()` que appendea al historial (rechaza precio idéntico;
  baseline automático al crear producto).
- API `verduras/routes/catalog.py` bajo `/api/verduras/businesses/<bid>/...`:
  categorías y productos (GET público, POST con header `x-api-key` contra
  `SERVICE_API_KEY`, comparación en tiempo constante vía `verduras/auth.py`),
  y `POST .../products/<pid>/price` para el cambio diario con historial.
- Migraciones PROPIAS del módulo: `verduras/migrations/` con
  `version_table='alembic_version_verduras'` y filtro include_object a solo
  tablas `verduras_*`; revisión inicial `3fdc7c9baadf` (3 tablas + índices,
  downgrade completo). El `env.py` de core EXCLUYE `verduras_*` de su
  autogenerate: las dos cadenas conviven en la misma DB sin tocarse.
- Tests `verduras/tests/test_catalog.py` (23 casos) + smoke previos: 37 en
  total, en verde. Autogenerate + upgrade + roundtrip verificados sobre
  sqlite desechable. Suite completa de core: 633 passed.

#### Módulo verduras — Semana 2: ventas por peso + pedidos WhatsApp (v0.3.0)
- Models `verduras/models_sales.py`: `verduras_business_settings` (WhatsApp
  del negocio, abierto/cerrado, domicilio habilitado), `verduras_sales`
  (walk-in POS o delivery, con `idempotency_key` + constraint único
  business+key igual que `orders` en core), `verduras_sale_items` (líneas
  con SNAPSHOT de nombre/unidad/precio — integridad contable) y
  `verduras_sale_counters` (numeración atómica diaria). FKs solo a
  `businesses.id` / tablas `verduras_*`.
- Servicio `verduras/services/sales.py`: cantidades Decimal con precisión de
  gramo (0.001 kg; enteras para 'unidad'), precio SIEMPRE del catálogo
  (nunca del cliente), idempotencia con recuperación por IntegrityError
  (patrón `create_order_idempotent` de core), numeración `V-YYYYMMDD-NNN`
  con row lock y fecha UTC (regla timezone del repo: `date.today()`
  desalinearía los contadores en Colombia a las 7pm), rate limiter 3/min por
  IP+business con ban de 10 min, honeypot + time-to-submit ≥ 3s en checkout
  público, transiciones pending→completed|cancelled idempotentes, anti-IDOR
  por business y builder del enlace `wa.me` con resumen del pedido (teléfono
  del negocio en settings; `Business` no lo tiene a propósito).
- API `verduras/routes/sales.py`: settings (GET/POST), creación de venta
  (delivery público con guards / walk-in POS con `x-api-key`), listado con
  filtros `status`/`date_from`/`date_to`, detalle, complete y cancel.
  Respuestas incluyen `whatsapp_link` prearmado; el replay de idempotencia
  se marca con `"replay": true`.
- Migración delta `b8d2e4f6a9c1_add_verduras_sales_tables` (4 tablas +
  índices, downgrade completo), verificada en sqlite desechable con ciclo
  upgrade → downgrade → upgrade: 7/7 tablas `verduras_*` y core intacto.
- Tests `verduras/tests/test_sales.py` (50 casos): matemática por peso,
  snapshot contable, idempotencia (replay + carrera concurrente simulada),
  numeración diaria por business, gates de delivery, transiciones, rate
  limiter, guards públicos, enlace wa.me y API completa (auth del POS,
  checkout público, scoping,  espejo de restaurante → 409). Módulo: 87/87
  en verde. Suite completa de core: 633 passed (sin regresiones).
  Ruff: all checks passed.

#### Módulo verduras — Semana 3: inventario por lotes + merma (v0.4.0)
- Models `verduras/models_inventory.py`: `verduras_lots` (compras por
  lote: "50kg de tomate a $90.000" — el costo/kg se DERIVA de
  total/cantidad, jamás se almacena) y `verduras_merma` (kg dañados con
  la PÉRDIDA en COP congelada al registrar, snapshot contable). FKs solo
  a `businesses.id` / tablas `verduras_*`.
- Servicio `verduras/services/inventory.py`: stock EN TIEMPO REAL
  DERIVADO como compras − ventas − merma (no se almacena: auditable,
  sin bugs de sincronización; ventas canceladas no descuentan), costo
  promedio PONDERADO por cantidad (30kg a $1.500 + 20kg a $2.500 →
  $1.900, no $2.000), valor del stock en COP, merma con costo promedio
  de lotes (o costo manual si aún no hay lotes; sin base de costo se
  rechaza para no inventar pérdidas en cero) y reporte semanal/mensual
  con pérdida por producto, % de aporte y % sobre las compras del
  período (el indicador que el verdulero quiere bajar).
- API `verduras/routes/inventory.py` bajo `/api/verduras/businesses/<bid>/
  inventory/...`: stock (total y por producto), lotes (POST/GET), merma
  (POST/GET) y reporte. TODO requiere `x-api-key`: costos, stock y
  pérdidas son dato privado del negocio.
- Migración delta `e7a9c1d3f5b2_add_verduras_inventory_tables` (2 tablas
  + índices, downgrade completo), verificada en sqlite desechable con
  upgrade → roundtrip → downgrade → re-upgrade: 9/9 tablas `verduras_*`,
  core intacto.
- Tests `verduras/tests/test_inventory.py` (31 casos): ciclo completo
  compro→vender→perder integrado con las ventas reales de Semana 2,
  stock negativo visible, snapshot inmune a lotes futuros, reporte con
  límites de período y API auth. Módulo: 118/118 en verde. Ruff: all
  checks passed. Puente de core: 11/11.

#### Módulo verduras — Dashboard POS del tendero (v0.5.0)
- Frontend Jinja2 + sesión (mismo patrón que core): login slug+PIN y
  pantalla de venta de mostrador, con design system PROPIO del vertical
  (claro #FAFAFA, verde #16A34A/#15803D con separación acento/botón por
  contraste WCAG, estados siempre con icono+texto, sidebar propia, bottom
  nav, targets táctiles ≥ 56px, lenguaje de verdulero).
- Auth del POS: PIN 4-6 dígitos hasheado con werkzeug en
  `verduras_business_settings` (tabla propia del módulo; core es dueño de
  `businesses`), configurado por onboarding server-to-server (`POST
  .../pos-pin` con x-api-key) — la SERVICE_API_KEY jamás llega al
  navegador. Lockout 5 intentos → 10 min. Mensajes de login genéricos.
- Venta walk-in por sesión con CSRF (guard manual en la factory que
  respeta WTF_CSRF_ENABLED y exenta /api/*, mismo criterio de core); el
  frontend envía X-CSRFToken. Ticket imprimible (window.print con CSS
  @media print) y formato es-CO ($1.234.567,00).
- Migración delta `f3b8d2c4e6a1` (columnas pos_pin_hash/pos_pin_updated_at
  vía batch mode, verificada en sqlite desechable upgrade→downgrade→
  re-upgrade).
- Tests `verduras/tests/test_pos.py` (21 casos): setup de PIN, login,
  lockout, segregación de claves (la x-api-key NO da sesión), venta por
  sesión, pantalla POS y guard CSRF activado. Fixtures limpian el lockout
  en memoria entre tests (aislamiento). Módulo: 139/139 en verde. Ruff:
  all checks passed.

#### Módulo verduras — Semana 4: báscula digital (v0.6.0)
- Servicio `verduras/services/scale.py`: lectura con degradación grácil —
  la báscula es AYUDA, nunca requisito; ante cualquier problema el POS
  pide ingreso manual y la venta continúa. Errores tipados (`ScaleDisabled`,
  `ScaleUnavailable`, `ScaleRead`) que la ruta traduce a 409 con
  `error_code` legible (nunca 500). Parseadores PURos por protocolo
  (`generic` ASCII con locale es-CO, `toledo` frames de gramos/kg —
  comunes en Colombia), registro `PARSERS` extensible sin tocar transporte
  ni ruta. Todo normalizado a kg con precisión de gramo (contrato con el
  servicio de ventas); cero, fuera de rango (>300 kg) o frame ilegible =
  error, jamás un peso dudoso.
- Transporte serial INYECTABLE (`ScaleTransport` protocol): pyserial se
  importa perezosamente SOLO si la báscula está activada (dependencia
  opcional verificada en PyPI v3.5); el servicio se prueba completo con
  transporte falso, sin hardware. El servicio cierra el puerto que él abre
  y no toca el que le inyectan.
- Config opcional en settings del módulo: `VERDURAS_SCALE_ENABLED/_PORT/
  _BAUDRATE/_PROTOCOL/_TIMEOUT_S` (apagada por defecto).
- Endpoint `GET /pos/<slug>/api/scale/weight` por sesión del tendero (sin
  x-api-key en el navegador). POS: botón "Leer báscula" SOLO en productos
  por peso y con báscula activada; soporta lb (conversión kg→lb en el
  cliente); el ingreso manual queda intacto.
- Tests `verduras/tests/test_scale.py` (33 casos): parsers, unidades,
  redondeo, rangos, errores de transporte, cierre de puertos, endpoint con
  sesión y flag `scale_enabled` en pos-data. Módulo: 172/172 en verde.
  Ruff: all checks passed.

#### Módulo verduras — Semana 5: alertas de rotación (v0.7.0)
- Columna `min_stock` (Numeric 12,3 nullable) en `verduras_products`:
  umbral OPT-IN por producto — sin configuración, cero alertas (el
  verdulero decide qué vigilar). Migración delta `d9c4e2a6b8f1`
  (batch_alter, verificada upgrade→downgrade→re-upgrade con columna
  presente/ausente).
- Servicio `verduras/services/alerts.py`: REUTILIZA el stock derivado de
  inventario (compras − ventas − merma; fuente única de verdad, cero
  recálculo) y la única semántica de "vendido" (excluye canceladas, vía
  nuevo parámetro `since` en `_sum_sales`). Velocidad de venta de los
  últimos 7 días → "a este ritmo te dura ~N días" (estimación, None sin
  datos; solo para severidad `low`). Severidades: `out` (stock ≤ 0) y
  `low` (stock ≤ umbral). Mensajes en lenguaje de verdulero con plural
  de 'unidad' ("2 unidades"). Orden: out primero; entre lows, el que se
  agota antes; sin estimación al final.
- API: `GET .../inventory/alerts` y `POST
  .../inventory/products/<pid>/min-stock` (x-api-key, anti-IDOR heredado;
  `null` limpia el umbral, 0 se rechaza a favor de null).
- POS: mapa product_id→severidad en pos-data; badge "Queda poco"
  (warn) / "Agotado" (danger) en las tarjetas — SIEMPRE icono + texto
  (accesibilidad), informativo, jamás bloquea la venta; el cálculo de
  alertas está blindado para no tumbar el POS.
- Tests `verduras/tests/test_alerts.py` (26 casos): umbrales, velocidad,
  canceladas, ventana de 7 días, merma cuenta, orden, plural, API auth,
  anti-IDOR y mapa del POS. Módulo: 198/198 en verde. Ruff: all checks
  passed.

#### Registro self-service multi-vertical (v0.8.0, core + módulo)
- Core: `businesses` gana `owner_user_id` (FK users, SET NULL), `plan_type`,
  `subscription_expires_at`, `has_used_trial` y `pos_setup_token` —
  suscripción a nivel tenant para verticales sin fila en `restaurants`
  (migración `b2e4c6a8d0f2`, batch_alter, encadenada al head f1a2b3c4d5e6;
  backward-compatible: espejos quedan NULL/default y su suscripción se
  sigue leyendo de `restaurants`).
- Core: `Business.create_direct_vertical()` (dueño + plan + trial de 60
  días con `has_used_trial`), `app/services/business_registration.py`
  (slug con RESERVED_SLUGS, trial ÚNICO por email/teléfono reusando
  TrialHistory — el trial es del SaaS completo, no de un vertical), rutas
  `/register/verduras` (GET/POST, requiere sesión, CSRF del guard manual)
  y `/register/verduras/ready/<slug>` (muestra el enlace de setup una vez,
  token viaja por sesión), templates standalone con el sistema visual del
  funnel, y anti-bucle en `register()` para dueños de verticales.
- Cross-app: el setup del POS vive en la app del módulo (5100) — core
  enlaza con `VERDURAS_BASE_URL` (patrón `ASTRO_BASE_URL`). El token viaja
  por la DB compartida (`businesses.pos_setup_token`), canal del monorepo:
  cero HTTP nuevo.
- Módulo: `get_setup_target()`/`consume_setup_token()` en pos_auth
  (comparación en tiempo constante, token de UN SOLO USO, WhatsApp en
  `verduras_business_settings` vía update_settings — contrato respetado);
  rutas `/pos/setup/<slug>/<token>` GET/POST (el POST pasa por el guard
  CSRF de la factory) + template `pos_setup.html` con el design system
  del vertical.
- Tests: `tests/test_business_registration.py` (17: trial único por email
  Y teléfono, plan pago inactivo, slugs reservados/duplicados, teléfono,
  dueño con restaurante, flujo web completo con patrón CSRF del proyecto,
  espejos sin owner, flujo restaurante intacto + anti-bucle) y
  `verduras/tests/test_pos_setup_token.py` (14: token válido/inválido/usado,
  PIN débil no consume, login posterior, rutas end-to-end). Suites: core
  708 passed · módulo 212 passed.

#### Ciclo de suscripción para verticales (v0.9.0, core + módulo)
- Core: `get_business_subscription_status(business)` en
  `app/utils/subscription.py` — la MISMA máquina de estados que restaurantes
  (activo → expiring_soon → grace_period → expired → dormant), leyendo de
  `businesses`. Los businesses legacy (piloto/onboarding asistido, sin dueño
  ni fecha) quedan activos SIEMPRE: jamás se bloquean ventas por un campo
  que nunca se les asignó (backward-compatible).
- Core: scheduler de lifecycle extendido (`_lifecycle_businesses` en
  `app/tasks.py`): vencidos + grace y cancelaciones expiradas → dormant con
  datos preservados. Los espejos de restaurantes (owner NULL) NO se tocan —
  su ciclo ya corre sobre `restaurants`; correr ambos sería doble
  contabilidad.
- Core: pagos de businesses con MercadoPago en el MISMO funnel: preferencia
  con `external_reference = biz:<business_id>:<plan>`
  (`build_biz_mp_preference_data`), activación idempotente
  (`activate_business_from_payment`: activa, sube plan, extiende fecha,
  limpia dormant_at) reutilizada por callback y webhook (`process_mp_webhook_payment`
  entiende el prefijo `biz:`). Idempotencia callback↔webhook con la MISMA
  convención de restaurantes: transacción `topup_plan` con `mp_payment_id`
  (constraint UNIQUE). Solo `approved` activa (pendiente/fallido no toca el
  Business). Registro con plan pago deja `pending_business_id` y redirige a
  `/payment`; `verduras_ready` recupera el token de setup desde la fila del
  Business para el aterrizaje post-pago.
- Módulo: el POS respeta el ciclo — `pos_view` consulta el status (vía
  `context.get_subscription_status`, delegación 100% a core) y muestra
  `pos_renewal.html` (mensaje en lenguaje de verdulero + enlace de
  renovación a core vía nuevo `CORE_BASE_URL`) cuando `can_crud` es False;
  `pos_sell` tiene el segundo candado (sesión viva + suscripción vencida →
  409 `suscripcion_inactiva`, nunca 500).
- Migraciones: `c3d5e7f9a1b2` (flags de cajón en restaurants, otra sesión)
  y `d4e6f8a0b2c3` (`subscription_state` + `dormant_at` en businesses) —
  esta última cierra el hueco real detectado en Postgres: sin la columna,
  TODO insert en `businesses` (incluidos espejos de restaurantes) fallaba
  con UndefinedColumn. Cadena lineal validada bidireccionalmente (probe
  upgrade→downgrade→upgrade) con un solo head.
- Tests: `tests/test_business_subscription.py` (18: estados, bandas,
  legacy sin bloqueo, scheduler, activación idempotente, webhook `biz:`,
  callback end-to-end) y `verduras/tests/test_pos_renewal.py` (8: gate del
  POS, pantalla de renovación, venta bloqueada vencida, legacy sin bloqueo,
  delegación a core). Suites: core 733 passed · módulo 220 passed.

---

## [1.6.0] - 2026-09-20 (tag git `v1.6.0` — versión estable)

> Versión estable etiquetada. Incluye
> trazabilidad de pedidos, ciclo de vida de suscripcion sin borrado (`dormant`),
> diferenciacion de los dos Copilots y hardening de seguridad de IA.

### Anadido

#### 1. Trazabilidad de pedidos (`OrderEvent`)
- Modelo `OrderEvent` en `app/models/orders.py` para auditar cada accion de un pedido.
- Helpers en `app/services/order_service.py`: `log_event()`, `resolve_actor()`,
  `serialize_event()` + mapas de etiquetas (`ROLE_LABELS`, `STATUS_LABELS`,
  `PAYMENT_METHOD_LABELS`, `ORDER_EVENT_TYPES`).
- Instrumentacion en `app/routes/orders.py` y `app/routes/api_orders.py`
  (creacion, pago, cambio de estado, cancelacion, restauracion) y
  `app/routes/public.py` / `app/services/cash_register_service.py` (flujo de caja).
- Timeline de eventos en `app/template/dashboard/order_detail.html` y
  `app/template/dashboard/cash_register_print.html` (ticket: solo rol, sin nombres de empleados).
- Test `tests/test_order_traceability.py` (nuevo).
- Migracion `migrations/versions/7c5dc42affdd_add_order_events_table.py` (nueva, sin track).

#### 2. Ciclo de vida de suscripcion sin borrado destructivo (`dormant`)
- `app/models/core.py`: campos `subscription_state` (`active`/`dormant`, default `active`)
  y `dormant_at`.
- `app/tasks.py`: `delete_inactive_accounts` reemplazado por
  `manage_subscription_lifecycle` (3 AM) -> marca cuentas inactivas >30d o expiradas
  >grace como **`dormant`** (congela CRUD, **preserva todos los datos**; reactivables en 1 clic).
- `app/utils/auth.py` (`require_active`): `dormant` redirige a `dashboard.subscription`
  con banner de reactivacion en vez de "suspendida, contacta soporte" (402 en JSON).
- `app/utils/subscription.py` (`get_subscription_status`): estado `dormant` con mensaje de bienvenida.
- Banner "Hola de nuevo!" en `app/template/dashboard/subscription.html`; texto de datos
  preservados en `app/templates/public/subscription_expired.html`.
- Migracion `migrations/versions/c4c47adbb493_add_subscription_lifecycle_fields.py` (nueva, sin track).

#### 3. Diferenciacion Copilot Estrategico vs Copilot de Caja
- Renombrado "Copilot VZ" -> **"Copilot Estrategico"** con subtitulo "Ventas, rentabilidad y
  tendencias" en `app/template/common/base.html`, `navigation.html`, `insights_sidebar.html`,
  `insights.html` y `insights_chat.html`.
- Burbujas del chat etiquetadas como **"Estratega"** en `app/static/js/insights.js`.
- Color del Estrategico: naranja `#f97316` -> **indigo `#6366f1`**
  (`app/static/CSS/insights.css` + `output.css` regenerado; paleta de graficos en `insights.js`).
- **Copilot de Caja** (naranja) en `cash-register-copilot.js` con subtitulo
  "Cobros, pagos y pendientes"; badge "Asistente" en `cash_register.html`.
- Cross-sell en `app/services/insights/prompt_builder.py` (CASH_SYSTEM_PROMPT redirige
  preguntas de estrategia al Copilot Estrategico).
- Fix de edicion en `insights.js`: al editar un mensaje ahora aparece el indicador de
  escritura y se bloquea el composer.

#### 4. Hardening de seguridad de IA (prompt injection)
- `app/services/insights/message_handler.py`: `sanitize_user_message()` (max 2000 chars +
  filtrado de patrones de inyeccion -> `[FILTRADO]`).
- `app/services/insights/llm_service.py`: `validate_llm_response()` (detector de red flags)
  + log de intento de inyeccion y rechazo de la respuesta.
- `app/services/insights/data_service.py`: ajustes menores de consulta.

#### 5. Documentacion / memoria
- `memories/repo/orderfox-codebase-guide.md` (v2.0) y `memories/repo/authentication-policy.md`
  (v2.0) reescritos contra el estado real del repo.
- `AGENTS.md`, `docs/DOFA.md`, `docs/01-ARCHITECTURE/ARCH-04_Flujo_de_Suscripcion.md` actualizados.

### Cambiado
- `app/services/order_service.py`: +163 lineas (trazabilidad + validacion de cantidad).
- `app/routes/employees.py`, `app/template/employees/waiter.html`, `tests/test_employees.py`:
  gestion de roles de empleados / portal de mesero (cambios previos en el arbol de trabajo).
- Secciones legales en `app/template/dashboard/legal/sections/*.html`
  (`datos`, `faq`, `privacidad`, `suscripciones`, `terminos`, `copilot`): actualizacion de
  textos de retencion/reactivacion de datos.

### Notas tecnicas
- `GRACE_PERIOD_DAYS = 5` en `app/utils/subscription.py` (los textos legales dicen 14; pendiente homogeneizar).
- `settings.APP_VERSION = '1.4.0'` desincronizado del ultimo tag git `v1.4.1`.
- Migraciones nuevas aun sin commit: aplicar con `flask db upgrade` tras commitear.
- Tailwind v4: `output.css` es generado (`npm run build:css`); no editar a mano.

### Como probar / verificar
```bash
# 1. Aplicar migraciones (desde raiz, entorno activo)
$env:FLASK_APP="run.py"
.\.venv\Scripts\flask.exe db upgrade

# 2. Suite de pruebas (resultado esperado: 462 passed)
.\.venv\Scripts\pytest.exe tests -q

# 3. Sintaxis de archivos Python tocados
.\.venv\Scripts\python.exe -m py_compile app\tasks.py app\models\core.py `
  app\utils\subscription.py app\utils\auth.py app\services\order_service.py

# 4. Verificar columnas de lifecycle en la DB local (MariaDB XAMPP)
#    SELECT subscription_state, dormant_at FROM restaurants LIMIT 1;
```

**Verificacion manual:**
- **Trazabilidad:** crear/editar/cancelar un pedido -> el timeline en
  `order_detail.html` lista los eventos con actor y rol correctos.
- **Dormant:** poner `is_active=0, subscription_state='dormant'` a un restaurante ->
  al entrar al dashboard redirige a `/dashboard/subscription` con el banner "Hola de nuevo!".
- **Copilots:** el chat lateral es indigo ("Estratega"); en Caja el asistente es naranja
  y deriva preguntas de estrategia al Estrategico.
- **Inyeccion IA:** enviar "ignore previous instructions" -> el mensaje se registra como
  `[FILTRADO]` y la respuesta sospechosa se rechaza (ver logs).

---

## [1.5.0] — 2026-08-17

### Rediseño del Dashboard Home

Reestructuración completa del dashboard principal con layout de grid 2 columnas, cards de color semáforo, gráficas Chart.js y métricas de caja en tiempo real.

### Añadido

- **Layout grid 2 columnas** en `index.html`: Hero 100%, 3 contadores 33% cada uno, barras+dona 50/50, productos+revenue 50/50, menú digital 100%. Mobile stacks a 1 columna.
- **3 cards de estado con color semáforo**: Pendientes `#FF7A29` naranja, Confirmados `#30A46C` verde, Entregados `#3B82F6` azul. Fondos `rgba()` al 12% opacidad, sin bordes, texto blanco.
- **Gráfica de barras** (`initWeeklyChart`): ventas semanales por día con toggle `$`/`#`.
- **Gráfica de dona** (`initDoughnutChart`): distribución pendientes/confirmados/entregados. Colores: `['#FF7A29', '#30A46C', '#3B82F6']`.
- **Gráfica de tendencia de ingresos** (`initRevenueChart`): línea con 30 días de datos, área sombreada.
- **Sección de productos Top 5** con toggle Hoy/30d.
- **Alerta de pedidos expirados**: visible solo cuando `expired_count > 0`. Fondo `#2D1A0A`, borde `#FF7A29`, texto naranja.
- **Métrica "Cobrado hoy"** en hero: muestra pagos reales en caja. Oculta cuando `vendido == cobrado` o ambos cero. Alerta `#FF7A29` cuando `vendido > cobrado`.
- **4 endpoints API** con `@require_role('owner')`:
  - `GET /dashboard/api/weekly-stats` → ventas e pedidos por día (7 días)
  - `GET /dashboard/api/top-products?days=30` → productos más vendidos
  - `GET /dashboard/api/collected-today` → vendido vs cobrado
  - `GET /dashboard/api/revenue-trend` → tendencia 30 días
- **`weekly_sales_by_day()`** en `data_service.py`: ventas diarias por día de la semana en TZ Colombia.
- **`revenue_trend_30d()`** en `data_service.py`: ventas diarias de los últimos 30 días.
- **`expired_today`** en `get_today_overview()`: cuenta pedidos expirados hoy (query por `updated_at`).
- **`CSP connect-src`**: agregado `cdn.jsdelivr.net` para Chart.js source maps.
- **Employee logout**: ahora redirige al login del empleado (no al admin). Guarda `session['employee_slug']` al login.
- **Confirmación al cancelar**: `orders.js` muestra `confirm()` antes de cancelar un pedido desde la lista.

### Cambiado

- **`dashboard_service.py:_get_date_range()`** — rangos calculados en hora de Colombia (UTC-5), consistente con CashRegisterService. Retorna `(start, end)` donde `end` es exclusivo.
- **`dashboard_service.py:get_today_overview()`** — ventas ahora usan `_paid_base_query` (pagados, status != cancelled, payment_method NOT NULL). Antes usaba `status.in_(['confirmed', 'delivered'])` que incluía no pagados.
- **`dashboard_service.py:get_extended_stats()`** — alineado con mismos criterios de caja.
- **`dashboard.js` v4** — refactor completo: `setChartMode($/#)`, `setProductsMode(Hoy/30d)`, `fetchCollectedToday()`, `fetchTopProducts()`, `initRevenueChart()`. Polling cada 30s.
- **`_orders_list.html`** — badges y bordes de pedidos usan colores semáforo. Headers de sección coloreados.
- **`order_detail.html`** — mensaje de cancelar corregido: "El pedido cambiará a estado cancelado. Puedes restaurarlo después desde la lista de cancelados."
- **`order_create.html` / `order_create_pos.html`** — nombre del cliente ahora es opcional. Eliminado `required` y texto "obligatorio".
- **`order_service.py:create_order()`** — `customer_name` ya no lanza `ValueError` si está vacío.
- **`cashier.html`** — 4 botones de pago: Efectivo, Nequi, **Bancolombia** (amarillo), Tarjeta. Grid `grid-cols-2`.
- **`auth.py` login** — limpia `session['employee_slug']` al entrar como dueño.

### Seguridad

- **4 endpoints de dashboard** protegidos con `@require_role('owner')`: stats, ai-stats, weekly-stats, top-products, collected-today, revenue-trend.
- **Dashboard index** protegido con `@require_role('owner')`.

### Seguridad — Roles y permisos (v2.1.0)

Implementación completa del sistema de roles: `owner`, `cashier`, `waiter`.

#### Añadido

- **`require_role(*roles)`** en `app/utils/auth.py`: decorador que verifica que el usuario autenticado tiene uno de los roles permitidos. Soporta sesión Flask y Bearer JWT (API móvil). Redirige a portal de empleado si no tiene permisos.
- **`require_role_check(*roles)`** en `app/utils/auth.py`: función reutilizable para `before_request`. Retorna None si pasa; respuesta JSON 403 o redirect si no.
- **`_EMPLOYEE_ALLOWED_ENDPOINTS`** en `app/routes/orders.py`: whitelist de endpoints que los empleados pueden usar desde su portal (`change_status`, `register_payment`).
- **`_require_dashboard_owner()`** en `app/routes/orders.py`: `before_request` que bloquea empleados en rutas de pedidos del dashboard, salvo los endpoints permitidos.
- **`app/routes/employees.py`** (nuevo): portal de empleado con login PIN, menú de pedidos, caja registradora.

#### Cambiado

- **`require_auth`** — ahora acepta `employee_id` en sesión (portal del empleado). Antes solo aceptaba `user_id`.
- **`_get_restaurant_unified`** — busca restaurante por `user_id` O `employee_id`.
- **`require_active`** — identifica al dueño por `role='owner'` (no `users[0]`). Corrige bug donde el primer usuario podía ser un empleado.
- **`require_role('owner')`** agregado a endpoints protegidos:
  - `GET /dashboard/` — solo dueño
  - `GET /dashboard/api/stats` — solo dueño
  - `GET /dashboard/api/ai-stats` — solo dueño
  - `GET /dashboard/api/weekly-stats` — solo dueño
  - `GET /dashboard/api/top-products` — solo dueño
  - `GET /dashboard/api/collected-today` — solo dueño
  - `GET /dashboard/api/revenue-trend` — solo dueño
  - `POST /orders/create` — solo dueño
  - `POST /orders/<id>/cancel` — solo dueño
  - `POST /orders/<id>/delete` — solo dueño
- **`require_role('owner', 'cashier', 'waiter')`** en `PATCH /orders/<id>/status` — todos los roles pueden cambiar estado.
- **`require_role('owner', 'cashier')`** en `POST /orders/<id>/payment` — solo dueño y cajero registran pago.
- **`app/routes/dashboard.py:achievements()`** — identifica dueño por `role='owner'` (no `users[0]`).

#### Flujo de empleados

1. **Login**: empleado ingresa PIN en `/empleado/<slug>` → sesión `employee_id`
2. **Portal**: ve pedidos activos, puede cambiar estados, registrar pagos
3. **Bloqueo**: no puede acceder a `/dashboard/`, `/orders/create`, cancelar/eliminar pedidos
4. **Logout**: vuelve al login del empleado (no al admin)

#### Archivos modificados (roles)

| Archivo | Cambios |
|---------|---------|
| `app/utils/auth.py` | `require_role`, `require_role_check`, `require_auth` acepta `employee_id` |
| `app/routes/orders.py` | `before_request` con whitelist, `@require_role` en endpoints |
| `app/routes/dashboard.py` | `@require_role('owner')` en index y 6 API endpoints |
| `app/routes/employees.py` | **Nuevo**: portal completo de empleado |

---

### Archivos modificados (rediseño dashboard)

| Archivo | Cambios |
|---------|---------|
| `app/routes/dashboard.py` | 4 endpoints API, `cobrado_hoy`, `expired_count`, `@require_role('owner')` |
| `app/services/dashboard_service.py` | `_get_date_range()` en Colombia TZ, `expired_today`, ventas con `_paid_base_query` |
| `app/services/insights/data_service.py` | `weekly_sales_by_day()`, `revenue_trend_30d()` |
| `app/static/js/dashboard.js` | v4 completo: charts, polling, toggles |
| `app/static/js/orders.js` | `confirm()` antes de cancelar |
| `app/template/dashboard/index.html` | Layout grid 2-col, cards color, dona, revenue, alerta expirados |
| `app/template/dashboard/_orders_list.html` | Colores semáforo en badges y bordes |
| `app/template/dashboard/order_detail.html` | Mensaje de cancelar corregido |
| `app/template/dashboard/order_create.html` | Nombre opcional |
| `app/template/employees/order_create_pos.html` | Nombre opcional, details colapsado |
| `app/template/employees/cashier.html` | 4 botones de pago (Bancolombia agregado) |
| `app/services/order_service.py` | `customer_name` opcional |
| `app/routes/employees.py` | **Nuevo**: logout redirige a login del empleado, guarda `employee_slug` en sesión |
| `app/routes/auth.py` | Limpieza de `employee_slug` en login |
| `app/routes/employees.py` | Logout redirige a login del empleado |
| `app/__init__.py` | CSP `cdn.jsdelivr.net` en `connect-src` |

### Cómo probar

1. **Dashboard**: `python run.py` → ir a `/dashboard/` → verificar grid 2-col, cards de color, gráficas con datos.
2. **Alerta expirados**: crear un pedido pending, esperar 24h (o modificar `expires_at` en DB), verificar que aparece la alerta.
3. **Cancelar desde lista**: presionar "Rechazar" → verificar que aparece `confirm()`.
4. **Logout empleado**: login con PIN → cerrar sesión → verificar que vuelve al login del empleado, no al admin.
5. **Roles**: login como empleado → intentar acceder a `/dashboard/` → debe redirigir al portal del empleado. Login como dueño → puede acceder a todo.
6. **Tests**: `pytest tests/ -x -q` → 434 tests pasan.

---

## [1.4.2] — 2026-07-21

### Seguridad — Race conditions en tokens IA

Auditoría completa del flujo de tokens identificó 5 vectores explotables. Todos parcheados.

### Añadido
- **`POST /api/v1/webhooks/mercadopago`** — endpoint dedicado de webhooks con verificación de firma HMAC-SHA256 (`x-signature`) e idempotencia por `data.id`. Reemplaza el endpoint `/webhook` legacy (sin verificación).
- **`app/utils/mp_webhook.py`** — utilidades compartidas `extract_mp_signature()` y `verify_mp_signature()` reutilizables por cualquier endpoint de webhook.
- **Variable `MP_WEBHOOK_SECRET`** en `settings.py` y `.env.example`. Si está configurado, los webhooks rechazan peticiones con firma inválida (fail-closed).
- **Migración Alembic** `a4b2c3d4e5f6`: índice UNIQUE sobre `ai_token_transactions.mp_payment_id`. MySQL permite múltiples NULLs, así que los consumos sin referencia MP no se bloquean.

### Cambiado
- **`TokenService.consume_token()`** — lock pesimista `SELECT ... FOR UPDATE` sobre la billetera. Cierra el TOCTOU que permitía doble consumo cuando un usuario tenía 1 token restante y disparaba 2 requests concurrentes.
- **`TokenService.credit_topup_purchase()`** — `UPDATE ... SET extra_tokens = extra_tokens + N` atómico en SQL. Reemplaza el read-then-write que causaba lost updates al acreditar top-ups.
- **`initialize_or_reset_token_wallet()`** — lock pesimista en el bloque de creación + UPDATE atómico en el reset mensual. Evita duplicación de wallets y race conditions en el reset del plan.
- **`app/routes/auth.py:webhook()`** — el endpoint legacy ahora también valida firma HMAC cuando `MP_WEBHOOK_SECRET` está configurado.
- **`app/models.py`** — `AITokenTransaction.mp_payment_id` ahora es `unique=True` en la capa de modelo (la migración ya lo aplica a nivel DB).

### Operacional
- `flask db upgrade` necesario en el siguiente deploy para aplicar la migración.
- Configurar `MP_WEBHOOK_SECRET` en el `.env` del servidor con la clave que da Mercado Pago en su dashboard de Webhooks.

---

## [1.4.1] — 2026-07-18

### Añadido
- **Pantalla completa para Copilot VZ** — nuevo `base_fullscreen.html` que elimina sidebar del dashboard, banners de suscripción y `md:ml-[260px]`; el body es `flex flex-col overflow-hidden` para llenar el viewport
- **Saludo dinámico** — rotación aleatoria entre 8 frases profesionales en cada nuevo chat (ya no dice "soy tu Copilot VZ")
- **Factorización masiva de templates**: todo `<style>` y `<script>` inline extraído a archivos CSS/JS externos
  - `insights.html`: 1740 → 29 líneas (7 partials + CSS/JS externos)
  - `legal.html`: 746 → 174 líneas
  - `auth/index.html`: 334 → 152 líneas
  - `auth/plans.html`: 509 → 282 líneas
  - `auth/register_setup.html`, `register_verify.html`, `sync_clerk.html`, `receipt.html`
- Nuevos archivos CSS estáticos: `insights.css`, `legal.css`, `plans.css`, `auth_index.css`, `receipt.css`, `register_setup.css`, `register_verify.css`
- Nuevos archivos JS estáticos: `insights_greetings.js`, `legal.js`, `auth_index.js`, `register_setup.js`, `register_verify.js`, `sync_clerk.js`
- Nuevos partials para Copilot VZ: `insights_sidebar.html`, `insights_chat.html`, `insights_mobile_nav.html`, `insights_modals.html`
- Agentes opencode: `astro-page-builder`, `db-migration-handler`, `flask-blueprint-generator`, `test-suite-runner`

### Cambiado
- **insights.js** — refactor: eliminación de lógica duplicada, limpieza de funciones obsoletas, mejora de scroll-to-bottom
- **AGENTS.md** — actualizado con nuevos agentes y comandos
- **`settings.py`** y **`package.json`** — dependencias y configuración actualizadas
- Templates auth y dashboard: eliminación de código inline duplicado, carga diferida de recursos
- CSRF: exenciones refinadas en `app/csrf.py` y `app/routes/api_public.py`

### Eliminado
- `LICENSE` — archivo de licencia removido
- `app/static/img/Zorro.png` — imagen no utilizada
- ~3277 líneas de código inline de templates (CSS/JS embebido)

### Cómo probar
1. `flask run` — navegar a `/insights/` — debe cargar en pantalla completa sin sidebar del dashboard
2. Verificar sidebar en desktop (visible, con perfil y botones de navegación)
3. Click en "Nuevo Chat" — saludo cambia aleatoriamente
4. Abrir/cerrar drawer en mobile (< 768px)
5. Verificar que modales (renombrar, eliminar, contexto, chart, onboarding) funcionan
6. Verificar que `legal.html` carga correctamente con estilos externos
7. Verificar que `auth/plans.html` y `auth/index.html` mantienen diseño original con CSS externo
8. `npm run build:css` — verificar que no hay roturas en estilos compilados

---

## [1.4.0] — 2026-07-15

### Añadido
- **Copilot VZ** — Analista de negocios IA completamente funcional
  - Clasificador híbrido (SQL rápido + análisis profundo con DeepSeek)
  - Prompt builder con 12 reglas estrictas de identidad, estilo y alcance
  - Context manager con compresión en 2 fases (resumen + modo comprimido)
  - Sistema de gráficas automáticas (Chart.js + sanitizer)
  - Onboarding inteligente según madurez de datos (4 niveles)
  - Sugerencias dinámicas de bienvenida y seguimiento contextual
  - Motor de eventos automáticos (APScheduler)
  - Anillo de contexto SVG con persistencia
  - Disclaimer "Copilot VZ puede cometer errores" inteligente
  - Edición de mensajes y regeneración de respuestas
  - Conversaciones ancladas, búsqueda y renombrado
- **Frontend Astro standalone** para el menú digital público
  - Migración completa del menú QR a Astro
  - URLs redirigidas desde Flask al nuevo frontend
- Documentación completa de Copilot VZ (GUIDE-07)

### Cambiado
- Migración del menú público de Flask/Jinja2 a Astro
- Dashboard: rediseño Friendly AI-Centric (Velzia)
- Panel de suscripción: diseño renovado en pestañas (Plan Actual, Historial, Planes)
- Autenticación: flujo Clerk sync simplificado, plantillas login pulidas
- Sidebar/navbar: logo y marca actualizados en todas las páginas
- Modal de compra de tokens con packs de 5K y 10K
- `AGENTS.md` actualizado con guía de Copilot VZ
- Logo del zorro reemplazado por robot chef en el menú digital (Astro favicon)
- System prompt de Copilot VZ: versión v1.3 (regla de identidad vs nombre del restaurante)

### Arreglado
- Disclaimer de Copilot VZ no aparecía en conversaciones nuevas
- Botón de "Editar" en página de perfil del dashboard corregido
- Pantalla de error 429 rediseñada y 500 estilizada
- Varias correcciones en templates auth y dashboard

---

### Añadido
- Sistema de tokens AI (Velzia 2.0.0)
  - `AITokenWallet` por usuario con plan_tokens + extra_tokens
  - `AITokenTransaction` como log inmutable de operaciones
  - Plan Elite con tokens ilimitados
  - Top-up packs via Mercado Pago (5K = 15 tokens, 10K = 35 tokens)
- `PreRegistration` — pre-registro con selección de plan
- `Expense` — registro de gastos del restaurante
- `OrderCounter` — contador atómico diario para números de orden

### Cambiado
- Clerk JWT como método de autenticación para Scanner IA
- `is_active` ahora controla visibilidad del restaurante (no acceso)

---

## [1.2.0] — 2026-03-01

### Añadido
- Rate limiting inteligente con detección de patrones de spam
- Sistema de período de gracia de 14 días post-expiración
- PWA con Workbox service workers + Dexie IndexedDB
- Plantillas de error personalizadas (400, 403, 404, 429, 500)

### Cambiado
- Refactor: lógica de negocio extraída a `app/services/`
- Timezone: sanitización completa a UTC con `AwareDateTime`
- `get_subscription_status()` como fuente única de verdad

---

## [1.1.0] — 2026-01-15

### Añadido
- Autenticación con Clerk OAuth
- Integración con Cloudinary para imágenes
- Integración con Mercado Pago para pagos de suscripción
- Tareas programadas con APScheduler

### Cambiado
- Migración de SQLite a MySQL 8.x
- Arquitectura de rutas: patrón de doble blueprint (web + API)

---

## [1.0.0] — 2025-11-01

### Añadido
- Lanzamiento inicial de Orderfox
- CRUD completo de restaurantes, productos, categorías, modificadores
- Menú público con QR por mesa
- Sistema de pedidos en tiempo real
- Dashboard del dueño con estadísticas
- Planes de suscripción (Emprendedor, Crecimiento, Elite)
- Trial de 7 días con auto-creación de cuenta
- Autenticación tradicional (email + password)
