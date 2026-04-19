"""
Application configuration loaded from environment / .env file.
Uses pydantic-settings for validation and type coercion.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ─── App ───────────────────────────────────────────
    app_name: str = "Kinoscribe"
    debug: bool = False

    # ─── Database ──────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./data/subtitle_translator.db"

    # ─── LLM / Ollama ─────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    ollama_refine_model: str = "llama3"

    # ─── Translation defaults ──────────────────────────
    default_source_language: str = "en"
    default_target_language: str = "fr"

    # ─── Subtitle constraints ──────────────────────────
    cps_limit: int = 25
    sliding_window_size: int = 20

    # ─── TMDB ──────────────────────────────────────────
    tmdb_api_key: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Singleton — import this everywhere
settings = Settings()