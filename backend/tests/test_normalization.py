import pytest


# Import after env vars set by conftest.py
from app.main import _normalize_gait, _normalize_angle


class TestNormalizeGait:
    def test_none_returns_none(self):
        assert _normalize_gait(None) is None

    def test_empty_returns_none(self):
        assert _normalize_gait("") is None

    def test_toelt_lowercase(self):
        assert _normalize_gait("toelt") == "Tölt"

    def test_toelt_with_umlaut(self):
        assert _normalize_gait("tölt") == "Tölt"

    def test_tolt_without_umlaut(self):
        assert _normalize_gait("tolt") == "Tölt"

    def test_canonical_toelt_passthrough(self):
        assert _normalize_gait("Tölt") == "Tölt"

    def test_trab(self):
        assert _normalize_gait("trab") == "Trab"

    def test_schritt(self):
        assert _normalize_gait("schritt") == "Schritt"

    def test_galopp(self):
        assert _normalize_gait("galopp") == "Galopp"

    def test_rennpass(self):
        assert _normalize_gait("rennpass") == "Rennpass"

    def test_unknown_value_passes_through(self):
        assert _normalize_gait("Unbekannt") == "Unbekannt"


class TestNormalizeAngle:
    def test_none_returns_none(self):
        assert _normalize_angle(None) is None

    def test_empty_returns_none(self):
        assert _normalize_angle("") is None

    def test_schraeg_vorn_ascii(self):
        assert _normalize_angle("schraeg_vorn") == "schräg_vorn"

    def test_schraeg_hinten_ascii(self):
        assert _normalize_angle("schraeg_hinten") == "schräg_hinten"

    def test_canonical_umlaut_passthrough(self):
        assert _normalize_angle("schräg_vorn") == "schräg_vorn"

    def test_seitlich_links(self):
        assert _normalize_angle("seitlich_links") == "seitlich_links"

    def test_seitlich_rechts(self):
        assert _normalize_angle("seitlich_rechts") == "seitlich_rechts"

    def test_unknown_value_passes_through(self):
        assert _normalize_angle("diagonal") == "diagonal"
