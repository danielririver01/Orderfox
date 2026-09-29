# 04 — Flujos funcionales y reglas de negocio (AS-IS)

**Commit de referencia:** `cd96aa763c086dea93e4aede46191b9add9067fa` · **Fecha:** 2026-09-29

> **Aviso importante.** Esta reconstrucción se hizo leyendo el código y ejecutando
> el sistema. **Describe qué ocurre, no por qué.** Las intenciones de negocio
> detrás de cada regla siguen sin confirmar: todo lo que aparece aquí como regla
> está en estado `[CÓDIGO]` o `[INFERIDO]`, **nunca** `[CONFIRMADO]`.

---

## 1. Actores identificados

| Actor | Cómo entra | Evidencia |
|---|---|---|
| **Visitante** | Landing pública (Astro) y `/planes` | `astro/src/pages/index.astro`, `app/routes/auth.py:228` |
| **Comensal** | Escanea el QR → menú público. Sin cuenta | `app/routes/public.py`, `astro/src/pages/[slug]/index.astro` |
| **Dueño (`owner`)** | `/login` + Clerk | `app/routes/auth.py:163`, `app/models/core.py:122` |
| **Cajero (`cashier`)** | `/empleado/<slug>` con PIN | `app/routes/employees.py` |
| **Mesero (`waiter`)** | `/empleado/<slug>` con PIN | `app/routes/employees.py` |
| **Sistema (APScheduler)** | 7 tareas programadas | `app/tasks.py` |
| **Scanner IA** | Servidor a servidor con `SERVICE_API_KEY` | `app/extensions.py:14-20` |
| **Mercado Pago** | Webhooks firmados (HMAC) | `app/utils/mp_webhook.py` |
| **Clerk** | Webhooks firmados (Svix) | `app/routes/api_webhooks.py` |

---

## 2. Catálogo de funciones

### 2.1 Alta, autenticación y suscripción

| Función | Usuario | Entrada | Resultado | Evidencia | Clasif. |
|---|---|---|---|---|---|
| Ver planes y precios | Visitante | — | 3 planes + prueba | `app/routes/auth.py:228` · `[EJECUTADO]` `GET /planes` → **200** | `[EJECUTADO]` |
| Guardar plan elegido | Visitante | `plan_key` | Plan en sesión | `POST /api/save-plan-selection` · `app/routes/auth.py:264` | `[CÓDIGO]` |
| Registrarse | Visitante | Alta en Clerk | Usuario en Clerk | `app/routes/auth.py:245` | `[CÓDIGO]` |
| Sincronizar con Clerk | Dueño | Sesión Clerk | Fila en `users` con `clerk_id`; decide destino | `POST /api/sync-clerk` · `app/routes/auth.py:30-157` | `[CÓDIGO]` |
| Crear restaurante | Dueño | Nombre, slug, WhatsApp, tipo de cocina | Fila en `restaurants` + `has_used_trial=True` | `/setup-account` · `app/routes/auth.py:292` | `[CÓDIGO]` |
| Iniciar sesión | Dueño | Correo y contraseña | `session['user_id']` | `app/routes/auth.py:163` · `[EJECUTADO]` `GET /login` → **200** | `[EJECUTADO]` |
| Cerrar sesión | Dueño | — | Sesión limpia, caché desactivada | `app/routes/auth.py:558` | `[CÓDIGO]` |
| Pagar suscripción | Dueño | Plan | Redirección al checkout de Mercado Pago | `app/routes/auth.py:411-452` | `[CÓDIGO]` |
| Recibir el resultado del pago | Mercado Pago | `status`, `external_reference` | Suscripción renovada + recompensa | `/payment-callback` · `app/routes/auth.py:455` | `[CÓDIGO]` |
| Webhook de pago (actual) | Mercado Pago | Cuerpo + `x-signature` | Pago acreditado (idempotente) | `POST /api/v1/webhooks/mercadopago` · `app/routes/api_webhooks.py:136` | `[CÓDIGO]` |
| Webhook de pago (**legacy**) | Mercado Pago | IPN | Igual que el anterior | `POST /webhook` · `app/routes/auth.py:508` | `[CÓDIGO]` duplicado |
| Renovar | Dueño | — | Vuelve al flujo de pago | `/renew` · `app/routes/auth.py:377` | `[CÓDIGO]` |
| Cancelar cuenta (web) | Dueño | Confirmación | `subscription_state='cancellation_pending'`, conserva acceso | `POST /dashboard/cancel-account` · prueba `test_account_deletion.py:25` | `[EJECUTADO]` ✅ |
| Cancelar cuenta (API) | Dueño | `{"confirmation":"CANCELAR"}` | **HTTP 500, no cancela nada** | `POST /api/dashboard/cancel-account` · `app/routes/api_dashboard.py:215` | `[EJECUTADO]` ❌ **rota** ([R-02](06-riesgos-y-deuda-tecnica.md#r-02)) |
| Reactivar cuenta | Dueño | — | `dormant` → activo | `POST /dashboard/resume-subscription` | `[CÓDIGO]` |

### 2.2 Catálogo

| Función | Usuario | Entrada | Resultado | Evidencia | Clasif. |
|---|---|---|---|---|---|
| Crear categoría | Dueño | Nombre, descripción, orden | Fila en `categories` | `app/routes/categories.py` + `category_service.py` | `[CÓDIGO]` |
| Reordenar categorías | Dueño | Nuevo `sort_order` | Orden del menú actualizado | `PATCH /categories/<id>/reorder` | `[CÓDIGO]` |
| Activar/desactivar categoría | Dueño | — | `is_active` invertido | `PATCH /categories/<id>/toggle` | `[CÓDIGO]` |
| Crear producto | Dueño | Nombre, precio, categoría, imagen | Fila en `products` **si no se supera el límite del plan** | `product_service.py` + `check_product_limit` | `[CÓDIGO]` |
| Subir imagen | Dueño | Archivo ≤ 16 MB | URL de Cloudinary | `image_handler.py`; `MAX_CONTENT_LENGTH` en `settings.py:56` | `[CÓDIGO]` |
| Foto automática | Sistema | Producto sin imagen | Imagen de Unsplash/Gemini/biblioteca local | `auto_photo_service.py` (481) | `[CÓDIGO]` |
| Cambiar la foto sugerida | Dueño | — | Otra del `suggested_image_pool` | `POST /products/<id>/swap-photo` | `[CÓDIGO]` |
| Crear modificador | Dueño | Nombre, precio extra | Fila en `modifiers` | `app/routes/products.py` | `[CÓDIGO]` **solo Élite** |
| Crear mesa | Dueño | Nombre, capacidad | Fila en `tables` | `table_service.py` | `[CÓDIGO]` |
| Generar QR de mesa | Dueño | — | PNG descargable | `qr_service.py`; `/dashboard/tables/<id>/qr` | `[CÓDIGO]` **no en plan Emprendedor** |
| Generar QR del menú | Dueño | — | PNG del menú del local | `/dashboard/menu/<slug>/qr` | `[CÓDIGO]` |

### 2.3 Pedidos

| Función | Usuario | Entrada | Resultado | Evidencia | Clasif. |
|---|---|---|---|---|---|
| Ver el menú público | Comensal | `slug` (+ `table_id`) | Menú del restaurante | `GET /menu/<slug>` → 302 a Astro · `app/routes/public.py:26` | `[EJECUTADO]` |
| Consultar el menú por API | Comensal/Astro | `slug` | JSON del menú | `GET /api/public/menu/<slug>` · `[EJECUTADO]` slug inexistente → **404** | `[EJECUTADO]` |
| Iniciar checkout | Comensal | — | Marca de tiempo en sesión (anti-bot) | `POST /menu/api/init-checkout` · `app/routes/public.py:20-24` | `[CÓDIGO]` |
| **Crear pedido** | Comensal | Carrito, nombre, teléfono, `idempotency_key` | Pedido `pending` + notificación ntfy | `POST /menu/api/order` · `app/routes/public.py` | `[CÓDIGO]` |
| Crear pedido (panel) | Dueño/Mesero | Productos | Pedido `pending` | `POST /orders/create` | `[CÓDIGO]` |
| Cambiar el estado | Dueño/Empleado | Nuevo estado | Transición validada + `OrderEvent` | `PATCH /orders/<id>/status` · `order_service.py:206` | `[CÓDIGO]` |
| Registrar pago | Cajero/Dueño | Método, importe recibido | `paid_at`, `change_due` | `POST /orders/<id>/payment` · `order_service.py:530` | `[CÓDIGO]` |
| Cancelar pedido | Dueño/Empleado | — | `status='cancelled'` | `POST /orders/<id>/cancel` | `[CÓDIGO]` |
| Imprimir recibo | Cajero | — | Vista imprimible | `GET /orders/<id>/receipt` | `[CÓDIGO]` |
| Ver pedidos en tiempo real | Dueño | Sondeo | Lista actualizada | `GET /dashboard/api/check-orders` | `[INFERIDO]` es *polling*, no WebSocket |
| Expirar pedidos | Sistema | Cada hora | `pending` → `expired` | `app/tasks.py:124-166` | `[CÓDIGO]` |

### 2.4 Reservas

| Función | Usuario | Entrada | Resultado | Evidencia | Clasif. |
|---|---|---|---|---|---|
| Consultar configuración | Comensal | `slug` | Si acepta reservas, antelación, máximo de personas | `GET /menu/api/reservations/config` | `[CÓDIGO]` |
| Comprobar disponibilidad | Comensal | Fecha, hora, personas | `available: true/false` | `POST /menu/api/reservations/check` | `[CÓDIGO]` |
| Solicitar reserva | Comensal | Fecha, hora, personas, nombre, WhatsApp | Reserva `pending` + ntfy | `POST /menu/api/reservations` · `app/routes/public.py:104-141` | `[CÓDIGO]` |
| Confirmar / rechazar | Dueño | — | `confirmed` / `rejected` + motivo | `PATCH /api/reservations/<id>/confirm` \| `/reject` | `[CÓDIGO]` |
| Marcar completada / no-show | Dueño | — | `completed` / `no_show` | `PATCH .../complete` \| `/no-show` | `[CÓDIGO]` |
| Ver calendario del día | Dueño | Fecha | Ocupación por mesa | `GET /api/reservations/calendar` | `[CÓDIGO]` |
| Ajustar parámetros | Dueño | Duración, margen, antelación | `reservation_settings` | `GET/PATCH /api/reservations/settings` | `[CÓDIGO]` |
| Saludo al llegar (QR) | Comensal | `table_id` | Si hay reserva confirmada hoy → `completed` + saludo | `POST /menu/api/reservations/arrival` · `app/routes/public.py:146-165` | `[CÓDIGO]` |
| Recordatorio automático | Sistema | Cada 30 min | ntfy una sola vez (`reminder_sent`) | `app/tasks.py:324-330` | `[CÓDIGO]` |

### 2.5 Caja

| Función | Usuario | Entrada | Resultado | Evidencia | Clasif. |
|---|---|---|---|---|---|
| Ver resumen del turno | Cajero/Dueño | Rango | Totales por método de pago | `GET /cash-register/api/summary` | `[CÓDIGO]` |
| Ver pedidos sin cobrar | Cajero | — | Lista de pendientes | `GET /cash-register/api/pending` | `[CÓDIGO]` |
| **Cerrar caja** | Cajero/Dueño | Rango | `CashRegister` con la instantánea | `POST /cash-register/close` · `cash_register_service.py` | `[CÓDIGO]` |
| Imprimir cierre | Cajero | `close_id` | Vista imprimible | `GET /cash-register/close/<id>/print` | `[CÓDIGO]` |
| Preguntar al copiloto de caja | Cajero/Dueño | Pregunta | Respuesta del LLM | `POST /cash-register/copilot/conversations/<cid>/messages` | `[CÓDIGO]` |

### 2.6 Copilot VZ

| Función | Usuario | Entrada | Resultado | Evidencia | Clasif. |
|---|---|---|---|---|---|
| Abrir el copiloto | Dueño | — | Interfaz de chat | `GET /insights/` · `[EJECUTADO]` sin sesión → **302 a `/login`** | `[EJECUTADO]` |
| Crear conversación | Dueño | Título | `CopilotConversation` | `POST /insights/api/conversations` | `[CÓDIGO]` |
| **Enviar mensaje** | Dueño | Texto (≤ 2000 car.) | Respuesta, gráfico, fuentes, pasos de razonamiento | `POST /insights/api/conversations/<cid>/messages` · `message_handler.py` | `[CÓDIGO]` |
| Fijar / renombrar / borrar | Dueño | — | Gestión de conversaciones | `PATCH /pin`, `PUT`, `DELETE` | `[CÓDIGO]` |
| Ver evento de negocio | Dueño | — | Aviso proactivo pendiente | `GET /insights/api/events/pending` | `[CÓDIGO]` |
| Consumir / descartar evento | Dueño | `eid` | Abre conversación / lo archiva | `POST .../consume` \| `/dismiss` | `[CÓDIGO]` |
| Ajustar profundidad | Dueño | `fast`/`normal`/`detailed` | `copilot_analysis_depth` | `PUT /insights/api/settings` | `[CÓDIGO]` |
| Activar/desactivar benchmark | Dueño | booleano | `allow_benchmark` | `PATCH /insights/api/settings/benchmark` | `[CÓDIGO]` |

### 2.7 Empleados

| Función | Usuario | Entrada | Resultado | Evidencia | Clasif. |
|---|---|---|---|---|---|
| Crear empleado | Dueño | Nombre, rol, PIN | Usuario `cashier`/`waiter` **si el plan lo permite** | `POST /dashboard/equipo/crear` · `@require_role('owner')` | `[CÓDIGO]` |
| Cambiar PIN | Dueño | Nuevo PIN | `pin_hash` actualizado | `POST /dashboard/equipo/<id>/cambiar-pin` | `[CÓDIGO]` |
| Desactivar / reactivar | Dueño | — | `is_active` | `POST .../desactivar` \| `/reactivar` | `[CÓDIGO]` |
| Desbloquear tras 5 fallos | Dueño | — | `locked_until=NULL` | `POST .../desbloquear` | `[CÓDIGO]` |
| Entrar al portal | Cajero/Mesero | PIN | `session['employee_id']` | `GET/POST /empleado/<slug>` | `[CÓDIGO]` |
| Pantalla de cajero | Cajero | — | Cobros | `GET /empleado/<slug>/caja` | `[CÓDIGO]` |
| Pantalla de mesero | Mesero | — | Pedidos | `GET /empleado/<slug>/pedidos` | `[CÓDIGO]` |

### 2.8 Créditos de IA y recompensas

| Función | Usuario | Entrada | Resultado | Evidencia | Clasif. |
|---|---|---|---|---|---|
| Consultar saldo | Dueño / Scanner IA | — | Tokens de plan + extra | `GET /api/tokens/status` | `[CÓDIGO]` |
| Consumir token | Scanner IA | `SERVICE_API_KEY` | −1 token, transacción registrada | `POST /api/tokens/consume` · `token_service.py:109` | `[CÓDIGO]` |
| Comprar paquete | Dueño | `pack_id` | Preferencia de Mercado Pago | `POST /api/tokens/topup/initiate` | `[CÓDIGO]` |
| Acreditar compra | Mercado Pago | `mp_payment_id` | +tokens (idempotente por `UNIQUE`) | `GET /api/tokens/topup/callback` | `[CÓDIGO]` |
| Recibir "Sorpresa Velzia" | Dueño | Pago aprobado | `RewardClaim` + correo | `reward_service.py` | `[CÓDIGO]` |
| Reclamar recompensa | Dueño | `short_code` | Cupón o beneficio | `GET /reclamar/<short_code>` → `POST /reclamar/claim` | `[CÓDIGO]` |
| Ver logros | Dueño | — | Logros conseguidos | `GET /dashboard/logros` | `[CÓDIGO]` |

---

## 3. Flujos detallados

### 3.1 Pedido desde el menú público — el flujo crítico

`[CÓDIGO]` `app/routes/public.py` (`create_order`). Orden **exacto** de las validaciones:

```
1.  ¿Viene 'cart' en el cuerpo?            → si no: 400
2.  HONEYPOT: ¿'user_secondary_email'?      → si sí: 403 "Actividad sospechosa"
3.  TIEMPO: ¿menos de 3.0 s desde init-checkout? → si sí: 429
4.  ¿Existe el restaurante?                 → si no: 404
5.  ¿restaurant.is_open?                    → si no: 403 "Estamos cerrados"
6.  ¿is_ordering_enabled (suscripción)?     → si no: 403 "Pedidos desactivados"
7.  Expira pedidos pendientes de +30 min
8.  RATE LIMIT: ¿>3 pedidos/min de esta IP? → si sí: 429 + retry_after 600
9.  Genera número de pedido (contador atómico)
10. Construye notas (teléfono, mesa, ciudad, dirección)
11. Crea el pedido IDEMPOTENTE con idempotency_key
12. Notifica por ntfy al restaurante
```

**Reglas extraídas:**

| # | Regla | Evidencia | Clasif. |
|---|---|---|---|
| RN-01 | Un campo oculto `user_secondary_email` relleno ⇒ es un bot | `app/routes/public.py:109` | `[CÓDIGO]` |
| RN-02 | Deben pasar **≥ 3 segundos** entre abrir el checkout y enviarlo | `app/routes/public.py` (`time.time() - start_time < 3.0`) | `[CÓDIGO]` |
| RN-03 | Máx. **3 pedidos/minuto** por IP y restaurante; ban de **10 min** | `app/utils/rate_limiter.py:14-15` | `[CÓDIGO]` |
| RN-04 | Un restaurante **cerrado** (`is_open=False`) no recibe pedidos | `app/routes/public.py` | `[CÓDIGO]` |
| RN-05 | Una suscripción no vigente **desactiva los pedidos públicos** | `PublicMenuService.is_ordering_enabled` | `[CÓDIGO]` |
| RN-06 | Los pedidos pendientes de más de 30 min se expiran al llegar uno nuevo | `expire_old_pending_orders(..., minutes=30)` | `[CÓDIGO]` |
| RN-07 | Reenviar el mismo `idempotency_key` devuelve el pedido original | `order_service.py:295` + `UNIQUE(restaurant_id, idempotency_key)` | `[CÓDIGO]` |
| RN-08 | El pedido guarda **copia** del nombre y precio del producto | `app/models/orders.py:56-57` | `[CÓDIGO]` |
| RN-09 | El pedido nace `pending` y caduca según `pending_expiry_hours` (def. 24 h) | `order_service.py:267-290` | `[CÓDIGO]` |

`[INFERIDO]` RN-06 y RN-09 conviven con dos ventanas distintas (30 min al crear,
24 h en la tarea programada). `[PENDIENTE]` ¿cuál es la política real de
caducidad? Ver [07-preguntas-pendientes.md](07-preguntas-pendientes.md) (D-07).

### 3.2 Estado de la suscripción — la fuente única de verdad

`[CÓDIGO]` `get_subscription_status(restaurant)` en `app/utils/subscription.py:184-330`
devuelve un objeto ya calculado que el frontend consume tal cual.

**Árbol de decisión real:**

```
¿restaurante?                       no → not_found
¿is_active?         no → ¿dormant? sí → dormant  |  no → inactive
¿cancellation_pending?  sí → ¿aún vigente? sí → cancellation_pending (can_crud=True)
                                            no → dormant
¿subscription_expires_at?           no → no_subscription
Faltan N días:
    5..7  → expiring_soon_neutral      (can_crud=True)
    2..4  → expiring_soon_warning      (can_crud=True)
    1     → expiring_soon_urgent       (can_crud=True)
    >7    → active                     (can_crud=True)
    ≤0    → (periodo de gracia / vencida)
```

| # | Regla | Evidencia | Clasif. |
|---|---|---|---|
| RN-10 | Periodo de gracia = **5 días** tras el vencimiento | `GRACE_PERIOD_DAYS = 5` (`subscription.py:96`) | `[CÓDIGO]` |
| RN-11 | En gracia se **puede usar la IA** pero **no comprar créditos** | `can_use_ai` vs `can_buy_tokens` (`subscription.py:129-147`) | `[CÓDIGO]` |
| RN-12 | Cancelar **no borra nada**: conserva acceso hasta el vencimiento | `app/routes/dashboard.py` (cancel-account) | `[CÓDIGO]` |
| RN-13 | Las cuentas inactivas pasan a `dormant` tras **30 días**, **sin borrar datos** | `INACTIVE_GRACE_DAYS = 30` (`app/tasks.py:49`) | `[CÓDIGO]` |
| RN-14 | Los avisos de vencimiento se envían a los **5, 2 y 1** días | `reminder_service.py`; `app/tasks.py:304` | `[CÓDIGO]` |

> `[CONTRADICCIÓN]` El docstring de `is_subscription_active` dice **10 días** de
> gracia mientras la constante vale **5**. Ver [C-03](06-riesgos-y-deuda-tecnica.md#c-03).

### 3.3 Planes y límites

`[CÓDIGO]` `PLAN_LIMITS` en `app/utils/subscription.py:5-61`:

| Característica | Emprendedor | Crecimiento | Élite | Prueba |
|---|---|---|---|---|
| Precio (COP/mes) | 30.000 | 40.000 | 50.000 | 0 |
| Duración (días) | 30 | 30 | 30 | **60** |
| Productos activos | **25** | **100** | ∞ | ∞ |
| Empleados | **1** | **5** | ∞ | ∞ |
| QR de menú | ✅ | ✅ | ✅ | ✅ |
| QR por mesa | ❌ | ✅ | ✅ | ✅ |
| Modificadores | ❌ | ❌ | ✅ | ✅ |
| Temas de marca | ❌ | ✅ | ✅ | ✅ |
| Color propio | ❌ | ❌ | ✅ | ✅ |
| Créditos IA/mes | 150 | 400 | 1.000 | 50 |
| Seguimientos gratis del Copilot | 4 | 4 | **8** | 4 |

> `[CONTRADICCIÓN]` El `README.md:17` anuncia *"Prueba gratuita de **10 días**"*
> mientras el código concede **60 días** (`duration_days: 60`, nombre
> `'Prueba Premium · 60 días'`). Ver [C-02](06-riesgos-y-deuda-tecnica.md#c-02).

| # | Regla | Evidencia | Clasif. |
|---|---|---|---|
| RN-15 | El límite de productos cuenta solo los **activos** (`is_active=True`) | `check_product_limit` (`subscription.py:162-182`) | `[CÓDIGO]` |
| RN-16 | Con la suscripción vencida, `check_product_limit` **siempre deniega** | `subscription.py:166-167` | `[CÓDIGO]` |
| RN-17 | `check_feature_access` exige suscripción **estrictamente vigente** (sin gracia) | `subscription.py:156` | `[CÓDIGO]` |
| RN-18 | Un plan desconocido cae por defecto en **`emprendedor`** | `get_plan_limits` (`subscription.py:150`) | `[CÓDIGO]` |

### 3.4 Créditos de IA

`[CÓDIGO]` `app/services/token_service.py` y `app/models/tokens.py`.

| # | Regla | Evidencia | Clasif. |
|---|---|---|---|
| RN-19 | Una billetera por usuario (`UNIQUE(user_id)`) | `app/models/tokens.py:22-23` | `[CÓDIGO]` |
| RN-20 | Se gastan primero los tokens del plan, luego los comprados | `app/models/tokens.py:16-17` | `[CÓDIGO]` |
| RN-21 | Los tokens comprados **no expiran**; los del plan se reinician al renovar | ídem | `[CÓDIGO]` |
| RN-22 | `plan_limit = NULL` ⇒ Élite ilimitado | `app/models/tokens.py:24-25` | `[CÓDIGO]` |
| RN-23 | El consumo usa **bloqueo pesimista** `SELECT ... FOR UPDATE` para evitar TOCTOU | `token_service.py:128-131` | `[CÓDIGO]` |
| RN-24 | `mp_payment_id` es **UNIQUE**: un webhook repetido no acredita dos veces | `app/models/tokens.py:80` | `[CÓDIGO]` |
| RN-25 | El primer análisis profundo de una conversación cuesta **1 token**; los seguimientos son gratis hasta el tope | `message_handler.py:286-317` | `[CÓDIGO]` |
| RN-26 | Tope de seguimientos: **4** (8 en Élite); al superarlo, el siguiente mensaje cobra un token nuevo | `settings.py:80-84` | `[CÓDIGO]` |
| RN-27 | Las consultas rápidas (SQL directo) y las de catálogo **no consumen** tokens | `message_handler.py:288-295` | `[CÓDIGO]` |

> ⚠️ **RN-28 — El token se cobra antes de llamar al LLM y no se devuelve si falla.**
> `[CÓDIGO]` `message_handler.py:296` llama a `consume_token`, que hace
> `db.session.commit()` (`token_service.py:159`), **antes** de la llamada al
> LLM. Si DeepSeek falla, la ruta devuelve **502** en
> `message_handler.py:441-447` **sin ninguna devolución ni compensación**.
> `[EJECUTADO]` Observado en las pruebas `TestLLMCallTelemetry`: el log muestra
> `WALLET: Token consumido para usuario 1` seguido de `assert 502 == 200`.
> Ver [R-05](06-riesgos-y-deuda-tecnica.md#r-05).

### 3.5 Copilot VZ — clasificación y protecciones

| # | Regla | Evidencia | Clasif. |
|---|---|---|---|
| RN-29 | Clasificador híbrido: `quick` (SQL, gratis) vs `analysis` (LLM, 1 token) | `insights/classifier.py` | `[CÓDIGO]` |
| RN-30 | Mensaje de usuario limitado a **2000 caracteres** | `insights/message_handler.py` | `[CÓDIGO]` |
| RN-31 | Sanitización anti-inyección: los patrones detectados se sustituyen por `[FILTRADO]` | `insights/message_handler.py` | `[CÓDIGO]` |
| RN-32 | La respuesta del LLM se valida antes de mostrarla (`validate_llm_response`) | `insights/llm_service.py` | `[CÓDIGO]` |
| RN-33 | El contexto se comprime en 2 fases al superar el 80 %/85 % de 12K tokens | `insights/context_manager.py` | `[CÓDIGO]` |
| RN-34 | Máx. **15** mensajes de historial por llamada, **también en Élite** | `COPILOT_MAX_HISTORY_MESSAGES` (`settings.py:87`) | `[CÓDIGO]` |
| RN-35 | Profundidad configurable: `fast` 7 días / `normal` 60 / `detailed` 90 | `AGENTS.md` + `copilot_analysis_depth` | `[CÓDIGO]` |
| RN-36 | Búsqueda web (Tavily) es **opt-in**, apagada por defecto | `web_search_enabled` def. `False` (`core.py:74-75`) | `[CÓDIGO]` |
| RN-37 | Tope mensual de búsquedas web: **1.000** (configurable) | `TAVILY_MONTHLY_LIMIT` | `[CÓDIGO]` |
| RN-38 | Cada conversación guarda la **versión del prompt** usada | `copilot_conversations.prompt_version` | `[CÓDIGO]` |

### 3.6 Benchmarks anónimos

| # | Regla | Evidencia | Clasif. |
|---|---|---|---|
| RN-39 | Se publican **medianas**, nunca valores individuales | `app/models/ai.py` (`PlatformBenchmark`) | `[CÓDIGO]` |
| RN-40 | Una cohorte solo se publica si cumple **k-anonymity (k ≥ 5)** | `insights/benchmark_service.py`; docstring del modelo | `[CÓDIGO]` |
| RN-41 | Cohortes: `global` y por `cuisine_type` | `platform_benchmarks.cohort` (UNIQUE) | `[CÓDIGO]` |
| RN-42 | La participación es **opt-out** (`allow_benchmark` por defecto `True`) | `app/models/core.py:64-66` | `[CÓDIGO]` |
| RN-43 | Se recalculan cada noche a las **04:15** | `app/tasks.py:314-321` | `[CÓDIGO]` |

> `[PENDIENTE]` RN-42 tiene implicaciones legales. El código cita la **Ley 1581
> de 2012** como respaldo, pero un esquema opt-out para compartir datos de
> negocio debería validarlo el propietario. Ver
> [07-preguntas-pendientes.md](07-preguntas-pendientes.md) (D-02).

### 3.7 Reservas

| # | Regla | Evidencia | Clasif. |
|---|---|---|---|
| RN-44 | Ocupación = `hora + service_duration_min + cleanup_buffer_min` (90 + 15 por defecto) | `app/models/reservations.py:62-66` | `[CÓDIGO]` |
| RN-45 | Antelación mínima 2 h; máxima 30 días | `reservation_settings` | `[CÓDIGO]` |
| RN-46 | Una mesa sin `capacity` se trata como **4 personas** | `app/models/core.py:227` | `[CÓDIGO]` |
| RN-47 | Las reservas se guardan en **hora local de Colombia**, no en UTC | `app/models/reservations.py:4-12` | `[CÓDIGO]` |
| RN-48 | Mismo anti-spam que los pedidos: honeypot + 3/min por IP | `app/routes/public.py:104-118` | `[CÓDIGO]` |
| RN-49 | Las reservas se desactivan si el restaurante **no tiene mesas activas** | `app/routes/public.py:64-70` | `[CÓDIGO]` |
| RN-50 | El recordatorio se envía **una sola vez** (`reminder_sent`) | `app/models/reservations.py:42` | `[CÓDIGO]` |

### 3.8 Caja

| # | Regla | Evidencia | Clasif. |
|---|---|---|---|
| RN-51 | Un cierre **no puede solaparse** con otro del mismo restaurante | Docstring `app/models/cash.py:11-12` + `CashRegisterService` | `[CÓDIGO]` |
| RN-52 | `UNIQUE(restaurant_id, period_start)` como red de seguridad en BD | `app/models/cash.py:51-53` | `[CÓDIGO]` |
| RN-53 | Las ventas se agregan por **`paid_at`**, no por `created_at` | `app/models/cash.py:5` | `[CÓDIGO]` |
| RN-54 | **Cualquier usuario del restaurante puede cerrar caja** (sin filtro por rol) | Docstring `app/models/cash.py:11-13` | `[CÓDIGO]` ⚠️ |
| RN-55 | Métodos soportados: `cash`, `nequi`, `bancolombia`, `card` | `app/models/cash.py:36-45` | `[CÓDIGO]` |

`[PENDIENTE]` RN-54 es un hueco de control interno: un mesero podría cerrar la
caja. El propio código lo reconoce como pendiente. Ver
[07-preguntas-pendientes.md](07-preguntas-pendientes.md) (D-08).

### 3.9 Recompensas ("Sorpresa Velzia")

`[CÓDIGO]` `app/services/reward_service.py:105-130`.

| Rareza | Probabilidad |
|---|---|
| `common` 🎁 | **70 %** |
| `uncommon` 🌟 | **25 %** |
| `rare` 💎 | **5 %** |

| # | Regla | Evidencia | Clasif. |
|---|---|---|---|
| RN-56 | La rareza se sortea con `random.random()` en cada pago aprobado | `reward_service.py:124-131` | `[CÓDIGO]` |
| RN-57 | Se evita repetir el mismo premio dos veces seguidas (`last_reward_type`) | `reward_service.py:134-143` | `[CÓDIGO]` |
| RN-58 | Cada recompensa genera `short_code` y `token` **únicos** | `app/models/rewards.py` (`RewardClaim`) | `[CÓDIGO]` |
| RN-59 | Las rachas (`streaks`) mejoran la rareza por tramos (`tier`) | `reward_service.py:93-97`, `streak_service.py` | `[CÓDIGO]` |
| RN-60 | Los cupones de descuento caducan y se expiran cada hora | `app/tasks.py:168-190` | `[CÓDIGO]` |

### 3.10 Empleados y PIN

| # | Regla | Evidencia | Clasif. |
|---|---|---|---|
| RN-61 | Solo el `owner` administra empleados | `@require_role('owner')` en `employees.py` | `[CÓDIGO]` |
| RN-62 | Máximo de empleados según plan: 1 / 5 / ∞ | `max_employees` en `PLAN_LIMITS` | `[CÓDIGO]` |
| RN-63 | **5** PIN fallidos ⇒ bloqueo de **30 minutos** | `employee_service.py:44-45` | `[CÓDIGO]` |
| RN-64 | Un PIN correcto reinicia el contador de fallos | `employee_service.py:199` | `[CÓDIGO]` |
| RN-65 | Los empleados se **desactivan**, no se borran | `users.is_active` | `[CÓDIGO]` |
| RN-66 | El dueño nunca tiene PIN (`pin_hash` NULL) | `app/models/core.py:124` | `[CÓDIGO]` |
| RN-67 | Si coexisten sesión de dueño y de empleado, **gana el dueño** | `app/utils/restaurant.py:9-18` | `[CÓDIGO]` |

### 3.11 Trazabilidad de pedidos

`[CÓDIGO]` Cada cambio relevante escribe un `OrderEvent` con `actor_id`,
`actor_role`, `event_type` y `metadata` (`app/services/order_service.py:45-60`).
La traza sobrevive al borrado del usuario (`actor_id` → SET NULL) pero **no** al
del pedido (CASCADE).

### 3.12 Tareas automáticas

| Tarea | Cuándo | Efecto de negocio |
|---|---|---|
| `manage_subscription_lifecycle` | 03:00 | Suspende (`dormant`) cuentas inactivas o vencidas, **sin borrar datos** |
| `expire_pending_orders` | cada hora :00 | `pending` → `expired` |
| `scan_business_events` | cada hora :30 | Genera avisos proactivos del Copilot |
| `expire_coupons` | cada hora :45 | Caduca cupones |
| `send_subscription_reminders` | 13:00 UTC (08:00 CO) | Correos de aviso |
| `compute_platform_benchmarks` | 04:15 | Recalcula medianas anónimas |
| `send_reservation_reminders` | cada 30 min | ntfy de reservas próximas |

---

## 4. Reglas que el código permite y podrían no ser deseadas

> Formato sugerido en la guía: *el código permite X; encontrado en Y; pendiente
> de confirmar si es intencional.*

| # | Observación | Evidencia | Clasificación |
|---|---|---|---|
| O-01 | El código permite pasar un pedido de **`delivered` a `cancelled`**: un pedido ya entregado se puede cancelar. | `order_service.py:211` | `[CÓDIGO]`, `[PENDIENTE]` |
| O-02 | El código permite **reabrir** un pedido cancelado (`cancelled → pending`). | `order_service.py:212` | `[CÓDIGO]`, `[PENDIENTE]` |
| O-03 | El código permite que **cualquier usuario del restaurante cierre la caja**, incluido un mesero. | `app/models/cash.py:11-13` | `[CÓDIGO]`, `[PENDIENTE]` |
| O-04 | El código permite **varios usuarios con rol `owner`** en el mismo restaurante, y toma el primero que encuentra. | `app/utils/auth.py:106-107` | `[CÓDIGO]`, `[PENDIENTE]` |
| O-05 | El código **exime del rate limiting global a todo usuario con sesión iniciada**. | `app/__init__.py:22-24` | `[CÓDIGO]`, `[PENDIENTE]` |
| O-06 | El código **cobra el token de IA antes de llamar al LLM y no lo devuelve si falla**. | `message_handler.py:296` + `:441-447` | `[EJECUTADO]`, `[PENDIENTE]` |
| O-07 | El código activa el **benchmark anónimo por defecto** (opt-out), no opt-in. | `app/models/core.py:64-66` | `[CÓDIGO]`, `[PENDIENTE]` |
| O-08 | El código permite **categorías y productos con nombres duplicados** dentro del mismo restaurante. | Sin `UNIQUE` en el esquema | `[CÓDIGO]`, `[PENDIENTE]` |
| O-09 | El código **no exige moneda ni decimales**: todo importe es un entero en COP. | `app/models/core.py:173` | `[CÓDIGO]`, `[PENDIENTE]` |
| O-10 | El código mantiene **dos webhooks de Mercado Pago** activos simultáneamente. | `auth.py:508` y `api_webhooks.py:136` | `[CÓDIGO]`, `[PENDIENTE]` |

Estas diez observaciones se llevan a la sesión de validación:
[07-preguntas-pendientes.md](07-preguntas-pendientes.md).
