# 06 — Operación (correr, probar, pilotear)

## Levantar todo en local

```bash
# 1. Entorno y DB (desde la raíz del monorepo)
.\.venv\Scripts\Activate.ps1
flask db upgrade                      # cadena de core (dueña de businesses)

# 2. Velzia Core → http://localhost:5000
python run.py

# 3. Menú público (Astro) → http://localhost:4321
cd astro; npm run dev

# 4. Mundo Verduras → http://localhost:5100
.\.venv\Scripts\python verduras/run.py
```

Puertos: core `5000` · Astro `4321` · **verduras `5100`**.
El módulo lee el `.env` de la raíz (`DATABASE_URL`, `VERDURAS_BASE_URL`,
`CORE_BASE_URL`, flags de báscula). Sin `.env`, revisar `.env.example`.

Alta de una verdulería (flujo completo):

1. Registro en core → selector `/register/vertical` → tarjeta Verdurería
   (`auth.register_verduras`) → plan + WhatsApp.
2. Core crea el Business directo + emite `pos_setup_token`.
3. El dueño abre `/pos/setup/<slug>/<token>` (puerto 5100): elige PIN,
   confirma WhatsApp. El enlace muere al usarse.
4. Operación diaria: `/pos/login` (slug + PIN) o handoff SSO desde
   "Tus mundos" en core (`/dashboard/mundos/pos/<slug>`).

## Suites de tests

| Suite | Comando | Qué cubre |
|-------|---------|-----------|
| Core | `pytest tests/` (sqlite in-memory) | Puente Business↔Restaurant, registro, hub, SSO, billing, cupos, delete |
| Módulo | `pytest verduras/tests` (sqlite in-memory) | Catálogo, ventas, inventario, POS, setup, SSO, escala, renewal |

No se mezclan (`pytest.ini` limita `testpaths` a `tests/`).

Tests clave del área:

- Core: `test_business_bridge.py`, `test_business_registration.py`,
  `test_register_vertical.py`, `test_worlds_hub.py`, `test_world_quota.py`,
  `test_mundos_pos_sso.py`, `test_user_billing.py`,
  `test_business_subscription.py`, `test_account_deletion.py`.
- Módulo: `test_catalog.py`, `test_sales.py`, `test_inventory.py`,
  `test_alerts.py`, `test_clientes.py`, `test_pos*.py` (pos, setup_token,
  sso, ventas, inventario, config, renewal), `test_scale.py`.

## Healthchecks del módulo

| Ruta | Qué dice |
|------|----------|
| `GET /` | Identidad (`module`, `version`) |
| `GET /health` | Liveness/readiness: proceso + DB compartida |
| `GET /health/core-bridge` | Diagnóstico: espejos vs businesses verduras |

## Roadmap (plan de producto Velzia Verduras)

| Semana | Módulo | Estado |
|--------|--------|--------|
| 1 | Catálogo + precios por peso | ✅ |
| 2 | Ventas por peso + pedidos WhatsApp + tickets | ✅ |
| 3 | Inventario (lotes, costo/kg) + Merma + tickets | ✅ |
| 4 | Báscula digital (opcional, apagada por defecto) | ✅ |
| 5 | Alertas de rotación (umbral opt-in por producto) | ✅ |
| 6 | **Piloto con cliente real** | ⬜ Pendiente |

## Decisiones diferidas (no perder)

1. **Báscula por negocio.** Hoy la config vive en `.env` (una báscula por
   servidor); debe moverse a `verduras_business_settings` (cada tendero,
   SU báscula). El endpoint ya acepta parámetros por llamada: el cambio
   de fuente es trivial. La pantalla de auto-detección espera a tener la
   primera báscula física para probar.
2. **Turnos de caja.** Ingreso/Retiro habilitado; turnos diferidos (v1 sin
   turnos).
3. **Delivery.** Eliminado del selector a propósito (decisión de producto
   2026-09-22). No re-agregar sin confirmación del dueño.
4. **Fusión a main.** Al fusionar `feature/verduras`: reconciliar cabezas
   de migración con `main` y re-estampar el dev DB una última vez.
5. **Auth del módulo #2.** Al construir el segundo vertical, extraer el
   patrón de `pos_auth.py` a `modules_common/auth.py` (ver `04-puentes.md`).
