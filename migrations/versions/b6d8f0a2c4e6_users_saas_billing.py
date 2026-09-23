"""billing saas en users (fuente única) + owner en espejos

Revision ID: b6d8f0a2c4e6
Revises: e5f7a9b1c3d4
Create Date: 2026-09-22

Decision de arquitectura (Ecosistema Multi-Mundos):
- `User` = UNICA fuente de verdad del billing (plan, estado, vencimiento).
- `Business`/`Restaurant` conservan su informacion OPERATIVA; sus columnas de
  suscripcion pasan a ser CACHE de legibilidad (sincronizadas al pagar/expire),
  y los reads delegan al User cuando existe dueño.
- Backfill: cada usuario hereda el billing de su restaurante o de su business
  propio. Los espejos de restaurantes ganan owner_user_id (data completa).
  Businesses SIN dueño (piloto/API) quedan intocables (regla de oro legacy).
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'b6d8f0a2c4e6'
down_revision = 'e5f7a9b1c3d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('plan_type', sa.String(length=20), nullable=False,
                  server_default='trial'))
    op.add_column(
        'users',
        sa.Column('subscription_expires_at', sa.DateTime(timezone=True),
                  nullable=True))
    op.add_column(
        'users',
        sa.Column('subscription_state', sa.String(length=20), nullable=False,
                  server_default='active'))
    op.add_column(
        'users',
        sa.Column('has_used_trial', sa.Boolean(), nullable=False,
                  server_default=sa.false()))

    # ── Backfill (subqueries correlacionadas: portable PG/MySQL/SQLite) ──
    # 1) Dueño con restaurante: hereda el billing de su restaurante.
    op.execute("""
        UPDATE users SET plan_type = (
            SELECT r.plan_type FROM restaurants r
            WHERE r.id = users.restaurant_id)
        WHERE users.restaurant_id IS NOT NULL
    """)
    op.execute("""
        UPDATE users SET subscription_expires_at = (
            SELECT r.subscription_expires_at FROM restaurants r
            WHERE r.id = users.restaurant_id)
        WHERE users.restaurant_id IS NOT NULL
    """)
    op.execute("""
        UPDATE users SET subscription_state = (
            SELECT r.subscription_state FROM restaurants r
            WHERE r.id = users.restaurant_id)
        WHERE users.restaurant_id IS NOT NULL
    """)
    op.execute("""
        UPDATE users SET has_used_trial = (
            SELECT r.has_used_trial FROM restaurants r
            WHERE r.id = users.restaurant_id)
        WHERE users.restaurant_id IS NOT NULL
    """)
    # 2) Dueño de vertical directo (verduras, ...): hereda el billing de su
    #    Business (no sobreescribe lo heredado del restaurante si tiene ambos).
    op.execute("""
        UPDATE users SET plan_type = (
            SELECT b.plan_type FROM businesses b
            WHERE b.owner_user_id = users.id AND b.vertical != 'restaurant'
            LIMIT 1)
        WHERE plan_type = 'trial' AND subscription_state = 'active'
          AND subscription_expires_at IS NULL
          AND EXISTS (
              SELECT 1 FROM businesses b2
              WHERE b2.owner_user_id = users.id AND b2.vertical != 'restaurant')
    """)
    op.execute("""
        UPDATE users SET subscription_expires_at = (
            SELECT b.subscription_expires_at FROM businesses b
            WHERE b.owner_user_id = users.id AND b.vertical != 'restaurant'
            LIMIT 1)
        WHERE subscription_expires_at IS NULL
          AND EXISTS (
              SELECT 1 FROM businesses b2
              WHERE b2.owner_user_id = users.id AND b2.vertical != 'restaurant')
    """)
    op.execute("""
        UPDATE users SET has_used_trial = (
            SELECT b.has_used_trial FROM businesses b
            WHERE b.owner_user_id = users.id AND b.vertical != 'restaurant'
            LIMIT 1)
        WHERE has_used_trial = false
          AND EXISTS (
              SELECT 1 FROM businesses b2
              WHERE b2.owner_user_id = users.id AND b2.vertical != 'restaurant')
    """)
    # 3) Espejos de restaurantes: owner_user_id = dueño (data completa; el
    #    conteo de mundos por usuario sale solo de `businesses` owned).
    #    Varios users pueden compartir restaurant_id (dueño + empleados):
    #    se elige el dueño real (email no-empleado) y luego el id menor.
    op.execute("""
        UPDATE businesses SET owner_user_id = (
            SELECT u.id FROM users u WHERE u.restaurant_id = businesses.id
            ORDER BY (u.email LIKE '%@empleado.velzia'), u.id
            LIMIT 1)
        WHERE owner_user_id IS NULL
          AND EXISTS (
              SELECT 1 FROM users u2 WHERE u2.restaurant_id = businesses.id)
    """)


def downgrade() -> None:
    # Los espejos vuelven a su estado original (owner NULL).
    op.execute("""
        UPDATE businesses SET owner_user_id = NULL
        WHERE vertical = 'restaurant'
    """)
    with op.batch_alter_table('users') as batch:
        batch.drop_column('has_used_trial')
        batch.drop_column('subscription_state')
        batch.drop_column('subscription_expires_at')
        batch.drop_column('plan_type')
