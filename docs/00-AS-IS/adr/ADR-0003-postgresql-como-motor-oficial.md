# ADR-0003 — PostgreSQL es el motor de base de datos oficial

| Campo | Valor |
|---|---|
| **Estado** | Aceptado |
| **Fecha** | 2026-09-29 |
| **Decide** | Daniel (propietario del producto) |
| **Commit de referencia** | `cd96aa7` (diagnóstico) |
| **Clasificación de la evidencia** | **`[CONFIRMADO]`** — validado por el propietario |

> Primer ADR de este repositorio con una decisión **confirmada por el
> propietario**, no inferida del código.

---

## Contexto

El diagnóstico encontró **siete fuentes del repositorio dando tres respuestas
distintas** sobre qué motor de base de datos usa el sistema (C-01 / VLZ-4):

| Fuente | Decía |
|---|---|
| `README.md:21` | MySQL |
| `AGENTS.md:3` | MariaDB local / MySQL 8 en CI y producción |
| `settings.py:22` | `postgresql+psycopg2` por defecto |
| `.env.example:7` | `mysql+pymysql` |
| `.github/workflows/ci.yml:14` | servicio `postgres:14` |
| `Dockerfile:4` | `libpq-dev` (PostgreSQL) |
| `Dockerfile.dev:4` | `default-libmysqlclient-dev` (MySQL) |
| `deploy/backup_pg.sh`, `setup_pg.sql`, `pg_listen.conf` | PostgreSQL |
| `requirements.txt` | **ambos** drivers instalados |

**Consecuencia medida:** las pruebas corrían en SQLite, el CI en PostgreSQL y
el desarrollo local documentado en MariaDB. Tres motores en tres entornos, con
ninguna prueba cubriendo las diferencias de dialecto.

Esto importaba especialmente en el consumo de créditos de IA, que depende de un
bloqueo pesimista (`app/services/token_service.py:131`) cuyo comportamiento
difiere entre motores y que en SQLite es prácticamente un no-op.

## Decisión

**PostgreSQL es el motor oficial**, en producción, en CI y en desarrollo local.

Confirmado por el propietario el 2026-09-29, coincidiendo con lo que ya hacían
el CI y los scripts de `deploy/`. La documentación era la que iba por detrás.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| MySQL / MariaDB | Habría obligado a rehacer el CI y todos los scripts de `deploy/`, que ya son PostgreSQL. Más trabajo para llegar al mismo sitio |
| Soportar ambos deliberadamente | Duplica la superficie de prueba de un equipo pequeño, sin beneficio claro |

## Consecuencias

**Ya aplicadas** (commit de este ADR)

- `README.md` → «SQLAlchemy, PostgreSQL»
- `AGENTS.md` → stack actualizado
- `.env.example` → `postgresql+psycopg2://…`
- `Dockerfile.dev` → `libpq-dev` en vez de `default-libmysqlclient-dev`

**Pendientes, porque afectan a la máquina del propietario**

- Retirar `PyMySQL==1.1.2` de `requirements.txt`. Ningún módulo de `app/` lo
  importa —solo se menciona en un comentario de
  `app/services/insights/benchmark_service.py:42`— pero si el entorno local
  sigue en MariaDB/XAMPP, quitarlo lo rompe.
- Revisar la sección de `AGENTS.md` que describe la herramienta MCP
  `Conexion_MYSQL` apuntando a XAMPP en el puerto 3306.
- Decidir si la suite de pruebas deja de forzar SQLite
  (`tests/conftest.py:6`) o si al menos una suite de integración corre contra
  PostgreSQL real. **Sin esto, la decisión no cambia lo que se prueba.**

**Coste asumido**

Las pruebas seguirán en SQLite mientras no se aborde el último punto, así que
las diferencias de dialecto siguen sin cubrirse. La decisión alinea la
documentación y las imágenes, no todavía la verificación.

## Evidencia

- Contradicción documentada en `docs/00-AS-IS/06-riesgos-y-deuda-tecnica.md` § C-01
- Decisión en `docs/00-AS-IS/07-preguntas-pendientes.md` § D-01
- Seguimiento en Linear: **VLZ-4**
