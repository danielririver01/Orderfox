# Velzia — Ficha de Producto

## 1. ¿Qué problema resuelve Velzia?

Velzia es una **suite SaaS dual** para restaurantes que cubre **ingresos y egresos** en una sola plataforma:

### 🍽️ Ordenfox (Flask) — Gestión de pedidos en mesa
| Problema | Impacto |
|----------|---------|
| **Pérdida de pedidos por WhatsApp** | Clientes envían pedidos desordenados por chat, el personal se confunde, se pierden comandas |
| **Proceso manual de toma de pedidos** | Dependencia de libretas, WhatsApp desorganizado o sistemas POS caros |
| **Alta fricción para pedidos digitales** | Menús digitales existentes requieren registro, app o navegación compleja |

### 📄 Scanner IA (Next.js) — Control de gastos
| Problema | Impacto |
|----------|---------|
| **Gastos desorganizados** | Dueños pierden el rastro de compras, insumos y gastos operativos |
| **Tickets extraviados** | Recibos físicos se pierden o terminan en un cajón |
| **Sin visibilidad financiera** | No hay forma fácil de ver en qué se gasta el dinero mes a mes |

**Propuesta de valor unificada:** Velzia cubre **ingresos** (pedidos en mesa vía menú digital QR) y **egresos** (escaneo inteligente de gastos con IA) en un solo ecosistema, compartiendo DB, auth y sistema de tokens.

---

## 2. ¿A quién va dirigido exactamente?

**Dueños y administradores de restaurantes PyMEs en Latinoamérica** que:
- Facturan entre 5 y 50 cubiertos diarios
- Hoy toman pedidos por WhatsApp o de forma verbal
- Quieren digitalizarse sin presupuesto para sistemas grandes (iFood, Rappi, POS caros)
- Necesitan **control de gastos** además de gestión de pedidos
- No tienen equipo técnico interno

**Perfil típico:** Restaurantes pequeños y medianos, cafeterías, pizzerías, comida rápida, emprendimientos gastronómicos en LATAM.

---

## 3. ¿Cómo funciona hoy paso a paso?

### 🍽️ Ordenfox — Flujo de Pedidos (Flask + MySQL)
1. El cliente escanea un **código QR** en la mesa
2. Ve el **menú digital** en su celular (sin app, sin registro)
3. Navega por categorías, productos y modificadores (ej. "sin cebolla", "tamaño grande")
4. Agrega al carrito y **realiza el pedido**
5. El pedido llega en **tiempo real** al dashboard del restaurante (BroadcastChannel + polling)
6. El restaurante confirma, prepara y entrega desde el dashboard (pending → confirmed → delivered)

### 📄 Scanner IA — Flujo de Gastos (Next.js + Prisma + MySQL)
1. El usuario inicia sesión vía Clerk (autenticación compartida con Ordenfox)
2. Toma una foto de un ticket/recibo o sube una imagen
3. **Google Vision API** extrae el texto bruto del ticket
4. **DeepSeek AI** estructura los datos: monto, comercio, fecha, categoría, items
5. El sistema asigna **puntajes de confianza** (amountConfidence, itemsConfidence)
6. El usuario revisa, edita si es necesario y guarda el gasto
7. El gasto se categoriza automáticamente y se refleja en dashboards con gráficos (donut, tendencia mensual, gasto diario)

### 🔗 Integración entre ambos sistemas
- **Base de datos compartida** (`orderfox` MySQL) — usuarios, tokens, planes
- **Autenticación unificada** — Clerk + Flask JWT bridge
- **Sistema de tokens compartido** — `ai_token_wallets` se usa en ambos lados
- **Registro unificado** — Sign-up redirige a Flask (`/register?plan=trial`) que crea el usuario en ambos sistemas
- **Pagos centralizados** — Recarga de tokens procesada via Flask (Mercado Pago)

---

## 4. ¿Qué tiene ya hecho y qué le falta?

### ✅ Ordenfox (Flask) — Funcionalidad de negocio completa
| Componente | Estado |
|------------|--------|
| Menú digital público responsive (móvil-first) | ✅ |
| Dashboard web con pedidos en tiempo real | ✅ |
| CRUD completo de productos, categorías y modificadores | ✅ |
| Autenticación Clerk OAuth + JWT + sesión web | ✅ |
| Sistema de suscripciones (7 días trial + 14 días gracia) | ✅ |
| Pagos Mercado Pago | ✅ |
| Rate limiting inteligente anti-spam | ✅ |
| CSRF protection | ✅ |
| Subida de imágenes a Cloudinary | ✅ |
| Soporte PWA (sin service worker real implementado) | ⚠️ No funcional |
| Video presentación promocional | ✅ |
| Tema oscuro automático | ✅ |

### ✅ Backend refactorizado — Service Layer completo
| Componente | Archivo | Estado |
|------------|---------|--------|
| Auth service | `app/services/auth_service.py` (858 líneas) | ✅ |
| Order service | `app/services/order_service.py` | ✅ |
| Product service | `app/services/product_service.py` | ✅ |
| Category service | `app/services/category_service.py` | ✅ |
| Dashboard service | `app/services/dashboard_service.py` | ✅ |
| Public menu service | `app/services/public_menu_service.py` | ✅ |
| Table service | `app/services/table_service.py` | ✅ |
| Token service | `app/services/token_service.py` | ✅ |

### ✅ Frontend refactorizado — Módulos extraídos
| Antes (monolito) | Después (modular) | Reducción |
|------------------|-------------------|-----------|
| `menu-public.js`: **657 líneas** | orquestador de **147 líneas** | -78% |
| `showToast` en 5+ archivos | `toast.js` unificado | ✅ |
| 3 enfoques de fetch | `api-client.js` unificado | ✅ |
| 132 `onclick` en templates | `event-delegation.js` centralizado | ✅ |
| Image preview duplicado | `image-preview.js` compartido | ✅ |

### ✅ Scanner IA (Next.js) — Completo
| Componente | Estado |
|------------|--------|
| Escaneo de tickets con Google Vision OCR | ✅ |
| Estructuración con DeepSeek AI (monto, comercio, fecha, categoría, items) | ✅ |
| Sistema de confianza (confidence scores) | ✅ |
| Dashboard con estadísticas y 3 gráficos SVG (donut, tendencia, diario) | ✅ |
| Gestión de categorías con presupuestos mensuales | ✅ |
| Historial con búsqueda, filtros y exportación CSV | ✅ |
| Edición de gastos con visor de ticket original | ✅ |
| Sistema de tokens (consumo por scan + recarga Mercado Pago) | ✅ |
| Plan Elite (scans ilimitados) | ✅ |
| Animaciones Framer Motion | ✅ |
| Tema oscuro completo | ✅ |

### ✅ Tests implementados
| Archivo | Lo que prueba |
|---------|---------------|
| `tests/conftest.py` | Fixtures, app factory, test DB |
| `tests/test_subscription.py` | Lógica de suscripciones (trial, grace, expired, active) |
| `tests/test_rate_limiter.py` | Rate limiting inteligente |
| `tests/test_image_handler.py` | Subida y manejo de imágenes |

### ❌ Lo que falta / mejorar
| Pendiente | Prioridad |
|-----------|-----------|
| **Pruebas E2E** para flujo crítico QR → menú → carrito → checkout | 🟡 Media |
| **Tests del Scanner IA (Next.js)** — 0 tests en ese proyecto | 🟡 Media |
| **Panel de análisis de ventas** en Ordenfox | 🟡 Media |
| **Gestión de mesas** (asignar QR por mesa) | 🟡 Media |
| **Multi-sucursal** para una misma cuenta | 🟡 Media |
| **Notificaciones push** | 🟢 Baja |
| **App móvil nativa / APK** (en progreso según commits) | 🟢 Baja |
| **Integración con servicios de delivery** (PedidosYa, iFood, Rappi) | 🟢 Baja |
| **Impresión automática de comandas** | 🟢 Baja |
| **Migrar `onclick` restantes** en templates → `data-action` + event delegation | 🟡 Media |
| **Unificar `menu_public.html`** para que herede de `public_base.html` | 🟡 Media |

---

## 5. ¿Qué lo hace diferente de otros sistemas?

| Aspecto | Velzia | Competidores típicos |
|---------|--------|----------------------|
| **Cobertura** | **Ingresos + Egresos** (menú QR + escáner IA de gastos) en un sistema | Solo pedidos o solo contabilidad |
| **Costo** | SaaS directo, prueba gratis, sin comisiones por pedido | Comisiones 15-30% o licencias caras |
| **Scanner IA** | Google Vision + DeepSeek AI estructuran tickets automáticamente | Ningún menú QR lo ofrece |
| **Canales de pedido** | QR directo, sin registro para el cliente | App propia con registro obligatorio |
| **Arquitectura** | Flask + Next.js integrados, misma DB, auth unificada | Generalmente monolíticos o completamente separados |
| **Conectividad** | 100% online — no funciona sin internet | Dependencia total de conexión |
| **Propiedad de datos** | El restaurante tiene su propio slug y QR físico | Dependencia del marketplace |
| **Calidad de código** | Service layers, módulos JS, tests unitarios — post-refactor | Varía |

**Diferenciador clave:** Velzia es la **única plataforma que unifica el ciclo completo del restaurante**: cómo los clientes piden (QR → menú → pedido) y cómo el dueño controla sus gastos (foto → IA → categorizado → dashboard). Todo en un solo ecosistema, sin comisiones por pedido.

---

## 6. ¿En qué etapa está el proyecto?

### 🟢 **MVP+ pulido — Listo para producción (con deuda menor)**

| Indicador | Detalle |
|-----------|---------|
| **Ordenfox (Flask)** | Core loop completo. Service layer implementado. Código modularizado. |
| **Scanner IA (Next.js)** | Pipeline OCR→DeepSeek completo. Dashboards, gráficos, exportación. |
| **Integración** | DB compartida, auth Clerk+JWT bridge, pagos centralizados. |
| **Refactor backend** | **Completado** — 8 servicios, rutas simplificadas, eliminación de duplicación masiva. |
| **Refactor frontend** | **Completado** — `menu-public.js` de 657→147 líneas, `toast.js`, `api-client.js`, `event-delegation.js`. |
| **Tests** | **Implementados** — subscription, rate limiter, image handler. Faltan E2E y tests de Next.js. |
| **Base de datos** | MySQL con migraciones Alembic (Flask) + Prisma (Next.js). Migración de datos legacy completada. |
| **Pagos** | Mercado Pago integrado. Recarga de tokens y suscripciones. |
| **Hosting** | Configurado para producción (WhiteNoise, Gunicorn, URLs en .env). |

**Conclusión:** El producto es **funcional de punta a punta y está refactorizado**. Un dueño de restaurante puede hoy registrar su negocio, recibir pedidos en tiempo real, escanear gastos con IA y ver dashboards financieros — todo desde un panel unificado. La deuda técnica principal está resuelta (service layer, modularización JS, tests). Quedan mejoras menores (E2E, multi-sucursal, push notifications).

---

*Documento actualizado el 2026-06-10 — incluye análisis de `Orderfox` (Flask) + `Receipt-Scanner-AI` (Next.js). Refactor backend y frontend completados en junio 2026.*
