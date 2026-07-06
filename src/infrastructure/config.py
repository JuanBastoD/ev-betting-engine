from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, sourced from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(alias="DATABASE_URL")
    odds_api_key: str = Field(alias="ODDS_API_KEY")
    odds_api_base_url: str = Field(
        default="https://api.the-odds-api.com/v4", alias="ODDS_API_BASE_URL"
    )
    sportmonks_api_token: str = Field(alias="SPORTMONKS_API_TOKEN")
    sportmonks_base_url: str = Field(
        default="https://api.sportmonks.com/v3/football", alias="SPORTMONKS_BASE_URL"
    )
    kelly_fraction: float = Field(default=0.5, ge=0.0, le=1.0, alias="KELLY_FRACTION")
    min_ev_threshold: float = Field(default=0.02, ge=0.0, alias="MIN_EV_THRESHOLD")
    sharp_bookmaker: str = Field(default="Pinnacle", alias="SHARP_BOOKMAKER")

    # --- Phase 9: orchestration (pipeline/scheduler/API) ---
    sport_key: str = Field(default="soccer_epl", alias="SPORT_KEY")
    local_bookmaker: str = Field(default="Betplay", alias="LOCAL_BOOKMAKER")
    # Average goals scored per team per match across the tracked league -
    # team_strength.py needs this to normalize attack/defense ratings, and
    # deriving it needs every team's form at once (out of scope for a
    # single-team StatsProvider call), so it's plain configuration for now.
    league_average_goals: float = Field(default=1.35, gt=0.0, alias="LEAGUE_AVERAGE_GOALS")
    # CONFIRMATION (both market and statistical model must agree) or
    # INDEPENDENT (statistical model alone) - see ConfirmationMode.
    match_confirmation_mode: str = Field(default="CONFIRMATION", alias="MATCH_CONFIRMATION_MODE")
    market_weight: float = Field(default=0.5, ge=0.0, le=1.0, alias="MARKET_WEIGHT")
    pipeline_interval_seconds: int = Field(default=3600, gt=0, alias="PIPELINE_INTERVAL_SECONDS")
