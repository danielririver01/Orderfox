"""
Puente multi-vertical Restaurant ↔ Business (rama feature/verduras).

Cubre:
1. Invariante 1:1 alineado por ID (crear Restaurant → Business con mismo ID).
2. Alias Tenant is Business.
3. Sincronización en updates (name, slug, is_active).
4. Borrado manual en cascada (delete Restaurant → sin Business huérfano).
5. Verticales directos (create_direct) en la banda >= 1.000.000.
6. Backfill de la migración a1f6e3d2b4c5 (mismo SQL, validado sobre SQLite).
"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import Business, Restaurant, Tenant, db

# ───────────── 1. Invariante 1:1 alineado por ID ─────────────

def test_restaurant_creation_creates_mirror_business_with_same_id(db, sample_restaurant):
    biz = db.session.get(Business, sample_restaurant.id)
    assert biz is not None
    assert biz.vertical == 'restaurant'
    assert biz.slug == sample_restaurant.slug
    assert biz.name == sample_restaurant.name
    assert biz.is_active == bool(sample_restaurant.is_active)


def test_business_id_alignment_invariant(db, sample_restaurant):
    """El invariante del puente: businesses.id == restaurants.id (espejo)."""
    biz = Business.query.filter_by(slug=sample_restaurant.slug).one()
    assert biz.id == sample_restaurant.id
    # Y la relación viewonly resuelve el perfil por ese mismo ID.
    assert biz.restaurant_profile.id == sample_restaurant.id


def test_alias_tenant_is_business():
    assert Tenant is Business


# ───────────── 3. Sincronización en updates ─────────────

def test_restaurant_update_syncs_business(db, sample_restaurant):
    sample_restaurant.name = 'Nuevo Nombre SL'
    sample_restaurant.slug = 'nuevo-nombre-sl'
    sample_restaurant.is_active = False
    db.session.commit()

    biz = db.session.get(Business, sample_restaurant.id)
    assert biz.name == 'Nuevo Nombre SL'
    assert biz.slug == 'nuevo-nombre-sl'
    assert biz.is_active is False


# ───────────── 4. Borrado sin huérfanos ─────────────

def test_restaurant_delete_removes_business(db, sample_restaurant):
    biz_id = sample_restaurant.id
    assert db.session.get(Business, biz_id) is not None

    db.session.delete(sample_restaurant)
    db.session.commit()

    assert db.session.get(Business, biz_id) is None


# ───────────── 5. Verticales directos (banda reservada) ─────────────

def test_create_direct_verduras_business(db):
    r = Restaurant(name='R', slug='r-1', whatsapp_phone='+573001112233')
    db.session.add(r)
    db.session.commit()
    assert r.id < 1_000_000  # espejos viven bajo la banda

    biz = Business.create_direct(
        vertical='verduras', name='Verduras La Central', slug='verduras-la-central')

    assert biz.id >= 1_000_000
    assert biz.vertical == 'verduras'
    assert biz.restaurant_profile is None  # sin espejo


def test_create_direct_rejects_restaurant_vertical(db):
    with pytest.raises(ValueError):
        Business.create_direct(vertical='restaurant', name='X', slug='x')


def test_direct_and_mirror_ids_never_collide(db, sample_restaurant):
    """Aunque MAX(id) arranque bajo la banda, nunca se cruza con los espejos."""
    biz = Business.create_direct(vertical='delivery', name='D', slug='d-1')
    assert biz.id != sample_restaurant.id

    # Un espejo nuevo sigue tomando su ID de `restaurants` (autoincrement),
    # no de la banda: r2.id < 1_000_000 y no choca con el direct.
    r2 = Restaurant(name='R2', slug='r-2', whatsapp_phone='+573004445566')
    db.session.add(r2)
    db.session.commit()
    assert r2.id < 1_000_000
    assert r2.id != biz.id
    assert db.session.get(Business, r2.id).vertical == 'restaurant'


def test_direct_slug_must_be_unique(db, sample_restaurant):
    with pytest.raises(IntegrityError):
        Business.create_direct(vertical='delivery', name='Dup',
                               slug=sample_restaurant.slug)
        db.session.commit()
    db.session.rollback()


# ───────────── 6. Backfill de la migración (mismo SQL) ─────────────

def _run_businesses_migration_sql():
    """Réplica del backfill del upgrade() de a1f6e3d2b4c5 sobre la DB del test.

    El DDL ya lo aplicó db.create_all() desde el modelo; aquí se valida el
    INSERT..SELECT alineado por ID (la parte con lógica de la migración).
    """
    db.session.execute(text("DELETE FROM businesses"))
    db.session.execute(text("""
        INSERT INTO businesses (id, vertical, name, slug, is_active, created_at, updated_at)
        SELECT r.id, 'restaurant', r.name, r.slug, r.is_active,
               COALESCE(r.created_at, CURRENT_TIMESTAMP),
               COALESCE(r.created_at, CURRENT_TIMESTAMP)
        FROM restaurants r
    """))
    db.session.commit()


def test_migration_backfill_aligns_ids_one_to_one(db):
    """
    Valida el SQL de backfill de a1f6e3d2b4c5: cada restaurante termina con
    un Business del MISMO ID (la garantía que hace válidas las FKs
    restaurant_id existentes sin migrarlas).
    """
    # Dos restaurantes creados ANTES de que el puente exista, y sin espejo
    # (simula el estado previo a la migración): los borramos a mano.
    r1 = Restaurant(name='Pre A', slug='pre-a', whatsapp_phone='+573001111111')
    r2 = Restaurant(name='Pre B', slug='pre-b', whatsapp_phone='+573002222222')
    db.session.add_all([r1, r2])
    db.session.commit()
    db.session.execute(text("DELETE FROM businesses"))
    db.session.commit()

    assert Business.query.count() == 0  # estado pre-migración

    _run_businesses_migration_sql()

    rows = db.session.execute(
        text("SELECT id, vertical, slug FROM businesses ORDER BY id")).all()
    restaurant_ids = {r.id for r in Restaurant.query.all()}
    business_by_id = {rid: (vert, slug) for rid, vert, slug in rows}

    assert set(business_by_id.keys()) == restaurant_ids
    for rid, (vert, slug) in business_by_id.items():
        assert vert == 'restaurant'
        r = db.session.get(Restaurant, rid)
        assert r.slug == slug


def test_migration_backfill_is_idempotent_safe(db):
    """El INSERT..SELECT sin WHERE no debe usarse dos veces: PK única lo grita."""
    r = Restaurant(name='Pre', slug='pre', whatsapp_phone='+573003333333')
    db.session.add(r)
    db.session.commit()
    db.session.execute(text("DELETE FROM businesses"))
    db.session.commit()

    _run_businesses_migration_sql()
    with pytest.raises(IntegrityError):
        db.session.execute(text("""
            INSERT INTO businesses (id, vertical, name, slug, is_active, created_at, updated_at)
            SELECT r.id, 'restaurant', r.name, r.slug, r.is_active,
                   COALESCE(r.created_at, CURRENT_TIMESTAMP),
                   COALESCE(r.created_at, CURRENT_TIMESTAMP)
            FROM restaurants r
        """))
        db.session.commit()
    db.session.rollback()
