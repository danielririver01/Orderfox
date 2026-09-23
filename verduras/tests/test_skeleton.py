"""
Contratos base del módulo Verduras (Tier MODULO).

Cubren:
1. API /api/businesses filtrada por el vertical (nunca expone espejos
   de restaurantes).
2. Servicio de contexto: require_business valida existencia/vertical/activo.
3. El puente Business ↔ Restaurant está ACTIVO en el proceso del módulo
   (crear un Restaurant de core desde el módulo genera su espejo).

NOTA: el smoke de endpoints base (/, /health, 404) se movió a
verify_verduras_skeleton.py (Tier DESECHABLE, no corre en CI).
"""
import pytest

from app.models import Business, Restaurant
from verduras.services.context import (
    BusinessNotFoundError,
    BusinessNotVegetalError,
    require_business,
)

SLUG = 'v'


def _slug():
    """Slug único por test (los slugs son unique)."""
    _slug.n = getattr(_slug, 'n', 0) + 1
    return f'verduras-{_slug.n}'


def _mk_restaurant(db):
    """Crea un Restaurant de core; el puente genera su Business espejo."""
    r = Restaurant(
        name=f'Rest {_slug()}',
        slug=_slug(),
        whatsapp_phone='+573001112233',
    )
    db.session.add(r)
    db.session.flush()
    return r


def _mk_verduras_business(db):
    """Business directo del vertical (banda >= 1_000_000)."""
    return Business.create_direct(vertical='verduras', name='Verduras La Central',
                                  slug=_slug())


# ── API /api/businesses ─────────────────────────────────────


class TestBusinessesAPI:
    def test_list_only_verduras_vertical(self, client, db):
        _mk_restaurant(db)  # espejo vertical='restaurant': NO debe aparecer
        biz = _mk_verduras_business(db)
        res = client.get('/api/businesses')
        assert res.status_code == 200
        items = res.get_json()['data']['businesses']
        assert [b['id'] for b in items] == [biz.id]
        assert items[0]['vertical'] == 'verduras'

    def test_detail_ok(self, client, db):
        biz = _mk_verduras_business(db)
        res = client.get(f'/api/businesses/{biz.id}')
        assert res.status_code == 200
        assert res.get_json()['data']['name'] == 'Verduras La Central'

    def test_detail_not_found(self, client, db):
        # db requerido: garantiza create_all aunque ningún test previo haya
        # creado datos en esta función de test.
        res = client.get('/api/businesses/987654321')
        assert res.status_code == 404
        assert res.get_json()['error_code'] == 'business_not_found'

    def test_detail_restaurant_mirror_conflict(self, client, db):
        """Un espejo de restaurante existe pero NO es tenant de este vertical."""
        r = _mk_restaurant(db)
        res = client.get(f'/api/businesses/{r.id}')
        assert res.status_code == 409
        assert res.get_json()['error_code'] == 'business_not_available'


# ── Servicio de contexto ────────────────────────────────────


class TestContextService:
    def test_require_business_ok(self, db):
        biz = _mk_verduras_business(db)
        assert require_business(biz.id).id == biz.id

    def test_require_business_missing(self, db):
        with pytest.raises(BusinessNotFoundError):
            require_business(987654321)

    def test_require_business_wrong_vertical(self, db):
        r = _mk_restaurant(db)
        with pytest.raises(BusinessNotVegetalError):
            require_business(r.id)

    def test_require_business_inactive(self, db):
        biz = _mk_verduras_business(db)
        biz.is_active = False
        db.session.commit()
        with pytest.raises(BusinessNotVegetalError):
            require_business(biz.id)


# ── Puente activo en el proceso del módulo ──────────────────


class TestCoreBridgeInModule:
    def test_restaurant_creation_makes_business_mirror(self, db):
        r = _mk_restaurant(db)
        mirror = db.session.get(Business, r.id)
        assert mirror is not None
        assert mirror.vertical == 'restaurant'
        assert mirror.name == r.name

    def test_direct_vertical_ids_never_collide(self, db):
        biz = _mk_verduras_business(db)
        assert biz.id >= 1_000_000
        r = _mk_restaurant(db)
        assert r.id < 1_000_000
        assert r.id != biz.id
