# Diagnóstico AS-IS — Orderfox / Velzia

> **Qué es esto:** una descripción de **lo que el sistema hace hoy**, reconstruida
> leyendo y ejecutando el código. No es una propuesta, ni un diseño, ni una lista
> de mejoras. Los cambios deseados (TO-BE) **no** viven en esta carpeta.

---

## 1. Línea base — ¿qué versión exacta estamos documentando?

| Dato | Valor |
|---|---|
| Repositorio | `danielririver01/Orderfox` |
| Rama principal | `main` |
| Rama de este análisis | `arena/01a0eae0-orderfox` (derivada de `main`) |
| **Commit de referencia** | `cd96aa763c086dea93e4aede46191b9add9067fa` |
| Mensaje del commit | `fix: toast fuera de pantalla en móvil — una sola fuente de verdad de posicionamiento` |
| Fecha del commit | 2026-09-18 13:22:02 -0500 |
| Autor | Daniel |
| Etiquetas Git | **ninguna** (`git tag` no devuelve resultados) |
| Fecha del diagnóstico | 2026-09-29 |
| Estado del working tree | limpio — **no se modificó una sola línea de código de la aplicación** |

> ⚠️ **No hay ninguna etiqueta Git en el repositorio.** La única referencia estable
> para este diagnóstico es el hash del commit. Crear una etiqueta (p. ej.
> `as-is-2026-09-29`) apuntando a `cd96aa7` es una decisión pendiente del
> propietario — ver [07-preguntas-pendientes.md](07-preguntas-pendientes.md) (D-11).

### Entorno verificado en esta revisión

| Componente | Versión usada aquí | Versión que declara el proyecto |
|---|---|---|
| Python | **3.11.2** (Debian 12) | 3.12+ (README, Dockerfile, CI) |
| Node.js | 22.22.3 | 20 (CI, Dockerfile) |
| npm | 10.9.8 | — |
| Base de datos usada para verificar | SQLite (archivo y memoria) | MySQL / MariaDB / PostgreSQL, según el documento que se lea |
| Docker | **no disponible** en el entorno de revisión | requerido por `docker-compose.yml` |
| Git | 2.39.5 | — |

Las dependencias de `requirements-dev.txt` **se instalaron sin errores sobre
Python 3.11**, pese a que el proyecto declara 3.12+.

---

## 2. Cómo leer estos documentos — clasificación de cada hallazgo

Cada afirmación relevante lleva una etiqueta. **No hay inferencias presentadas
como requisitos aprobados.**

| Etiqueta | Significado |
|---|---|
| `[EJECUTADO]` | Comprobado ejecutando el sistema en esta revisión. Se indica el comando y la salida. |
| `[CÓDIGO]` | Leído directamente en el código fuente. Se cita `archivo:línea`. |
| `[INFERIDO]` | Deducción razonable a partir del código. **Puede estar equivocada.** |
| `[CONTRADICCIÓN]` | Dos fuentes del repositorio se contradicen. Se citan ambas. |
| `[PENDIENTE]` | Requiere confirmación del propietario del producto. |
| `[CONFIRMADO]` | Validado por el propietario. **Hoy no hay ninguno: no ha habido sesión de validación.** |

> **Estado actual:** ningún hallazgo está en `[CONFIRMADO]`. Todo lo que aparece
> aquí proviene del código y de su ejecución, no de una decisión de negocio
> validada.

---

## 3. Índice

| Documento | Contenido |
|---|---|
| [01-inventario.md](01-inventario.md) | Estructura, puntos de entrada, módulos, dependencias, configuración, tests, CI/CD, código sin uso |
| [02-arquitectura-actual.md](02-arquitectura-actual.md) | Componentes, capas, blueprints, límites, integraciones externas, tareas programadas |
| [03-modelo-de-datos.md](03-modelo-de-datos.md) | 27 tablas, relaciones, estados, restricciones y *drift* entre modelos y migraciones |
| [04-flujos-funcionales.md](04-flujos-funcionales.md) | Tabla Función / Usuario / Entrada / Resultado / Evidencia + reglas de negocio extraídas |
| [05-compilacion-y-despliegue.md](05-compilacion-y-despliegue.md) | Instalación reproducible verificada, pruebas, build, despliegue |
| [06-riesgos-y-deuda-tecnica.md](06-riesgos-y-deuda-tecnica.md) | Hallazgos priorizados, 2 bugs reproducidos, contradicciones documentales |
| [07-preguntas-pendientes.md](07-preguntas-pendientes.md) | Decisiones cortas que necesita responder el propietario |
| [adr/](adr/) | Registros de decisiones de arquitectura de este ejercicio |

---

## 4. Alcance y límites de este diagnóstico

**Lo que sí se hizo:**

- Se instalaron las dependencias reales y se arrancó la aplicación Flask.
- Se extrajo el mapa de rutas **en ejecución** (200 reglas, 25 blueprints).
- Se ejecutó la suite completa de pruebas (`pytest`) y se identificó la causa raíz de cada fallo.
- Se aplicaron las 31 migraciones de Alembic sobre una base limpia.
- Se compararon los modelos SQLAlchemy contra la cabeza de migraciones (`flask db check`).
- Se compiló el CSS de producción (Tailwind 4).
- Se hicieron peticiones HTTP reales contra 13 endpoints.
- Se reprodujeron dos errores de ejecución con guiones aislados.

**Lo que NO se hizo (y por qué):**

| No verificado | Motivo |
|---|---|
| MySQL / MariaDB / PostgreSQL reales | No hay motor de base de datos en el entorno de revisión. Se usó SQLite. |
| Docker / `docker compose up` | Docker no está instalado en el entorno de revisión. |
| Frontend Astro en ejecución | No se instalaron sus dependencias; se documenta por lectura de código. |
| Clerk, Mercado Pago, Cloudinary, DeepSeek, Tavily, ntfy.sh, Unsplash, Gemini | Servicios externos: requieren credenciales reales. |
| Scanner IA (`Receipt-Scanner-AI`) | Repositorio **externo**, no incluido en este checkout. |
| Pruebas de carga k6 y auditoría ZAP/Trivy | Requieren binarios y scripts PowerShell no disponibles aquí. |
| Interfaz de usuario real (recorrido pantalla por pantalla) | Requiere datos sembrados y sesión autenticada con Clerk. |

**Consecuencia:** el comportamiento en producción con MySQL/PostgreSQL puede
diferir del verificado con SQLite, especialmente en bloqueos (`SELECT ... FOR
UPDATE`), tipos de fecha y restricciones únicas.

---

## 5. Dónde vive cada cosa

El diagnóstico está repartido en tres sitios, **sin mantener el mismo documento
en dos de ellos**. La decisión y su justificación están en
[adr/ADR-0002](adr/ADR-0002-distribucion-entre-repo-google-docs-y-linear.md).

| Destino | Qué contiene | Enlace |
|---|---|---|
| **Este repositorio** (`docs/00-AS-IS/`) | Inventario, arquitectura, modelo de datos, catálogo de funciones **con su evidencia `archivo:línea`**, compilación, pruebas, despliegue y ADR | estás aquí |
| **Google Docs** | Visión, alcance y reglas de negocio **en lenguaje de negocio**, sin referencias al código | [Velzia — Visión, alcance y reglas de negocio](https://docs.google.com/document/d/1yDKcLooFkk72JCBDiMWJq8_qXV43IfyvC7nZmmXDUsE/edit) |
| **Linear** | Los hallazgos convertidos en trabajo accionable: 20 incidencias con evidencia y criterio de cierre | equipo **Velzia**, proyecto *Diagnóstico AS-IS (commit cd96aa7)* — `VLZ-1` … `VLZ-20` |

### Regla de precedencia

> Las reglas de negocio aparecen en dos formas: **trazable** (documento 04 de
> este repositorio, con `archivo:línea`) y **legible** (Google Docs, en lenguaje
> de negocio). No son dos copias del mismo documento, pero **describen el mismo
> comportamiento**.
>
> **El repositorio manda.** Si una regla cambia, se actualiza aquí primero y
> después en Google Docs. El documento de Google no lleva evidencia
> precisamente para que nadie lo confunda con la fuente de verdad.

### Correspondencia entre hallazgos e incidencias

| Documento 06 | Linear |
|---|---|
| R-01 `NameError` en `require_active` | `VLZ-1` |
| R-02 `POST /api/dashboard/cancel-account` | `VLZ-2` |
| R-03 Drift modelos ↔ migraciones | `VLZ-3` |
| C-01 Motor de base de datos | `VLZ-4` |
| R-10 `flake8 --exit-zero` | `VLZ-5` |
| R-05 Crédito de IA no devuelto | `VLZ-6` |
| R-04 Scheduler múltiple | `VLZ-7` |
| R-06 Rate limiter con estado inexistente | `VLZ-8` |
| C-02 Prueba gratuita 10 vs 60 días | `VLZ-9` |
| Deuda de pruebas (doc 05 §4) | `VLZ-10` |
| R-07 `SESSION_COOKIE_SECURE` | `VLZ-11` |
| R-12 `rescues_db.py` | `VLZ-12` |
| R-15 + despliegue (doc 05 §6-7) | `VLZ-13` |
| C-04 Versión | `VLZ-14` |
| C-05 OpenAPI | `VLZ-15` |
| R-08 Rate limiter global | `VLZ-16` |
| C-03 + C-07 Contradicciones documentales | `VLZ-17` |
| R-09 + R-11 + R-14 Higiene del repositorio | `VLZ-18` |
| R-13 Herramientas solo-Windows | `VLZ-19` |
| Documento 07 (11 decisiones) | `VLZ-20` |

---

## 6. Separación AS-IS / TO-BE

- **AS-IS** — esta carpeta (`docs/00-AS-IS/`). Solo describe el estado actual.
- **TO-BE** — no existe todavía. No se ha creado ningún documento de propuesta,
  y los hallazgos del documento 06 **no son un plan de trabajo aprobado**: son
  observaciones a priorizar con el propietario.

La documentación previa del repositorio (`docs/01-ARCHITECTURE/`,
`docs/02-GUIDES/`, etc.) **no fue modificada**. En varios puntos contradice al
código; esas contradicciones están listadas en
[06-riesgos-y-deuda-tecnica.md](06-riesgos-y-deuda-tecnica.md), sin tocar los
documentos originales.
