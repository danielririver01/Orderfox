"""add unique constraint on ai_token_tx mp_payment_id

Revision ID: a4b2c3d4e5f6
Revises: 68f3dd225165
Create Date: 2026-07-21 22:10:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a4b2c3d4e5f6'
down_revision = '68f3dd225165'
branch_labels = None
depends_on = None


def upgrade():
    # Limpiar duplicados con JOIN (más seguro que subquery en MySQL).
    # Solo afecta filas con mp_payment_id no nulo.
    op.execute("""
        DELETE t1 FROM ai_token_transactions t1
        INNER JOIN ai_token_transactions t2
        ON t1.mp_payment_id = t2.mp_payment_id
        WHERE t1.id > t2.id
          AND t1.mp_payment_id IS NOT NULL
    """)
    # Crear UNIQUE sobre mp_payment_id. MySQL permite múltiples NULLs
    # en índices únicos, así que los consumos sin referencia MP no
    # se bloquean entre sí.
    with op.batch_alter_table('ai_token_transactions', schema=None) as batch_op:
        batch_op.create_unique_constraint(
            'uq_ai_token_tx_mp_payment_id', ['mp_payment_id']
        )


def downgrade():
    with op.batch_alter_table('ai_token_transactions', schema=None) as batch_op:
        batch_op.drop_constraint('uq_ai_token_tx_mp_payment_id', type_='unique')
