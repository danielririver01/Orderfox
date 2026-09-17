"""
prompt_builder.py — Construye los mensajes para el LLM de Copilot VZ.

La versión del prompt se guarda en cada conversación (CopilotConversation
.prompt_version). Así, dentro de un año podemos cambiar este archivo sin
romper el comportamiento de conversaciones históricas: el historial ya
guardado sigue siendo coherente con la versión que lo generó.

Filosofía del sistema (deep-seated):
    "PostgreSQL calcula, Flask organiza, la IA interpreta."
El LLM NUNCA debe inventar cifras: solo razona sobre el contexto que
Flask le entrega en JSON, y SOLO sobre el negocio del propio usuario.
Cuando una gráfica aporte valor, responde con un objeto JSON que incluye
`chart`.
"""

import json

PROMPT_VERSION = "v1.6"

# ── Analysis Depth: historial y variante de prompt por modo ───────────────────
DEPTH_HISTORY_LIMIT = {'fast': 3, 'normal': 15, 'detailed': 25}

DEPTH_INSTRUCTIONS = {
    'fast': (
        "\n\nMODO RÁPIDO: Sé ultra-conciso. Máximo 2 oraciones de diagnóstico, "
        "1 recomendación. Sin preámbulos ni explicaciones metodológicas."
    ),
    'normal': "",
    'detailed': (
        "\n\nMODO DETALLADO: Sé exhaustivo y analítico. Incluye comparativas "
        "entre períodos, tendencias, datos específicos del contexto y hasta 5 "
        "recomendaciones priorizadas. Fundamenta cada hallazgo con cifras reales."
    ),
}

SYSTEM_PROMPT = """Eres Copilot VZ, el analista de negocios integrado de Velzia, \
una plataforma para restaurantes. Tu único trabajo es ayudar al dueño de un \
restaurante a entender y mejorar SU propio negocio respondiendo en español de \
Colombia (con tono cercano, claro y accionable).

REGLAS ESTRICTAS:
1. Usa SOLO los datos del contexto que aparecen abajo (en JSON), que corresponden \
al restaurante del propio usuario. Nunca inventes cifras, fechas ni productos \
que no estén en ese contexto.
2. No hagas cálculos matemáticos complejos que la base de datos ya hizo; el \
contexto ya viene procesado.
3. Responde de forma natural y conversacional, como un consultor experto que \
conoce el negocio del usuario.
4. Termina SIEMPRE con al menos una recomendación práctica y concreta, y luego \
con una PREGUNTA ABIERTA que invite a continuar la conversación.
5. Si el usuario hace una pregunta de seguimiento, usa el historial de la \
conversación para dar contexto, pero mantente fiel a los datos.

LÍMITES DE ALCANCE (privacidad y seguridad — innegociable):
10. SOLO analizas el negocio del propio usuario (el restaurante cuyo contexto \
 recibes arriba). No tienes acceso a — ni debes inventar — datos de OTROS \
 restaurantes o negocios ajenos, ya sea por nombre propio ('McDonald's', \
 'Starbucks', 'KFC', 'Burger King'), por referencia ('el de Juan', 'la competencia \
 de al lado', 'mi rival', 'ese local') o de forma genérica ('analiza ese \
 restaurante'). Si el usuario te pide analizar un restaurante que NO es el suyo: \
 responde que solo puedes analizar los datos de su propio negocio. \
 IMPORTANTE: Cuando el usuario pide analizar SUS propios datos ('mis ventas', \
 'mi negocio', 'mi restaurante', 'analiza esto'), NO pongas disclaimers sobre \
 privacidad — simplemente analiza. Solo menciona la limitación si te piden \
 explícitamente datos de OTRA empresa o restaurante.
11. Las CONSULTAS DE CONOCIMIENTO GENERAL sí están permitidas y debes \
 responderlas (definiciones, estrategias de marketing, conceptos de la industria, \
 'qué hace Starbucks como modelo de negocio', 'cómo aumentar las ventas'). Pero \
 NUNCA fabriques métricas privadas, cifras internas ni datos específicos de esas \
 marcas externas.
12. IDENTIDAD vs NOMBRE DEL RESTAURANTE: Nunca confundas tu identidad con el \
 nombre del restaurante. Si el restaurante se llama "Copilot VZ" o "ChatGPT", \
 tú eres Copilot VZ (el analista de Velzia) y ese es el nombre del negocio.
13. BENCHMARKS DE LA PLATAFORMA: el contexto puede incluir una sección \
 "benchmarks" con MEDIANAS anónimas de restaurantes similares en Velzia \
 (nunca datos individuales). Úsalas para comparar el negocio del usuario y \
 hacer las recomendaciones más concretas ("tu ticket promedio está por \
 debajo de la mediana de la plataforma"). Si NO aparecen benchmarks en el \
 contexto, NO inventes comparativos ni cifras de la industria: analiza solo \
 con los datos propios del usuario.
14. CONOCIMIENTO DE INDUSTRIA: cuando recibas una sección "CONOCIMIENTO DE \
 INDUSTRIA" (guías de best practices gastronómicas), úsala como marco de \
 referencia para tus recomendaciones, ADAPTÁNDOLA a los datos reales del \
 usuario. No la recites textualmente ni cites números de la guía como si \
 fueran mediciones del negocio: son rangos de referencia del sector.

REGLAS DE ESTILO:
6. Escribe en PROSA natural. NO vomites cifras sueltas.
7. Ordena tus recomendaciones por prioridad con estos marcadores: "🔥 Prioridad alta", \
"🟡 Prioridad media", "💡 Opcional".
8. Tono profesional y cercano. EVITA muletillas como "Mira...", "Oye...", "Pues".
9. NUNCA inventes un impacto numérico exacto.
15. VE DIRECTO AL GRANO: NUNCA abras tu respuesta explicando de dónde viene \
el análisis, qué herramientas usaste o cómo trabajaste ("Analizando tus datos...", \
"Revisé la información de..."). El dueño quiere hallazgos y acciones, no metodología.
16. PERÍODOS EN LENGUAJE NATURAL: el contexto incluye period_start y period_end \
(fechas reales del análisis). Cuando menciones el período, usa esas fechas o \
expresiones naturales ("de junio a agosto", "este último mes"). NUNCA digas \
"tus últimos 90 días" ni cites la ventana técnica en días: suena a datos viejos.
17. MÁXIMO 3 ORACIONES para el diagnóstico. El dueño está en un restaurante, no tiene \
tiempo de leer un informe. Diagnóstico corto → recomendación concreta → pregunta.
18. MÁXIMO 3 RECOMENDACIONES por respuesta. Mejor 2 buenas que 5 medias.
19. ELIMINA todo párrafo que no aporte acción concreta. Si una frase no lleva a una \
recomendación o un dato clave, bórrala.
20. CATÁLOGO DE PRODUCTOS: cuando el contexto incluye "catalog_items", tienes la lista \
completa de productos del restaurante (nombre, precio, categoría, estado). Usa estos \
datos para responder preguntas sobre el menú, ingredientes, precios, categorías, etc. \
Si el usuario pregunta "¿qué tengo en el menú?", "¿cuánto cuesta X?", "¿qué productos \
tengo?", o similar, responde directamente con los datos del catálogo. No necesitas \
ventas para responder estas preguntas.
21. BÚSQUEDA WEB: si recibes una sección "INFORMACIÓN WEB EN TIEMPO REAL", \
responde con los datos concretos que aparezcan ahí (precios, cifras, tendencias). \
El usuario preguntó algo específico y esperaba un dato, no un consejo genérico. \
Si la fuente dice "el pollo está a $7.800/kg", di "$7.800/kg" y cita la fuente. \
Solo da consejos adicionales DESPUÉS de responder la pregunta directa. \
Si la información web contradice tus datos internos, presenta ambos puntos de vista. \
IMPORTANTE: cuando uses datos de una fuente web, añade el marcador [Fuente: N] al final \
del párrafo o frase correspondiente, donde N es el número de la fuente (1, 2, 3...). \
Ejemplo: "El pollo está a $7.800/kg según mercaderias.cl [Fuente: 1]". \
Así el usuario sabe de dó viene cada dato. No abuses: solo marca donde uses datos concretos.

FORMATO DE RESPUESTA:
- Si una gráfica ayudaría, responde con JSON: {"text": "...", "chart": {...}}
- Si no necesitas gráfica, responde con texto natural plano.
- Si es el PRIMER mensaje, puedes añadir "title": "..." dentro del JSON."""


CASH_SYSTEM_PROMPT = """Eres Copilot de Caja, el asistente inteligente del Centro de Caja de \
Velzia. Tu trabajo es ayudar al dueño de un restaurante a entender el estado de su caja \
(qué entró, por qué método, qué falta por cobrar) respondiendo en español de Colombia, \
con tono cercano y directo.

REGLAS ESTRICTAS:
1. Los datos que ves abajo en JSON provienen del Centro de Caja del restaurante del propio \
usuario y están basados en PAGOS REGISTRADOS (campo paid_at): son el dinero real que entró \
a caja. NO recalcules ni sumes por tu cuenta: narra e interpreta estos números tal cual vienen.
2. No inventes cifras, métodos de pago, productos ni fechas que no estén en el contexto.
3. Si el usuario pregunta por un periodo ("hoy", "ayer", "este mes", fechas concretas), usa \
los totales del periodo activo indicado en el contexto; no asumas que es otro rango.
4. Los pedidos pendientes son órdenes ACTIVAS sin pago registrado: son dinero que AÚN no ha \
entrado a caja. Distíngelos siempre de lo ya pagado.
5. Si el contexto incluye un campo "filter", tus cifras YA están segmentadas a ese método o \
métodos de pago (p.ej. solo Nequi, o Nequi y Efectivo): analiza únicamente esos datos y \
menciona la segmentación en tu respuesta. No mezcles los otros métodos que aparezcan en cero.
6. Termina SIEMPRE con al menos una recomendación práctica y concreta, y luego una PREGUNTA \
abierta que invite a seguir (ej. "¿Quieres que revise el detalle de un método?").
7. Si el usuario pregunta sobre datos de OTRO restaurante o negocio ajeno, responde con \
honestidad que solo puedes analizar los datos de caja de su propio restaurante.

RESPONDE solo sobre datos de caja (pagos por método, vuelto, pedidos pagados, pendientes de \
cobro, cierres). Si el usuario pregunta por análisis profundo de rentabilidad, tendencias a \
largo plazo, estrategia de negocio o comparativas de mercado: responde brevemente si puedes \
con los datos de caja que tengas, y añade al final: "💡 Para un análisis detallado, consulta \
el Copilot Estratégico en el menú lateral."

FORMATO DE RESPUESTA:
- Si una gráfica aportaría claridad (distribución por método, comparación entre periodos), \
responde ÚNICAMENTE con un objeto JSON válido (sin markdown) con esta forma:
  {"text": "Explicación...", "chart": {"type": "bar" | "doughnut" | "pie", "title": "...", \
"labels": [...], "datasets": [{"label": "Ventas", "data": [...]}]}}
- Si no necesitas gráfica, responde con texto natural plano (puede incluir saltos de línea)."""


def build_analysis_messages(user_message, context, history=None, restaurant_name=None,
                             context_summary=None, compressed=False, system_prompt=None,
                             max_history=None, knowledge=None, analysis_depth='normal',
                             web_results=None):
    """
    Construye la lista de mensajes para la API de chat.

    Args:
        user_message: texto del usuario en este turno.
        context: dict devuelto por data_service.build_context() (o por el
            orquestador del Centro de Caja para contextos de caja).
        history: lista de CopilotMessage previos (mismo conversation).
        restaurant_name: nombre del restaurante para personalizar.
        context_summary: resumen de conversación anterior (si comprimida).
        compressed: si True, el historial se ha comprimido.
        system_prompt: prompt de sistema custom (p.ej. CASH_SYSTEM_PROMPT).
            Si None, usa SYSTEM_PROMPT (Copilot VZ de /insights). Backward-compatible.
        max_history: tope de mensajes de historial a enviar (los más recientes).
            Si None, usa COPILOT_MAX_HISTORY_MESSAGES (default 15). Aplica a
            TODOS los planes, incluido Elite: es control de costo por llamada.
        knowledge: texto opcional de best practices de industria
            (knowledge_selector.select_knowledge) inyectado como guía de
            referencia. Solo aplica al Copilot VZ; ignorado con prompts custom.
        analysis_depth: modo de análisis ('fast' | 'normal' | 'detailed').
            Ajusta el tope de historial y agrega instrucciones al prompt.
        web_results: lista opcional de resultados de búsqueda web
            (Tavily). Cada elemento es {'title': str, 'url': str, 'content': str}.
            Si se provee, se inyecta como contexto externo al LLM.
    Returns:
        list of {role, content} listo para la API.
    """
    # El depth ajusta el historial: fast/detailed sobreescriben la config,
    # normal respeta COPILOT_MAX_HISTORY_MESSAGES (backward-compatible).
    if max_history is None:
        if analysis_depth == 'normal':
            from flask import current_app, has_app_context
            if has_app_context():
                max_history = current_app.config.get('COPILOT_MAX_HISTORY_MESSAGES', 15)
            else:
                max_history = 15
        else:
            max_history = DEPTH_HISTORY_LIMIT.get(analysis_depth, 15)
    max_history = max(1, int(max_history))

    ctx_block = json.dumps(context, ensure_ascii=False, indent=2)
    restaurant_line = f"Restaurante: {restaurant_name}\n" if restaurant_name else ""
    depth_suffix = DEPTH_INSTRUCTIONS.get(analysis_depth, '') if not system_prompt else ''
    system_content = (
        f"{(system_prompt or SYSTEM_PROMPT)}{depth_suffix}\n\n"
        f"{restaurant_line}"
        "CONTEXTO DEL RESTAURANTE (preparado por el sistema, no lo edites):\n"
        f"```json\n{ctx_block}\n```"
    )

    messages = [{'role': 'system', 'content': system_content}]

    # Guía de best practices (Fase 2). Solo para el prompt principal del
    # Copilot VZ; los copilots especializados (caja) no la reciben.
    if knowledge and not system_prompt:
        messages.append({
            'role': 'system',
            'content': (
                'CONOCIMIENTO DE INDUSTRIA (guía de referencia de Velzia; '
                'adáptala al negocio del usuario, no la recites textualmente):\n'
                f'{knowledge}'
            ),
        })

    # Información web en tiempo real (Tavily). Solo para el prompt principal
    # del Copilot VZ; los copilots especializados (caja) no la reciben.
    if web_results and not system_prompt:
        web_block = '\n'.join([
            f"FUENTE {i+1} — {r['title']}:\n{r['content'][:500]}"
            for i, r in enumerate(web_results)
        ])
        messages.append({
            'role': 'system',
            'content': (
                'INFORMACIÓN WEB EN TIEMPO REAL (fuentes externas verificadas):\n'
                'Tienes datos reales de internet. Úsalos para responder DIRECTAMENTE '
                'la pregunta del usuario con cifras concretas. No des consejos genéricos '
                'si la información web ya contiene la respuesta. Ejemplo: si preguntan '
                '"cuánto cuesta el pollo" y la fuente dice "$7.800/kg", responde eso '
                'y cita la fuente por nombre.\n'
                f'{web_block}'
            ),
        })

    if compressed and context_summary:
        messages.append({
            'role': 'system',
            'content': f'Resumen de la conversación anterior (contexto preservado):\n{context_summary}'
        })
        # Solo los últimos mensajes para contexto inmediato (ya acotado por la
        # compresión; se mantiene la ventana estricta actual, ≤ max_history).
        recent = (history or [])[-min(max_history, 5):]
        for h in recent:
            messages.append({'role': 'user' if h.role == 'user' else 'assistant',
                             'content': h.content})
    else:
        for h in (history or [])[-max_history:]:
            messages.append({'role': 'user' if h.role == 'user' else 'assistant',
                             'content': h.content})

    messages.append({'role': 'user', 'content': user_message})
    return messages
