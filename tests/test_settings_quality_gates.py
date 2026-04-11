import pytest


def test_settings_quality_gate_defaults(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CITATION_GATE_MIN_COVERAGE", raising=False)

    from common.config import Settings

    s = Settings(_env_file=None)
    assert s.citation_gate_min_coverage == pytest.approx(0.6)


def test_settings_quality_gate_env_overrides(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CITATION_GATE_MIN_COVERAGE", "0.75")

    from common.config import Settings

    s = Settings(_env_file=None)
    assert s.citation_gate_min_coverage == pytest.approx(0.75)
