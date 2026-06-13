# Análisis Arquitectónico — Frontend Orderfox

**Fecha:** 2026-06-05
**Auditoría:** Full-stack architect review
**Stack:** Flask + Vanilla JS + Tailwind CSS v4
**Salud general:** 4/10 — requiere intervención antes de agregar nuevas funcionalidades.

---

## Resumen Ejecutivo

El frontend de Orderfox muestra signos claros de **evolución orgánica sin gobierno técnico**. El código ha crecido por acumulación de funcionalidades sin un plan arquitectónico compartido, resultando en 5 implementaciones de `showToast`, 3 sistemas de fetch, 2 carritos en paralelo, 132 `onclick` en templates y un módulo de 657 líneas (`menu-public.js`) que es el punto más crítico del sistema. La deuda técnica es **alta** pero **recuperable** con refactors incrementales. El riesgo mayor es que el menú público (ruta crítica de conversión QR → orden) tenga la peor calidad del código base.

---

## 1. Problemas de Calidad

### 🔴 CRITICAL

| # | Problema | Evidencia | Por qué es crítico | Causa Raíz |
|---|----------|-----------|-------------------|------------|
| C1 | **Monolito de 657 líneas: `menu-public.js`** | Archivo completo. Contiene: cart + localStorage + detail panel + category nav + IntersectionObserver + search + sidebar + checkout + WhatsApp + QR + flip cards + deep link + HTML escaping | Es la página más visitada (QR → cliente). Cualquier error rompe el embudo de conversión. Imposible testear, mantener o extender. | Nunca se refactorizó. Se agregaron features por capas sin extraer responsabilidades. |
| C2 | **Dos carritos paralelos** | `cart.js` (legacy, usado por `public_base.html`) vs `menu-public.js` (nuevo 3-panel). Diferentes keys de localStorage, diferentes endpoints, diferentes modales de checkout/success. | Colisión silenciosa: si un usuario visita ambos menús, un carrito sobrescribe al otro. Estado global inconsistente. | Se construyó un nuevo menú público (3-panel) sin reutilizar el carrito legacy. No hubo mandato de refactor. |
| C3 | **`showToast` implementado 5+ veces con APIs inconsistentes** | `ui-utils.js`, `auth-common.js`, `cart.js`, `products.js`, `order_create.js`, `menu-public.js` (inline), `qr_pages.js` (`mostrarToast`). Cada uno con diferente CSS, duración, API de parámetros. | Inconsistencia visual y funcional. Bugs corregidos en uno no se propagan. | Cultura de copia-pega sin un módulo compartido. |
| C4 | **`lang="en"` en 6+ templates con contenido 100% español** | `common/base.html`, `auth/reset_password.html`, `auth/register_verify.html`, `auth/register_setup.html`, `auth/forgot_password.html`, `auth/payment.html` | Rompe accesibilidad para lectores de pantalla. | Error de copia del boilerplate inicial de Tailwind/Flask. Nunca se detectó en code review. |

### 🟠 HIGH

| # | Problema | Evidencia | Por qué es importante | Causa Raíz |
|---|----------|-----------|----------------------|------------|
| H1 | **Zero module system (25 archivos en scope global)** | Ningún archivo tiene `import`/`export`. Todas las funciones cuelgan de `window.*`. | Colisiones de nombres garantizadas. `showToast` global se sobrescribe según orden de carga. Sin encapsulamiento. | Decisión inicial de no usar bundler, pero nunca se introdujeron módulos ES nativos (soportados desde 2018). |
| H2 | **132 `onclick=` en templates vs `addEventListener`** | Esparcidos en `menu_public.html`, `public_base.html`, `tables.html`, `subscription.html`, `order_detail.html`, `orders.html`, `product_form.html`, `category_form.html`, `categories.html`, `products.html`, `products_category.html`, etc. | Vector XSS si el valor incluye interpolación Jinja. Acopla comportamiento a HTML. Impide event delegation. | Convención no establecida. Los templates crecieron con `onclick` por ser el camino más rápido. |
| H3 | **`menu_public.html` standalone (no extiende `public_base.html`)** | `menu_public.html` comienza con `<!DOCTYPE html>` — página completa con su propio `<head>`, cart HTML, checkout modal, success modal, toast. | Duplica ~200+ líneas de HTML del carrito, checkout, modales que ya están en `public_base.html`. | Layout 3-panel no encajaba en `public_base.html`. En vez de refactorizar la base, se creó página separada. |
| H4 | **3 enfoques diferentes de fetch** | 1. Monkeypatch global en `auth-common.js` (CSRF automático). 2. Manual con `X-CSRFToken`. 3. Manual con `X-Requested-With`. | Inconsistente, propenso a errores de CSRF, difícil de auditar. | El monkeypatch fue agregado tarde. Los archivos existentes nunca se migraron. |
| H5 | **HTML-in-JS antipattern (~1,000 líneas de templates en strings JS)** | `cart.js` (updateDisplay), `menu-public.js` (renderDetailPanel), `categories-dashboard.js` (CRUD panel), `modifiers-modal.js`, `order-detail-panel.js`. | Mezcla lógica de negocio con presentación. Sin syntax highlighting. Dificulta i18n. | Al necesitar contenido dinámico sin framework frontend, se recurrió a strings HTML como solución rápida. |
| H6 | **2 configuraciones de Tailwind con colores primarios diferentes** | `tailwind.app.js` → `primary: "#f97316"` (naranja dashboard). `tailwind.login.js` → `primary: "#f2460d"` (naranja más intenso). | Inconsistencia de marca entre auth y dashboard. | Diferentes páginas requirieron diferentes paletas sin centralizar. |
| H7 | **Modifier modal duplicado (~300 líneas) en 2 archivos** | `products_category.html` y `products.html` contienen el mismo modal de modifiers para mobile y desktop. | Si se agrega un campo al modal, hay que editarlo en 2 templates + el JS asociado. | `products_category.html` se creó como copia de `products.html` sin extraer el modal a componente compartido. |

### 🟡 MEDIUM

| # | Problema | Impacto |
|---|----------|---------|
| M1 | **23 de 26 scripts sin `defer`** — carga secuencial bloqueante | Incrementa tiempo de renderizado. |
| M2 | **Missing `for` en etiquetas `label` (~10 formularios)** — login, checkout, register | Menos accesible para lectores de pantalla. |
| M3 | **Missing `alt` text en imágenes de productos/categorías (5+ instancias)** | Afecta accesibilidad y SEO. |
| M4 | **Polling de órdenes falla en silencio** — `orders-realtime.js` `if (!res.ok) return;` | Dashboard muestra datos obsoletos sin indicación al usuario. |
| M5 | **Pagination duplicada** — `products.js` y `products-dashboard.js` con lógica casi idéntica | Duplicación de lógica de negocio. |
| M6 | **Toggle logic duplicada** — `categories.js:toggleCategory()` vs `products.js:toggleProduct()` con misma lógica de optimistic update | Duplicación que podría ser una utility. |
| M7 | **3 menús públicos no extienden `public_base.html`** — `menu_public.html`, `menu_novedades.html`, `menu_category_products.html` | Duplicación de ~500+ líneas de HTML, CSS y JS. |
| M8 | **Imagen preview JS duplicado en `product_form.html` y `category_form.html`** | Mantenimiento duplicado. |
| M9 | **Padding del sidebar no heredado en algunos templates del dashboard** | Offset visual inconsistente. |
| M10 | **CDN Tailwind sin purge** en la mayoría de páginas | ~500KB+ CSS muerto enviado al cliente. |

---

## 2. Análisis de Causas Raíz

### 2.1 ¿Por qué el frontend no tiene módulos?

**Decisión inicial pragmática que nunca se corrigió.** El proyecto empezó como Flask monolitico con jQuery-like vanilla JS. No se introdujo un bundler porque la premisa era "sin framework frontend". Cuando los módulos ES nativos se volvieron estándar (2018+), el proyecto ya tenía 10+ archivos JS globales y migrarlos requería refactorizar los `onclick=` a event listeners. El equipo optó por no hacerlo.

**Patrón sistémico:** *Lock-in de deuda técnica* — una decisión temprana (scripts globales + onclick) hace que cualquier mejora requiera un refactor costoso, lo que desincentiva la mejora.

### 2.2 ¿Por qué hay 5 implementaciones de showToast?

**Cultura de copia-pega sin módulo compartido.** Cada archivo necesitaba un toast y:
1. `ui-utils.js` fue creado primero (Material Symbols).
2. `auth-common.js` agregó `window.showToast` propio.
3. `cart.js` necesitaba toast y creó el suyo.
4. `products.js` no encontró `window.showToast` en el scope y creó su versión.
5. `order_create.js` es inline y definió su propio showToast.

**Patrón sistémico:** *Duplicación por desconocimiento* — sin un manifiesto de dependencias compartidas, cada desarrollador resuelve el mismo problema desde cero.

### 2.3 ¿Por qué menu-public.js es un monolito de 657 líneas?

**Refactor diferido indefinidamente.** Cada nueva feature se agregó al mismo archivo porque:
1. Ya tenía acceso al state global del carrito.
2. Ya tenía las funciones auxiliares (render, toast, fetch).
3. Extraer requería crear un módulo y cambiar los `onclick=` del template.
4. Cada feature nueva aumentaba el costo de refactor.

**Patrón sistémico:** *Tragedia de los comunes arquitectónica* — un archivo que crece sin control porque todas las features dependen de él.

### 2.4 ¿Por qué hay 3 enfoques de fetch?

**Parches incrementales sin migración.**
1. **Fase 1:** Los primeros archivos implementaron fetch manual con headers CSRF.
2. **Fase 2:** Se creó `auth-common.js` con monkeypatch global.
3. **Problema:** El monkeypatch se agregó pero los archivos existentes nunca se migraron porque "funcionan".

**Patrón sistémico:** *Parche sin migración* — se introduce una mejora pero no se aplica retroactivamente.

---

## 3. Roadmap de Refactorización Priorizado

### Fase 1: Quick Wins (~2 horas, esfuerzo bajo, impacto alto)

| # | Qué hacer | Archivos | Riesgo | Métrica de éxito |
|---|-----------|----------|--------|-----------------|
| 1.1 | Corregir `lang="en"` → `lang="es"` en 6 templates | `base.html`, `reset_password.html`, `register_verify.html`, `register_setup.html`, `forgot_password.html`, `payment.html` | Bajo | `grep '<html lang="en"'` retorna 0 |
| 1.2 | Agregar `defer` a scripts sin él | Todos los templates que cargan JS | Bajo-medio | Lighthouse "Eliminar recursos bloqueantes" mejora |
| 1.3 | Agregar `alt` text a imágenes de productos | `menu_public.html`, `public_base.html`, `components/product_macros.html` | Bajo | WAVE: 0 missing alt text |
| 1.4 | Agregar `for` en labels faltantes | Formularios en templates | Muy bajo | `html-validate` sin errores de labels |
| 1.5 | Unificar color primario Tailwind (a `#f97316`) | `tailwind.app.js`, `tailwind.login.js` | Medio | 1 sola definición de `primary` |

### Fase 2: Modularización JS (5-8 días, esfuerzo medio, impacto alto)

| # | Qué hacer | Archivos | Riesgo |
|---|-----------|----------|--------|
| 2.1 | Crear `api-client.js` como módulo ES con fetch wrapper unificado | Nuevo + `auth-common.js` (remover monkeypatch) + `cart.js`, `categories.js`, `modifiers-modal.js`, `orders-realtime.js`, `order_detail.js`, `subscription.js`, `products.js`, `orders.js` | Medio |
| 2.2 | Crear `toast.js` como módulo ES exportando `showToast()` | Nuevo + eliminar de `ui-utils.js`, `auth-common.js`, `cart.js`, `products.js`, `order_create.js` | Medio |
| 2.3 | Migrar 132 `onclick=` a `addEventListener` con data attributes | Todos los templates + JS asociados | Alto (hacer página por página) |
| 2.4 | Agregar `type="module"` a scripts principales | Templates + todos los archivos JS | Alto (requiere 2.3 primero) |

> **Nota:** 2.3 y 2.4 deben hacerse en ese orden. Si agregas `type="module"` sin migrar `onclick`, todo se rompe.

### Fase 3: Refactor Templates (3-5 días, esfuerzo medio, impacto alto)

| # | Qué hacer | Archivos | Riesgo |
|---|-----------|----------|--------|
| 3.1 | Extraer cart HTML a `components/cart_drawer.html` | `public_base.html` → `components/cart_drawer.html` | Bajo |
| 3.2 | Hacer que `menu_public.html` herede de `public_base.html` | `menu_public.html`, `public_base.html` | **Alto** — layout completamente diferente |
| 3.2 alt | Alternativa: extraer modales duplicados a `components/` | `public_base.html`, `menu_public.html` | Bajo (80% beneficio, 20% riesgo) |
| 3.3 | Extraer modifier modal a `components/modifier_modal.html` | `products.html`, `products_category.html` | Bajo |
| 3.4 | Unificar image preview JS | `product_form.html`, `category_form.html` | Bajo |

### Fase 4: Extracción de Servicios de menu-public.js (5-7 días, esfuerzo alto, impacto alto)

| # | Qué hacer | Archivos | Riesgo |
|---|-----------|----------|--------|
| 4.1 | Extraer `cart-core.js` — lógica pura de carrito (state + localStorage) | `public/cart-core.js` | Medio |
| 4.2 | Extraer `checkout.js` — address modal, processOrder, success | `public/checkout.js` | Medio |
| 4.3 | Extraer `detail-panel.js` — render de detail panel + extras | `public/detail-panel.js` | Medio |
| 4.4 | `menu-public.js` queda como orquestador (< 100 líneas) | `menu-public.js` | Bajo si pasos anteriores funcionan |
| 4.5 | Crear `toggle-utils.js` — función genérica de optimistic toggle | Nuevo + refactor `categories.js`, `products.js` | Bajo |

### Fase 5: Arquitectura a Largo Plazo (esfuerzo alto, impacto medio-alto)

| # | Qué hacer | Riesgo |
|---|-----------|--------|
| 5.1 | Introducir Vite como bundler para JS y CSS | Alto — cambia pipeline de build |
| 5.2 | Considerar Alpine.js para interactividad declarativa en templates dashboard | Medio |
| 5.3 | Agregar tests E2E (Playwright) para flujos críticos: QR → menú → carrito → checkout | Medio |

---

## 4. Resumen de Priorización

| Prioridad | Ítem | Impacto | Esfuerzo |
|-----------|------|---------|----------|
| **P0** | Fase 1.1-1.5 (Quick wins) | Alto | Bajo (~2h) |
| **P1** | Fase 3.1, 3.3 (Extraer componentes template duplicados) | Alto | Bajo-Medio |
| **P2** | Fase 4.1-4.4 (Extraer servicios de `menu-public.js`) | **Crítico** | Alto |
| **P3** | Fase 3.2 (Unificar `menu_public.html` en `public_base.html`) | Alto | Alto |
| **P4** | Fase 2.1-2.2 (`api-client.js` + `toast.js`) | Alto | Medio |
| **P5** | Fase 2.3 (Migrar `onclick`) | Alto | Alto |
| **P6** | Fase 2.4 (`type="module"`) | Alto | Medio |
| **P7** | Fase 4.5 (Toggle utility) | Medio | Bajo |
| **P8** | Fase 5 (Vite/Alpine/Testing) | Medio | Alto |

---

## 5. Riesgos de Implementación

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| Regresión en menú público (Fase 4) | Alta | Crítico | Feature flags. Mantener monolito funcional hasta validación en prod. |
| Rotura por migración `onclick` → modules (Fase 2) | Alta | Alto | Migrar onclick primero. Usar `data-action` + event delegation. |
| Layout roto al unificar `menu_public.html` (Fase 3.2) | Media | Alto | No forzar. Alternativa de extraer modales es 80% beneficio con 20% riesgo. |
| Monkeypatch CSRF legacy (Fase 2.1) | Media | Medio | Mantener monkeypatch hasta migración completa. |
| Cambio de color primario (Fase 1.5) | Baja | Bajo | Elegir `#f97316` como canonical (más usado). |

---

## 6. Stack Technical Debt Summary

| Dimensión | Estado Actual | Target |
|-----------|--------------|--------|
| **Modularidad JS** | 25 archivos globales, 0 imports | Módulos ES con imports/exports |
| **Toast** | 5+ implementaciones | 1 módulo compartido |
| **Fetch/CSRF** | 3 enfoques inconsistentes | 1 API client unificado |
| **Templates** | 3 menús públicos standalone | Herencia de `public_base.html` |
| **Event binding** | 132 onclick | addEventListener + event delegation |
| **Accesibilidad** | `lang="en"`, missing alt/labels | WCAG 2.2 AA compliant |
| **Performance** | 23/26 scripts sin defer, CDN sin purge | Scripts diferidos, CSS purgado |
| **Testing** | 0 tests frontend | E2E para flujo crítico QR→orden |
| **Build** | Sin bundler JS | Vite o similar |
| **Consistencia visual** | 2 colores primarios | 1 design token system |

---

## 7. Nota Final

El frontend de Orderfox es el típico caso de un producto que creció rápido sin inversión en infraestructura frontend. La buena noticia es que el stack es simple (vanilla JS + Jinja2) y no hay dependencias pesadas que compliquen el refactor. Cada fase del roadmap propuesto es independiente y puede ejecutarse sin bloquear el desarrollo de features.

**Recomendación:** Comenzar con los Quick Wins (Fase 1) para generar momentum, luego atacar la extracción de `menu-public.js` (Fase 4) que es el riesgo más grande para el negocio.
