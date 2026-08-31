"""
classifier.py — Router híbrido de Copilot VZ.

Decide si una pregunta del usuario es:
  - Nivel 1 (quick): consulta que PostgreSQL/Flask resuelven directo.
    Respuesta inmediata, GRATIS, sin llamar al LLM.
  - Nivel 2 (analysis): requiere razonamiento del LLM.
    Consume 1 crédito IA la primera vez por conversación.

Implementado con patrones fijos (regex) en v1: 100% determinista,
cero latencia, cero falsos positivos en los casos comunes. Si no
matchea ningún patrón N1, cae a N2 (análisis). El set de patrones
puede crecer sin tocar el resto del sistema.
"""

import re

# ── Guard de alcance: consultas a restaurantes ajenos ─────────────────────────
# Detecta, SIN IA y de forma determinista, cuándo el usuario pide DATOS o
# análisis de un negocio que NO es el suyo. En ese caso Copilot VZ debe
# responder directo ("solo analizo tu restaurante") sin llamar al LLM ni
# consumir crédito. No se activa para conocimiento general
# (p.ej. "qué estrategias usa Starbucks"), solo ante intención de obtener
# cifras de un tercero.
FOREIGN_BRANDS = (
    "mcdonald's", "mcdonalds", "mc donald", "mcdo", "starbucks", "kfc",
    "burger king", "burgerking", "domino's", "dominos", "pizza hut",
    "pizza huts", "subway", "taco bell", "wendy's", "wendys", "popeyes",
    "chipotle", "little caesars", "papa john's", "papa johns",
    "crepes & waffles", "crepes and waffles", "el corral", "juan valdez",
    "coster", "kokoriko", "presto", "frisby", "mostaza", "tennin", "mcdia",
)

# Palabras que indican que el usuario quiere DATOS/análisis (no charla general).
_DATA_KEYWORDS = (
    "venta", "vendio", "vendió", "vendi", "ingreso", "ingresó", "factur",
    "recaud", "pedido", "pedidos", "orden", "ordenes", "ticket", "anal",
    "compar", "rentabil", "gananc", "margen", "costo", "utilidad", "reporte",
    "informe", "predic", "tenden", "cuanto", "cuánto", "facturac",
)

# Preguntas de asistencia/capacidades que NO requieren datos del restaurante:
# "qué puedes hacer", "dame consejos", "cómo empiezo", "configúrame X", etc.
# En estos casos el LLM responde sin contexto de ventas (regla 11 del prompt),
# así que NO deben ser bloqueadas por el guard de madurez de datos.
_GENERAL_HELP_RE = re.compile(
    r'(qué puedes hacer|que puedes hacer|qué puede hacer|que puede hacer|'
    r'para qué sirves|para que sirves|qué hace copilot|que hace copilot|'
    r'cuáles son tus funciones|cuales son tus funciones|qué funciones|'
    r'que funciones|qué puedes analizar|que puedes analizar|qué analiza|'
    r'que analiza|ayúdame|ayudame|dame consejos|dame tips|qué me recomiendas|'
    r'que me recomiendas|qué consejos|que consejos|qué sugieres|que sugieres|'
    r'qué puedo hacer|que puedo hacer|cómo puedo empezar|cómo empezar|'
    r'como puedo empezar|como empezar|cómo empezar a vender|como empezar a '
    r'vender|para empezar a vender|configurar mi restaurante|organizar mi '
    r'menú|organizar mi menu|cómo funciona|cómo funciono|como funciona|'
    r'cómo me ayudas|como me ayudas|qué es copilot|que es copilot|'
    r'para qué sirve copilot|para que sirve copilot|qué más sabes hacer|'
    r'que mas sabes hacer|qué sabes hacer|que sabes hacer|'
    r'qué puedes hacer por mi|que puedes hacer por mi)',
    re.IGNORECASE,
)


def is_general_assistance(text):
    """True si el mensaje pide ayuda/capacidades y NO requiere datos del
    restaurante. Estas preguntas el LLM las responde sin contexto de ventas,
    así que deben saltarse los guards de madurez de datos (nivel 0/1) y de
    ventas (has_sales)."""
    if not text:
        return False
    return bool(_GENERAL_HELP_RE.search(text.lower()))

# Sustantivos comunes que NO son nombre de restaurante (para el patrón "de <Nombre>").
_COMMON_NOUNS = {
    "ayer", "hoy", "mes", "semana", "dia", "día", "año", "ano", "enero",
    "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "octubre", "noviembre", "diciembre", "lunes", "martes",
    "miercoles", "miércoles", "jueves", "viernes", "sabado", "sábado",
    "domingo", "restaurante", "local", "negocio", "tienda", "empresa",
    "menu", "menú", "producto", "cliente", "venta", "ventas", "pedido",
    "proveedor", "caja", "barrio", "ciudad", "pais", "país", "zona",
    "mi", "tu", "su", "mis", "tus", "sus", "el", "la", "los", "las",
    "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas",
    "aquel", "aquella", "aquellos", "aquellas", "ello",
    "informe", "reporte", "lista", "listado", "historial", "movimiento",
    "total", "detalle", "resumen", "balance", "cuenta", "gasto", "gastos",
    "inversion", "inversión", "inversiones",
    # Palabras interrogativas que abren consultas
    "qué", "que", "cuál", "cual", "cuáles", "cuales", "cómo", "como",
    "cuándo", "cuando", "dónde", "donde", "quién", "quien", "quiénes",
    "quienes", "cuánto", "cuanto", "cuánta", "cuanta", "cuántos",
    "cuantos", "cuántas", "cuantas", "para", "por",
    # Verbos de inicio de consulta
    "quiero", "necesito", "dame", "muestra", "enséñame", "enseñame",
    "dime", "explícame", "explicame", "muéstrame", "muestrame",
    "ayúdame", "ayudame", "cuéntame", "cuentame", "háblame", "hablame",
    "analiza", "compara", "recomiéndame", "recomiendame", "sugiére",
    "sugiere", "calcúlame", "calculame", "mira", "revisa", "ver", "checa",
    "busca", "muéstrame", "muestrame",
    # Verbos modales/auxiliares comunes (falsos positivos con trigger débil)
    "puedo", "puede", "pueden", "puedes", "podria", "podría", "podrian",
    "podrían", "debo", "debe", "deben", "debes", "debemos",
    "tengo", "tiene", "tienen", "tienes", "tenemos",
    "quiero", "quiere", "quieren", "quieres",
    "saber", "sabes", "sabe", "saben",
    "hacer", "hago", "hace", "hacen", "haces",
    "ser", "es", "son", "soy", "eres", "somos",
    "estar", "estoy", "estas", "está", "estamos", "estan",
    "haber", "he", "has", "ha", "han", "hemos",
    "ir", "voy", "vas", "va", "van", "vamos",
    "dar", "doy", "das", "da", "dan", "damos",
    "poner", "pongo", "pones", "pone", "ponen",
    "cosa", "cosas", "algo", "nada", "todo", "toda",
    "cada", "varios", "varias", "mucho", "mucha",
    "asi", "así", "bien", "mal", "mejor", "peor",
}

# Patrón 1 (fuerte): marcadores explícitos de establecimiento + nombre.
# Son inequívocos: si alguien dice "restaurante X", X es un restaurante.
# NO incluir artículos solos (el, la, los, las, al) porque son greedy
# y consumen la palabra siguiente como nombre capturado.
_STRONG_TRIGGER_RE = re.compile(
    r'(?:restaurante|negocio|local)\s+'
    r'([A-ZÁÉÍÓÚÑa-záéíóúñ][\wáéíóúñ]{2,})',
    re.IGNORECASE,
)

# Patrón 2 (débil): "de/del/de la X" — la preposición "de" es ubicua en
# español, así que exigimos nombres capturados de ≥4 caracteres para
# reducir falsos positivos (p.ej. "de mas", "de ese" se filtran por
# longitud, no por lista de palabras).
_WEAK_TRIGGER_RE = re.compile(
    r'(?:de la|del|de)\s+'
    r'([A-ZÁÉÍÓÚÑa-záéíóúñ][\wáéíóúñ]{3,})',
    re.IGNORECASE,
)

# Patrón 3: nombre propio como sujeto + verbo de datos en pasado.
# Captura casos como "Felicia vendió mucho" donde el nombre del
# restaurante aparece SIN marcador explícito.
_DATA_VERB_RE = re.compile(
    r'\b([A-ZÁÉÍÓÚÑ][\wáéíóúñ]{2,})\s+'
    r'(?:vend[iió]o?|factur[oó]|registr[oó]|present[oó]|'
    r'alcanz[oó]|consigui[oó]|logr[oó]|gener[oó]|obtuv[oó])',
)


def _is_common_noun(name):
    """True si el nombre capturado es un sustantivo común (no un restaurante).

    Compara también contra el singular de plurales regulares: "reportes" →
    "reporte", "ventas" → "venta", "pedidos" → "pedido", etc. Sin esto, frases
    como "qué tipo de reportes" disparaban el guard de alcance porque "reportes"
    (plural) no estaba en _COMMON_NOUNS.
    """
    lowered = name.lower()
    if lowered in _COMMON_NOUNS:
        return True
    if lowered.endswith('es') and lowered[:-2] in _COMMON_NOUNS:
        return True
    if lowered.endswith('s') and lowered[:-1] in _COMMON_NOUNS:
        return True
    return False


def is_foreign_restaurant_query(text, restaurant_name=None, restaurant_slug=None):
    """True si el usuario pide DATOS/análisis de un restaurante AJENO.

    Barato y determinista (sin IA). No se activa para conocimiento general
    ("qué hace Starbucks"), solo cuando hay intención de obtener cifras de
    un tercero. Si menciona el nombre o slug de su propio restaurante, se
    permite; si menciona otro restaurante por nombre, se bloquea antes de
    llamar al LLM.
    """
    if not text:
        return False
    lowered = text.lower()

    # ── Identificadores del restaurante del usuario (no asumir que existen) ──
    # Incluye nombre completo, slug, y palabras significativas del nombre
    # para evitar falsos positivos con nombres multi-palabra
    # (ej. "Ventas de la esquina gourmet" → trigger captura "esquina",
    # pero si el restaurante del usuario es "La Esquina Gourmet",
    # "esquina" está en own_ids y no se bloquea).
    own_ids = set()
    if restaurant_name and restaurant_name.strip():
        name_lower = restaurant_name.strip().lower()
        own_ids.add(name_lower)
        for w in name_lower.split():
            w = w.strip("'-")
            if len(w) > 2 and w not in _COMMON_NOUNS:
                own_ids.add(w)
    if restaurant_slug and restaurant_slug.strip():
        slug_lower = restaurant_slug.strip().lower()
        own_ids.add(slug_lower)
        for w in slug_lower.split('-'):
            if len(w) > 2 and w not in _COMMON_NOUNS:
                own_ids.add(w)

    has_data = any(kw in lowered for kw in _DATA_KEYWORDS)
    if not has_data:
        return False

    # 1) Marcas conocidas + intención de datos → bloqueado SOLO si ninguna
    #    coincide con el propio restaurante del usuario.
    #    Ej: restaurante "El Corral" preguntando por "el corral" → permite;
    #    restaurante "La Esquina" preguntando por "KFC" → bloquea.
    matched_brands = [b for b in FOREIGN_BRANDS if b in lowered]
    if matched_brands:
        all_match_own = all(
            any(b in ident for ident in own_ids) for b in matched_brands
        )
        if not all_match_own:
            return True

    # 2) Trigger fuerte (restaurante/local/negocio + <Nombre>).
    for m in _STRONG_TRIGGER_RE.finditer(text):
        name = m.group(1).lower()
        if _is_common_noun(name) or len(name) <= 1:
            continue
        if name in own_ids:  # Menciona su propio negocio → permitir
            continue
        return True

    # 3) Trigger débil (de/del/de la + <Nombre>, min 4 caracteres).
    for m in _WEAK_TRIGGER_RE.finditer(text):
        name = m.group(1).lower()
        if _is_common_noun(name) or len(name) <= 1:
            continue
        if name in own_ids:
            continue
        return True

    # 4) <NombrePropio> + verbo de datos en pasado (sin marcador).
    #    "Felicia vendió mucho", "El Corral facturó 500", etc.
    for m in _DATA_VERB_RE.finditer(text):
        name = m.group(1).lower()
        if _is_common_noun(name) or len(name) <= 1:
            continue
        if name in own_ids:
            continue
        return True

    return False


# Cada entrada: (intent, regex sobre texto normalizado en minúsculas)
# Orden importa: los más específicos primero.
QUICK_PATTERNS = [
    ('sales_today',       r'(venta|vend|ingreso|factur|recaud).{0,12}(hoy|el dia de hoy|dia de hoy)'),
    ('sales_yesterday',   r'(venta|vend|ingreso|factur|recaud).{0,12}(ayer)'),
    ('sales_today',       r'\b(hoy|dia de hoy)\b.{0,20}(vend|venta|ingreso)'),
    ('orders_today',      r'(pedido|orden|ordenes|pedidos).{0,12}(hoy|ayer|dia)'),
    ('orders_today',      r'\b(hoy|ayer)\b.{0,15}(pedido|orden)'),
    ('top_product',       r'(producto|plato).{0,15}(mas vendido|m.s vendid|top|mejor)'),
    ('top_product',       r'(mas vendido|m.s vendid|top venta|producto estrella)'),
    ('avg_ticket',        r'(ticket promedio|valor promedio|promedio.{0,6}pedido|cuanto promedia)'),
    ('new_customers',     r'(cliente nuev|clientes nuev|nuevos clientes|cliente.{0,8}nuevo)'),
    ('compare_months',    r'(compar|contrast|vs|frente a|mes pasado|mes anterior|este mes.{0,6}anterior)'),
    ('week_sales',        r'(venta|vend|ingreso).{0,12}(semana|esta semana|7 dias|7 d.ias)'),
    ('month_sales',       r'(venta|vend|ingreso).{0,12}(mes|este mes|30 dias|30 d.ias|mensual)'),
]


# ── Ventanas de tiempo dinámicas ─────────────────────────────────────────────
# "analiza mis ventas de los últimos 15 días" → ventana = 15.
# Aplica al análisis (Nivel 2): las consultas rápidas conservan sus ventanas
# fijas (hoy/ayer/semana/mes) definidas en QUICK_PATTERNS.
MAX_WINDOW_DAYS = 365
CUSTOM_WINDOW_RE = re.compile(
    r'(?:últimos?|ultimos?|últimas?|ultimas?|pasados?|pasadas?|hace|hasta|en los|en las)\s+'
    r'(\d{1,3})\s+(?:días?|dias?)',
    re.IGNORECASE,
)


def extract_custom_window(text):
    """Extrae una ventana explícita de tipo 'últimos X días'.

    Retorna int entre 1 y MAX_WINDOW_DAYS, o None si no hay un número
    explícito de días (la ventana por defecto la decide classify()).
    Ejemplos: 'últimos 15 días' → 15 · 'hace 45 dias' → 45 · 'último mes' → None.
    """
    if not text:
        return None
    m = CUSTOM_WINDOW_RE.search(text)
    if not m:
        return None
    n = int(m.group(1))
    return max(1, min(MAX_WINDOW_DAYS, n))


# Preguntas que buscan CONSEJO/Acción, no un dato puntual. Estas SIEMPRE van
# a análisis (Nivel 2 con LLM), aunque contengan palabras de consulta rápida:
# "mis ventas bajaron este mes, ¿qué hago?" merece una estrategia, no solo el
# número del mes. Se evalúa ANTES de QUICK_PATTERNS.
ADVICE_SEEKING_RE = re.compile(
    r'('
    r'qu[eé]\s+(hago|hacer|puedo\s+hacer|me\s+(recomienda|sugiere))'   # qué hago / qué me recomienda
    r'|c[oó]mo\s+(puedo|hago|le\s+hago|mejoro|mejorar|aumento|subo|subir)'  # cómo puedo/hago/mejoro...
    r'|consejos?'                                                       # consejos
    r'|dame\s+(ideas|estrategias|tips)'                                 # dame ideas/estrategias/tips
    r')',
    re.IGNORECASE,
)


def classify(text):
    """
    Retorna dict:
      {
        'level':  'quick' | 'analysis',
        'intent': 'sales_today' | 'sales_analysis' | ...
        'window': int  (días de contexto sugeridos para data_service)
      }
    """
    if not text:
        return {'level': 'analysis', 'intent': 'general_analysis', 'window': 90}

    norm = text.lower()

    # Consejo buscado → siempre Nivel 2 (el quick solo responde datos secos).
    if not ADVICE_SEEKING_RE.search(norm):
        for intent, pattern in QUICK_PATTERNS:
            if re.search(pattern, norm):
                return {'level': 'quick', 'intent': intent, 'window': _window_for_intent(intent)}

    return {
        'level': 'analysis',
        'intent': _analysis_intent(norm),
        'window': extract_custom_window(norm) or 90,
    }


def _window_for_intent(intent):
    return {
        'sales_today': 1,
        'sales_yesterday': 2,
        'orders_today': 1,
        'top_product': 30,
        'avg_ticket': 30,
        'new_customers': 1,
        'compare_months': 60,
        'week_sales': 7,
        'month_sales': 30,
    }.get(intent, 30)


def _analysis_intent(norm):
    """Clasifica la intención de análisis para enriquecer el contexto/metadata."""
    if re.search(r'(por que|baj|ca.?|cay|sub|crec|tendencia|razón|razon)', norm):
        return 'sales_analysis'
    if re.search(r'(rentabil|gananci|margen|costo|food\s*cost|utilidad|profit)', norm):
        return 'profitability_analysis'
    if re.search(r'(recomend|sugerenc|promocion|mejor|optimiz|deberia|deber.a)', norm):
        return 'recommendations'
    if re.search(r'(informe|reporte|resumen ejecutiv|ejecutiv)', norm):
        return 'executive_report'
    if re.search(r'(tenden|predic|futur|proyect)', norm):
        return 'trend_analysis'
    return 'general_analysis'
