"""
Validador de la Knowledge Base de Copilot VZ.

Uso:
    python knowledge_base/_validate.py
        Verifica tamaño de todos los documentos y prueba el selector con
        queries de ejemplo.

    python knowledge_base/_validate.py --doc food_cost.md --query "mi merma subio"
        Prueba un documento y una query específica.

Salida de ejemplo:
    food_cost.md            1701 chars  OK
    menu_engineering.md     1505 chars  OK

Regla dura: knowledge_selector TRUNCA a MAX_KNOWLEDGE_CHARS (2600).
Un documento que excede el tope se inyecta cortado a media guía.
"""

import argparse
import sys
from pathlib import Path

KB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(KB_DIR.parent))

from app.services.insights.knowledge_selector import (  # noqa: E402
    DOCS,
    MAX_KNOWLEDGE_CHARS,
    select_knowledge,
)

# Queries típicas de dueños de restaurante para verificar el matcheo.
SAMPLE_QUERIES = [
    'Como mejoro mis ventas?',
    'Mi food cost esta muy alto',
    'Que promocion hago para los martes?',
    'Cual es mi plato estrella y cual deberia quitar del menu?',
    'Como hago para que mis meseros vendan mas?',
]


def check_sizes():
    """Verifica el tamaño de cada documento registrado en DOCS."""
    print('-' * 60)
    print('TAMAÑOS (límite duro: %d chars)' % MAX_KNOWLEDGE_CHARS)
    print('-' * 60)
    failures = 0
    for doc in DOCS:
        path = KB_DIR / doc['file']
        if not path.exists():
            print(f"  {doc['file']:<25} FALTA EL ARCHIVO")
            failures += 1
            continue
        size = len(path.read_text(encoding='utf-8'))
        status = 'OK' if size <= MAX_KNOWLEDGE_CHARS else 'EXCEDE (se truncará)'
        if size > MAX_KNOWLEDGE_CHARS:
            failures += 1
        print(f"  {doc['file']:<25} {size:>6} chars  {status}")
    return failures


def test_selection():
    """Prueba que cada query típica seleccione el documento esperado."""
    from app.services.insights.classifier import classify

    print()
    print('-' * 60)
    print('SELECCIÓN CON QUERIES TÍPICAS')
    print('-' * 60)
    for q in SAMPLE_QUERIES:
        c = classify(q)
        doc = select_knowledge(q.lower(), c.get('intent'))
        name = doc.split('\n')[0] if doc else '(ninguno — respuesta sin guía KB)'
        print(f"  {q!r}")
        print(f"    -> {c['level']} / {c['intent']} -> {name}")


def test_custom(query):
    """Prueba una query del usuario."""
    doc = select_knowledge(query.lower())
    if doc:
        print(f"\nQuery: {query!r}")
        print("Documento seleccionado:")
        print(doc[:400] + ('...' if len(doc) > 400 else ''))
    else:
        print(f"\nQuery: {query!r} -> NINGÚN documento matchea.")
        print("Revisa las keywords en knowledge_selector.py.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--doc', help='documento a inspeccionar')
    parser.add_argument('--query', help='probar el selector con esta query')
    args = parser.parse_args()

    if args.query:
        test_custom(args.query)
        return

    failures = check_sizes()

    if args.doc:
        path = KB_DIR / args.doc
        if path.exists():
            content = path.read_text(encoding='utf-8')
            print(f"\n--- {args.doc} ({len(content)} chars) ---")
            print(content)

    test_selection()

    print()
    if failures:
        print(f"RESULTADO: {failures} documento(s) exceden el límite. "
              "Pídele a Gemini reducirlos antes de usarlos.")
        sys.exit(1)
    print('RESULTADO: todos los documentos dentro del límite.')


if __name__ == '__main__':
    main()
