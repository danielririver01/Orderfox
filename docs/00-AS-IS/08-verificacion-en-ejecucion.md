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

---

# Segunda pasada — portal de empleados, caja, reservas y frontend Astro

**Fecha:** 2026-09-29 · Mismo commit. Banco de pruebas ampliado: restaurante
plan Élite, dueño, **cajero (PIN 4739)**, **mesero (PIN 8261)**, 2 mesas
(capacidad 4 y 2), 3 pedidos pagados (efectivo, Nequi, tarjeta) y reservas
habilitadas.

> Esta pasada **corrige un error del documento 04**. Conviene leer primero
> la sección 7.

## 6. Resultados de la segunda pasada

### 6.1 Roles y portal de empleados

| Prueba | Resultado | Veredicto |
|---|---|---|
| Login del cajero con PIN correcto | **302** → `/empleado/<slug>/caja` | ✅ |
| Login del mesero con PIN correcto | **302** → `/empleado/<slug>/pedidos` | ✅ |
| Cajero → `/empleado/<slug>/caja` | **200** | ✅ |
| Cajero → `/empleado/<slug>/pedidos` | **302** (bloqueado) | ✅ |
| Cajero → `/dashboard/` y `/dashboard/equipo` | **302** (bloqueado) | ✅ **RN-61 confirmada** |
| Mesero → `/empleado/<slug>/pedidos` | **200** | ✅ |
| Mesero → `/empleado/<slug>/caja` y `/cash-register/` | **302** (bloqueado) | ✅ |
| PIN débil al crear empleado (`1111`) | Rechazado: *«Este PIN es demasiado fácil de adivinar»* | ✅ regla no documentada antes |

`[EJECUTADO]` **Regla nueva encontrada:** el PIN debe ser exactamente 4 dígitos
y no estar en una lista negra de PIN triviales
(`app/services/employee_service.py:57-63`).

### 6.2 Centro de caja

| Prueba | Resultado | Veredicto |
|---|---|---|
| **Dueño** cierra caja del día | **200**, cierre creado | ✅ |
| **Cajero** intenta cerrar caja | **403 forbidden** | ⚠️ **contradice RN-54** — ver §7 |
| **Mesero** intenta cerrar caja | Bloqueado (no alcanza ni la pantalla) | ⚠️ ídem |
| Segundo cierre del **mismo rango** | **409** *«Ya cerraste caja para el periodo 28/09/2026. Este periodo no se puede cerrar dos veces.»* | ✅ **RN-51 y RN-52 confirmadas** |

### 6.3 Reservas de extremo a extremo

| Prueba | Resultado | Veredicto |
|---|---|---|
| `GET /menu/api/reservations/config` | `enabled: true`, `min_notice_hours: 2`, `max_advance_days: 30`, **`max_party_size: 100`** | ✅ |
| Disponibilidad antes de reservar (19:00, 4 pers.) | `available: true` | ✅ |
| Crear reserva | **201**, estado `pending`, mesa 1 asignada | ✅ |
| Antelación < 2 h | **400** *«Las reservas requieren al menos 2 horas de anticipación»* | ✅ **RN-45** |
| Antelación > 30 días | **400** *«Solo se puede reservar con máximo 30 días de anticipación»* | ✅ **RN-45** |
| 200 personas | **400** *«El número de personas debe estar entre 1 y 100»* | ✅ |
| Honeypot relleno | **403** *«Actividad sospechosa detectada.»* | ✅ **RN-48** |

**Fórmula de ocupación (RN-44) verificada al minuto.** Con una reserva a las
19:00 y `service_duration_min = 90` + `cleanup_buffer_min = 15`, la mesa debe
liberarse exactamente a las **20:45**:

| Hora consultada | ¿Disponible? |
|---|---|
| 19:30 | ❌ no |
| 20:30 | ❌ no |
| **20:45** | ✅ **sí** |
| 21:00 | ✅ sí |

`[EJECUTADO]` **Matiz no documentado antes:** una reserva en estado `pending`
—es decir, **sin que el restaurante la haya confirmado**— ya tiene mesa
asignada y **bloquea la disponibilidad**. Una solicitud sin aprobar ocupa la
mesa igual que una confirmada.

### 6.4 Frontend Astro en ejecución

`[EJECUTADO]` `npm install` (275 paquetes, 12 s) y `astro dev` arrancaron sin
errores: **Astro v7.0.7 listo en 1,76 s**.

| Prueba | Resultado |
|---|---|
| `GET /` (landing) | **200** |
| `GET /aji-brasa/` (menú) | **200**, 81 KB de HTML |
| Datos reales de Flask en el HTML | ✅ nombre del restaurante, categoría «Platos», producto «Bandeja paisa», precio `32.000` |
| `GET /no-existe/` | **200** ⚠️ — ver [R-22](#r-22) |

**El contrato Astro ↔ Flask funciona de extremo a extremo.** El menú público se
renderiza en el servidor con datos que vienen de `GET /api/public/menu/<slug>`.

---

## 7. Corrección a un error del documento 04

<a id="correccion-rn-54"></a>
### ❗ RN-54 era incorrecta: **solo el dueño puede cerrar la caja**

**Qué documenté (mal).** En [04-flujos-funcionales.md](04-flujos-funcionales.md)
escribí, como RN-54 y como observación O-03, que *«cualquier usuario del
restaurante puede cerrar caja, incluido un mesero»*, y lo elevé a decisión
pendiente **D-08**.

**De dónde salió el error.** Me apoyé en el docstring del modelo
(`app/models/cash.py:11-13`):

> *«`closed_by` queda registrado para soportar roles (cajero/admin) en el
> futuro; hoy todos los usuarios del restaurante pueden cerrar caja.»*

**Qué dice el código que se ejecuta.** `app/routes/cash_register.py:143-146`:

```python
@cash_register_bp.route('/close', methods=['POST'])
@require_auth
@require_active
@require_role('owner')
def close():
```

**Comprobación en ejecución:**

```
DUEÑO   POST /cash-register/close -> HTTP 200  (cierre creado)
CAJERO  POST /cash-register/close -> HTTP 403  forbidden
MESERO  POST /cash-register/close -> bloqueado antes de llegar
```

`/cash-register/api/summary` también es `@require_role('owner')`. El cajero solo
alcanza la portada `/cash-register/` (`@require_role('owner', 'cashier')`).

**Lecciones que deja este error:**

1. Un docstring **no es evidencia de comportamiento**. Debí clasificar RN-54
   como `[INFERIDO]`, no como `[CÓDIGO]`.
2. La contradicción real no es de negocio sino documental: el docstring del
   modelo está obsoleto respecto al decorador de la ruta. Se registra como
   **C-08**.
3. **D-08 cambia de sentido**: ya no es «quién puede cerrar la caja» (la
   respuesta es: solo el dueño), sino «¿debería poder también el cajero?».

---

## 8. Hallazgos nuevos de la segunda pasada

<a id="r-21"></a>
### 🔴 R-21 — Cinco PIN erróneos bloquean a **toda la plantilla** durante 30 minutos

**Estado:** `[EJECUTADO]` — reproducido.

**Qué documenté antes (RN-63):** *«5 PIN fallidos ⇒ bloqueo de 30 minutos»*,
dando a entender que el bloqueo es **del empleado**. No lo es.

**Qué ocurre en realidad.** `EmployeeService.authenticate_employee`
(`app/services/employee_service.py:203-209`) incrementa
`failed_pin_attempts` de **todos los empleados activos** en cada intento
fallido, porque no sabe a quién iba dirigido el PIN:

```python
for candidate in participants:
    candidate.failed_pin_attempts = (candidate.failed_pin_attempts or 0) + 1
    if candidate.failed_pin_attempts >= MAX_PIN_ATTEMPTS:
        candidate.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
```

**Prueba en ejecución.** Tras **dos** intentos con un PIN inexistente, ambos
empleados subieron a la vez:

```
Marta Cajera   cashier  intentos=2
Luis Mesero    waiter   intentos=2
```

Llevando el contador a 4 y lanzando el quinto fallo:

```
Marta Cajera   cashier  intentos=5  bloqueado_hasta=2026-09-29 03:36:22
Luis Mesero    waiter   intentos=5  bloqueado_hasta=2026-09-29 03:36:22

Cajero con su PIN CORRECTO (4739) -> HTTP 401
   «Cuenta bloqueada por intentos fallidos. Espera 30 min…»
Mesero con su PIN CORRECTO (8261) -> HTTP 401
   «Cuenta bloqueada por intentos fallidos. Espera 30 min…»
```

**El mesero nunca falló un PIN y queda igualmente fuera.**

**Impacto.** `/empleado/<slug>` es una URL **pública** y el `slug` es el mismo
que aparece en el menú y en los QR de las mesas. Cualquiera que lo conozca
puede dejar sin acceso al portal a todo el personal durante 30 minutos. En hora
punta eso es una interrupción de servicio, no una molestia.

**Atenuantes reales:**
- La ruta tiene su propio límite: `@limiter.limit("5 per minute; 20 per hour")`
  (`app/routes/employees.py:258`).
- El dueño puede desbloquear desde *Equipo* (`POST /dashboard/equipo/<id>/desbloquear`).

**Por qué los atenuantes no cierran el hueco:**
- El límite es **por IP** y el almacén es `memory://`
  ([R-08](06-riesgos-y-deuda-tecnica.md#r-08)): se reinicia con cada despliegue
  y no se comparte entre los 3 workers de gunicorn.
- 20 intentos por hora siguen bastando: solo hacen falta **5**.
- El dueño puede desbloquear, pero necesita entrar al panel desde otro
  dispositivo mientras el local está en servicio.

**El diseño es deliberado** —el docstring explica que se castiga a todos porque
«el atacante no sabe a qué empleado ataca»— pero **la consecuencia operativa no
parece haberse evaluado**. Es una decisión de negocio a validar, no
necesariamente un bug.

`[EJECUTADO]` **Efecto secundario de usabilidad:** el límite de 5/minuto cuenta
**GET y POST del mismo endpoint**. Cargar la página ya consume cuota, así que un
empleado que se equivoque dos veces puede recibir un **429** antes de agotar sus
intentos de PIN.

---

<a id="r-22"></a>
### 🟠 R-22 — Astro responde HTTP 200 cuando el menú no existe o la API está caída

**Estado:** `[EJECUTADO]` — reproducido.

```
GET http://localhost:4321/no-existe/   ->  HTTP 200   (61 KB)
<title>Error al cargar el menú</title>
```

Mientras tanto, Flask sí responde correctamente:

```
GET /api/public/menu/no-existe  ->  HTTP 404
```

**Causa.** `astro/src/pages/[slug]/index.astro:33-42` captura el error de
`fetchMenu` y renderiza una página de error, pero **no fija el código de
estado**:

```javascript
try {
  const response = await fetchMenu(slug);
  ...
} catch (e) {
  console.error('fetchMenu error:', e);
}
```

**Impacto.** El problema no es el slug inexistente, sino que **es el mismo
camino de código para una caída de la API**:

- Si Flask deja de responder, **todos** los menús devuelven `200 OK` con el
  texto «Error al cargar el menú».
- Cualquier monitor que compruebe el estado HTTP **verá el sistema sano
  durante una caída total del menú público**. Y no hay endpoint de salud
  ([R-15](06-riesgos-y-deuda-tecnica.md#r-15)) que sirva de alternativa.
- Los buscadores indexan páginas de error de restaurantes que no existen.

---

## 9. Lo que sigue sin verificarse

| Flujo | Motivo |
|---|---|
| Pago con Mercado Pago de extremo a extremo | Requiere credenciales reales y webhooks entrantes |
| Alta con Clerk | Requiere credenciales reales |
| Copilot VZ con respuesta real | Requiere clave de DeepSeek |
| Notificación ntfy | Requiere un tema configurado y red saliente |
| Recompensas y cupones de extremo a extremo | Dependen de un pago aprobado de Mercado Pago |
| Fotos automáticas de productos | Requieren claves de Unsplash y Gemini |
| Comportamiento con MySQL/PostgreSQL | No hay motor disponible; todo se verificó con SQLite |

**Ya no queda nada verificable sin credenciales externas.** Los flujos de
pedidos, reservas, caja, roles y el frontend público están comprobados en
ejecución; el resto depende de terceros.
