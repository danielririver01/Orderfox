import re

from app.services.theme_service import (
    BRAND_THEMES,
    DEFAULT_BRAND_COLOR,
    get_branding_permissions,
    theme_for_color,
)
from app.utils.subscription import get_plan_limits


class TestPlanLimitsBranding:

    def test_branding_flags_in_all_plans(self):
        for plan in ('emprendedor', 'crecimiento', 'elite', 'trial'):
            limits = get_plan_limits(plan)
            assert 'brand_themes' in limits
            assert 'brand_custom_color' in limits

    def test_emprendedor_no_branding(self):
        limits = get_plan_limits('emprendedor')
        assert limits['brand_themes'] is False
        assert limits['brand_custom_color'] is False

    def test_crecimiento_themes_only(self):
        limits = get_plan_limits('crecimiento')
        assert limits['brand_themes'] is True
        assert limits['brand_custom_color'] is False

    def test_elite_full_branding(self):
        limits = get_plan_limits('elite')
        assert limits['brand_themes'] is True
        assert limits['brand_custom_color'] is True

    def test_trial_full_branding(self):
        limits = get_plan_limits('trial')
        assert limits['brand_themes'] is True
        assert limits['brand_custom_color'] is True

    def test_unknown_plan_safe_defaults(self):
        limits = get_plan_limits('platinum_dream')
        assert limits['brand_themes'] is False
        assert limits['brand_custom_color'] is False


class TestBrandThemes:

    def test_exactly_eight_themes(self):
        assert len(BRAND_THEMES) == 8

    def test_each_theme_has_required_fields(self):
        required = {'key', 'name', 'hex'}
        for theme in BRAND_THEMES:
            assert required.issubset(theme.keys())
            assert theme['key']
            assert theme['name']

    def test_all_hexes_valid_rgb(self):
        for theme in BRAND_THEMES:
            assert re.fullmatch(r'#[0-9A-Fa-f]{6}', theme['hex']), theme['hex']

    def test_expected_theme_palette(self):
        hexes = {t['hex'].lower() for t in BRAND_THEMES}
        assert hexes == {
            '#ff7a29', '#e5484d', '#30a46c', '#2563eb',
            '#7c3aed', '#ec4899', '#f59e0b', '#0ea5e9',
        }

    def test_default_color_is_theme(self):
        assert DEFAULT_BRAND_COLOR.lower() in {t['hex'].lower() for t in BRAND_THEMES}

    def test_theme_for_color_case_insensitive(self):
        assert theme_for_color('#FF7A29') == theme_for_color('#ff7a29')
        assert theme_for_color('#FF7A29')['key'] == 'velzia'


class TestGetBrandingPermissions:

    def test_emprendedor(self):
        perms = get_branding_permissions('emprendedor')
        assert perms == {'themes_allowed': False, 'custom_allowed': False}

    def test_crecimiento(self):
        perms = get_branding_permissions('crecimiento')
        assert perms == {'themes_allowed': True, 'custom_allowed': False}

    def test_elite(self):
        perms = get_branding_permissions('elite')
        assert perms == {'themes_allowed': True, 'custom_allowed': True}

    def test_trial(self):
        perms = get_branding_permissions('trial')
        assert perms == {'themes_allowed': True, 'custom_allowed': True}

    def test_unknown_plan(self):
        perms = get_branding_permissions('platinum_dream')
        assert perms == {'themes_allowed': False, 'custom_allowed': False}


class TestCanApplyBrandColor:
    """Validación defensiva en DashboardService.update_profile."""

    @staticmethod
    def _restaurant(plan_type, brand_color=None):
        return type('R', (), {'plan_type': plan_type, 'brand_color': brand_color})

    def test_elite_can_apply_any_hex(self):
        from app.services.dashboard_service import DashboardService
        r = self._restaurant('elite')
        assert DashboardService._can_apply_brand_color(r, '#123456') is True

    def test_trial_can_apply_any_hex(self):
        from app.services.dashboard_service import DashboardService
        r = self._restaurant('trial')
        assert DashboardService._can_apply_brand_color(r, '#abcdef') is True

    def test_crecimiento_accepts_themes(self):
        from app.services.dashboard_service import DashboardService
        r = self._restaurant('crecimiento')
        assert DashboardService._can_apply_brand_color(r, '#30A46C') is True

    def test_crecimiento_rejects_free_hex(self):
        from app.services.dashboard_service import DashboardService
        r = self._restaurant('crecimiento')
        assert DashboardService._can_apply_brand_color(r, '#123456') is False

    def test_emprendedor_rejects_theme(self):
        from app.services.dashboard_service import DashboardService
        r = self._restaurant('emprendedor')
        assert DashboardService._can_apply_brand_color(r, '#30A46C') is False

    def test_emprendedor_accepts_default(self):
        from app.services.dashboard_service import DashboardService
        r = self._restaurant('emprendedor')
        assert DashboardService._can_apply_brand_color(r, DEFAULT_BRAND_COLOR) is True

    def test_downgrade_respects_saved_color(self):
        """Si el restaurante ya guardó un color libre (de un plan superior),
        se respeta — solo se bloquean cambios futuros."""
        from app.services.dashboard_service import DashboardService
        r = self._restaurant('emprendedor', brand_color='#123456')
        assert DashboardService._can_apply_brand_color(r, '#123456') is True
        assert DashboardService._can_apply_brand_color(r, '#654321') is False

    def test_downgrade_respects_saved_theme(self):
        from app.services.dashboard_service import DashboardService
        r = self._restaurant('crecimiento', brand_color='#30A46C')
        assert DashboardService._can_apply_brand_color(r, '#30A46C') is True

    def test_case_insensitive_comparison(self):
        from app.services.dashboard_service import DashboardService
        r = self._restaurant('emprendedor', brand_color='#FF7A29')
        assert DashboardService._can_apply_brand_color(r, '#ff7a29') is True