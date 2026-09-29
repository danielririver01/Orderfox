# ADR-0002 — Distribución del diagnóstico entre repositorio, Google Docs y Linear

| Campo | Valor |
|---|---|
| **Estado** | Aceptado |
| **Fecha** | 2026-09-29 |
| **Decide** | Analista del diagnóstico AS-IS (pendiente de ratificación por el propietario) |
| **Commit de referencia** | `cd96aa763c086dea93e4aede46191b9add9067fa` |
| **Clasificación de la evidencia** | `[EJECUTADO]` — los tres destinos existen y están poblados |

---

## Contexto

El diagnóstico produce tres tipos de contenido con audiencias y ciclos de vida
distintos:

1. **Descripción técnica del sistema** — la lee quien va a tocar el código.
   Necesita evidencia precisa (`archivo:línea`) y debe versionarse junto al
   código que describe, porque queda obsoleta en cuanto el código cambia.
2. **Reglas de negocio, visión y alcance** — las lee quien decide sobre el
   producto. No necesitan rutas de archivo; necesitan lenguaje claro.
3. **Hallazgos y deuda** — no son documentación: son **trabajo pendiente**, con
   prioridad, responsable y criterio de cierre.

Meter los tres en el mismo sitio degrada los tres. Un documento de 600 líneas
con bugs, reglas y arquitectura mezclados no lo lee nadie entero, y los
hallazgos se pierden dentro del texto en lugar de convertirse en trabajo.

La restricción explícita del encargo era: **no mantener el mismo documento
completo en dos lugares**.

## Decisión

| Destino | Contenido | Por qué ahí |
|---|---|---|
| **Repositorio** `docs/00-AS-IS/` | Inventario, arquitectura, modelo de datos, catálogo de funciones con evidencia, compilación, pruebas, despliegue, ADR | Se versiona con el código que describe; la evidencia son rutas de este mismo repositorio |
| **Google Docs** | Visión, alcance, reglas de negocio en lenguaje de negocio, contradicciones comerciales y las 11 decisiones | Audiencia no técnica; se comenta y se valida en el propio documento |
| **Linear** (equipo Velzia, proyecto *Diagnóstico AS-IS*) | 20 incidencias: cada hallazgo con su evidencia, su clasificación de confianza y su criterio de cierre | Un hallazgo sin responsable ni criterio de cierre no se arregla; Linear le da estado |

### Resolución del solapamiento

Las reglas de negocio son el único contenido que aparece en dos sitios, y lo
hacen **en dos formas distintas**:

- Repositorio (documento 04): forma **trazable** — cada regla lleva
  `archivo:línea` y su clasificación de confianza.
- Google Docs: forma **legible** — la misma regla en lenguaje de negocio, sin
  ninguna referencia al código.

**El repositorio manda.** Si una regla cambia, se actualiza primero aquí y
después en Google Docs. El documento de Google se dejó deliberadamente **sin
evidencia** para que nadie lo confunda con la fuente de verdad.

Los hallazgos **no** se duplican: el documento 06 es la explicación con
evidencia; Linear es el seguimiento. Cada incidencia apunta a la sección del
documento en lugar de repetirla entera, y el README del diagnóstico incluye la
tabla de correspondencia completa.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Todo en el repositorio | El propietario y cualquier interlocutor no técnico no entran a `docs/`; los hallazgos se quedarían como texto sin responsable ni estado |
| Todo en Google Docs | Se desincroniza del código el mismo día en que alguien hace *merge*; y la evidencia `archivo:línea` no tiene sentido fuera del repositorio |
| Todo en Linear | Linear sirve para trabajo, no para documentación de referencia; un modelo de datos de 27 tablas no cabe en una incidencia |
| Copiar los documentos completos a los tres sitios | Es exactamente lo que el encargo prohibía: tres copias que divergen a la primera edición |

## Consecuencias

**Positivas**

- Cada audiencia encuentra su material en el formato que le sirve.
- Los hallazgos dejan de ser texto y pasan a ser trabajo con estado.
- Actualizar el código y su documentación técnica es un solo *commit*.
- Se puede archivar el proyecto de Linear cuando se cierre sin perder el
  diagnóstico.

**Negativas / coste asumido**

- Las reglas de negocio hay que mantenerlas en dos redacciones. Se mitiga con
  la regla de precedencia, pero **el coste existe**.
- Tres destinos significan tres sitios donde mirar. Se mitiga con la tabla de
  correspondencia del README.
- Se creó un equipo nuevo en Linear (**Velzia**, clave `VLZ`) porque el único
  equipo existente (`Frubber`) corresponde a otro producto. Si el propietario
  prefiere otra estructura, hay que mover 20 incidencias.

**Qué queda pendiente**

- Ratificación del propietario, en particular la creación del equipo `VLZ`.
- Decidir si el documento de Google Docs se congela cuando se cierren las 11
  decisiones o si pasa a ser el documento vivo de producto.

## Evidencia

- Repositorio: `docs/00-AS-IS/` — 11 archivos, 163 referencias `archivo:línea`
  verificadas contra el código, 70 enlaces internos validados.
- Google Docs: *Velzia — Visión, alcance y reglas de negocio (AS-IS, commit
  cd96aa7)*, documento `1yDKcLooFkk72JCBDiMWJq8_qXV43IfyvC7nZmmXDUsE`.
- Linear: equipo `Velzia` (`VLZ`), proyecto *Diagnóstico AS-IS (commit
  cd96aa7)*, incidencias `VLZ-1` … `VLZ-20`, con las etiquetas
  `comprobado-en-ejecucion`, `contradiccion`, `deuda-tecnica` y
  `pendiente-de-validacion`.
