import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class Settings:
    def __init__(self) -> None:
        self.app_env: str = os.getenv("APP_ENV", "development")
        self.database_url: str = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:juras123@localhost:5432/juras",
        )
        self.cors_origins: list[str] = [
            o.strip()
            for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
            if o.strip()
        ]
        self.simulation_max_active: int = int(os.getenv("SIMULATION_MAX_ACTIVE", "3"))
        self.simulation_default_interval_ms: int = int(
            os.getenv("SIMULATION_DEFAULT_INTERVAL_MS", "2000")
        )
        self.simulation_min_interval_ms: int = int(
            os.getenv("SIMULATION_MIN_INTERVAL_MS", "500")
        )
        self.simulation_max_duration_sec: int = int(
            os.getenv("SIMULATION_MAX_DURATION_SEC", "300")
        )
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.mapbox_access_token: str = os.getenv("MAPBOX_ACCESS_TOKEN", "")
        self.mapbox_station_cache_seconds: int = int(
            os.getenv("MAPBOX_STATION_CACHE_SECONDS", "600")
        )
        self.data_label: str = "illustrative demo data, not surveyed Purani Mandi geometry"


settings = Settings()
