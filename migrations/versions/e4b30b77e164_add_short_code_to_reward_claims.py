"""add short_code to reward_claims

Revision ID: e4b30b77e164
Revises: dae7bfff86f3
Create Date: 2026-07-25 13:29:44.009923

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'e4b30b77e164'
down_revision = 'dae7bfff86f3'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE reward_claims ADD COLUMN IF NOT EXISTS short_code VARCHAR(30) NULL")

    op.execute("UPDATE reward_claims SET short_code = CONCAT('mig-', id) WHERE short_code IS NULL OR short_code = ''")

    op.execute("ALTER TABLE reward_claims MODIFY COLUMN short_code VARCHAR(30) NOT NULL")

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
