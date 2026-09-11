"""add short_code to reward_claims

Revision ID: e4b30b77e164
Revises: dae7bfff86f3
Create Date: 2026-07-25 13:29:44.009923

v1.5 (feature/reservas): reescrito para ser cross-dialect e idempotente.
La versión anterior usaba `ADD COLUMN IF NOT EXISTS` y `id::text`, que solo
son sintaxis válida en MariaDB/PostgreSQL y rompían `flask db upgrade` en
SQLite (tests/CI) y MySQL 8 en bases frescas. Ahora usa el patrón inspector
del proyecto (ver f3e7d1a2b9c0) y sa.func para el backfill.
"""
from alembic import op
import sqlalchemy as sa

revision = 'e4b30b77e164'
down_revision = 'dae7bfff86f3'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col['name'] for col in inspector.get_columns('reward_claims')}

    if 'short_code' not in columns:
        op.add_column('reward_claims',
                      sa.Column('short_code', sa.String(length=30), nullable=True))

    # Backfill: 'mig-<id>' para filas sin código. Se hace en Python (select +
    # update por lote) porque es 100% portable entre SQLite/MySQL/MariaDB —
    # solo afecta filas legacy pre-migración, nunca será un volumen grande.
    rows = bind.execute(sa.text(
        "SELECT id FROM reward_claims WHERE short_code IS NULL OR short_code = ''"
    )).fetchall()
    if rows:
        ids = [r[0] for r in rows]
        bind.execute(
            sa.text("UPDATE reward_claims SET short_code = :code WHERE id = :id"),
            [{'id': rid, 'code': f'mig-{rid}'} for rid in ids],
        )

    # batch mode: SQLite no soporta ALTER COLUMN suelto; batch recrea la tabla
    # (cross-dialect: MySQL/MariaDB/SQLite).
    with op.batch_alter_table('reward_claims') as batch_op:
        batch_op.alter_column('short_code', existing_type=sa.String(30), nullable=False)
    try:
        op.create_index('ix_reward_claims_short_code', 'reward_claims', ['short_code'], unique=True)
    except Exception:
        pass


def downgrade():
    try:
        op.drop_index('ix_reward_claims_short_code', table_name='reward_claims')
    except Exception:
        pass
    try:
        op.drop_column('reward_claims', 'short_code')
    except Exception:
        pass
