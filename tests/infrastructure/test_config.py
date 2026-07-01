import pytest
from pydantic import ValidationError

from src.infrastructure.config import Settings


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("DATABASE_URL", "ODDS_API_KEY", "KELLY_FRACTION", "MIN_EV_THRESHOLD", "SHARP_BOOKMAKER"):
        monkeypatch.delenv(key, raising=False)


def test_settings_loads_required_values_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/ev_betting")
    monkeypatch.setenv("ODDS_API_KEY", "secret-key")

    settings = Settings()

    assert settings.database_url == "postgresql://user:pass@localhost:5432/ev_betting"
    assert settings.odds_api_key == "secret-key"


def test_settings_applies_defaults_for_optional_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/ev_betting")
    monkeypatch.setenv("ODDS_API_KEY", "secret-key")

    settings = Settings()

    assert settings.kelly_fraction == 0.5
    assert settings.min_ev_threshold == 0.02
    assert settings.sharp_bookmaker == "Pinnacle"


def test_settings_reads_overridden_values_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/ev_betting")
    monkeypatch.setenv("ODDS_API_KEY", "secret-key")
    monkeypatch.setenv("KELLY_FRACTION", "0.25")
    monkeypatch.setenv("MIN_EV_THRESHOLD", "0.05")
    monkeypatch.setenv("SHARP_BOOKMAKER", "Betfair Exchange")

    settings = Settings()

    assert settings.kelly_fraction == 0.25
    assert settings.min_ev_threshold == 0.05
    assert settings.sharp_bookmaker == "Betfair Exchange"


def test_settings_requires_database_url_and_odds_api_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("invalid_kelly_fraction", ["-0.1", "1.1"])
def test_settings_rejects_kelly_fraction_out_of_range(
    monkeypatch: pytest.MonkeyPatch, tmp_path, invalid_kelly_fraction: str
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/ev_betting")
    monkeypatch.setenv("ODDS_API_KEY", "secret-key")
    monkeypatch.setenv("KELLY_FRACTION", invalid_kelly_fraction)

    with pytest.raises(ValidationError):
        Settings()
