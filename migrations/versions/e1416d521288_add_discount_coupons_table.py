"""add discount_coupons table

Revision ID: e1416d521288
Revises: a1403ad41719
Create Date: 2026-07-28 12:31:36.994296

"""
from alembic import op
import sqlalchemy as sa
from app.models import AwareDateTime

revision = 'e1416d521288'
down_revision = 'a1403ad41719'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('discount_coupons',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=False),
        sa.Column('percentage', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('reward_claim_id', sa.Integer(), nullable=True),
        sa.Column('preference_id', sa.String(length=100), nullable=True),
        sa.Column('applied_to_payment_id', sa.String(length=50), nullable=True),
        sa.Column('reserved_at', AwareDateTime(timezone=True), nullable=True),
        sa.Column('applied_at', AwareDateTime(timezone=True), nullable=True),
        sa.Column('expires_at', AwareDateTime(timezone=True), nullable=False),
        sa.Column('created_at', AwareDateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reward_claim_id'], ['reward_claims.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('discount_coupons') as batch_op:
        batch_op.create_index('ix_discount_coupons_restaurant_id', ['restaurant_id'])


def downgrade():
    with op.batch_alter_table('discount_coupons') as batch_op:
        batch_op.drop_index('ix_discount_coupons_restaurant_id')
    op.drop_table('discount_coupons')
