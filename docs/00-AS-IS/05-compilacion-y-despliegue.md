# 05 — Compilación, ejecución y despliegue (AS-IS)

**Commit de referencia:** `cd96aa763c086dea93e4aede46191b9add9067fa` · **Fecha:** 2026-09-29

> Todo lo marcado `[EJECUTADO]` se ejecutó realmente en un entorno limpio
> (Debian 12, sin `.venv`, sin `node_modules`, sin base de datos previa) durante
> esta revisión. Los comandos y las salidas son reales, no copiados de otra
> documentación.

---

## 1. Requisitos previos

| Requisito | Declarado por el proyecto | Verificado aquí |
|---|---|---|
| Python | **3.12+** (`README.md`, `Dockerfile`, CI) | ✅ funcionó también con **3.11.2** |
| Node.js | 20 (CI, Dockerfile) | ✅ funcionó con **22.22.3** |
| Base de datos | MySQL / MariaDB / PostgreSQL *(no hay acuerdo — ver [C-01](06-riesgos-y-deuda-tecnica.md#c-01))* | ⚠️ solo se verificó con **SQLite** |
| Docker | Opcional (`docker-compose.yml`) | ❌ no disponible en el entorno de revisión |

---

## 2. Instalación reproducible verificada

### Paso 1 — Entorno virtual y dependencias de Python

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-dev.txt     # CI usa este, no requirements.txt
```

`[EJECUTADO]` Resultado: **éxito**. Se instalaron 110 paquetes. Dos requirieron
compilación de *wheel* (`Flask-APScheduler`, `svix`) y ambas terminaron bien.
**No hubo ningún conflicto de versiones** pese a que todas están fijadas con `==`.

> `[CÓDIGO]` `AGENTS.md` documenta el equivalente en Windows
> (`.\.venv\Scripts\Activate.ps1`). **No hay instrucciones para Linux/macOS en
> ningún documento del repositorio.**

### Paso 2 — Dependencias de Node y CSS

```bash
npm install
npm run build:css
```

`[EJECUTADO]` Resultado: **éxito**.

```
> tailwindcss -i ./app/static/CSS/src/input.css -o ./app/static/CSS/output.css --minify
≈ tailwindcss v4.2.4
Done in 313ms
```

Genera `app/static/CSS/output.css` (**148.868 bytes**).

> ⚠️ `[EJECUTADO]` **`app/static/CSS/output.css` está versionado en Git** y
> reconstruirlo produce una diferencia (cambia el carácter final de línea), por
> lo que `git status` queda sucio tras cada build. Ver
> [R-09](06-riesgos-y-deuda-tecnica.md#r-09).
>
> `[CÓDIGO]` No existe `tailwind.config.js`: Tailwind 4 se configura desde
> `app/static/CSS/src/input.css`.

### Paso 3 — Variables de entorno

```bash
cp .env.example .env
# y editar al menos SECRET_KEY
```

`[CÓDIGO]` `settings.py:14-18` **aborta el arranque** si falta `SECRET_KEY`:

```
ValueError: SECRET_KEY no está configurada.
```

**Variables mínimas para arrancar** (verificado):

| Variable | Obligatoria | Nota |
|---|---|---|
| `SECRET_KEY` | ✅ **sí** | Sin ella la app no arranca |
| `DATABASE_URL` | recomendable | Si falta, cae en `postgresql+psycopg2://localhost/orderfox` (`settings.py:22`) |
| `JWT_SECRET_KEY` | no | Si falta, reutiliza `SECRET_KEY` |
| `CLERK_SECRET_KEY` | no para arrancar | ✅ **sí para la suite de pruebas** (ver §4) |

Todas las demás (Mercado Pago, Cloudinary, DeepSeek, Tavily, Unsplash, Gemini,
correo, Sentry) son opcionales: sin ellas la funcionalidad correspondiente falla
en tiempo de ejecución, pero la aplicación arranca.

### Paso 4 — Migraciones

```bash
export FLASK_APP=app
flask db upgrade
```

`[EJECUTADO]` Resultado: **éxito sobre SQLite**. Se aplicaron las **31**
migraciones desde `baf135af1685_fresh_start` hasta `c0a5f7e8d9b1`.

`[EJECUTADO]` `flask db heads` → `c0a5f7e8d9b1 (head)`: **una sola cabeza**, sin
ramas divergentes.

### Paso 5 — Arrancar

```bash
python run.py                 # http://localhost:5000
```

`[EJECUTADO]` Arranca correctamente. Log de inicio:

```
INFO:apscheduler.scheduler:Scheduler started
INFO:apscheduler.scheduler:Added job "manage_subscription_lifecycle" ...
... (7 jobs)
 * Running on all addresses (0.0.0.0)
```

**Frontend Astro (proceso separado):**

```bash
cd astro && npm install && npm run dev      # http://localhost:4321
```

`[CÓDIGO]` No verificado en esta revisión. `astro/astro.config.mjs` define el
proxy `/menu/api → http://localhost:5000`, así que **Flask debe estar corriendo
antes**.

---

## 3. Verificación de humo — respuestas reales

`[EJECUTADO]` Peticiones HTTP contra la instancia arrancada:

| Método y ruta | Código | Redirección |
|---|---|---|
| `GET /` | **301** | `https://menu.velzia.shop/` |
| `GET /login` | **200** | — |
| `GET /planes` | **200** | — |
| `GET /legal` | **200** | — |
| `GET /terms` | **302** | `/legal` |
| `GET /privacy` | **302** | `/legal` |
| `GET /api/docs/` | **200** | Swagger UI |
| `GET /api/docs/spec.json` | **200** | OpenAPI 3.0.3, 15 rutas |
| `GET /dashboard/` | **302** | `/login` (protección correcta) |
| `GET /insights/` | **302** | `/login` (protección correcta) |
| `GET /menu` | **404** | Sin restaurante activo en la base vacía |
| `GET /api/public/menu/noexiste` | **404** | Correcto |
| `GET /noexiste-404` | **404** | Página de error propia |
| `POST /api/auth/sync-clerk` | **404** | ⚠️ **ruta que la spec documenta pero no existe** |
| `POST /api/orders/create` | **404** | ⚠️ **ruta que la spec documenta pero no existe** |

`[EJECUTADO]` El mapa de rutas en ejecución contiene **200 reglas** y **25
blueprints**.

---

## 4. Pruebas

### 4.1 Hallazgo histórico: variable requerida para pruebas

`[EJECUTADO]` Ejecutando la suite **tal cual**, sin variables adicionales:

```
14 failed, 608 passed, 1049 warnings in 65.52s
```

`[EJECUTADO]` Ejecutando la suite **con `CLERK_SECRET_KEY` definida** (como hace
el CI):

```
2 failed, 620 passed, 1060 warnings in 63.52s
Cobertura total: 58.38 %   (umbral exigido: 35 %)
```

**Causa raíz de los 12 fallos que desaparecen:** `AuthService.delete_clerk_user`
devuelve `(False, 'Clerk no está configurado…')` cuando falta
`CLERK_SECRET_KEY` (`app/services/auth_service.py:403-405`), y 12 pruebas de
`tests/test_account_deletion.py` dependen de esa ruta. El CI lo resuelve fijando
`CLERK_SECRET_KEY: sk_test_dummy` (`.github/workflows/ci.yml:31`), pero **en el commit de referencia ningún documento del repositorio
mencionaba este requisito**. La guía vigente y `tests/conftest.py` ya lo
documentan/configuran; ver la actualización al final de esta sección.

> **Comando reproducible verificado:**
> ```bash
> SECRET_KEY=x JWT_SECRET_KEY=x CLERK_SECRET_KEY=sk_test_dummy \
>   CLERK_PUBLISHABLE_KEY=pk_test_dummy \
>   .venv/bin/python -m pytest -q
> ```

### 4.2 Hallazgo histórico: los 2 fallos de telemetría

`[EJECUTADO]` Ambos en `tests/test_copilot_follow_up_cap.py::TestLLMCallTelemetry`:

```
assert 502 == 200
WARNING app:message_handler.py:407 Web search failed: TAVILY_API_KEY no está configurada
INFO    app:token_service.py:160 WALLET: Token consumido para usuario 1
```

`[CÓDIGO]` En el commit de referencia el CI los excluía de forma permanente
con `-k "not TestLLMCallTelemetry"` (`.github/workflows/ci.yml:67`). Este
comportamiento ya no existe en el workflow vigente: actualmente se ejecuta
`pytest --tb=short -q --no-header` sin ese filtro.

`[INFERIDO]` En el commit de referencia estas dos pruebas dependían de una
llamada real al LLM. La implementación vigente simula DeepSeek y desactiva la
búsqueda web en el fixture `fake_deepseek`, por lo que no requiere
`TAVILY_API_KEY`, internet ni un proveedor externo.

### 4.3 Configuración de pruebas

| Aspecto | Valor | Evidencia |
|---|---|---|
| Base de datos | **`sqlite:///:memory:`** forzada | `tests/conftest.py:6` |
| Umbral de cobertura | **35 %** (actual: 58,38 %) | `pytest.ini:6` |
| Marcadores | `slow`, `integration` | `pytest.ini:7-9` |
| Fixtures | `app` (sesión), `db`/`client` (función), factorías `sample_*` | `tests/conftest.py` |

`[CÓDIGO]` **La suite nunca se ejecuta contra el motor de producción.** El CI
levanta PostgreSQL y corre `flask db upgrade` contra él, pero `conftest.py`
sobrescribe `DATABASE_URL` a SQLite antes de importar la app: las pruebas
**no** usan esa base.

### 4.4 Pruebas que no se pueden ejecutar aquí

| Suite | Motivo |
|---|---|
| k6 (`tests/k6/`) | `package.json` apunta a `C:\PROGRA~1\k6\k6.exe`: **solo Windows** |
| Seguridad (`tests/security/`) | Orquestada con `.ps1` (ZAP, Trivy): **solo Windows** |
| Frontend (`tests/frontend/*.test.js`) | `npm test` = `echo "Error: no test specified" && exit 1`: **no hay runner** |

---

## 5. Calidad de código

```bash
.venv/bin/flake8 app/ --max-line-length=120 --exit-zero --statistics
```

`[EJECUTADO]` Resumen (los más relevantes):

| Código | Nº | Significado |
|---|---|---|
| **F821** | **5** | **Nombre indefinido → `NameError` en ejecución** |
| F811 | 5 | Redefinición de un nombre sin usar |
| F841 | 8 | Variable local asignada y nunca usada |
| F601 | 2 | Clave de diccionario repetida con valores distintos |
| F401 | 41 | Importación sin usar |
| E501 | 69 | Línea de más de 120 caracteres |
| E302 | 96 | Faltan líneas en blanco entre definiciones |
| W293 | 103 | Línea en blanco con espacios |

> ⚠️ El CI ejecuta flake8 con **`--exit-zero`**: **el lint nunca rompe la
> construcción**, ni siquiera con los 5 `F821`. Ver
> [R-01](06-riesgos-y-deuda-tecnica.md#r-01) y [R-02](06-riesgos-y-deuda-tecnica.md#r-02).

`[CÓDIGO]` El CI ejecuta `pip-audit --strict` como puerta bloqueante y Bandit
como chequeo informativo (`--exit-zero`).

---

## 6. Ejecución con Docker

`[CÓDIGO]` No verificado (Docker no disponible). Documentado por lectura.

```bash
cp .env.example .env
docker compose up -d      # documentado en README.md
```

**Servicios de `docker-compose.yml`:**

| Servicio | Imagen / build | Puerto | Comando |
|---|---|---|---|
| `orderfox` | `Dockerfile` | 5000 | `flask db upgrade && gunicorn --workers 3 --timeout 120 run:app` |
| `orderfox-scheduler` | `Dockerfile` | — | `python run_scheduler.py` |
| `receipt-scanner` | `../Receipt-Scanner-AI` | 3000 | `pnpm prisma generate && pnpm start` |

### Problemas detectados en la configuración de Docker

| # | Problema | Evidencia |
|---|---|---|
| 1 | **No hay servicio de base de datos.** `docker-compose.yml` no define ningún contenedor de MySQL/PostgreSQL: la base debe existir fuera. | `docker-compose.yml` completo |
| 2 | **`docker-compose.override.yml` referencia un servicio `mysql` inexistente**, que no aparece en el fichero base. | `docker-compose.override.yml:2-4` |
| 3 | **`docker compose up` falla sin el repo hermano.** El servicio `receipt-scanner` se construye desde `../Receipt-Scanner-AI`, que no forma parte de este checkout. | `docker-compose.yml:37-38` |
| 4 | **Drivers incoherentes entre imágenes.** `Dockerfile` instala `libpq-dev` (PostgreSQL) y `Dockerfile.dev` instala `default-libmysqlclient-dev` (MySQL). | `Dockerfile:4`, `Dockerfile.dev:4` |
| 5 | **El README promete algo que no ocurre.** `README.md` dice que tras `docker compose up -d` la app estará en `localhost:5000`; con los puntos 1 y 3 eso no se cumple en un clon limpio. | `README.md:36-40` |

**Aspectos correctos del `Dockerfile` de producción:**
build multi-etapa (builder Python + builder CSS Node), `USER appuser` sin
privilegios, `FLASK_DEBUG=False`, `PYTHONUNBUFFERED=1`.

---

## 7. Despliegue en producción

`[CÓDIGO]` No verificado. Reconstruido desde `.github/workflows/ci.yml` y `deploy/`.

### Cadena de despliegue

```
push a main
   └─► job "test"  (PostgreSQL 14 · Python 3.12 · Node 20)
          └─► job "deploy"  (environment: production)
                 └─► SSH a Oracle Cloud
                        └─► cd /var/www/orderfox
                            bash -s < deploy/update_server.sh
```

### Infraestructura observada

| Elemento | Archivo |
|---|---|
| Proveedor | Oracle Cloud (ARM) — `gunicorn_config.py:1` |
| Proceso | systemd: `deploy/systemd/orderfox.service` |
| Proxy inverso | nginx: `deploy/nginx/orderfox.conf`, `orderfox_ssl.conf` |
| Preparación del servidor | `deploy/setup_server.sh` |
| Actualización | `deploy/update_server.sh` |
| Copias de seguridad | `deploy/backup_pg.sh` (**PostgreSQL**) |
| Base de datos | `deploy/setup_pg.sql`, `deploy/pg_listen.conf` (**PostgreSQL**) |
| Diagnóstico | `deploy/debug_502.sh` |

`[INFERIDO]` El nombre de los scripts (`backup_pg`, `setup_pg`, `pg_listen`) y el
servicio del CI indican que **producción usa PostgreSQL**, en contra de lo que
dicen `README.md` y `AGENTS.md` (MySQL/MariaDB). Ver
[C-01](06-riesgos-y-deuda-tecnica.md#c-01). `[PENDIENTE]` confirmar.

### Configuración de gunicorn: dos fuentes en conflicto

| Fuente | `bind` | `workers` | ¿Se usa? |
|---|---|---|---|
| `gunicorn_config.py` | `127.0.0.1:8000` | `CPU*2+1` | ❌ **ningún entrypoint lo carga** |
| `Dockerfile:41`, `start.sh:7`, `docker-compose.yml:19` | `0.0.0.0:5000` | `3` fijos | ✅ el real |

`[CÓDIGO]` `gunicorn_config.py` también define `accesslog`/`errorlog` en
`/var/log/orderfox/` y `preload_app = True`. **Nada de eso se aplica**, porque
no se pasa `-c gunicorn_config.py`.

`[INFERIDO]` Si se empezara a usar `gunicorn_config.py`, `preload_app = True`
cambiaría además el comportamiento del scheduler descrito en
[R-04](06-riesgos-y-deuda-tecnica.md#r-04).

### Sin rollback automatizado

`[CÓDIGO]` El workflow no contempla verificación posterior ni reversión. No hay
endpoint de salud (`/health`) contra el que comprobar el despliegue, ni paso de
*smoke test*. `deploy/debug_502.sh` sugiere que los errores 502 posteriores al
despliegue han sido un problema recurrente.

---

## 8. Resumen: ¿el sistema compila y ejecuta?

| Comprobación | Resultado |
|---|---|
| Instalar dependencias de Python | ✅ `[EJECUTADO]` |
| Instalar dependencias de Node | ✅ `[EJECUTADO]` |
| Compilar CSS | ✅ `[EJECUTADO]` (ensucia el árbol de Git) |
| Aplicar migraciones | ✅ `[EJECUTADO]` (SQLite) |
| Arrancar la aplicación | ✅ `[EJECUTADO]` |
| Responder peticiones HTTP | ✅ `[EJECUTADO]` (13 endpoints) |
| Suite de pruebas | ⚠️ `[EJECUTADO]` en el commit de referencia: 620/622; el estado vigente se ejecuta con variables dummy y sin excluir telemetría |
| Lint | ⚠️ `[EJECUTADO]` 5 errores `F821` reales, ocultos por `--exit-zero` |
| Modelos ↔ migraciones | ❌ `[EJECUTADO]` desincronizados ([R-03](06-riesgos-y-deuda-tecnica.md#r-03)) |
| Docker | ❓ no verificable aquí; configuración incompleta por lectura |
| Despliegue | ❓ no verificable aquí |

**Conclusión del snapshot:** el proyecto **compilaba y ejecutaba correctamente
en un entorno limpio**, con dos salvedades históricas: la variable
`CLERK_SECRET_KEY` necesaria para las pruebas y la ausencia de instrucciones
para Linux/macOS. La variable ya está documentada en la guía vigente y fijada
con un valor dummy en `tests/conftest.py`; la telemetría tampoco se excluye del
CI vigente.
