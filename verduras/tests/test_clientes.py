"""
Clientes / Fiados: cuentas con abonos y saldo derivado (Tier GUARDIAN).

Es dinero (deuda): duplicado de nombre reutiliza, abono mayor al saldo
se rechaza, cliente ajeno es 404, libreta exige cliente y la deuda se
DERIVA (fiados − abonos), jamás se almacena.
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models import Business
from verduras.services import clientes as clientes_svc
from verduras.services.catalog import create_category, create_product
from verduras.services.sales import (
    VerdurasNotFoundError,
    VerdurasValidationError,
    create_sale,
)


def _slug():
    _slug.n = getattr(_slug, 'n', 0) + 1
    return f'fiado-{_slug.n}'


@pytest.fixture()
def biz(db) -> Business:
    return Business.create_direct(vertical='verduras',
                                  name='Verduras Fiado', slug=_slug())


@pytest.fixture()
def catalog_row(db, biz):
    cat = create_category(biz.id, 'Hortalizas')
    tomate = create_product(biz.id, cat.id, 'Tomate', 'kg', '3200.00')
    return SimpleNamespace(cat=cat, tomate=tomate)


@pytest.fixture()
def carmen(db, biz):
    return clientes_svc.get_or_create_client(biz.id, 'Carmen R.')


def _login_client(client, biz):
    from verduras.services.pos_auth import setup_pos_pin
    setup_pos_pin(biz.id, '4321')
    return client.post('/pos/login', data={'slug': biz.slug, 'pin': '4321'})


class TestClientesServicio:
    def test_duplicado_reutiliza(self, db, biz):
        c1 = clientes_svc.get_or_create_client(biz.id, 'Carmen R.')
        c2 = clientes_svc.get_or_create_client(biz.id, 'Carmen R.')
        assert c1.id == c2.id

    def test_nombre_requerido(self, db, biz):
        with pytest.raises(clientes_svc.ClientesValidationError):
            clientes_svc.get_or_create_client(biz.id, '   ')

    def test_saldo_derivado(self, db, biz, catalog_row, carmen):
        create_sale(biz.id,
                    [{'product_id': catalog_row.tomate.id,
                      'quantity': '1'}],
                    payment_method='libreta', client_id=carmen.id)
        create_sale(biz.id,
                    [{'product_id': catalog_row.tomate.id,
                      'quantity': '1'}],
                    payment_method='libreta', client_id=carmen.id)
        clientes_svc.registrar_abono(biz.id, carmen.id, '2000')
        assert clientes_svc.saldo_cliente(
            biz.id, carmen.id) == Decimal('4400.00')

    def test_abono_mayor_al_saldo_400(self, db, biz, catalog_row, carmen):
        create_sale(biz.id,
                    [{'product_id': catalog_row.tomate.id,
                      'quantity': '1'}],
                    payment_method='libreta', client_id=carmen.id)
        with pytest.raises(clientes_svc.ClientesValidationError,
                           match='supera la deuda'):
            clientes_svc.registrar_abono(biz.id, carmen.id, '999999')

    def test_cliente_ajeno_404(self, db, biz, carmen):
        other = Business.create_direct(vertical='verduras',
                                       name='Otro', slug=_slug())
        with pytest.raises(clientes_svc.ClientesNotFoundError):
            clientes_svc.saldo_cliente(other.id, carmen.id)

    def test_compromiso_ok_e_invalido(self, db, biz, carmen):
        c = clientes_svc.set_compromiso(biz.id, carmen.id, '2026-10-01')
        assert str(c.fecha_compromiso) == '2026-10-01'
        with pytest.raises(clientes_svc.ClientesValidationError):
            clientes_svc.set_compromiso(biz.id, carmen.id, 'ayer')


class TestLibretaExigeCliente:
    def test_sin_cliente_400(self, db, biz, catalog_row):
        with pytest.raises(VerdurasValidationError, match='exige un cliente'):
            create_sale(biz.id,
                        [{'product_id': catalog_row.tomate.id,
                          'quantity': '1'}],
                        payment_method='libreta')

    def test_cliente_ajeno_404(self, db, biz, catalog_row, carmen):
        other = Business.create_direct(vertical='verduras',
                                       name='Otro', slug=_slug())
        with pytest.raises(VerdurasNotFoundError):
            create_sale(other.id,
                        [{'product_id': catalog_row.tomate.id,
                          'quantity': '1'}],
                        payment_method='libreta', client_id=carmen.id)

    def test_cliente_en_otro_metodo_400(self, db, biz, catalog_row,
                                        carmen):
        with pytest.raises(VerdurasValidationError,
                           match='solo aplica'):
            create_sale(biz.id,
                        [{'product_id': catalog_row.tomate.id,
                          'quantity': '1'}],
                        payment_method='efectivo', client_id=carmen.id)


class TestClientesRutas:
    def test_buscar_y_detalle(self, client, db, biz, catalog_row, carmen):
        _login_client(client, biz)
        res = client.get(f'/pos/{biz.slug}/clientes/buscar?q=carmen')
        assert res.status_code == 200
        assert res.get_json()['data']['clientes'][0]['name'] == 'Carmen R.'
        cid = carmen.id
        res = client.get(f'/pos/{biz.slug}/clientes/{cid}')
        assert res.status_code == 200
        assert res.get_json()['data']['saldo'] == '$0'

    def test_abonar_y_compromiso_por_ruta(self, client, db, biz,
                                          catalog_row, carmen):
        create_sale(biz.id,
                    [{'product_id': catalog_row.tomate.id,
                      'quantity': '1'}],
                    payment_method='libreta', client_id=carmen.id)
        _login_client(client, biz)
        cid = carmen.id
        res = client.post(f'/pos/{biz.slug}/clientes/{cid}/abonar',
                          json={'monto': '1200'})
        assert res.status_code == 201
        assert res.get_json()['data']['saldo'] == '2000.00'
        res = client.post(f'/pos/{biz.slug}/clientes/{cid}/compromiso',
                          json={'fecha_compromiso': '2026-11-01'})
        assert res.status_code == 200

    def test_rutas_exigen_sesion(self, client, db, biz, carmen):
        assert client.get(
            f'/pos/{biz.slug}/clientes/buscar').status_code == 401
        assert client.post(
            f'/pos/{biz.slug}/clientes/{carmen.id}/abonar',
            json={'monto': '100'}).status_code == 401


class TestClientesPantalla:
    def test_pagina_con_saldos(self, client, db, biz, catalog_row,
                               carmen):
        create_sale(biz.id,
                    [{'product_id': catalog_row.tomate.id,
                      'quantity': '1'}],
                    payment_method='libreta', client_id=carmen.id)
        _login_client(client, biz)
        res = client.get(f'/pos/{biz.slug}/clientes')
        html = res.get_data(as_text=True)
        assert res.status_code == 200
        assert 'Carmen R.' in html
        assert '3.200' in html

    def test_pagina_exige_sesion(self, client, db, biz):
        from flask import url_for
        res = client.get(f'/pos/{biz.slug}/clientes',
                         follow_redirects=False)
        assert res.status_code == 302

    def test_nav_desbloqueada_en_pos(self, client, db, biz, catalog_row,
                                     carmen):
        _login_client(client, biz)
        html = client.get(f'/pos/{biz.slug}').get_data(as_text=True)
        assert f'/pos/{biz.slug}/clientes' in html
