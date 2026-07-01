import pytest
from pydantic import ValidationError

from src.infrastructure.config import Settings


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "DATABASE_URL",
        "ODDS_API_KEY",
        "ODDS_API_BASE_URL",
        "SPORTMONKS_API_TOKEN",
        "SPORTMONKS_BASE_URL",
        "KELLY_FRACTION",
        "MIN_EV_THRESHOLD",
        "SHARP_BOOKMAKER",
    ):
        monkeypatch.delenv(key, raising=False)


def _set_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/ev_betting")
    monkeypatch.setenv("ODDS_API_KEY", "secret-key")
    monkeypatch.setenv("SPORTMONKS_API_TOKEN", "secret-token")


def test_settings_loads_required_values_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch)

    settings = Settings()

    assert settings.database_url == "postgresql://user:pass@localhost:5432/ev_betting"
    assert settings.odds_api_key == "secret-key"
    assert settings.sportmonks_api_token == "secret-token"


def test_settings_applies_defaults_for_optional_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch)

    settings = Settings()

    assert settings.odds_api_base_url == "https://api.the-odds-api.com/v4"
    assert settings.sportmonks_base_url == "https://api.sportmonks.com/v3/football"
    assert settings.kelly_fraction == 0.5
    assert settings.min_ev_threshold == 0.02
    assert settings.sharp_bookmaker == "Pinnacle"


def test_settings_reads_overridden_values_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch)
    monkeypatch.setenv("ODDS_API_BASE_URL", "https://mock.odds.local/v4")
    monkeypatch.setenv("SPORTMONKS_BASE_URL", "https://mock.sportmonks.local/v3/football")
    monkeypatch.setenv("KELLY_FRACTION", "0.25")
    monkeypatch.setenv("MIN_EV_THRESHOLD", "0.05")
    monkeypatch.setenv("SHARP_BOOKMAKER", "Betfair Exchange")

    settings = Settings()

    assert settings.odds_api_base_url == "https://mock.odds.local/v4"
    assert settings.sportmonks_base_url == "https://mock.sportmonks.local/v3/football"
    assert settings.kelly_fraction == 0.25
    assert settings.min_ev_threshold == 0.05
    assert settings.sharp_bookmaker == "Betfair Exchange"


def test_settings_requires_database_url_and_odds_api_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValidationError):
        Settings()


def test_settings_requires_sportmonks_api_token(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/ev_betting")
    monkeypatch.setenv("ODDS_API_KEY", "secret-key")

    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("invalid_kelly_fraction", ["-0.1", "1.1"])
def test_settings_rejects_kelly_fraction_out_of_range(
    monkeypatch: pytest.MonkeyPatch, tmp_path, invalid_kelly_fraction: str
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch)
    monkeypatch.setenv("KELLY_FRACTION", invalid_kelly_fraction)

    with pytest.raises(ValidationError):
        Settings()
