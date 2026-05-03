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

    # ─── Security ─────────────────────────────────────
    secret_key: str = "change-me-in-production-use-a-long-random-string"
    # SSH host key verification: 'none' (accept all), 'auto' (use ~/.ssh/known_hosts), or path to known_hosts file
    ssh_known_hosts: str = "none"

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

    # ─── Mount (SSHFS/CIFS) ──────────────────────────────
    mount_base_dir: str = ""  # empty = auto (data/mounts)
    mount_enabled: bool = True  # Global toggle: disable to skip all mounting

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Singleton — import this everywhere
settings = Settings()