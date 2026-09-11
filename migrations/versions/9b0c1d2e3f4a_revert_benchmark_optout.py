"""revert benchmark to opt-out, drop benchmark_card_seen

Revision ID: 9b0c1d2e3f4a
Revises: 8a4b5c6d7e8f
Create Date: 2026-08-26

v1.5 (feature/reservas): reescrito cross-dialect. La versión anterior usaba
`ALTER COLUMN ... SET DEFAULT/NOT NULL` (solo MariaDB/PostgreSQL) y rompía
`flask db upgrade` en SQLite/MySQL en bases frescas. Ahora usa batch mode
(recrea la tabla en SQLite; ALTER real en MySQL/MariaDB).
"""
from alembic import op
import sqlalchemy as sa

revision = '9b0c1d2e3f4a'
down_revision = '8a4b5c6d7e8f'
branch_labels = None
depends_on = None


def upgrade():
    # Opt-out: todos los restaurantes existentes pasan a opt-in de benchmarks.
    op.execute('UPDATE restaurants SET allow_benchmark = 1')

    with op.batch_alter_table('restaurants') as batch_op:
        batch_op.alter_column('allow_benchmark', existing_type=sa.Boolean(),
                              server_default=sa.true(), nullable=False)
        batch_op.drop_column('benchmark_card_seen')


def downgrade():
    op.add_column('restaurants',
        sa.Column('benchmark_card_seen', sa.Boolean(),
                  server_default='0', nullable=False))
    op.execute('UPDATE restaurants SET allow_benchmark = 0')

    with op.batch_alter_table('restaurants') as batch_op:
        batch_op.alter_column('allow_benchmark', existing_type=sa.Boolean(),
                              server_default=sa.false(), nullable=False)
