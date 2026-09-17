"""add orders.idempotency_key for duplicate order protection

Revision ID: c0a5f7e8d9b1
Revises: b7c8d9e0f1a2
Create Date: 2026-09-17

v1.5: columna `idempotency_key` en `orders` (String 64, nullable) + unique
constraint (restaurant_id, idempotency_key). El cliente envía un UUID por
intento de pedido; si el mismo reintento llega dos veces (doble tap,
respuesta perdida en red, re-POST), la DB rechaza el duplicado y el backend
devuelve el pedido original en vez de crear otro.

NULL = pedidos creados sin clave (flujo viejo). El constraint único de
MariaDB/MySQL ignora filas con NULL, así que no restringe nada existente.
"""
from alembic import op
import sqlalchemy as sa

revision = 'c0a5f7e8d9b1'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('orders') as batch_op:
        batch_op.add_column(
            sa.Column('idempotency_key', sa.String(64), nullable=True))
        batch_op.create_unique_constraint(
            'uq_orders_restaurant_idempotency',
            ['restaurant_id', 'idempotency_key'])


def downgrade():
    with op.batch_alter_table('orders') as batch_op:
        batch_op.drop_constraint('uq_orders_restaurant_idempotency',
                                 type_='unique')
        batch_op.drop_column('idempotency_key')
