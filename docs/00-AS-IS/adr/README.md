# Registros de decisiones de arquitectura (ADR)

Un **ADR** captura una decisión de arquitectura: qué se decidió, en qué contexto
y qué consecuencias tiene. No es documentación de diseño ni una propuesta: es un
registro **inmutable** de algo que ya se decidió.

---

## Regla de esta carpeta

> **Aquí solo entran decisiones tomadas y confirmadas.**
>
> Lo que está deducido del código pero no validado por el propietario **no es un
> ADR todavía**: vive en [`../02-arquitectura-actual.md §13`](../02-arquitectura-actual.md#13-decisiones-de-arquitectura-observables)
> como *decisión observable*, y pasa a ADR cuando alguien la confirma.

Esta separación es deliberada: evita convertir una inferencia del analista en un
requisito aprobado.

---

## Índice

| ADR | Título | Estado | Fecha |
|---|---|---|---|
| [ADR-0001](ADR-0001-ubicacion-de-la-documentacion-as-is.md) | Ubicación de la documentación AS-IS en `docs/00-AS-IS/` | Aceptado | 2026-09-29 |
| [ADR-0002](ADR-0002-distribucion-entre-repo-google-docs-y-linear.md) | Distribución del diagnóstico entre repositorio, Google Docs y Linear | Aceptado | 2026-09-29 |

---

## Pendientes de formalizar

Diez decisiones están **presentes en el código** pero no confirmadas. Se
documentan como observaciones en
[`../02-arquitectura-actual.md §13`](../02-arquitectura-actual.md#13-decisiones-de-arquitectura-observables)
y se convertirán en ADR cuando el propietario indique cuáles fueron deliberadas:

| Ref. | Decisión observada | Bloqueada por |
|---|---|---|
| A-01 | Monolito Flask en capas en lugar de microservicios | — |
| A-02 | Multi-inquilino por columna `restaurant_id` | — |
| A-03 | Menú público desacoplado en Astro/Vercel, unido por redirección | — |
| A-04 | Identidad delegada en Clerk, conservando el login propio | [D-03](../07-preguntas-pendientes.md#d-03--se-mantiene-el-login-propio-con-contraseña-además-de-clerk) |
| A-05 | Importes en enteros (COP, sin decimales ni moneda) | — |
| A-06 | Todo en UTC salvo las reservas, en hora local de Colombia | — |
| A-07 | Las cuentas nunca se borran: pasan a `dormant` | — |
| A-08 | Scheduler integrado en el proceso web | [D-04](../07-preguntas-pendientes.md#d-04--llegan-duplicados-los-correos-y-las-notificaciones-automáticas) |
| A-09 | Base de datos compartida con el Scanner IA externo | [D-01](../07-preguntas-pendientes.md#d-01--cuál-es-el-motor-de-base-de-datos) |
| A-10 | CSRF manual por incompatibilidad de Flask-WTF 1.2.2 | — |

---

## Relación con el registro de decisiones ya existente

El repositorio ya tenía `docs/04-RECORDS/REC-02_Decision_Log.md`. **No se ha
modificado.** Cuando el propietario decida cuál de los dos formatos se queda,
conviene fusionarlos en uno: mantener dos registros de decisiones en paralelo es
exactamente el tipo de duplicación que este diagnóstico intenta evitar.

---

## Plantilla

Copiar [`TEMPLATE.md`](TEMPLATE.md) y numerar de forma correlativa:
`ADR-NNNN-titulo-en-minusculas-con-guiones.md`.

**Estados posibles:** `Propuesto` · `Aceptado` · `Rechazado` · `Obsoleto` ·
`Sustituido por ADR-NNNN`.

Un ADR aceptado **no se edita**: si la decisión cambia, se escribe uno nuevo que
sustituya al anterior y se actualiza el estado del viejo.
