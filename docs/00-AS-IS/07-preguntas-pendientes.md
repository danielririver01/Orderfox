# 07 — Decisiones que necesitan al propietario

**Commit de referencia:** `cd96aa763c086dea93e4aede46191b9add9067fa` · **Fecha:** 2026-09-29

> ## ✅ Cuatro decisiones confirmadas — 2026-09-29, por Daniel (propietario)
>
> | # | Decisión | Estado |
> |---|---|---|
> | **D-01** | **PostgreSQL** es el motor oficial | `[CONFIRMADO]` |
> | **D-02** | El benchmark anónimo **sigue siendo opt-out** | `[CONFIRMADO]` |
> | **D-09** | Si el LLM falla, **el crédito se devuelve** | `[CONFIRMADO]` |
> | **D-10** | La prueba gratuita es de **60 días** | `[CONFIRMADO]` |
>
> Son las primeras afirmaciones de todo el diagnóstico que dejan de ser
> inferencias. El resto sigue en `[PENDIENTE]`.

> **Doce preguntas.** Ninguna se puede responder leyendo el código: todas
> requieren una decisión de negocio o el conocimiento de cómo se comporta el
> sistema en producción.
>
> Mientras no estén respondidas, los hallazgos asociados **permanecen en estado
> `[PENDIENTE]`** y no deben tratarse como requisitos.

---

## Las tres primeras (bloquean al resto)

### ✅ D-01 — ¿Cuál es **el** motor de base de datos?

> **RESUELTA (2026-09-29, Daniel): PostgreSQL.** Alineados `README.md`,
> `AGENTS.md`, `.env.example` y `Dockerfile.dev`. Ver ADR-0003.
> Pendiente: retirar `PyMySQL` de `requirements.txt` y revisar las
> herramientas MCP de MySQL descritas en `AGENTS.md`.

**Por qué se pregunta:** siete fuentes del repositorio dan tres respuestas
distintas. Hoy conviven **SQLite** (pruebas), **PostgreSQL** (CI y scripts de
`deploy/`) y **MariaDB/MySQL** (`README.md`, `AGENTS.md`, `.env.example`), y
`requirements.txt` instala los dos drivers a la vez.

**Consecuencia de no decidirlo:** ninguna prueba se ejecuta contra el motor
real; las diferencias de dialecto (bloqueos `FOR UPDATE`, tipos de fecha,
`ON CONFLICT`) quedan sin cubrir.

**Opciones:**
- **(a)** PostgreSQL es el oficial → corregir `README.md`, `AGENTS.md`,
  `.env.example`, `Dockerfile.dev` y retirar `PyMySQL`
- **(b)** MySQL es el oficial → corregir el CI, los scripts de `deploy/` y
  retirar `psycopg2`
- **(c)** Se soportan ambos deliberadamente → documentarlo y probar en los dos

**Evidencia:** [C-01](06-riesgos-y-deuda-tecnica.md#c-01)

---

### ✅ D-02 — ¿El benchmark anónimo debe ser opt-out o opt-in?

> **RESUELTA (2026-09-29, Daniel): se mantiene opt-out.** El comportamiento
> actual es el deseado; no hay cambio de código. RN-42 pasa a `[CONFIRMADO]`.

**Por qué se pregunta:** `restaurants.allow_benchmark` viene en `True`. Todo
restaurante nuevo **comparte sus métricas por defecto** (solo medianas, con
k ≥ 5) sin pedir consentimiento explícito. El código cita la **Ley 1581 de 2012**
como respaldo (`app/models/core.py:64-66`).

**Consecuencia de no decidirlo:** es la única regla del sistema con implicación
legal directa. Un cambio a opt-in vaciaría las cohortes hasta que los usuarios
las activen.

**Opciones:** **(a)** mantener opt-out con aviso claro en el alta ·
**(b)** pasar a opt-in · **(c)** opt-out pero con confirmación en el primer uso
del Copilot

**Evidencia:** [RN-42](04-flujos-funcionales.md#36-benchmarks-anónimos)

---

### D-03 — ¿Se mantiene el login propio con contraseña además de Clerk?

**Por qué se pregunta:** conviven dos sistemas de identidad. `users.password`
sigue siendo obligatorio y `check_password` se sigue usando
(`app/models/core.py:141`), pero el alta real pasa por Clerk
(`POST /api/sync-clerk`).

**Consecuencia de no decidirlo:** dos superficies de autenticación que mantener
y auditar; no está claro cuál es la de verdad.

**Opciones:** **(a)** Clerk es el único proveedor → retirar el login propio ·
**(b)** el login propio es el plan B si Clerk cae → documentarlo como tal ·
**(c)** el login propio es solo para empleados/administración

> 🧪 **Evidencia nueva de la verificación en ejecución:** la página de login
> **ya no renderiza el formulario de contraseña**. `app/template/auth/index.html`
> contiene solo el widget de Clerk: cero apariciones de `form.email` y cero de
> `csrf_token`. Es decir, el login propio existe en la ruta
> (`AuthService.authenticate`) pero **la interfaz no lo expone**. Eso inclina la
> respuesta hacia (a) o (b), pero sigue siendo una decisión de producto: hay que
> decidir si se retira del código o se conserva como plan de contingencia.

**Evidencia:** [02 §4.1](02-arquitectura-actual.md#41-tres-mecanismos-coexistentes) · [08 §6.1](08-verificacion-en-ejecucion.md)

---

## Comportamiento en producción (solo el propietario puede confirmarlo)

### D-04 — ¿Llegan duplicados los correos y las notificaciones automáticas?

**Por qué se pregunta:** el scheduler arranca dentro de `create_app()`, y en
producción hay `gunicorn --workers 3` **más** un contenedor
`orderfox-scheduler` aparte. Sobre el papel, las 7 tareas quedarían programadas
4 veces, sin bloqueo distribuido.

**Esto es una inferencia, no un hecho comprobado.** Basta mirar los logs de un
día para confirmarlo o descartarlo: si `send_subscription_reminders` aparece una
sola vez a las 13:00 UTC, no hay problema.

**Evidencia:** [R-04](06-riesgos-y-deuda-tecnica.md#r-04)

---

### D-05 — ¿Se pueden eliminar los artefactos y el material no productivo?

**Por qué se pregunta:** hay archivos versionados que no parecen necesarios para
ejecutar el sistema, pero podrían tener valor para alguien.

| Elemento | ¿Se puede borrar? |
|---|---|
| `test_qr_*.png`, `menu_check.json`, `test_flask_*.txt` | ❓ |
| `video_presentation/` (material de marketing, abril 2026) | ❓ |
| `backups/felicia_reset_2026-09-03/snapshot.json` (datos de un cliente) | ❓ |
| `migrations/versions/backup/` (3 migraciones fuera de la cadena) | ❓ |
| `migrations/supabase_schema.sql` | ❓ ¿se sigue usando Supabase? |
| `app/templates/public/subscription_expired.html` (**inalcanzable**) | ❓ |
| `gunicorn_config.py` (**ningún entrypoint lo carga**) | ❓ borrarlo o empezar a usarlo |
| 6 plantillas Jinja2 sin referencia detectada | ❓ verificar antes de borrar |

**Evidencia:** [R-11](06-riesgos-y-deuda-tecnica.md#r-11), [01 §11](01-inventario.md#11-código-abandonado-duplicado-o-sin-uso-aparente)

---

## Reglas de negocio que el código permite y quizá no debería

### D-06 — ¿Un pedido ya entregado puede cancelarse?

La máquina de estados permite `delivered → cancelled` y también
`cancelled → pending` (reapertura).

**Opciones:** **(a)** es correcto, cubre devoluciones y correcciones ·
**(b)** solo con rol `owner` · **(c)** no debería permitirse

**Evidencia:** [O-01, O-02](04-flujos-funcionales.md#4-reglas-que-el-código-permite-y-podrían-no-ser-deseadas)

---

### D-07 — ¿Cuál es la política real de caducidad de pedidos: 30 minutos o 24 horas?

Hay dos ventanas distintas en el mismo flujo:
- Al crear un pedido, se expiran los pendientes de **más de 30 minutos**
  (`expire_old_pending_orders(..., minutes=30)`)
- Cada pedido nace con `expires_at = ahora + pending_expiry_hours` (**24 h** por
  defecto), y la tarea horaria usa ese campo

Un pedido puede expirar a los 30 minutos si llega otro pedido, o aguantar 24 h
si no llega ninguno.

**Evidencia:** [RN-06, RN-09](04-flujos-funcionales.md#31-pedido-desde-el-menú-público--el-flujo-crítico)

---

### D-08 — ¿Debería el **cajero** poder cerrar la caja?

> ⚠️ **Esta pregunta cambió de sentido al verificarla en ejecución.**
> Originalmente decía *«hoy cualquier usuario puede cerrar la caja, incluido un
> mesero»*, apoyándome en un docstring obsoleto. **Es falso.**

**Lo que ocurre hoy, comprobado:** el cierre es `@require_role('owner')`.
Dueño → **200**; cajero → **403**; mesero → bloqueado antes de llegar.

**Lo que queda por decidir** es si el perfil que de hecho cuadra la caja en el
local —el cajero— debería poder cerrarla, o si el cierre es deliberadamente una
atribución exclusiva del dueño.

**Opciones:** **(a)** seguir solo `owner` · **(b)** permitir también `cashier`
(la columna `closed_by` ya distingue quién cerró) · **(c)** el cajero cierra y
el dueño valida después

**Tarea asociada en cualquier caso:** corregir el docstring de
`app/models/cash.py:11-13`, que contradice al código (**C-08**).

**Evidencia:** [08-verificacion-en-ejecucion.md §7](08-verificacion-en-ejecucion.md#correccion-rn-54)

---

### ✅ D-09 — Si el LLM falla, ¿el crédito se devuelve?

> **RESUELTA (2026-09-29, Daniel): sí, se devuelve.** Hay que implementar la
> compensación cuando la llamada al LLM termina en error → VLZ-6.

Hoy **no**. El token se descuenta y se confirma con `commit()` antes de llamar a
DeepSeek; si la llamada falla, la API responde 502 sin compensación.

**Opciones:** **(a)** el intento se cobra, es deliberado → documentarlo en los
términos · **(b)** se debe devolver ante error técnico · **(c)** cobrar solo
después de una respuesta válida

**Evidencia:** [R-05](06-riesgos-y-deuda-tecnica.md#r-05)

---

### ✅ D-10 — ¿La prueba gratuita es de 10 días o de 60?

> **RESUELTA (2026-09-29, Daniel): 60 días.** El código ya era correcto;
> se corrigió `README.md`. Queda alinear la landing pública.

El `README.md` anuncia **10 días**. El código concede **60**
(`'duration_days': 60`, `'Prueba Premium · 60 días'`).

Es una discrepancia comercial: seis veces más producto gratis del anunciado.
Hay que decidir cuál gana y alinear la otra fuente.

**Evidencia:** [C-02](06-riesgos-y-deuda-tecnica.md#c-02)

---

### D-12 — ¿El bloqueo por PIN debe seguir afectando a toda la plantilla?

> Decisión **nueva**, surgida de la verificación en ejecución.

Cinco PIN erróneos bloquean **30 minutos a todos los empleados**, incluido quien
nunca falló. Comprobado: tras el quinto fallo, cajero y mesero quedaron ambos
bloqueados y ninguno pudo entrar con su PIN correcto.

`/empleado/<slug>` es una URL pública y el `slug` es el mismo del menú y de los
QR de las mesas. Cualquiera que lo conozca puede dejar sin portal al personal
durante media hora, en plena hora punta.

El diseño es deliberado (el código lo explica: «el atacante no sabe a qué
empleado ataca»), pero la consecuencia operativa no parece haberse sopesado.

**Opciones:** **(a)** mantenerlo y asumir el riesgo · **(b)** bloquear solo al
empleado cuyo PIN coincide parcialmente, o por dispositivo/IP en vez de por
cuenta · **(c)** mantener el bloqueo global pero reducirlo mucho (p. ej. 2 min)
y escalar progresivamente · **(d)** añadir un desbloqueo que no dependa de que
el dueño entre al panel

**Evidencia:** [R-21](08-verificacion-en-ejecucion.md#r-21)

---

## Gobernanza

### D-11 — ¿Cuál es la versión desplegada y cómo se decide de ahora en adelante?

Cinco fuentes dan cinco versiones (`1.0.0`, `1.3.0`, `1.4.0`, `1.6.0`) y **no
existe ninguna etiqueta Git**. La etiqueta `release` que llega a Sentry es
`APP_VERSION = 1.4.0`, que no coincide con el CHANGELOG.

**Se necesitan dos respuestas:**
1. ¿Qué versión está hoy en producción?
2. ¿Cuál será la fuente única de verdad — etiquetas Git, `settings.APP_VERSION`
   o el CHANGELOG?

**Propuesta operativa mínima:** etiquetar `cd96aa7` como `as-is-2026-09-29` para
que este diagnóstico tenga una referencia estable.

**Evidencia:** [C-04](06-riesgos-y-deuda-tecnica.md#c-04)

---

## Cómo cerrar estas preguntas

1. Sesión de validación con el propietario, pregunta por pregunta.
2. Cada respuesta se registra como **ADR** en [`adr/`](adr/) si cambia o fija una
   decisión de arquitectura.
3. El hallazgo asociado pasa de `[PENDIENTE]` a **`[CONFIRMADO]`** en el
   documento correspondiente, citando la fecha y quién lo confirmó.
4. Solo entonces tiene sentido abrir un documento **TO-BE**: hasta que D-01,
   D-02 y D-03 estén cerradas, cualquier propuesta se apoyaría en supuestos.
