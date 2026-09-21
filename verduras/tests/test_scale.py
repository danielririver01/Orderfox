"""
Tests de la báscula digital (Semana 4).

Cubren:
- Parseadores de protocolo (funciones puras): generic ASCII y Toledo.
- Servicio read_weight con transporte FALSO (sin pyserial, sin hardware):
  unidades, redondeo a gramo, rango, cero, frames ilegibles, errores de
  transporte, cierre del puerto y protocolo desconocido.
- Endpoint GET /pos/<slug>/api/scale/weight: sesión obligatoria, disabled
  → 409 legible (nunca 500), lectura OK, y el flag scale_enabled en pos-data.
"""
import pytest

from app.models import Business
from verduras.services import scale as scale_service
from verduras.services.pos_auth import setup_pos_pin
from verduras.services.scale import (
    ScaleDisabledError,
    ScaleError,
    ScaleReadError,
    ScaleUnavailableError,
    parse_generic_ascii,
    parse_toledo,
)


def _slug():
    _slug.n = getattr(_slug, 'n', 0) + 1
    return f'scale-{_slug.n}'


@pytest.fixture()
def biz(db) -> Business:
    return Business.create_direct(vertical='verduras',
                                  name='Verduras La Báscula', slug=_slug())


class FakeTransport:
    """Transporte falso: devuelve frames pregrabados y registra el cierre."""

    def __init__(self, frames):
        self.frames = list(frames)
        self.closed = False

    def read_line(self, timeout_s: float) -> bytes:
        if not self.frames:
            return b''
        return self.frames.pop(0)

    def close(self) -> None:
        self.closed = True


def _read(frames, **kw):
    return scale_service.read_weight(
        FakeTransport(frames), enabled=True, **kw)


# ═════════════════ Parseadores (puros) ═════════════════


class TestGenericParser:
    def test_basic_ascii(self):
        assert parse_generic_ascii(b'S 1.234 kg\r\n') == 1.234

    def test_comma_decimal_locale_es(self):
        assert parse_generic_ascii(b'US 0,500 kg') == 0.5

    def test_integer_only(self):
        assert parse_generic_ascii(b'12 kg') == 12.0

    def test_empty_returns_none(self):
        assert parse_generic_ascii(b'') is None

    def test_no_number_returns_none(self):
        assert parse_generic_ascii(b'STABLE \r\n') is None


class TestToledoParser:
    def test_six_digits_are_grams(self):
        assert parse_toledo(b'000123') == 0.123

    def test_seven_digits_are_grams(self):
        assert parse_toledo(b'0012345') == 12.345  # 12345 g

    def test_decimal_frame_in_kg(self):
        assert parse_toledo(b'| 12.345 kg') == 12.345

    def test_comma_decimal_frame(self):
        assert parse_toledo(b'| 12,345 kg') == 12.345

    def test_too_short_digits_return_none(self):
        assert parse_toledo(b'123') is None  # no es frame de 6-7 dígitos

    def test_garbage_returns_none(self):
        assert parse_toledo(b'\x02??\x03') is None

    def test_empty_returns_none(self):
        assert parse_toledo(b'') is None


# ═════════════════ Servicio read_weight ═════════════════


class TestReadWeight:
    def test_disabled_raises(self):
        with pytest.raises(ScaleDisabledError):
            scale_service.read_weight(FakeTransport([b'1.0']),
                                      enabled=False)

    def test_unknown_protocol_raises(self):
        with pytest.raises(ScaleError, match='desconocido'):
            _read([b'1.0'], protocol='marte')

    def test_happy_path_generic(self):
        assert _read([b'S 1.234 kg\r\n']) == 1.234

    def test_happy_path_toledo_grams(self):
        assert _read([b'000500\n'], protocol='toledo') == 0.5

    def test_rounds_to_gram(self):
        assert _read([b'0.5004 kg']) == 0.5

    def test_zero_raises_read_error(self):
        with pytest.raises(ScaleReadError, match='cero'):
            _read([b'0.000 kg'])

    def test_negative_zero_raises(self):
        with pytest.raises(ScaleReadError):
            _read([b'-0.000'])

    def test_out_of_range_raises(self):
        with pytest.raises(ScaleReadError, match='rango'):
            _read([b'500.0 kg'])

    def test_garbage_frame_raises(self):
        with pytest.raises(ScaleReadError, match='manualmente'):
            _read([b'\x02\x03'])

    def test_timeout_empty_frame_raises(self):
        with pytest.raises(ScaleReadError):
            _read([])

    def test_transport_oserror_is_unavailable(self):
        class Broken:
            def read_line(self, timeout_s):
                raise OSError('port gone')

            def close(self):
                pass

        with pytest.raises(ScaleUnavailableError):
            scale_service.read_weight(Broken(), enabled=True)

    def test_provided_transport_not_closed_by_service(self):
        t = FakeTransport([b'1.0 kg'])
        scale_service.read_weight(t, enabled=True)
        assert t.closed is False  # el dueño del transporte lo cierra

    def test_own_transport_closed_via_factory(self, monkeypatch):
        t = FakeTransport([b'1.0 kg'])
        monkeypatch.setattr(scale_service, '_transport_factory',
                            lambda **kw: t)
        weight = scale_service.read_weight(
            None, enabled=True, port='COM9', baudrate=9600)
        assert weight == 1.0
        assert t.closed is True  # el servicio cierra lo que él abrió

    def test_factory_unavailable_raises(self, monkeypatch):
        def boom(**kw):
            raise ScaleUnavailableError('puerto ocupado')
        monkeypatch.setattr(scale_service, '_transport_factory', boom)
        with pytest.raises(ScaleUnavailableError, match='ocupado'):
            scale_service.read_weight(None, enabled=True)


# ═════════════════ Endpoint del POS ═════════════════


class TestScaleEndpoint:
    def _login(self, client, biz):
        setup_pos_pin(biz.id, '4321')
        client.post('/pos/login', data={'slug': biz.slug, 'pin': '4321'})

    def test_requires_pos_session(self, client, db, biz):
        res = client.get(f'/pos/{biz.slug}/api/scale/weight')
        assert res.status_code == 401

    def test_disabled_409_never_500(self, client, db, biz):
        self._login(client, biz)
        res = client.get(f'/pos/{biz.slug}/api/scale/weight')
        assert res.status_code == 409
        assert res.get_json()['error_code'] == 'scale_disabled'

    def test_read_ok_with_fake_transport(self, app, client, db, biz,
                                          monkeypatch):
        monkeypatch.setitem(app.config, 'SCALE_ENABLED', True)
        monkeypatch.setattr(
            scale_service, '_transport_factory',
            lambda **kw: FakeTransport([b'S 2.750 kg\r\n']))
        self._login(client, biz)
        res = client.get(f'/pos/{biz.slug}/api/scale/weight')
        assert res.status_code == 200
        assert res.get_json()['data']['weight_kg'] == 2.75

    def test_read_error_409_legible(self, app, client, db, biz,
                                     monkeypatch):
        monkeypatch.setitem(app.config, 'SCALE_ENABLED', True)
        monkeypatch.setattr(
            scale_service, '_transport_factory',
            lambda **kw: FakeTransport([b'\x02\x03']))
        self._login(client, biz)
        res = client.get(f'/pos/{biz.slug}/api/scale/weight')
        assert res.status_code == 409
        assert res.get_json()['error_code'] == 'scale_read_error'

    def test_unavailable_409(self, app, client, db, biz, monkeypatch):
        monkeypatch.setitem(app.config, 'SCALE_ENABLED', True)

        def boom(**kw):
            raise ScaleUnavailableError('puerto ocupado')
        monkeypatch.setattr(scale_service, '_transport_factory', boom)
        self._login(client, biz)
        res = client.get(f'/pos/{biz.slug}/api/scale/weight')
        assert res.status_code == 409
        assert res.get_json()['error_code'] == 'scale_unavailable'

    def test_pos_view_exposes_scale_flag_false_by_default(self, client, db,
                                                          biz):
        self._login(client, biz)
        res = client.get(f'/pos/{biz.slug}')
        assert res.status_code == 200
        assert b'"scale_enabled": false' in res.data

    def test_pos_view_exposes_scale_flag_when_enabled(self, app, client, db,
                                                      biz):
        app.config['SCALE_ENABLED'] = True
        try:
            self._login(client, biz)
            res = client.get(f'/pos/{biz.slug}')
            assert res.status_code == 200
            assert b'"scale_enabled": true' in res.data
        finally:
            app.config['SCALE_ENABLED'] = False
