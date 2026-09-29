"""SESSION_SECRET rule (2026-09-29): production refuses a missing / default / short secret; development falls back
to the public dev secret with a warning. No DB needed."""
import pytest

from auth.security import DEV_SESSION_SECRET, session_secret

STRONG = "x" * 48


def test_production_requires_a_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    for bad in ("", DEV_SESSION_SECRET, "short-secret"):
        monkeypatch.setenv("SESSION_SECRET", bad)
        with pytest.raises(RuntimeError):
            session_secret()


def test_production_accepts_a_strong_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", STRONG)
    assert session_secret() == STRONG


def test_development_falls_back_with_a_warning(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with pytest.warns(RuntimeWarning):
        assert session_secret() == DEV_SESSION_SECRET
