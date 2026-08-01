"""add_streaks

Revision ID: a1403ad41719
Revises: a1b2c3d4e5f6
Create Date: 2026-07-28 10:26:51.788404

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1403ad41719'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('streaks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=False),
        sa.Column('renewal_count', sa.Integer(), nullable=False),
        sa.Column('highest_tier', sa.Integer(), nullable=False),
        sa.Column('last_renewal_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_payment_id', sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('streaks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_streaks_restaurant_id'), ['restaurant_id'], unique=True)


def downgrade():
    with op.batch_alter_table('streaks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_streaks_restaurant_id'))
    op.drop_table('streaks')
