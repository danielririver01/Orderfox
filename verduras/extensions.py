"""
Extensiones del módulo Verduras.

⚠️ Contrato del monorepo: la instancia `db` es LA de velzia core
(`app.models.db`), no una nueva. Compartirla es lo que permite:
- que los models de core y del módulo vivan en el mismo metadata,
- que los listeners del puente Business ↔ Restaurant corran en este proceso,
- un solo `create_all`/`migrate` para todo.

Migraciones propias (separadas de las de core, MISMA DB):
- `version_table='alembic_version_verduras'`: cadena de versiones propia,
  no choca con `alembic_version` de core.
- `include_object`: solo tablas `verduras_*` — un autogenerate del módulo
  NUNCA intenta alterar las tablas de core (y viceversa: el env.py de core
  filtra las verduras_* para excluirlas de SU autogenerate).

Cuando el módulo se extraiga a repo propio (git subtree split), esta
importación pasará a apuntar al paquete `velzia-core` publicado; el resto
del código no cambia porque solo usa `verduras.extensions.db`.
"""

from flask_migrate import Migrate
from flask_wtf import CSRFProtect

from app.models import db  # noqa: F401  (re-export: es la instancia de core)

# CSRF para el dashboard POS (login y venta por sesión). Igual que core:
# WTF_CSRF_CHECK_DEFAULT=False + guard manual en la factory, para no
# romper las APIs JSON (esas van con x-api-key).


def _only_module_tables(obj, name, type_, reflected, compare_to) -> bool:
    """Autogenerate del módulo: SOLO tablas verduras_* (core no se toca)."""
    if type_ == 'table':
        return (name or '').startswith('verduras_')
    return True


migrate = Migrate(version_table='alembic_version_verduras',
                  include_object=_only_module_tables)
csrf = CSRFProtect()
