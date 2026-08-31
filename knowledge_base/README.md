# Knowledge Base — Guía de mantenimiento

Documentos de best practices gastronómicas que Copilot VZ inyecta al prompt
del LLM cuando el usuario hace una pregunta relevante. Editables sin tocar código.

## Reglas técnicas (obligatorias)

| Regla | Valor | Por qué |
|-------|-------|---------|
| Tamaño máximo | **2600 caracteres** (~800 tokens) | `knowledge_selector.py` trunca lo que exceda → Gemini te devuelve 5000 chars y la IA recibe media guía |
| Idioma | Español de Colombia | El system prompt exige responder en es-CO |
| Vocabulario | Usar las palabras que escriben los dueños ("merma", "ticket", "martes", "combo") | El selector matchea por keywords, no por semántica |
| Cifras | Solo rangos de referencia del sector (ej. food cost 28-35%) | La regla 14 del prompt prohíbe citar números de la guía como si fueran mediciones del negocio |

## Flujo para mejorar un documento con Gemini Pro

### 1. Pega este prompt en Gemini

```
Actúa como consultor gastronómico senior con 20 años de experiencia en
restaurantes en Colombia. Voy a darte un documento interno de best practices.
Mejóralo cumpliendo ESTAS REGLAS SIN EXCEPCIÓN:

1. MÁXIMO 2500 caracteres (contados, incluyendo espacios). Si no cabe todo,
   prioriza: tablas accionables > reglas prácticas > errores comunes.
   Elimina introducciones y despedidas.
2. Español de Colombia. Tono directo, sin relleno.
3. Usa las palabras que un dueño de restaurante escribiría al buscar ayuda:
   merma, food cost, ticket promedio, combo, martes, mesero, cajero, etc.
4. Cifras SOLO como rangos de referencia del sector colombiano (ej. 28-35%).
   Nada de estadísticas inventadas o citadas de marcas específicas.
5. Formato: título H1, secciones cortas con H2, máximo 1-2 tablas,
   bullets de una línea.
6. NO agregues: fuentes, bibliografía, "en conclusión", frases motivacionales.

DOCUMENTO ACTUAL:
[pega aquí el contenido del .md]

QUÉ QUIERO MEJORAR:
[dime qué quieres agregar o cambiar, ej: "agrega sección sobre mermas por
preparación" o "actualiza rangos de precios 2026"]
```

### 2. Valida antes de guardar

```bash
python knowledge_base/_validate.py          # tamaños + prueba de matcheo
python knowledge_base/_validate.py --doc food_cost.md --query "mi merma subio"
```

Si dice `EXCEDE`, pídele a Gemini: "réducelo a menos de 2500 caracteres
manteniendo las tablas".

### 3. Si creas un documento NUEVO

Además de guardar el .md, registra sus keywords en
`app/services/insights/knowledge_selector.py`:

```python
{
    'key': 'mi_nuevo_doc',
    'file': 'mi_nuevo_doc.md',
    'keywords': ['redes', 'instagram', 'publicidad'],  # palabras del usuario
},
```

Y decide su fallback por intención en `INTENT_DOCS` si aplica.

### 4. Prueba que se seleccione correctamente

```bash
python knowledge_base/_validate.py --query "como mejoro mis redes sociales"
```

Debe mostrar tu nuevo documento como seleccionado.

## Documentos actuales

| Archivo | Tema | Keywords principales |
|---------|------|---------------------|
| `menu_engineering.md` | Matriz BCG de platos | menu, carta, plato, combo |
| `slow_days.md` | Activaciones días flojos | martes, promo, 2x1 |
| `food_cost.md` | Costeo y mermas | food cost, merma, proveedor |
| `ticket_promedio.md` | Cross-selling y upselling | ticket, vender mas, mesero |
