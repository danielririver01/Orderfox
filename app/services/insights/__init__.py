"""
Copilot VZ — Services package.

Filosofía (documentada en el proyecto):
    "PostgreSQL calcula, Flask organiza, la IA interpreta."

Este paquete contiene la lógica de negocio del módulo de análisis
conversacional de Velzia. No acopla a ningún proveedor de LLM en
concreto: llm_service.py es la única capa que conoce la API de DeepSeek,
por lo que cambiar de modelo es cambiar una línea de configuración.
"""

__all__ = ['classifier', 'data_service', 'conversation_service', 'prompt_builder', 'llm_service',
           'event_engine', 'event_templates', 'context_manager', 'chart_service']
