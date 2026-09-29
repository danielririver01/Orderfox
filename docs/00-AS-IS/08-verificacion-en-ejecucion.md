# 08 — Verificación en ejecución de los flujos funcionales (AS-IS)

**Commit de referencia:** `cd96aa763c086dea93e4aede46191b9add9067fa` · **Fecha:** 2026-09-29

> **Para qué existe este documento.** El documento
> [04-flujos-funcionales.md](04-flujos-funcionales.md) reconstruyó las reglas de
> negocio **leyendo el código**. Este las somete a prueba **ejecutando el
> sistema**: se sembró un restaurante real, se arrancó la aplicación y se
> hicieron peticiones HTTP contra el flujo público.
>
> El resultado es que la mayoría de las reglas se confirman, pero **tres no se
> comportan como el código sugiere al leerlo**. Esas tres son hallazgos nuevos
> que no existían en la primera pasada.

---

## 1. Montaje del banco de pruebas

| Elemento | Valor |
|---|---|
| Base de datos | SQLite en `/tmp/asis.db`, creada desde cero con `db.create_all()` |
| Arranque | `python run.py` (el entrypoint real), puerto 5000 |
| Restaurante | «Ají & Brasa», slug `aji-brasa`, plan `crecimiento`, activo, abierto, suscripción a 20 días |
| Catálogo | 1 categoría, 2 productos (Bandeja paisa $32.000, Ajiaco $28.000), 1 mesa |
| Cliente | `curl` con tarro de cookies, para reproducir la sesión de un comensal |

`[EJECUTADO]` Ningún archivo del repositorio fue modificado para esta
verificación; el guion de siembra vive fuera del árbol (`/tmp`).

---

## 2. Resultados

### 2.1 Reglas que se confirman

| Regla | Prueba realizada | Resultado | Veredicto |
|---|---|---|---|
| **RN-01** Honeypot | Pedido con `user_secondary_email` relleno | **403** *«Actividad sospechosa detectada.»* | ✅ confirmada |
| **RN-03** Máx. 3 pedidos/min por IP | 4 pedidos seguidos con espera >3 s entre ellos | 1.º, 2.º y 3.º → **200**; 4.º y 5.º → **429** *«…espera unos minutos.»* | ✅ confirmada |
| **RN-04** Restaurante cerrado | `is_open = 0` | **403** *«Estamos cerrados en este momento.»* | ✅ confirmada |
| **RN-05** Suscripción no vigente | Vencida hace 90 días | **403** *«Pedidos temporalmente desactivados.»* | ✅ confirmada |
| **RN-10** Gracia de 5 días | Vencida hace 2 días | **200**, pedido `ORD-005` creado | ✅ confirmada |
| — Restaurante inactivo | `is_active = 0` | **403** | ✅ confirmada |
| **RN-07** Idempotencia | Mismo `idempotency_key` dos veces | Ambas **200** con **el mismo `ORD-001`**; un solo pedido en la base | ✅ confirmada |
| **RN-07** (traza) | ídem | **Un solo** `order_created` en `order_events`: el reintento no duplica traza ni notificación | ✅ confirmada |
| **RN-08** Copia de nombre y precio | Pedido de 2×32.000 + 1×28.000 | `total = 92000`, nombres copiados en `order_items` | ✅ confirmada |
| **RN-02** Tiempo mínimo de 3 s | `init-checkout` e inmediatamente el pedido | **429** *«¡Uy, vas muy rápido!»* | ⚠️ funciona **solo si se llamó antes a `init-checkout`** — ver R-17 |

### 2.2 Máquina de estados de pedidos

`[EJECUTADO]` Matriz completa obtenida llamando a
`OrderService.validate_status_transition` sobre los 25 pares posibles:

```
        desde \ hacia │  pending  │ confirmed │ delivered │ cancelled │  expired
        ──────────────┼───────────┼───────────┼───────────┼───────────┼──────────
              pending │     ·     │     ✔     │     ·     │     ✔     │     ✔
            confirmed │     ·     │     ·     │     ✔     │     ✔     │     ·
            delivered │     ·     │     ·     │     ·     │     ✔     │     ·
            cancelled │     ✔     │     ·     │     ·     │     ·     │     ·
              expired │     ·     │     ·     │     ·     │     ·     │     ·
```

Confirma las observaciones del documento 04:

- `delivered → cancelled` está **permitida**: un pedido entregado se puede cancelar (**O-01**).
- `cancelled → pending` está **permitida**: un pedido cancelado se puede reabrir (**O-02**).
- `expired` es **terminal**: no admite ninguna salida.
- `pending → delivered` está **prohibida**: no se puede saltar la confirmación.
- `'completed'` **no es un estado válido**, lo que confirma el defecto
  [R-06](06-riesgos-y-deuda-tecnica.md#r-06) del rate limiter.

### 2.3 Contrato entre el frontend Astro y Flask

`[EJECUTADO]` Endpoints que el frontend invoca, extraídos de `astro/src/` y
contrastados con el mapa de rutas real:

| Llamada desde Astro | Ruta Flask | ¿Existe? |
|---|---|---|
| `{API_BASE}/menu/{slug}` | `GET /api/public/menu/<slug>` | ✅ **200** verificado |
| `{API_BASE}/menu/{slug}/categoria/{id}` | `GET /api/public/menu/<slug>/categoria/<id>` | ✅ |
| `{API_BASE}/menu/{slug}/novedades` | `GET /api/public/menu/<slug>/novedades` | ✅ |
| `/menu/api/order` | `POST /menu/api/order` | ✅ **200** verificado |
| `/menu/api/reservations` | `POST /menu/api/reservations` | ✅ |
| `/menu/api/reservations/check` | `POST /menu/api/reservations/check` | ✅ |
| `/menu/api/reservations/config` | `GET /menu/api/reservations/config` | ✅ |
| `/menu/api/reservations/arrival` | `POST /menu/api/reservations/arrival` | ✅ |
| **`/menu/api/init-checkout`** | existe en Flask | ❌ **Astro nunca la llama** — ver R-17 |

`[CÓDIGO]` Dos observaciones sobre la configuración del contrato:

1. `astro/src/lib/api.ts:9` fija como valor por defecto la URL **de producción**:
   `PUBLIC_MENU_API_URL || 'https://velzia.shop/api/public'`. Sin esa variable de
   entorno, un entorno de desarrollo consultaría datos de producción.
2. El proxy de desarrollo (`astro/astro.config.mjs:16-20`) solo cubre
   `/menu/api`. Las llamadas a `/api/public/*` **no pasan por el proxy** y van
   directas a `API_BASE`.

---

## 3. Hallazgos nuevos surgidos de la ejecución

<a id="r-17"></a>
### 🔴 R-17 — La protección anti-bot de 3 segundos está inerte en la arquitectura actual

**Estado:** `[EJECUTADO]` — reproducido.

**Cómo funciona la regla.** `app/routes/public.py:20-24` expone
`POST /menu/api/init-checkout`, que guarda `session['checkout_start_time']`.
Al crear el pedido se comprueba:

```python
start_time = session.get('checkout_start_time', 0)
if time.time() - start_time < 3.0:
    return jsonify({...}), 429
```

**El fallo.** Si nunca se llamó a `init-checkout`, `start_time` vale **0**, y
`time.time() - 0` es el tiempo Unix actual (≈ 1.79 × 10⁹), que siempre es mayor
que 3. **La comprobación pasa de forma trivial.**

**Prueba en ejecución** — sesión nueva, sin cookie previa, sin `init-checkout`
y sin ninguna espera:

```
POST /menu/api/order  →  HTTP 200
{"customer_name": "Bot sin init", "order_number": "ORD-003", "success": true}
```

**Por qué esto no es teórico.** Se buscó quién llama a `init-checkout`:

| Origen | ¿La llama? |
|---|---|
| `astro/` (el menú público actual, **el que usan los comensales**) | ❌ **0 coincidencias en todo el frontend** |
| `app/static/js/cart.js:267` | ✅ pero es del **menú legacy** |
| `app/static/js/public/menu-public.js:446` | ✅ pero es del **menú legacy** |

`[EJECUTADO]` Ninguna plantilla de `app/template/` carga esos dos archivos, y
`GET /menu/<slug>` redirige al frontend Astro. Es decir: **el menú que usan hoy
los comensales nunca llama a `init-checkout`**, de modo que todos los pedidos
reales pasan la comprobación sin esperar nada.

**Agravante arquitectónico.** `[INFERIDO]` Aunque Astro la llamase, la marca de
tiempo vive en la **sesión de Flask**. Astro se sirve desde otro origen
(`menu.velzia.shop` frente al dominio de la API), así que la cookie de sesión no
viajaría de forma fiable entre ambos. La regla, tal como está diseñada, no puede
funcionar con el frontend desacoplado.

**Qué queda en pie.** El honeypot (RN-01) y el límite de 3 pedidos por minuto
(RN-03) **sí funcionan**, y ambos se verificaron. La defensa en profundidad pasa
de tres capas a dos.

**Efecto colateral:** `cart.js` (495 líneas) y `menu-public.js` (659 líneas)
parecen ser código muerto del menú anterior — 1.154 líneas. Refuerza
[R-11](06-riesgos-y-deuda-tecnica.md#r-11).

---

<a id="r-18"></a>
### 🔴 R-18 — `/menu/<slug>` redirige a una URL con «None» y los valores por defecto de la configuración son código muerto

**Estado:** `[EJECUTADO]` — reproducido.

**Síntoma.** Con la aplicación arrancada sin `ASTRO_BASE_URL`:

```
GET /menu/aji-brasa        →  302  →  http://127.0.0.1:5000/menu/None/aji-brasa/
GET /menu/None/aji-brasa/  →  404
```

**Causa raíz.** `app/routes/public.py:40`:

```python
base_url = current_app.config.get('ASTRO_BASE_URL',
               current_app.config.get('BASE_URL', request.url_root.rstrip('/')))
```

`settings.py:50` define `ASTRO_BASE_URL = os.environ.get('ASTRO_BASE_URL')`, que
vale **`None`** cuando la variable de entorno no existe. Como la clave **existe
en la configuración** (aunque con valor `None`), `dict.get(clave, defecto)`
devuelve `None` y **el valor por defecto nunca se aplica**.

```
Config.ASTRO_BASE_URL = None
d.get("ASTRO_BASE_URL", d.get("BASE_URL")) = None
```

Toda la cascada de respaldo — `BASE_URL` y luego `request.url_root` — es
**inalcanzable**. Se escribió precisamente para evitar este caso y no puede
ejecutarse nunca.

**Impacto.** Los códigos QR impresos en las mesas apuntan a `/menu/<slug>`. En
un despliegue donde falte `ASTRO_BASE_URL`, **todos los QR llevan a un 404**.

**Alcance del patrón.** `[EJECUTADO]` **19 claves** de configuración valen `None`
cuando falta su variable de entorno: `ASTRO_BASE_URL`, `BASE_URL`,
`CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, `CLERK_WEBHOOK_SECRET`,
`CLOUDINARY_*` (3), `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`, `MAIL_*` (3), `MP_*` (3),
`SENTRY_DSN`, `SERVICE_API_KEY`, `UNSPLASH_ACCESS_KEY`.

Hay **14 puntos** que confían en un valor por defecto que nunca se aplicará:

| Ubicación | Valor por defecto inerte | Consecuencia si falta el entorno |
|---|---|---|
| `app/routes/public.py:40` | cascada `BASE_URL` → `url_root` | **404 en todos los QR** *(reproducido)* |
| `app/routes/api_auth.py:78` | `'https://velzia.co'` | URL base nula en la respuesta |
| `app/routes/api_auth.py:123` | `'https://velzia.co'` | **emisor (`iss`) del JWT a `None`** |
| `app/services/auth_service.py:432, 467, 519` | `'https://velzia.co'` | ídem, en emisión y validación de JWT |
| `app/routes/auth.py:435` | `request.url_root` | URL de retorno de Mercado Pago nula |
| `app/routes/tokens.py:132` | `request.url_root` | URL de retorno de la recarga nula |
| `app/services/reminder_service.py:35` | `''` | enlaces `None/...` en los correos |
| `app/services/reward_service.py:232` | `''` | enlaces `None/...` en las recompensas |
| `app/services/auth_service.py:268` | `''` | ídem |
| `app/routes/rewards.py:112` | `''` | lista de orígenes permitidos a `None` |

**El código ya conoce la solución.** Cuatro sitios usan el patrón correcto, con
`or` en lugar del segundo argumento de `get`:

```python
# app/routes/tables.py:38 · dashboard.py:35 · api_dashboard.py:23
base = current_app.config.get('ASTRO_BASE_URL') or current_app.config.get('BASE_URL', '')
```

La inconsistencia entre ambos patrones es lo que convierte esto en una trampa:
la generación del QR (`tables.py`) construye bien la URL, pero la redirección de
ese mismo QR (`public.py`) la construye mal.

---

<a id="r-19"></a>
### 🟡 R-19 — El contador diario de pedidos gasta un número en cada reintento idempotente

**Estado:** `[EJECUTADO]` — reproducido.

Tras la sesión de pruebas:

| Dato | Valor |
|---|---|
| Pedidos realmente creados | **3** (`ORD-001`, `ORD-003`, `ORD-004`) |
| Contador del día (`order_counters.counter`) | **4** |
| Números desperdiciados | **1** |

**Causa.** `app/routes/public.py` llama a
`OrderService.generate_order_number(restaurant.id)` **antes** de invocar a
`create_order_from_cart`, que es donde se comprueba la idempotencia. En un
reintento, el número ya se consumió y se descarta.

**Impacto.** Bajo, pero real: la numeración que ve el restaurante tiene huecos
(`ORD-001`, `ORD-003`, …). Para un dueño que cuadra caja, un salto en la
numeración parece un pedido perdido o borrado. También ocurre con cualquier
creación fallida posterior a ese punto.

---

<a id="r-20"></a>
### 🟡 R-20 — Un carrito con formato incorrecto devuelve 500 en lugar de 400

**Estado:** `[EJECUTADO]` — reproducido.

Enviando `cart` como lista en vez de diccionario (el formato esperado es
`{product_id: {quantity, extras}}`):

```
POST /menu/api/order  →  HTTP 500
{"error": "Error al crear el pedido. Inténtalo de nuevo.", "success": false}

ERROR:app:Error creating order from cart: 'list' object has no attribute 'keys'
```

Un error de formato del cliente se contabiliza como fallo del servidor. Además
de ser incorrecto semánticamente, contamina las métricas de error y, con Sentry
activo, genera ruido de alertas por peticiones malformadas.

---

## 4. Qué cambia respecto al documento 04

| Reglas | Antes | Ahora |
|---|---|---|
| RN-01, RN-03, RN-04, RN-05, RN-07, RN-08, RN-10 | `[CÓDIGO]` | **`[EJECUTADO]`** |
| O-01, O-02 (transiciones de estado) | `[CÓDIGO]` | **`[EJECUTADO]`** |
| RN-02 (tiempo mínimo de 3 s) | `[CÓDIGO]` — se daba por activa | **`[EJECUTADO]` — inerte con el frontend actual (R-17)** |

**Ninguna regla verificada resultó ser falsa.** Lo que cambió es el alcance de
una de ellas: RN-02 está implementada y funciona, pero **el frontend actual no
la activa**.

---

## 5. Lo que sigue sin verificarse

| Flujo | Motivo |
|---|---|
| Pago con Mercado Pago de extremo a extremo | Requiere credenciales reales y webhooks entrantes |
| Alta con Clerk | Requiere credenciales reales |
| Copilot VZ con respuesta real | Requiere clave de DeepSeek |
| Notificación ntfy | Requiere un tema configurado y red saliente |
| Frontend Astro en ejecución | No se instalaron sus dependencias; el contrato se verificó por contraste de rutas |
| Portal de empleados y caja | Requieren sesión autenticada; verificables en una segunda pasada |
| Reservas de extremo a extremo | Ídem; las reglas están documentadas por lectura en el documento 04 |
