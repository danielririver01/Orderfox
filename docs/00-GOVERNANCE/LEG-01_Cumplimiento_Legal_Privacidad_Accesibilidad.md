# LEG-01 — Cumplimiento Legal, Privacidad y Accesibilidad

> Estado: `Implementado` · Última auditoría: 2026-09-24 · Versión legal del hub `/legal`: **1.2**

## 1. Alcance

Auditoría y ajustes de cumplimiento para Velzia (core Flask + menú público Astro), incluyendo:
consentimiento en formularios, cookies, integraciones de terceros, accesibilidad (WCAG 2.1 AA),
datos del negocio y derechos de autor de imágenes.

Jurisdicción principal: **Colombia**.

## 2. Marco legal aplicable

| Norma | Aplicación en Velzia |
|-------|----------------------|
| **Ley 1581 de 2012** (datos personales) + Decreto 1377 de 2013 | Registro de tratamientos de clientes y titulares. Autorización previa, expresa e informada → checkbox en el registro (`accept_terms`). En checkout y reservas públicas: aviso informativo de finalidad bajo el botón (sin checkbox — decisión UX del titular, ver ADR-011; un gate en backend se implementó y se revirtió el mismo día por fricción en la conversión). Aviso de privacidad en `/legal#privacidad`. Derechos ARCO-P con respuesta en ≤15 días hábiles. Quejas → SIC. |
| **Ley 1480 de 2011** (Estatuto del Consumidor) | Derecho de retracto: art. 47 num. 5 permite excluirlo para servicios digitales de suministro inmediato SI hay consentimiento previo, expreso e informado → cláusula en Términos + Política de Reembolsos dedicada (`/legal#reembolsos`). Garantías y precios en COP con IVA incluido. |
| **Ley 527 de 1999** (comercio electrónico) | Valor probatorio de las confirmaciones electrónicas (pedidos con número ORD, idempotencia). |
| **Ley 679 de 2001** | Prohibición de contenido ilícito con menores — cubierto por la cláusula de uso lícito en Términos. |
| **Régimen de Habeas Data + Ley 1581** para empleados de restaurantes | Los empleados no son usuarios de Velzia: el titular de la cuenta es responsable de informarles la trazabilidad (cláusula expresa en Términos y FAQ). Velzia no tiene relación contractual con ellos. |

> **Nota LGPD/GDPR:** no aplican de forma directa (sin establecimiento ni oferta dirigida en
> Brasil/UE a la fecha). Si se abren esos mercados, revisar ANTES de lanzar (ver riesgos).

## 3. Cookies y seguimiento (verificado)

Inventario completo de tecnologías client-side del proyecto:

| Tecnología | Tipo | Finalidad | ¿Requiere banner? |
|------------|------|-----------|-------------------|
| Cookie de sesión Flask (`session`, `HttpOnly`, `Secure` en prod, `SameSite=Lax`) | Propia, estrictamente necesaria | Autenticación del panel y del flujo de checkout | **No** (necesaria para el servicio solicitado) |
| `localStorage` `velziaCart_<id>` | Propia, necesaria | Carrito del menú público | **No** |
| `sessionStorage` `velziaIdemKey_<id>` | Propia, necesaria | Idempotencia anti-duplicado de pedidos | **No** |
| Fuentes de Google (fonts.googleapis.com) | Tercero | Tipografía | No aplica consentimiento en CO; el navegador descarga el recurso pero no se comparten datos de usuario |

**Conclusión:** no hay cookies de publicidad, píxeles, ni analítica de terceros (no existe
gtag/GA/Meta Pixel/Hotjar; la dependencia `@vercel/analytics` está **sin usar** — solo en
`package-lock.json`, no en `package.json`). En Colombia el banner de cookies solo se exige para
cookies NO esenciales, por lo que **no se requiere banner**; el aviso informativo está en
`/legal#privacidad` y `/legal#datos`.

**Regla para el futuro:** si se agrega Google Analytics, Meta Pixel o similar, PRIMERO actualizar
la política de privacidad y agregar banner de consentimiento con opt-in, DESPUÉS activar el script.
Queda documentado aquí como gate obligatorio.

## 4. Terceros / encargados del tratamiento

> **Decisión del titular (2026-09-24):** los proveedores de IA y de búsqueda web del Copilot VZ
> NO se nombran en las páginas públicas (`/legal`, landing, menú) para no exponer arquitectura
> interna del negocio. En la política pública se describen como "proveedores de servicios de
> análisis e inteligencia artificial". Los nombres solo viven en configuración interna.

| Tercero | Datos que recibe | Cuándo | ¿Se publica en `/legal`? |
|---------|------------------|--------|--------------------------|
| Mercado Pago | Datos de pago (no los almacenamos) | Suscripción | Sí |
| Clerk | Credenciales e identidad | Login/registro | Sí |
| Cloudinary | Imágenes que el usuario sube | Logo, portada, fotos de productos | Sí |
| *(Proveedor de IA del Copilot — nombre interno)* | Texto de la consulta de negocio (sin credenciales) | Copilot VZ — análisis | **No** — descrito genéricamente |
| *(Proveedor de búsquedas web — nombre interno)* | Consulta de búsqueda web | Copilot VZ — solo si el usuario activa la función | **No** — descrito genéricamente |
| Unsplash | Nada (descarga pública de imágenes de respaldo) | Fallback de fotos de productos | Sí |
| WhatsApp/Meta | El cliente envía su propio mensaje | Confirmación de pedidos | Sí |
| Gmail (SMTP) | Correos transaccionales | Notificaciones del servicio | No es necesario detallarlo |
| Better Stack (opcional, `SENTRY_DSN`) | Stack traces — con scrubbing de cookies/credenciales | Error tracking (desactivado si no hay DSN) | No es necesario detallarlo |

> **Nota Ley 1581:** la norma exige informar que hay encargados del tratamiento y su finalidad,
> no el nombre comercial de cada subprocesador. La descripción por categoría cumple el deber de
> información sin regalar el mapa de proveedores.

## 5. Datos del negocio

Identificación del operador incluida en: footer del hub `/legal`, footer del menú público,
footer de la landing y sección "Identificación del Responsable" de Términos:

- Operador: **Jhoan Rivera** — Velzia
- NIT: **100.275.521-5**
- Domicilio: **Riosucio, Caldas, Colombia**
- Contacto: `velziaoficial@gmail.com` · WhatsApp `+57 312 300 0887`

> Mantener sincronizados estos 4 puntos si cambian (son constantes en templates, no variables de
> entorno, porque el `.env` no debe contener datos públicos de negocio).

## 6. Derechos de autor de imágenes

- El usuario declara (Términos, sección "Contenido del Usuario") que tiene derechos de uso de lo
  que sube, y otorga licencia limitada de exhibición mientras su cuenta esté activa.
- Las imágenes de respaldo (`brand.ts → PRODUCT_IMAGE_BANK`) provienen de **Unsplash** (licencia
  Unsplash: uso comercial sin atribución). Los recursos se cargan desde `images.unsplash.com`
  (hotlink permitido por la licencia); alternativa futura: descargarlas a Cloudinary propio.
- Logo e íconos: Material Symbols (Apache 2.0), favicon propio.

## 7. Accesibilidad (WCAG 2.1 AA) — cambios aplicados

| Criterio | Hallazgo | Corrección |
|----------|----------|------------|
| 1.1.1 / 2.5.3 | `<img>` del cover con `alt=""` dentro de texto decorativo (ok), pero detalle de producto sin alt coherente | Alt se asigna dinámicamente con el nombre del producto (ya existía en JS); verificado |
| 1.3.1 | Botones de cantidad `+`/`−` y eliminar sin nombre accesible | `aria-label` en qty-minus/qty-plus/remove-item (carrito y detalle) |
| 1.3.1 | Búsqueda sin etiqueta | `role="search"` + `aria-label` en el input |
| 1.4.3 | `--ink-faint` #8A7B68 sobre card daba 4.2:1 | Cambiado a **#9C8D7A** (4.6:1). `--legal-text-muted` #a1a1aa → **#b3b3bd** (4.6:1) |
| 2.1.1 / 2.4.7 | Foco invisible en algunos controles | Regla global `:focus-visible` con outline de 2px accent en el menú Astro |
| 2.4.4 / 2.5.3 | Botones con etiquetas ambiguas ("Comprar ahora") | Renombrados: "Revisar y confirmar pedido", "Confirmar y enviar pedido", "Volver al menú" |
| 2.4.1 | Drawer legal sin estado ARIA | `aria-expanded`/`aria-controls` sincronizados en `legal.js` |
| 4.1.2 | Modales sin rol | `role="dialog"` + `aria-modal` + `aria-labelledby` en checkout, reservas, carrito y detalle |
| 4.1.3 | Errores y toasts silenciosos | `role="alert"` en mensajes de error; `role="status"` en toasts, éxito de reserva y de pedido |
| 2.4.3 | Foco al abrir modales | Foco inicial en primer campo (checkout), fecha (reservas), botón cerrar (carrito) |

**Pendiente conocido (riesgo bajo):** el slider por contraste sobre imágenes de fondo del menú usa
gradientes oscuros — verificado visualmente; re-auditar si cambia la paleta. Los placeholders de
tipos date/time heredan el estilo del navegador (no interfieren con el foco visible).

## 8. Riesgos documentados (DOFA-legal)

| # | Riesgo | Prob. | Impacto | Mitigación / accionable |
|---|--------|-------|---------|------------------------|
| 1 | Personería natural (persona natural, no SAS): el NIT del footer sugiere matrícula mercantil de persona natural. Responsabilidad ilimitada del operador. | Alta | Medio | Evaluar constituir SAS ante la Cámara de Comercio de Manizales antes de escalar; mientras tanto la cláusula de indemnidad cubre parcialmente |
| 2 | Tratamiento de datos de clientes de terceros (los restaurantes cargan datos de sus comensales): Velzia actúa como encargado, el restaurante como responsable | Media | Alto | Cláusula de responsabilidad del usuario en Términos (ya existe); agregar al onboarding del restaurante la obligación de obtener consentimiento de SUS clientes (pendiente de producto) |
| 3 | Facturación electrónica: los planes se facturan vía Mercado Pago; DIAN exige factura electrónica para ventas a empresas | Media | Alto | Revisar con contador: habilitar emisión de factura electrónica DIAN o documento equivalente (pendiente, fuera de alcance de software) |
| 4 | "Prueba Premium 60 días" sin tarjeta: sin riesgo de cobro (verificado en código) | Baja | Bajo | Ninguna acción |
| 5 | Mensajes de WhatsApp enviados por el cliente: Velzia no envía mensajes automáticos → no aplica régimen de mensajes comerciales; mantenerlo así | Baja | Bajo | Si se implementa notificación automática por WhatsApp, requerir opt-in del cliente |
| 6 | Expansión internacional: sin GDPR/LGPD cubierto | Baja | Alto | Bloquear lanzamiento en UE/Brasil hasta auditoría específica |
| 7 | Copilot VZ envía datos de negocio al proveedor de IA (procesados en servidores externos) | Media | Medio | Documentado genéricamente en políticas (sin nombrar proveedor — decisión del titular); sanitización anti-inyección activa (`message_handler.py`); verificar DPA del proveedor (pendiente) |
| 8 | Empleados registrados por el titular sin su consentimiento directo | Media | Medio | La carga legal es del titular (cláusula en Términos); revisar que el flujo de Equipo muestre aviso al titular (pendiente de producto, no bloqueante) |

## 9. Verificaciones realizadas (evidencia)

- `py_compile` de `app/routes/public.py`
- Build de Astro (valida sintaxis de componentes y TypeScript)
- `node --check` de `app/static/js/legal.js`
- Tests de pedidos públicos, idempotencia y trazabilidad (42/42) tras revertir el gate de consentimiento
- Cálculo de contraste WCAG de los tokens modificados (4.5:1+)
