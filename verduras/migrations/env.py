"""
env.py de Alembic del módulo Verduras.

Espeja migrations/env.py de core con dos diferencias críticas:
1. `version_table='alembic_version_verduras'`: cadena de versiones propia,
   coexiste con `alembic_version` de core en la misma DB.
2. `include_object` reduce el autogenerate a SOLO tablas `verduras_*`:
   este env nunca ve (ni propone cambios sobre) las tablas de core.

Ambos valores llegan dos veces por diseño defensivo:
- Como kwargs del Migrate() de verduras/extensions.py → viajan en
  `configure_args` y se aplican con **conf_args en modo online.
- Declarados explícitos en el modo offline (que no usa conf_args).
"""
import logging
from logging.config import fileConfig

from alembic import context
from flask import current_app

config = context.config

fileConfig(config.config_file_name)
logger = logging.getLogger('alembic.env')


def get_engine():
    try:
        # Flask-SQLAlchemy<3 y Alchemical
        return current_app.extensions['migrate'].db.get_engine()
    except (TypeError, AttributeError):
        # Flask-SQLAlchemy>=3
        return current_app.extensions['migrate'].db.engine


def get_engine_url():
    try:
        return get_engine().url.render_as_string(hide_password=False).replace(
            '%', '%%')
    except AttributeError:
        return str(get_engine().url).replace('%', '%%')


# URL desde la app activa (DATABASE_URL del .env raíz vía settings del módulo)
config.set_main_option('sqlalchemy.url', get_engine_url())

# Metadata COMPARTIDA (core + módulo); el include_object la recorta a verduras_*
target_db = current_app.extensions['migrate'].db


def _only_module_tables(obj, name, type_, reflected, compare_to) -> bool:
    if type_ == 'table':
        return (name or '').startswith('verduras_')
    return True


def _process_revision_directives(context, revision, directives):
    """Cookbook de Alembic: no emitir revisión vacía en autogenerate."""
    if getattr(config.cmd_opts, 'autogenerate', False):
        script = directives[0]
        if script.upgrade_ops.is_empty():
            directives[:] = []
            logger.info('No changes in schema detected.')


def run_migrations_offline():
    context.configure(
        url=get_engine_url(),
        target_metadata=target_db.metadata,
        literal_binds=True,
        version_table='alembic_version_verduras',
        include_object=_only_module_tables,
        compare_type=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    # configure_args ya incluye version_table e include_object (kwargs del
    # Migrate del módulo); solo se completa el hook de autogenerate.
    conf_args = current_app.extensions['migrate'].configure_args
    if conf_args.get('process_revision_directives') is None:
        conf_args['process_revision_directives'] = _process_revision_directives

    connectable = get_engine()
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_db.metadata,
            **conf_args
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
