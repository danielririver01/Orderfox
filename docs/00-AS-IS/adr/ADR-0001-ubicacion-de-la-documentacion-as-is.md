# ADR-0001 — Ubicación de la documentación AS-IS en `docs/00-AS-IS/`

| Campo | Valor |
|---|---|
| **Estado** | Aceptado |
| **Fecha** | 2026-09-29 |
| **Decide** | Analista del diagnóstico AS-IS (pendiente de ratificación por el propietario) |
| **Commit de referencia** | `cd96aa763c086dea93e4aede46191b9add9067fa` |
| **Clasificación de la evidencia** | `[EJECUTADO]` — verificado sobre el árbol de archivos real |

---

## Contexto

El encargo pedía producir siete documentos con nombres concretos
(`01-inventario.md`, `02-arquitectura-actual.md`, …) más una carpeta `adr/`.

`docs/` **ya tenía una estructura numerada propia** antes de este trabajo:

```
docs/
├── 00-GOVERNANCE/
├── 01-ARCHITECTURE/     ARCH-01 … ARCH-04
├── 02-GUIDES/           GUIDE-01 … GUIDE-09
├── 03-PROCEDURES/       PROC-01, PROC-02, PROC-04, PROC-05
├── 04-RECORDS/          REC-02_Decision_Log.md, Test_Plans/
├── README.md            (índice maestro, declara versión 1.3.0)
└── AUDITORIA_2026-08-11.md, DOFA.md, DOCKER_SETUP.md, …
```

Colocar `01-inventario.md` y `02-arquitectura-actual.md` directamente en
`docs/` habría creado dos problemas concretos:

1. **Colisión de numeración.** Convivirían `docs/01-ARCHITECTURE/` (carpeta) y
   `docs/01-inventario.md` (archivo) en el mismo nivel, con el mismo prefijo y
   significados distintos.
2. **Ambigüedad sobre qué está vigente.** `docs/01-ARCHITECTURE/ARCH-01…` y
   `docs/00-AS-IS/02-arquitectura-actual.md` describen lo mismo desde premisas
   distintas, y en varios puntos **se contradicen** (motor de base de datos,
   versión del producto, duración de la prueba gratuita). Mezclarlos en la misma
   carpeta impediría saber cuál manda.

Una restricción del encargo era **no modificar el código ni el comportamiento
del sistema** durante esta primera revisión. Se aplicó el mismo criterio a la
documentación previa: **no se editó ni se movió ningún documento existente**.

## Decisión

Los siete entregables del diagnóstico AS-IS y la carpeta `adr/` viven en una
subcarpeta propia: **`docs/00-AS-IS/`**, con exactamente los nombres de archivo
pedidos.

La documentación previa de `docs/` **se deja intacta**. Sus contradicciones con
el código se registran en
[`../06-riesgos-y-deuda-tecnica.md`](../06-riesgos-y-deuda-tecnica.md) (sección
*Parte B — Contradicciones documentales*), **sin corregirlas en origen**.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Archivos sueltos en `docs/` | Colisiona con `01-ARCHITECTURE/`, `02-GUIDES/`, `03-PROCEDURES/` y mezcla dos sistemas de numeración incompatibles |
| Reescribir `docs/01-ARCHITECTURE/` con el contenido nuevo | Destruye la documentación previa antes de que el propietario decida qué conserva, y viola la instrucción de no modificar lo existente en esta fase |
| Carpeta `as-is/` sin prefijo numérico | No ordena primero en un listado alfabético; el objetivo es que el diagnóstico sea lo primero que se ve |
| Repositorio o wiki aparte | Rompe la trazabilidad: la evidencia son rutas `archivo:línea` de **este** repositorio, y debe versionarse junto al código que describe |

## Consecuencias

**Positivas**

- No se pierde ni se altera nada de la documentación previa.
- El prefijo `00-` hace que el diagnóstico aparezca el primero en `docs/`.
- El AS-IS queda físicamente aislado: una carpeta, un propósito, una fecha, un
  commit de referencia.
- Cuando el diagnóstico quede obsoleto, se archiva o se borra la carpeta entera
  sin tocar nada más.

**Negativas / coste asumido**

- `docs/` queda temporalmente con **dos** conjuntos de documentación de
  arquitectura que se contradicen. Se mitiga con un aviso explícito en
  [`../README.md §6`](../README.md#6-separación-as-is--to-be), pero **la
  duplicación existe** hasta que el propietario decida cuál se retira.
- Conviven **dos registros de decisiones**: `docs/04-RECORDS/REC-02_Decision_Log.md`
  y esta carpeta `adr/`. Conviene fusionarlos.

**Qué queda pendiente**

- Que el propietario decida el destino de `docs/01-ARCHITECTURE/`: actualizarla,
  archivarla o retirarla.
- Unificar `REC-02_Decision_Log.md` con `adr/` en un único registro.
- Ratificar este ADR o sustituirlo por otro con la ubicación definitiva.

## Evidencia

- Árbol de `docs/` antes de este trabajo: 28 archivos en 5 carpetas numeradas
  (`00-GOVERNANCE` … `04-RECORDS`).
- `docs/README.md:3` declara *"Versión del proyecto: 1.3.0"* frente a
  `settings.py:9` `APP_VERSION = '1.4.0'` → ejemplo concreto de por qué no se
  deben mezclar las dos documentaciones.
- `git status` al cerrar el trabajo: **ningún archivo previo modificado**; solo
  añadidos bajo `docs/00-AS-IS/`.
