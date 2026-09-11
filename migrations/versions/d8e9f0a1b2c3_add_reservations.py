"""reservations: tables.capacity, reservations, reservation_settings

Revision ID: d8e9f0a1b2c3
Revises: c1d2e3f4a5b6
Create Date: 2026-09-11

Feature reservas (v1.5):
- `tables.capacity` (nullable): capacidad de personas por mesa.
- `reservations`: reservas de clientes (fecha/hora en hora local Colombia,
  ver app/models/reservations.py).
- `reservation_settings`: config por restaurante (duración servicio, buffer
  limpieza, anticipación, recordatorio).

Idempotente: verifica existencia de columnas/tablas antes de crear (patrón
f3e7d1a2b9c0), seguro en entornos donde ya se aplicó manualmente.
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd8e9f0a1b2c3'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1) tables.capacity (reutiliza la tabla `tables` existente)
    tables_cols = {col['name'] for col in inspector.get_columns('tables')}
    if 'capacity' not in tables_cols:
        op.add_column('tables', sa.Column('capacity', sa.Integer(), nullable=True))

    # 2) reservations
    existing_tables = set(inspector.get_table_names())
    if 'reservations' not in existing_tables:
        op.create_table(
            'reservations',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('restaurant_id', sa.Integer(),
                      sa.ForeignKey('restaurants.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('table_id', sa.Integer(),
                      sa.ForeignKey('tables.id', ondelete='SET NULL'),
                      nullable=True),
            sa.Column('customer_name', sa.String(length=100), nullable=False),
            sa.Column('customer_whatsapp', sa.String(length=20), nullable=False),
            sa.Column('customer_note', sa.Text(), nullable=True),
            sa.Column('reservation_date', sa.Date(), nullable=False),
            sa.Column('reservation_time', sa.Time(), nullable=False),
            sa.Column('party_size', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(length=20), nullable=False,
                      server_default='pending'),
            sa.Column('rejection_reason', sa.Text(), nullable=True),
            sa.Column('reminder_sent', sa.Boolean(), nullable=False,
                      server_default=sa.false()),
            sa.Column('ip_address', sa.String(length=45), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index('ix_reservations_restaurant_id', 'reservations', ['restaurant_id'])
        op.create_index('ix_reservations_reservation_date', 'reservations', ['reservation_date'])
        op.create_index('ix_reservations_status', 'reservations', ['status'])
        op.create_index('ix_reservations_ip_address', 'reservations', ['ip_address'])

    # 3) reservation_settings
    if 'reservation_settings' not in existing_tables:
        op.create_table(
            'reservation_settings',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('restaurant_id', sa.Integer(),
                      sa.ForeignKey('restaurants.id', ondelete='CASCADE'),
                      nullable=False, unique=True),
            sa.Column('service_duration_min', sa.Integer(), nullable=False,
                      server_default='90'),
            sa.Column('cleanup_buffer_min', sa.Integer(), nullable=False,
                      server_default='15'),
            sa.Column('min_notice_hours', sa.Integer(), nullable=False,
                      server_default='2'),
            sa.Column('max_advance_days', sa.Integer(), nullable=False,
                      server_default='30'),
            sa.Column('reservations_enabled', sa.Boolean(), nullable=False,
                      server_default=sa.true()),
            sa.Column('reminder_enabled', sa.Boolean(), nullable=False,
                      server_default=sa.true()),
            sa.Column('reminder_hours_before', sa.Integer(), nullable=False,
                      server_default='2'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if 'reservation_settings' in existing_tables:
        op.drop_table('reservation_settings')
    if 'reservations' in existing_tables:
        op.drop_table('reservations')

    tables_cols = {col['name'] for col in inspector.get_columns('tables')}
    if 'capacity' in tables_cols:
        op.drop_column('tables', 'capacity')
