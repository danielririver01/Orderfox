"""restaurants.dormant_at: align DB type with model (TIMESTAMPTZ)

Revision ID: c9e0f1a2b3d4
Revises: b8d9f0a1c2e3
Create Date: 2026-09-30 00:00:00.000000

VLZ-3 / R-03: la migración c4c47adbb493 creó dormant_at como sa.DateTime()
sin timezone. En MySQL la distinción es invisible (por eso el check del
diagnóstico no lo detectó), pero en PostgreSQL produce
`timestamp without time zone` mientras el modelo usa AwareDateTime
(DateTime(timezone=True) -> timestamptz), igual que todas las demás columnas
de fecha. La app escribe UTC naive-as-UTC, por eso la conversión usa
AT TIME ZONE 'UTC' para no depender del timezone de la sesión del servidor.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c9e0f1a2b3d4'
down_revision = 'b8d9f0a1c2e3'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        'restaurants', 'dormant_at',
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using="dormant_at AT TIME ZONE 'UTC'",
    )


def downgrade():
    op.alter_column(
        'restaurants', 'dormant_at',
        type_=sa.DateTime(),
        existing_nullable=True,
        postgresql_using="dormant_at AT TIME ZONE 'UTC'",
    )
