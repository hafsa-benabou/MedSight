"""Configuration centralisée (variables d'environnement / fichier .env)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BACKEND_DIR.parent


def _default_data_dir() -> Path:
    for candidate in (ROOT_DIR / "data", BACKEND_DIR / "data", Path("/data")):
        if candidate.exists():
            return candidate
    return ROOT_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(ROOT_DIR / ".env"), str(BACKEND_DIR / ".env")), env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "MEDISIGHT API"
    app_version: str = "1.0.0"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://medisight:medisight@localhost:5432/medisight"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    data_dir: Path = _default_data_dir()
    model_dir: Path | None = None

    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60
    rate_limit_chat: int = 30
    rate_limit_pills: int = 10
    rate_limit_default: int = 120

    max_upload_mb: float = 8.0
    max_image_pixels: int = 40_000_000
    store_uploaded_images: bool = False
    conversation_retention_hours: int = 72
    identification_retention_hours: int = 24

    llm_provider: str = "none"  # none | anthropic | openai
    llm_model: str = ""
    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com"
    llm_timeout_seconds: float = 20.0

    medbase_api_key: str | None = None
    medbase_base_url: str = "https://api.medbase.ma/api/v1"

    simulated_stock_enabled: bool = True
    ocr_engine: str = "tesseract"  # tesseract | easyocr | none
    tesseract_langs: str = "fra+eng"

    emergency_samu: str = "141"
    emergency_civil_protection: str = "15"
    poison_center: str = "0801 000 180"

    @property
    def resolved_model_dir(self) -> Path:
        return self.model_dir or (self.data_dir / "models")

    @property
    def llm_enabled(self) -> bool:
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key and self.llm_model)
        if self.llm_provider == "openai":
            return bool(self.openai_api_key and self.llm_model)
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
