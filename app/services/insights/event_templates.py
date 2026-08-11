"""
event_templates.py — Templates de mensajes para BusinessEvents de Copilot VZ.

Cada template produce un mensaje de asistente sin LLM. El sistema detecta el
evento vía SQL y el template lo convierte en texto. Al pulsar "Analizar" en el
dashboard, ese texto queda como contexto inicial y se dispara el análisis IA
(DeepSeek) automáticamente desde el endpoint de consume.
"""

TEMPLATES = {
    "first_sales": {
        "title": "¡Ya tienes tus primeras ventas! 🎉",
        "priority": 100,
        "cooldown_days": None,
        "message": (
            "👋 ¡Hola! Soy **Copilot VZ**, tu analista de negocios.\n\n"
            "Ya tienes suficientes datos registrados para que pueda ayudarte "
            "a tomar mejores decisiones.\n\n"
            "Cada vez que detecte algo importante en tu negocio, te lo haré saber.\n\n"
            "¿Quieres ver tu primer análisis?"
        ),
    },
    "record_week": {
        "title": "¡Semana récord! 📈",
        "priority": 70,
        "cooldown_days": 30,
        "message": (
            "🎉 **¡Semana récord!**\n\n"
            "Esta semana tus ventas alcanzaron **{revenue}**, "
            "un **{pct}% más** que tu promedio semanal.\n\n"
            "Algo funcionó especialmente bien esta semana. Vale la pena "
            "descubrir qué cambió para intentar repetir ese resultado.\n\n"
            "**¿Quieres que analice qué impulsó este crecimiento?**"
        ),
    },
    "big_drop": {
        "title": "Tus ventas bajaron esta semana 📉",
        "priority": 90,
        "cooldown_days": 7,
        "message": (
            "⚠️ **Tus ventas disminuyeron**\n\n"
            "Esta semana facturaste **{revenue}**, "
            "un **{pct}% menos** que la semana anterior.\n\n"
            "Puede ser estacional, pero vale la pena revisarlo.\n\n"
            "¿Quieres que analice posibles causas?"
        ),
    },
    "top_product_new": {
        "title": "Nuevo producto más vendido ⭐",
        "priority": 60,
        "cooldown_days": 30,
        "message": (
            "⭐ **{product}** es ahora tu producto más vendido, "
            "desplazando a **{previous}**.\n\n"
            "¿Quieres analizar por qué está funcionando tan bien?"
        ),
    },
}

KIND_PRIORITY = {k: v["priority"] for k, v in TEMPLATES.items()}
KIND_COOLDOWN = {k: v["cooldown_days"] for k, v in TEMPLATES.items()}
