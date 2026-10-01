# Velzia Core + Mundos + Mundo Verduras

Documentación del desarrollo multi-vertical de Velzia (rama `feature/verduras`).
Es el hogar de todo lo relacionado con **Velzia Core**, el sistema de
**Mundos** y el **mundo Verduras** (Frubber POS) — para que cualquier
desarrollo futuro de esta área empiece y termine aquí.

> Estado: trabajo en rama `feature/verduras`, no mergeado a `main`.
> El tag `v1.6.0` sigue siendo la última versión estable del monolito.

## El sistema en 30 segundos

Velzia es un SaaS multi-vertical organizado en **mundos**: cada tipo de
negocio (restaurante, verdulería, farmacia…) es un mundo con su propio
frontend, pero todos comparten **Velzia Core**: identidad, facturación,
suscripciones y una sola base de datos.

```
┌─────────────────────────────────────────────────────────┐
│                      VELZIA CORE (Flask, :5000)          │
│  auth · billing · suscripciones · Copilot VZ (único)    │
│  Hub de Mundos · registro multi-vertical · SSO          │
└───────┬──────────────────────────────┬──────────────────┘
        │ DB compartida (businesses)   │ DB compartida (businesses)
┌───────▼──────────────┐   ┌───────────▼──────────────────┐
│ MUNDO Restaurante    │   │ MUNDO Verduras (:5100)       │
│ (monolito original)  │   │ Frubber POS — app Flask      │
│ menú QR · pedidos ·  │   │ propia: catálogo, ventas,    │
│ reservas · caja      │   │ inventario, merma, fiados    │
└──────────────────────┘   └──────────────────────────────┘
```

## Índice

| Archivo | Qué documenta |
|---------|---------------|
| `01-velzia-core.md` | Velzia Core: responsabilidades, entrypoints, puertos, reglas que no se rompen |
| `02-mundos.md` | El concepto Mundo: registro de verticales, selector, hub, registro multi-vertical, billing y cupos |
| `03-mundo-verduras.md` | El módulo `verduras/`: arquitectura, API, POS, inventario, ventas, auth y suscripción delegada |
| `04-puentes.md` | Integración core ↔ módulos: DB compartida, puente Business↔Restaurant, tokens, migraciones duales, reglas anti-duplicación |
| `05-datos.md` | Modelo de datos: tabla `businesses`, espejos, banda de IDs, tablas `verduras_*` |
| `06-operacion.md` | Cómo correr todo en local, suites de tests, roadmap y decisiones pendientes |

## Glosario

| Término | Significado |
|---------|-------------|
| **Velzia Core** | La app Flask original (`app/`): auth, billing, suscripciones, Copilot VZ, Hub de Mundos. Puerto 5000 |
| **Mundo** | Un vertical del SaaS con frontend propio (restaurante, verduras, farmacia…). Vive en `app/utils/verticals.py` |
| **Business** | Raíz del tenant multi-vertical (tabla `businesses`). Todo módulo nuevo cuelga de aquí, nunca de `restaurants` |
| **Espejo** | Fila de `businesses` con `vertical='restaurant'` y el mismo ID que su `restaurants` (puente automático) |
| **Vertical directo** | Business sin restaurante (verduras…), con ID ≥ 1.000.000 |
| **Mundo Verduras / Frubber POS** | La app Flask separada (`verduras/`, puerto 5100): POS de mostrador para verdulerías |
| **Handoff SSO** | Salto del dueño desde su dashboard (core) al POS del módulo sin re-loguearse (token de un solo uso, 5 min) |
| **Setup token** | Token de un solo uso que core emite al registrar un negocio; el módulo lo consume en el onboarding (PIN + WhatsApp) |

## Reglas de oro del área (resumen)

1. **Hay UN solo Velzia Core.** Los módulos nunca duplican auth, billing, suscripciones ni Copilot.
2. **Hay UN solo Copilot VZ, en core.** Los módulos se conectan por `business_id`; jamás construyen copilotos propios.
3. **Código nuevo usa `Business` + `business_id`.** Nunca crear FKs nuevas hacia `restaurants`.
4. **El trial es de la CUENTA, no del mundo.** `TrialHistory` se comparte; nadie cobra dos trials cambiando de vertical.
5. **DB compartida, migraciones separadas.** Core y cada módulo tienen su propia cadena (`alembic_version` vs `alembic_version_verduras`) y se excluyen mutuamente del autogenerate.
6. **Datos siempre preservados.** Gracia/vencido/dormant bloquean operar, nunca borran.

Detalle de cada regla en `04-puentes.md`.
