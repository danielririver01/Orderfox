# 03 — Mundo Verduras (Frubber POS)

Primer vertical no-restaurante de Velzia: app Flask **separada** dentro del
monorepo (`verduras/`, puerto **5100**), con su propia factory, settings,
blueprints y tests. Es el POS de mostrador para verdulerías: venta por
peso, inventario con merma, clientes/fiados y pedidos por WhatsApp.

Módulo actual: `MODULE_NAME = 'verduras'`, versión `0.9.0`
(`verduras/settings.py`).

## Arquitectura del módulo

```
verduras/
├── run.py              # Entrypoint (puerto 5100)
├── settings.py         # Config propia; lee el .env de la raíz
├── app_factory.py      # create_app() del módulo
├── extensions.py       # db (LA de core) + migrate propia + CSRF
├── auth.py             # x-api-key en tiempo constante, mismo patrón que core
├── models.py           # Catálogo (categorías, productos, price_history)
├── models_sales.py     # Ventas (settings, sales, items, cierres, caja, clientes…)
├── models_inventory.py # Inventario (lotes, merma, ajustes)
├── migrations/        # Cadena PROPIA (version_table alembic_version_verduras)
├── services/          # context · catalog · sales · inventory · pos_auth
├── routes/            # health · businesses · catalog · sales · inventory · dashboard*
└── tests/             # Suite propia (sqlite in-memory, no se mezcla con core)
```

- **Sin schedulers ni migraciones de core**: eso sigue viviendo en core.
  Si alguien corre `flask db ...` desde la app verduras, falla ruidoso en
  vez de ejecutar por accidente las migraciones de core (directorio
  `verduras/migrations/`).
- Las rutas nunca importan modelos de core directamente: usan los services.
- **Design system propio** (diferente a Restaurantes a propósito): claro
  `#FAFAF
...[truncated 7370 chars]