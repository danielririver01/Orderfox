"""protect external tables and align known schema differences

Revision ID: d1e2f3a4b5c6
Revises: c0a5f7e8d9b1
Create Date: 2026-09-29 21:15:00.000000

This migration is deliberately conservative:
- external ``velzia_*`` tables are excluded from autogenerate in env.py;
- the Copilot source index is aligned with SQLAlchemy's model name;
- RewardClaim.user_id is made NOT NULL only after a preflight check proves
  that existing data satisfies the invariant.
"""
from alembic import op
import sqlalchemy as sa


revision = 'd1e2f3a4b5c6'
down_revision = 'c0a5f7e8d9b1'
branch_labels = None
depends_on = None

OLD_SOURCE_INDEX = 'ix_copilot_conv_source'
SOURCE_INDEX = 'ix_copilot_conversations_source'

def _index_names(bind, table_name):
    return {index['name'] for index in sa.inspect(bind).get_indexes(table_name)}


def _set_reward_user_not_nullable(bind, nullable):
    column = next(
        column for column in sa.inspect(bind).get_columns('reward_claims')
        if column['name'] == 'user_id'
    )

    if not nullable and column['nullable']:
        null_count = bind.execute(
            sa.text('SELECT COUNT(*) FROM reward_claims WHERE user_id IS NULL')
        ).scalar_one()
        if null_count:
            raise RuntimeError(
                'No se puede hacer reward_claims.user_id NOT NULL: '
                f'existen {null_count} filas sin usuario asociado.'
            )

    if column['nullable'] == nullable:
        return

    alter_kwargs = {
        'existing_type': sa.Integer(),
        'existing_nullable': column['nullable'],
        'nullable': nullable,
    }
    if bind.dialect.name == 'sqlite':
        with op.batch_alter_table('reward_claims', schema=None) as batch_op:
            batch_op.alter_column('user_id', **alter_kwargs)
    else:
        op.alter_column('reward_claims', 'user_id', **alter_kwargs)


def upgrade():
    bind = op.get_bind()

    source_indexes = _index_names(bind, 'copilot_conversations')
    if OLD_SOURCE_INDEX in source_indexes:
        op.drop_index(OLD_SOURCE_INDEX, table_name='copilot_conversations')
        source_indexes.remove(OLD_SOURCE_INDEX)
    if SOURCE_INDEX not in source_indexes:
        op.create_index(
            SOURCE_INDEX,
            'copilot_conversations',
            ['source'],
            unique=False,
        )

    # The application always creates a reward claim for a known user. Fail
    # before changing the schema if legacy data violates that invariant.
    _set_reward_user_not_nullable(bind, nullable=False)


def downgrade():
    bind = op.get_bind()

    _set_reward_user_not_nullable(bind, nullable=True)

    source_indexes = _index_names(bind, 'copilot_conversations')
    if SOURCE_INDEX in source_indexes:
        op.drop_index(SOURCE_INDEX, table_name='copilot_conversations')
    if OLD_SOURCE_INDEX not in _index_names(bind, 'copilot_conversations'):
        op.create_index(
            OLD_SOURCE_INDEX,
            'copilot_conversations',
            ['source'],
            unique=False,
        )
