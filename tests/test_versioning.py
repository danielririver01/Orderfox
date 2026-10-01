"""Alineación de las fuentes de versión (C-04 / D-11 / VLZ-14).

La fuente única de verdad es el último **tag de Git**; `settings.APP_VERSION`
se sincroniza con él (regla en AGENTS.md) y el resto de fuentes se alinean a
`APP_VERSION`. Este guardián impide que vuelvan a divergir en silencio —
antes convivían cinco valores distintos y ninguno era el real.
"""
import json
from pathlib import Path

from settings import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


class TestVersionSourcesAligned:

    def test_app_version_has_tag_format(self):
        """APP_VERSION debe ser semver puro: el tag es 'v' + esto."""
        assert APP_VERSION == '1.6.0'
        parts = APP_VERSION.split('.')
        assert len(parts) == 3 and all(p.isdigit() for p in parts)

    def test_package_jsons_match_app_version(self):
        for rel in ('package.json', 'astro/package.json'):
            pkg = json.loads((ROOT / rel).read_text(encoding='utf-8'))
            assert pkg['version'] == APP_VERSION, (
                f'{rel} dice {pkg["version"]!r} y APP_VERSION es {APP_VERSION!r}: '
                'alinearlo al publicar la versión (fuente única = último tag de Git)'
            )

    def test_openapi_spec_uses_app_version(self, client):
        """La spec se construye desde settings.APP_VERSION: ya no se hardcodea
        (antes decía 1.3.0 con la app en 1.6.0)."""
        res = client.get('/api/docs/spec.json')
        assert res.status_code == 200
        assert res.get_json()['info']['version'] == APP_VERSION
