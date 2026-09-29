# 06 — Riesgos, deuda técnica y contradicciones (AS-IS)

**Commit de referencia:** `cd96aa763c086dea93e4aede46191b9add9067fa` · **Fecha:** 2026-09-29

> **Este documento NO es un plan de trabajo.** Es la lista de lo que se encontró,
> con su evidencia. Qué se arregla, en qué orden y si merece la pena **lo decide
> el propietario**. Nada de lo que sigue ha sido priorizado ni aprobado.
>
> Los defectos (R) y las contradicciones documentales (C) están separados a
> propósito: no es lo mismo un error de ejecución que dos documentos que no
> coinciden.

---

## Resumen

| Severidad | Defectos (R) | Descripción corta |
|---|---|---|
| 🔴 Alta | R-01, R-02, R-03, **R-17**, **R-18**, **R-21**, **R-24** | Errores reproducidos en ejecución, riesgo de migración destructiva e interrupción del portal de empleados |
| 🟠 Media | R-04, R-05, R-06, R-07, R-08, R-16, **R-22**, **R-23** | Comportamiento incorrecto o degradación en producción |
| 🟡 Baja | R-09 … R-15, **R-19**, **R-20** | Higiene, mantenibilidad, portabilidad |

> 🧪 **R-17 … R-22 no están en este documento.** Salieron de someter las reglas
> de negocio a prueba ejecutando el sistema, y viven con su evidencia completa
> en [08-verificacion-en-ejecucion.md](08-verificacion-en-ejecucion.md):
>
> | # | Hallazgo | Severidad |
> |---|---|---|
> | [R-17](08-verificacion-en-ejecucion.md#r-17) | La protección anti-bot de 3 segundos **está inerte**: el frontend Astro nunca llama a `init-checkout` | 🔴 |
> | [R-18](08-verificacion-en-ejecucion.md#r-18) | `/menu/<slug>` redirige a una URL con `None`; los valores por defecto de 14 llamadas `config.get(...)` son **código muerto** | 🔴 |
> | [R-19](08-verificacion-en-ejecucion.md#r-19) | El contador diario de pedidos gasta un número en cada reintento idempotente | 🟡 |
> | [R-20](08-verificacion-en-ejecucion.md#r-20) | Un carrito con formato incorrecto devuelve **500** en lugar de 400 | 🟡 |
> | [R-21](08-verificacion-en-ejecucion.md#r-21) | **5 PIN erróneos bloquean a toda la plantilla 30 min**, desde una URL pública | 🔴 |
> | [R-22](08-verificacion-en-ejecucion.md#r-22) | Astro responde **HTTP 200** cuando el menú no existe o la API está caída: una caída total es invisible al monitoreo | 🟠 |
> | [R-23](09-seguridad-alcance-y-limites.md#r-23) | `cryptography`, `idna` y `pyasn1` con CVE conocidas en el snapshot; VLZ-27 actualizó versiones y activó el escaneo de dependencias en CI | 🟠 |
> | [R-24](09-seguridad-alcance-y-limites.md#r-24) | **La firma de los webhooks de Mercado Pago no sigue la especificación oficial: rechaza TODAS las notificaciones reales.** Ningún pago se confirma por webhook | 🔴 |
>
> **R-16** (deuda de pruebas) está documentada en
> [05-compilacion-y-despliegue.md §4](05-compilacion-y-despliegue.md#4-pruebas).
>
> 🔒 **Sobre seguridad:** este documento recoge hallazgos de seguridad, pero
> **este trabajo no fue una auditoría de seguridad**. El alcance real —qué se
> comprobó y, sobre todo, qué no— está en
> [09-seguridad-alcance-y-limites.md](09-seguridad-alcance-y-limites.md).

<a id="c-08"></a>
> ❗ **C-08 — Un docstring obsoleto me hizo documentar una regla falsa.**
> `app/models/cash.py:11-13` afirma que *«hoy todos los usuarios del restaurante
> pueden cerrar caja»*, pero `app/routes/cash_register.py:143-146` exige
> `@require_role('owner')`. Verificado: dueño **200**, cajero **403**.
> Documenté la versión del docstring como RN-54 y la elevé a decisión D-08;
> ambas quedan corregidas. Detalle en
> [08-verificacion-en-ejecucion.md §7](08-verificacion-en-ejecucion.md#correccion-rn-54).

| Contradicciones documentales | C-01 … C-08 |
|---|---|

---

# Parte A — Defectos verificados

<a id="r-01"></a>
## 🔴 R-01 — `NameError` en `require_active`: rompe la transición `cancellation_pending → dormant`

**Estado:** `[EJECUTADO]` — reproducido.

`app/utils/auth.py:113-121` ejecuta:

```python
if restaurant.subscription_state == 'cancellation_pending':
    restaurant.is_active = False
    restaurant.subscription_state = 'dormant'
    restaurant.dormant_at = datetime.now(timezone.utc)   # ← línea 116
    db.session.commit()                                  # ← línea 117
```

Pero el módulo **no importa `datetime`, `timezone` ni `db`**. Sus únicas
importaciones son (`app/utils/auth.py:1-5`):

```python
from functools import wraps
from flask import session, redirect, url_for, flash, g, request, jsonify
import logging
from app.utils.restaurant import get_current_restaurant
from app.utils.subscription import is_subscription_active, check_feature_access
```

**Verificación estática:**

```
app/utils/auth.py:116:41: F821 undefined name 'datetime'
app/utils/auth.py:116:54: F821 undefined name 'timezone'
app/utils/auth.py:117:17: F821 undefined name 'db'
```

**Verificación en ejecución** — restaurante con `subscription_state =
'cancellation_pending'` y suscripción vencida hace 90 días (más allá de los 5
días de gracia), llamando a un endpoint decorado con `@require_active`:

```
NameError REPRODUCIDO -> name 'datetime' is not defined
```

**Impacto:** cualquier dueño que haya cancelado su suscripción y cuya fecha de
vencimiento ya pasó recibe un **error 500** al entrar al panel, en lugar de la
pantalla de reactivación. La transición a `dormant` no llega a ocurrir por esta
vía.

**Atenuante:** `[CÓDIGO]` la tarea nocturna `manage_subscription_lifecycle`
(`app/tasks.py:82-87`) cubre el mismo caso y **sí** importa `datetime`
correctamente. El usuario vería el 500 solo entre el vencimiento y la siguiente
ejecución de las 03:00.

**Por qué no lo detectó nadie:** las líneas 113-122 no tienen cobertura (la suite
reporta `app/utils/auth.py … 72% … 113-122` entre las líneas no cubiertas) y el
CI ejecuta flake8 con `--exit-zero`.

---

<a id="r-02"></a>
## 🔴 R-02 — `POST /api/dashboard/cancel-account` devuelve 500 y no cancela nada

**Estado:** `[EJECUTADO]` — reproducido.

`app/routes/api_dashboard.py` importa `datetime` y `timezone` (línea 6) pero
**no importa `db`**. El endpoint hace `db.session.commit()` (línea 215) y, en el
manejador de error, `db.session.rollback()` (línea 234).

**Verificación en ejecución:**

```
File "/home/user/Orderfox/app/routes/api_dashboard.py", line 234, in cancel_account
    db.session.rollback()
NameError: name 'db' is not defined
HTTP status: 500
subscription_state persistido: active      ← la cancelación NO se guardó
```

Nótese el doble fallo: el `NameError` original ocurre en la línea 215, lo captura
el `except Exception`, y el propio manejador **vuelve a fallar** en la línea 234.

**Impacto:** la cancelación de cuenta por API (móvil / integraciones) **está
rota**. El usuario ve un error del servidor y su suscripción sigue activa. La
versión web (`POST /dashboard/cancel-account`) sí funciona — hay una prueba que
lo cubre (`tests/test_account_deletion.py:25`), pero **ninguna prueba cubre la
variante API**.

---

<a id="r-03"></a>
## 🔴 R-03 — Los modelos y las migraciones están desincronizados: `flask db migrate` sería destructivo

**Estado:** `[EJECUTADO]` — `flask db check` sobre una base recién migrada.

```
Detected removed table 'velzia_category'
Detected removed table 'velzia_expense'
Detected removed table 'velzia_budget'
Detected removed index 'ix_copilot_conv_source' on 'copilot_conversations'
Detected added   index 'ix_copilot_conversations_source'
Detected removed index 'ix_orders_restaurant_paid_at' on 'orders'
Detected NOT NULL on column 'reward_claims.user_id'
ERROR [flask_migrate] Error: New upgrade operations detected
```

| Diferencia | Consecuencia si se autogenera una migración |
|---|---|
| 3 tablas `velzia_*` sin modelo | **Alembic las eliminaría.** Son las tablas del Scanner IA externo (Prisma) que comparte la misma base: se perderían datos de un servicio ajeno |
| `ix_copilot_conv_source` vs `ix_copilot_conversations_source` | Mismo índice con dos nombres: borrar y recrear |
| `ix_orders_restaurant_paid_at` no declarado en el modelo | **Se eliminaría** un índice que sí existe en producción, degradando las consultas del Centro de Caja (filtran por `restaurant_id` + `paid_at`) |
| `reward_claims.user_id` NOT NULL en el modelo, NULLABLE en la base | La integridad la garantiza hoy el código, no el esquema |

**Impacto:** `flask db migrate` **no se puede usar con seguridad** en este
repositorio tal cual está. La existencia de tres parches manuales en
`deploy/*_fix.py` sugiere que el problema ya se ha manifestado antes.

---

<a id="r-04"></a>
## 🟠 R-04 — El scheduler se inicia dentro de `create_app()`: se ejecutaría varias veces

**Estado:** `[CÓDIGO]` + `[INFERIDO]` — **no verificado en producción**.

`app/__init__.py:208` llama a `scheduler.start()` dentro de la *factory*, y
`run.py:8` ejecuta `app = create_app()` a nivel de módulo.

`docker-compose.yml` levanta simultáneamente:
- `orderfox`: `gunicorn --workers 3 run:app` → cada worker importa `run` y crea su scheduler
- `orderfox-scheduler`: `python run_scheduler.py` → otro `create_app()` más

`[INFERIDO]` **4 instancias del scheduler** ejecutando las mismas 7 tareas cron.
`app/extensions.py:7` usa `APScheduler()` sin `jobstore` compartido ni bloqueo
distribuido, así que no hay nada que impida la ejecución simultánea.

**Impacto potencial:** correos de recordatorio duplicados
(`send_subscription_reminders`), notificaciones ntfy repetidas
(`send_reservation_reminders`), y escrituras concurrentes en
`compute_platform_benchmarks`.

**Atenuante:** `[CÓDIGO]` varias tareas son idempotentes por diseño
(`reminder_sent`, filtros por estado), lo que limitaría el daño.

> ⚠️ **Esto es una inferencia, no un hecho comprobado.** Confirmar con los logs
> de producción antes de actuar — ver [07-preguntas-pendientes.md](07-preguntas-pendientes.md) (D-04).

---

<a id="r-05"></a>
## 🟠 R-05 — El crédito de IA se cobra antes de llamar al LLM y no se devuelve si falla

**Estado:** `[EJECUTADO]` — observado en la salida de las pruebas.

Secuencia en `app/services/insights/message_handler.py`:

1. Línea 296: `TokenService.consume_token(user, source='copilot_vz')`
2. `token_service.py:159`: **`db.session.commit()`** — el descuento ya es firme
3. Línea 316: `turn_consumed = True`
4. Líneas 430-441: llamada a DeepSeek
5. Líneas 441-447: si falla → **`return jsonify({...}), 502`**, **sin devolución**

**Evidencia en ejecución** (`tests/test_copilot_follow_up_cap.py::TestLLMCallTelemetry`):

```
INFO    app:token_service.py:160 WALLET: Token consumido para usuario 1
...
assert 502 == 200
```

El token se descuenta y acto seguido la petición falla con 502.

**Impacto:** ante una caída o un error de DeepSeek, el usuario **pierde el
crédito sin recibir respuesta**. Es un problema de facturación, no solo técnico.

**Agravante:** las dos únicas pruebas que recorren este camino son precisamente
las que el CI excluye con `-k "not TestLLMCallTelemetry"`.

`[PENDIENTE]` ¿Es una decisión de negocio deliberada ("el intento se cobra") o un
descuido? Ver [07-preguntas-pendientes.md](07-preguntas-pendientes.md) (D-09).

---

<a id="r-06"></a>
## 🟠 R-06 — El rate limiter de pedidos filtra por un estado que no existe

**Estado:** `[CÓDIGO]`.

`app/utils/rate_limiter.py:21-26`:

```python
return Order.query.filter(
    ...
    Order.status.in_(['pending', 'completed'])
).count()
```

`[CÓDIGO]` `'completed'` **no pertenece** a la máquina de estados de pedidos, que
es `pending | confirmed | delivered | cancelled | expired`
(`app/services/order_service.py:208-214`).

**Impacto:** el conteo solo considera pedidos en `pending`. Un atacante cuyos
pedidos fueran confirmados rápidamente (`confirmed`) **no sería contabilizado**,
y el límite de 3/minuto se podría superar.

**Atenuante:** en la práctica los pedidos recién creados están en `pending`
durante un tiempo, así que la protección funciona en el caso habitual.

`[INFERIDO]` Parece un residuo de una nomenclatura de estados anterior.

---

<a id="r-07"></a>
## 🟠 R-07 — `SESSION_COOKIE_SECURE = False` sin forma de activarlo por entorno

**Estado:** `[CÓDIGO]`.

`settings.py:109`:

```python
SESSION_COOKIE_SECURE = False  # True en producción con HTTPS
```

El comentario describe lo que **debería** pasar, pero **no hay ningún mecanismo
que lo haga**: no se lee de una variable de entorno ni hay una clase de
configuración por entorno.

`[EJECUTADO]` La cookie observada fue
`session=…; HttpOnly; Path=/; SameSite=Lax` — **sin `Secure`**.

**Impacto:** la cookie de sesión puede viajar por HTTP. `SameSite=Lax` y HSTS
mitigan bastante, pero no es equivalente.

---

<a id="r-08"></a>
## 🟠 R-08 — El rate limiter global es por proceso y en memoria

**Estado:** `[CÓDIGO]`.

`app/extensions.py:22-27`: `storage_uri = RATELIMIT_STORAGE_URL` o **`memory://`**.

**Consecuencias:**
1. Con `gunicorn --workers 3`, cada worker lleva su propio contador → el límite
   efectivo es **3×** el configurado.
2. Se pierde en cada reinicio o despliegue.

**Agravante:** `app/__init__.py:22-24` exime del límite a **cualquier usuario con
sesión iniciada**:

```python
@limiter.request_filter
def exempt_admins():
    return 'user_id' in session
```

`[INFERIDO]` Basta con autenticarse para no tener límite alguno en las rutas
protegidas por Flask-Limiter.

---

<a id="r-09"></a>
## 🟡 R-09 — `output.css` está versionado y se regenera distinto

**Estado:** `[EJECUTADO]`.

`app/static/CSS/output.css` (148 KB minificados) está en Git. Tras
`npm run build:css`, `git status` marca el archivo como modificado aunque no haya
cambiado nada del código fuente.

**Impacto:** ruido en cada PR, conflictos de fusión en un archivo generado, y
riesgo de que el CSS versionado se desincronice del que produce el build.

**Nota:** durante esta revisión el archivo se **restauró con
`git checkout --`** para dejar el árbol limpio.

---

<a id="r-10"></a>
## 🟡 R-10 — Cinco errores `F821` en total y el CI no rompe con el lint

**Estado:** `[EJECUTADO]`.

```
app/routes/api_dashboard.py:215:9: F821 undefined name 'db'
app/routes/api_dashboard.py:234:9: F821 undefined name 'db'
app/utils/auth.py:116:41: F821 undefined name 'datetime'
app/utils/auth.py:116:54: F821 undefined name 'timezone'
app/utils/auth.py:117:17: F821 undefined name 'db'
```

`.github/workflows/ci.yml:64` ejecuta
`flake8 app/ --max-line-length=120 --exit-zero`: **el lint no puede fallar**.

`[INFERIDO]` Con `--select=F821` sin `--exit-zero`, R-01 y R-02 se habrían
detectado en el primer PR. Ambos defectos existen precisamente porque esta
comprobación está desactivada.

Otros hallazgos del mismo análisis: 41 `F401` (importaciones sin usar), 8 `F841`
(variables sin usar), 5 `F811` (redefiniciones) y 2 `F601`
(`app/services/insights/data_service.py:379-380`, clave de diccionario `60`
repetida con valores distintos — el segundo valor gana silenciosamente).

---

<a id="r-11"></a>
## 🟡 R-11 — Código y artefactos muertos en el repositorio

**Estado:** `[EJECUTADO]` / `[INFERIDO]`.

| Elemento | Evidencia |
|---|---|
| `app/templates/public/subscription_expired.html` | **Inalcanzable**: Flask usa `template_folder='template'`. `grep` en todo el repo: 0 referencias |
| `gunicorn_config.py` | Ningún entrypoint lo carga |
| `test_flask_output.txt` (0 bytes), `test_flask_errors.txt` | Salidas de depuración versionadas |
| `test_qr_*.png` (3 archivos, 43 KB) | Capturas de prueba en la raíz |
| `menu_check.json` (18 KB) | Volcado de diagnóstico en la raíz |
| `video_presentation/` | Material de marketing de abril 2026 |
| `backups/felicia_reset_2026-09-03/snapshot.json` | Copia puntual de datos de un cliente |
| `migrations/versions/backup/` (3) | Migraciones fuera de la cadena |
| `migrations/supabase_schema.sql` | Sin referencias en `app/` |
| 6 plantillas Jinja2 sin referencia | `auth/clerk_handshake.html`, `auth/privacy.html`, `auth/terms.html`, `components/product_macros.html`, `email/change_email.html`, `errors/400.html` |

`[CÓDIGO]` `auth/privacy.html` y `auth/terms.html` son coherentes con lo
observado: `[EJECUTADO]` `/privacy` y `/terms` responden **302 → `/legal`**.

`[INFERIDO]` Las 6 plantillas podrían cargarse dinámicamente; **verificar antes
de eliminar**.

---

<a id="r-12"></a>
## 🟡 R-12 — `rescues_db.py`: script destructivo sin salvaguardas

**Estado:** `[CÓDIGO]`.

En la raíz del repositorio, `rescues_db.py` ejecuta:

```python
db.session.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
db.session.execute(text("DROP TABLE IF EXISTS ai_token_transactions;"))
db.session.execute(text("DROP TABLE IF EXISTS ai_token_wallets;"))
```

Sin confirmación, sin comprobar el entorno y sin copia de seguridad. Usa la
`DATABASE_URL` del `.env` **que esté cargado en ese momento**: ejecutarlo por
error con el `.env` de producción destruiría las billeteras de créditos de todos
los usuarios.

Además, `SET FOREIGN_KEY_CHECKS` es **sintaxis exclusiva de MySQL**: fallaría en
PostgreSQL, que es lo que apuntan el CI y los scripts de `deploy/`.

---

<a id="r-13"></a>
## 🟡 R-13 — Herramientas de calidad atadas a Windows

**Estado:** `[CÓDIGO]`.

| Herramienta | Atadura |
|---|---|
| k6 | `package.json`: `"k6": "C:\\PROGRA~1\\k6\\k6.exe"` |
| Auditoría de seguridad | 5 scripts `.ps1` (ZAP, Trivy, gitleaks) |
| Guía de inicio | `AGENTS.md`: `.\.venv\Scripts\Activate.ps1` |

**Impacto:** en Linux/macOS (y en el CI, que es `ubuntu-latest`) **ninguna de
estas suites se puede ejecutar**. No hay instrucciones de instalación para
sistemas no-Windows en ningún documento del repositorio.

---

<a id="r-14"></a>
## 🟡 R-14 — Archivos que superan el límite que el propio proyecto se impuso

**Estado:** `[EJECUTADO]`.

`AGENTS.md` establece: *"Archivos de **800+ líneas** se consideran críticos y
requieren factorización sí o sí"* y *"Archivos de 500+ líneas — NO refactorizar
automático"*.

| Archivo | Líneas | Regla |
|---|---|---|
| `app/services/insights/data_service.py` | **931** | 🔴 supera el umbral crítico de 800 |
| `app/routes/employees.py` | 640 | 🟠 >500 |
| `app/routes/dashboard.py` | 626 | 🟠 >500 |
| `app/services/dashboard_service.py` | 625 | 🟠 >500 |
| `app/services/order_service.py` | 622 | 🟠 >500 |
| `app/routes/auth.py` | 561 | 🟠 >500 |
| `app/services/auth_service.py` | 542 | 🟠 >500 |
| `app/routes/insights.py` | 536 | 🟠 >500 |
| `app/utils/subscription.py` | 530 | 🟠 >500 |
| `app/services/insights/message_handler.py` | 517 | 🟠 >500 |
| `app/services/public_menu_service.py` | 509 | 🟠 >500 |

**11 archivos** por encima de 500 líneas; **1** por encima del umbral crítico.

---

<a id="r-15"></a>
## 🟡 R-15 — Sin endpoint de salud

**Estado:** `[EJECUTADO]`.

Entre las 200 rutas **no hay ninguna** `/health`, `/healthz` o `/status`.

**Impacto:** nginx, systemd y el workflow de despliegue no tienen contra qué
verificar que la aplicación quedó viva tras un despliegue. La existencia de
`deploy/debug_502.sh` sugiere que los 502 posteriores al despliegue han sido un
problema real.

---

# Parte B — Contradicciones documentales

> Aquí no hay bugs: hay fuentes del propio repositorio que **se contradicen entre
> sí**. Cada una necesita que alguien decida cuál es la correcta.

<a id="c-01"></a>
## C-01 — ¿Qué motor de base de datos usa el sistema? (cuatro respuestas distintas)

| Fuente | Dice |
|---|---|
| `README.md:21` | *"Backend: Python (Flask), SQLAlchemy, **MySQL**"* |
| `AGENTS.md:3` | *"**MariaDB** (XAMPP, local) / **MySQL 8** (CI, prod)"* |
| `settings.py:22` | Valor por defecto: **`postgresql+psycopg2://localhost/orderfox`** |
| `.env.example:7` | `DATABASE_URL=mysql+pymysql://root:@localhost/orderfox` |
| `.github/workflows/ci.yml:14` | Servicio **`postgres:14`** |
| `Dockerfile:4` | Instala **`libpq-dev`** (PostgreSQL) |
| `Dockerfile.dev:4` | Instala **`default-libmysqlclient-dev`** (MySQL) |
| `deploy/backup_pg.sh`, `setup_pg.sql`, `pg_listen.conf` | **PostgreSQL** |
| `requirements.txt` | Instala **ambos** drivers: `PyMySQL` **y** `psycopg2-binary` |
| `rescues_db.py` | `SET FOREIGN_KEY_CHECKS` → **solo MySQL** |
| `migrations/supabase_schema.sql` | **PostgreSQL** (Supabase) |

`[INFERIDO]` Lo más probable: **producción y CI usan PostgreSQL**; el desarrollo
local histórico usaba MariaDB/XAMPP; y la documentación se quedó en el estado
anterior.

**Consecuencia real:** las pruebas corren en SQLite, el CI en PostgreSQL y el
desarrollo local (según `AGENTS.md`) en MariaDB. **Tres motores distintos en tres
entornos** — cualquier diferencia de dialecto (bloqueos `FOR UPDATE`, tipos de
fecha, `ON CONFLICT`) queda sin cubrir.

> Ver [07-preguntas-pendientes.md](07-preguntas-pendientes.md) (**D-01**, la
> decisión más importante de esta lista).

---

<a id="c-02"></a>
## C-02 — ¿Cuánto dura la prueba gratuita? ¿10 o 60 días?

| Fuente | Dice |
|---|---|
| `README.md:17` | *"Prueba gratuita de **10 días** sin tarjeta de crédito"* |
| `app/utils/subscription.py:58` | `'name': 'Prueba Premium · **60 días**'` |
| `app/utils/subscription.py:60` | `'duration_days': **60**` |

**El código concede 60 días.** Es una discrepancia con impacto comercial directo:
seis veces más producto gratis del que anuncia la página pública.

---

<a id="c-03"></a>
## C-03 — ¿Cuánto dura el periodo de gracia? ¿5 o 10 días?

| Fuente | Dice |
|---|---|
| `app/utils/subscription.py:96` | `GRACE_PERIOD_DAYS = **5**` |
| `app/utils/subscription.py:105` (docstring) | *"permite el acceso durante los **10 días** post-expiración"* |

**El código aplica 5 días.** El docstring está justo encima de la constante que
lo desmiente.

---

<a id="c-04"></a>
## C-04 — ¿Qué versión es esta? (cinco respuestas)

| Fuente | Versión |
|---|---|
| `settings.py:9` | `APP_VERSION = '1.4.0'` |
| `AGENTS.md:4` | `v1.4.0` |
| `app/routes/api_docs.py:31` | `version='1.3.0'` (título de la spec OpenAPI) |
| `docs/README.md:3` | *"Versión del proyecto: **1.3.0**"* |
| `package.json` | `"version": "1.0.0"` |
| `CHANGELOG.md` | Entrada más reciente: `[**1.6.0**] - 2026-08-22 (sin release / working tree)` |
| Etiquetas Git | **ninguna** |

`[EJECUTADO]` `git tag` no devuelve nada. **No existe ninguna fuente fiable de la
versión desplegada.** `AGENTS.md` ya reconocía el problema (*"`settings.APP_VERSION`
está desactualizado, no sincronizado con tags de git"*), pero la versión que
cita como correcta tampoco coincide con el CHANGELOG.

**Consecuencia:** la etiqueta `release` que se envía a Sentry
(`app/__init__.py:100`) es `APP_VERSION`, es decir `1.4.0`: los errores de
producción se agrupan bajo una versión que no corresponde al código desplegado.

---

<a id="c-05"></a>
## C-05 — La documentación OpenAPI describe rutas que no existen

`[EJECUTADO]` `GET /api/docs/spec.json` documenta **15 rutas**. Dos de ellas
devuelven **404** al invocarlas:

| En la spec | Real | Respuesta a la de la spec |
|---|---|---|
| `POST /api/auth/sync-clerk` | `POST /api/sync-clerk` | **404** |
| `POST /api/orders/create` | `POST /api/orders` | **404** |

Además, la cobertura es del **≈23 %**: 15 rutas documentadas frente a ~65
endpoints JSON reales.

---

<a id="c-06"></a>
## C-06 — El CI no usa la base de datos que dice `AGENTS.md`

| Fuente | Dice |
|---|---|
| `AGENTS.md:3` | *"MySQL 8 (**CI**, prod)"* |
| `AGENTS.md` (sección Arquitectura) | *"CI corre contra **MySQL** en contenedor"* |
| `.github/workflows/ci.yml:12-27` | Servicio **`postgres:14`** |

Es un caso concreto de C-01, pero conviene señalarlo aparte porque `AGENTS.md`
es el documento que leen los desarrolladores y los agentes de IA antes de tocar
nada.

---

<a id="c-07"></a>
## C-07 — Discrepancias menores entre documentación y código

| # | Contradicción | Fuentes |
|---|---|---|
| 1 | `LANDING_URL` por defecto | `settings.py:52` → `https://menu.velzia.shop/` vs `.env.example:73` → `https://velzia.shop/` |
| 2 | Estados de reserva en español en el comentario, en inglés en el código | `app/models/reservations.py:37` (`pendiente | confirmada | …`) vs valores reales `pending | confirmed | …` |
| 3 | `grace_period` descrito como estado de `subscription_state` | `AGENTS.md` lo lista como estado; la columna solo admite `active`, `cancellation_pending`, `dormant` — la gracia se calcula con fechas |
| 4 | `docs/README.md` no incluye `GUIDE-09_Better_Stack.md`, que sí existe | `docs/README.md` vs `docs/02-GUIDES/` |
| 5 | `AGENTS.md` referencia `PROC-03` implícitamente por numeración; el archivo no existe | `docs/03-PROCEDURES/` salta de `PROC-02` a `PROC-04` |
| 6 | El README promete que `docker compose up -d` deja la app en `localhost:5000` | No hay servicio de base de datos y `receipt-scanner` requiere un repo hermano ausente |
| 7 | `LOG_FORMAT=json` se lee pero nunca se aplica | `settings.py:124` vs `app/__init__.py:39-41` (`logging.basicConfig` sin formateador JSON) |

---

# Parte C — Lo que está bien

> Un diagnóstico honesto también registra lo que no hay que tocar.

| Fortaleza | Evidencia |
|---|---|
| **Idempotencia pensada a nivel de base de datos** | `UNIQUE(restaurant_id, idempotency_key)` en pedidos, `UNIQUE(mp_payment_id)` en transacciones, `UNIQUE(restaurant_id, period_start)` en cierres de caja |
| **Concurrencia tratada explícitamente** | `SELECT ... FOR UPDATE` en el consumo de créditos (`token_service.py:131`); contador atómico `order_counters`; hay una suite `test_race_conditions.py` |
| **Política de datos conservadora** | Las cuentas nunca se borran: pasan a `dormant` con todos los datos (`app/tasks.py:30-38`). Los históricos sobreviven con `SET NULL` |
| **Trazabilidad de pedidos** | `OrderEvent` registra actor, rol, tipo y metadatos de cada cambio |
| **Defensa en profundidad contra bots** | Honeypot + tiempo mínimo de 3 s + rate limit por IP en base de datos |
| **Verificación de firmas de webhooks** | HMAC-SHA256 con `hmac.compare_digest` (`app/utils/mp_webhook.py:34-50`); Svix para Clerk |
| **Redacción de datos sensibles en Sentry** | `before_send` filtra cabeceras y campos como `password`, `token`, `api_key` (`app/__init__.py:52-92`) |
| **Cabeceras de seguridad completas** | 7 cabeceras verificadas en ejecución, incluida HSTS |
| **Protección anti-inyección de prompts** | 3 capas documentadas y presentes en el código (`message_handler.py`, `llm_service.py`) |
| **Benchmarks con k-anonymity** | Solo medianas, solo cohortes con k ≥ 5 (`benchmark_service.py`) |
| **Cobertura razonable** | 58,38 %, muy por encima del umbral del 35 %, con 620 pruebas que pasan |
| **Decisiones difíciles documentadas *en el propio código*** | El porqué de la hora local en reservas (`models/reservations.py:4-12`), el porqué del CSRF manual (`__init__.py:104-112`), el porqué de un `import` a nivel de módulo (`__init__.py:148-152`) |
| **Migraciones lineales** | 31 migraciones, **una sola cabeza**, se aplican sin error desde cero |
| **Dependencias fijadas** | Las 60 con `==`, sin conflictos al instalar |
