"""Consistencia de la spec OpenAPI contra la app real (C-05 / VLZ-15).

La spec documentaba rutas que devolvían 404 (`/api/auth/sync-clerk`,
`/api/orders/create`). Este guardián recorre cada (path, método) documentado
y exige que exista en el `url_map` — la spec no puede volver a mentir.
"""
import re

HTTP_METHODS = {'get', 'post', 'put', 'patch', 'delete'}


def _spec_paths():
    """Dict de paths de la spec: {path: {method: operación}} (API pública)."""
    from app.routes.api_docs import _build_spec
    return _build_spec().to_dict()['paths']


def _normalize(rule):
    """`/api/orders/<int:id>` → `/api/orders/{id}` (sintaxis OpenAPI)."""
    return re.sub(r'<(?:(?:int|string|path|uuid|float):)?([^>]+)>', r'{\1}', rule)


class TestSpecMatchesReality:

    def test_every_documented_route_exists(self, app):
        paths = _spec_paths()

        real = {}
        for rule in app.url_map.iter_rules():
            for method in (rule.methods or set()) - {'HEAD', 'OPTIONS'}:
                real.setdefault(method, set()).add(_normalize(rule.rule))

        documented = [
            (m.upper(), p)
            for p, ops in paths.items()
            for m in ops if m in HTTP_METHODS
        ]
        assert documented, 'La spec está vacía — el guardián no sirve de nada.'

        missing = [(m, p) for m, p in documented if p not in real.get(m, set())]
        assert not missing, (
            f'La spec documenta {len(missing)} rutas que NO existen en la app: {missing}'
        )

    def test_the_two_previously_wrong_paths_are_fixed(self):
        paths = _spec_paths()
        # La ruta real vive en auth_bp sin prefijo /api/auth.
        assert '/api/sync-clerk' in paths
        assert '/api/auth/sync-clerk' not in paths
        # La creación autenticada es POST /api/orders, no /api/orders/create.
        assert '/api/orders/create' not in paths
        assert 'post' in paths['/api/orders']
