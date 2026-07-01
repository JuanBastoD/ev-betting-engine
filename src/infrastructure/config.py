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
    kelly_fraction: float = Field(default=0.5, ge=0.0, le=1.0, alias="KELLY_FRACTION")
    min_ev_threshold: float = Field(default=0.02, ge=0.0, alias="MIN_EV_THRESHOLD")
    sharp_bookmaker: str = Field(default="Pinnacle", alias="SHARP_BOOKMAKER")
