# Changelog

Todas las fechas en UTC.

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
