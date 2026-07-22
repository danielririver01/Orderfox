# Changelog

Todas las fechas en UTC.

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
