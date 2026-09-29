"""
Pruebas de la verificación de firma de los webhooks de Mercado Pago (VLZ-28).

REGLA DE ESTAS PRUEBAS: las firmas esperadas se calculan **a mano** dentro del
test, armando el manifiesto oficial carácter a carácter. Nunca se usan las
funciones de `app.utils.mp_webhook` para generar lo que luego se valida; si lo
hiciéramos, la prueba validaría la implementación contra sí misma y volvería a
pasar aunque el esquema fuese el equivocado — que es exactamente cómo el fallo
original sobrevivió.

Manifiesto oficial de Mercado Pago:

    id:<data.id>;request-id:<x-request-id>;ts:<ts>;
"""

import hashlib
import hmac

import pytest

from app.utils.mp_webhook import (
    build_mp_manifest,
    extract_mp_request_id,
    extract_mp_signature,
    verify_mp_signature,
)

SECRETO = 'clave_secreta_de_prueba'
DATA_ID = '132646402927'
REQUEST_ID = '5e278faa-87ac-48e9-8ebd-567f2d341302'
TS = '1790653594'


def firmar(manifiesto, secreto=SECRETO):
    """HMAC-SHA256 hex, calculado aquí y no por el código bajo prueba."""
    return hmac.new(
        secreto.encode('utf-8'), manifiesto.encode('utf-8'), hashlib.sha256
    ).hexdigest()


def firma_oficial(data_id=DATA_ID, request_id=REQUEST_ID, ts=TS, secreto=SECRETO):
    """Firma tal y como la calcularía Mercado Pago."""
    return firmar(f"id:{data_id};request-id:{request_id};ts:{ts};", secreto)


class TestManifiesto:
    """El manifiesto debe salir carácter a carácter como lo define MP."""

    def test_formato_oficial_exacto(self):
        assert build_mp_manifest(DATA_ID, REQUEST_ID, TS) == (
            f"id:{DATA_ID};request-id:{REQUEST_ID};ts:{TS};"
        )

    def test_data_id_se_normaliza_a_minusculas(self):
        assert build_mp_manifest('AbC123', REQUEST_ID, TS).startswith('id:abc123;')

    def test_omite_el_par_cuando_falta_el_request_id(self):
        # MP especifica que los pares sin valor se omiten, no se dejan vacíos.
        assert build_mp_manifest(DATA_ID, None, TS) == f"id:{DATA_ID};ts:{TS};"

    def test_omite_el_par_cuando_falta_el_ts(self):
        assert build_mp_manifest(DATA_ID, REQUEST_ID, None) == (
            f"id:{DATA_ID};request-id:{REQUEST_ID};"
        )

    def test_sin_ningun_dato_queda_vacio(self):
        assert build_mp_manifest(None, None, None) == ''


class TestVerificacionDeFirma:

    def test_acepta_una_firma_real_de_mercado_pago(self):
        """La prueba que el código anterior NO pasaba."""
        assert verify_mp_signature(
            DATA_ID, REQUEST_ID, TS, firma_oficial(), SECRETO
        ) is True

    def test_rechaza_el_esquema_antiguo(self):
        """Regresión de VLZ-28.

        El código anterior firmaba `{data_id}.{ts}.{secreto}`. Esa firma no
        debe validar nunca más: si volviese a hacerlo, es que alguien
        reintrodujo el esquema inventado.
        """
        firma_vieja = firmar(f"{DATA_ID}.{TS}.{SECRETO}")
        assert verify_mp_signature(
            DATA_ID, REQUEST_ID, TS, firma_vieja, SECRETO
        ) is False

    def test_rechaza_otro_secreto(self):
        ajena = firma_oficial(secreto='otro_secreto_distinto')
        assert verify_mp_signature(DATA_ID, REQUEST_ID, TS, ajena, SECRETO) is False

    def test_rechaza_firma_de_otro_pago(self):
        otra = firma_oficial(data_id='999999999')
        assert verify_mp_signature(DATA_ID, REQUEST_ID, TS, otra, SECRETO) is False

    def test_rechaza_si_cambia_el_request_id(self):
        """Si no se usara x-request-id, esta prueba fallaría."""
        otra = firma_oficial(request_id='00000000-0000-0000-0000-000000000000')
        assert verify_mp_signature(DATA_ID, REQUEST_ID, TS, otra, SECRETO) is False

    def test_rechaza_si_cambia_el_ts(self):
        otra = firma_oficial(ts='1700000000')
        assert verify_mp_signature(DATA_ID, REQUEST_ID, TS, otra, SECRETO) is False

    def test_acepta_hex_en_mayusculas(self):
        assert verify_mp_signature(
            DATA_ID, REQUEST_ID, TS, firma_oficial().upper(), SECRETO
        ) is True

    @pytest.mark.parametrize('v1, secreto', [
        (None, SECRETO),
        ('', SECRETO),
        (firma_oficial(), None),
        (firma_oficial(), ''),
    ])
    def test_rechaza_sin_firma_o_sin_secreto(self, v1, secreto):
        assert verify_mp_signature(DATA_ID, REQUEST_ID, TS, v1, secreto) is False

    def test_valida_aunque_no_llegue_el_request_id(self):
        """MP omite el par; la firma debe cuadrar con el manifiesto sin él."""
        sin_request = firmar(f"id:{DATA_ID};ts:{TS};")
        assert verify_mp_signature(DATA_ID, None, TS, sin_request, SECRETO) is True


class TestExtraccionDeCabeceras:

    def test_extrae_ts_y_v1(self):
        assert extract_mp_signature({'x-signature': f'ts={TS},v1=abc123'}) == (TS, 'abc123')

    def test_tolera_espacios_y_orden(self):
        assert extract_mp_signature({'x-signature': f' v1=abc123 , ts={TS} '}) == (TS, 'abc123')

    def test_ignora_v2_y_otros_campos(self):
        ts, v1 = extract_mp_signature({'x-signature': f'ts={TS},v1=abc,v2=def'})
        assert (ts, v1) == (TS, 'abc')

    def test_sin_cabecera_devuelve_nada(self):
        assert extract_mp_signature({}) == (None, None)

    def test_extrae_request_id(self):
        assert extract_mp_request_id({'x-request-id': REQUEST_ID}) == REQUEST_ID
        assert extract_mp_request_id({}) is None


class TestEndpointWebhook:
    """El endpoint completo, no solo la función de firma."""

    def _enviar(self, client, v1, request_id=REQUEST_ID, data_id=DATA_ID):
        return client.post(
            '/api/v1/webhooks/mercadopago',
            json={'action': 'payment.created', 'type': 'payment',
                  'data': {'id': data_id}},
            headers={'x-signature': f'ts={TS},v1={v1}', 'x-request-id': request_id},
        )

    def test_firma_real_de_mp_ya_no_devuelve_401(self, app, client):
        """Antes del arreglo esto era 401 invalid_signature."""
        app.config['MP_WEBHOOK_SECRET'] = SECRETO
        resp = self._enviar(client, firma_oficial())
        assert resp.status_code != 401, (
            'Una notificación legítima de Mercado Pago está siendo rechazada'
        )

    def test_firma_invalida_sigue_devolviendo_401(self, app, client):
        app.config['MP_WEBHOOK_SECRET'] = SECRETO
        resp = self._enviar(client, '0' * 64)
        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'invalid_signature'

    def test_sin_secreto_configurado_rechaza_todo(self, app, client):
        """Fail-closed: mejor no procesar que procesar sin verificar."""
        app.config['MP_WEBHOOK_SECRET'] = None
        resp = self._enviar(client, firma_oficial())
        assert resp.status_code == 503
        assert resp.get_json()['error'] == 'webhook_not_configured'

    def test_toma_el_data_id_del_query_param(self, app, client):
        """MP envía data.id en la URL además del cuerpo."""
        app.config['MP_WEBHOOK_SECRET'] = SECRETO
        resp = client.post(
            f'/api/v1/webhooks/mercadopago?data.id={DATA_ID}&type=payment',
            json={'action': 'payment.created', 'type': 'payment'},
            headers={'x-signature': f'ts={TS},v1={firma_oficial()}',
                     'x-request-id': REQUEST_ID},
        )
        assert resp.status_code != 401
