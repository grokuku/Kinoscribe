"""
Settings service — single source of truth for all app configuration.
On first boot, seeds the DB from env vars / defaults.
Services read from here, not from env vars directly.
"""

from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as env_settings
from app.core.logging import get_logger
from app.models.database import Setting

logger = get_logger(__name__)


# ─── Default settings schema ────────────────────────────────────────────────
# Each entry: key, default, description, input_type, options, category

DEFAULTS: List[dict] = [
    # ── Ollama / LLM ──────────────────────────────
    {
        "key": "ollama_base_url",
        "default": env_settings.ollama_base_url,
        "description": "URL du serveur Ollama sur le réseau",
        "input_type": "url",
        "category": "llm",
    },
    {
        "key": "ollama_model",
        "default": env_settings.ollama_model,
        "description": "Modèle LLM pour la traduction",
        "input_type": "text",
        "category": "llm",
    },
    {
        "key": "ollama_refine_model",
        "default": env_settings.ollama_refine_model,
        "description": "Modèle pour la passe d'affinage (si différent)",
        "input_type": "text",
        "category": "llm",
    },
    {
        "key": "llm_temperature",
        "default": "0.3",
        "description": "Température de génération (0.0 = déterministe, 1.0 = créatif)",
        "input_type": "number",
        "category": "llm",
    },
    # ── Traduction ────────────────────────────────
    {
        "key": "default_source_language",
        "default": env_settings.default_source_language,
        "description": "Langue source par défaut",
        "input_type": "select",
        "options": "en,es,de,it,pt,ja,ko,zh",
        "category": "translation",
    },
    {
        "key": "default_target_language",
        "default": env_settings.default_target_language,
        "description": "Langue cible par défaut",
        "input_type": "select",
        "options": "fr,en,es,de,it,pt",
        "category": "translation",
    },
    {
        "key": "sliding_window_size",
        "default": str(env_settings.sliding_window_size),
        "description": "Nombre de lignes précédentes dans la fenêtre glissante",
        "input_type": "number",
        "category": "translation",
    },
    {
        "key": "batch_size",
        "default": "10",
        "description": "Nombre de lignes traduites par appel LLM",
        "input_type": "number",
        "category": "translation",
    },
    # ── Sous-titres ───────────────────────────────
    {
        "key": "cps_limit",
        "default": str(env_settings.cps_limit),
        "description": "Limite caractères/seconde (au-delà = trop dense)",
        "input_type": "number",
        "category": "subtitles",
    },
    {
        "key": "auto_clean_sdh",
        "default": "true",
        "description": "Nettoyer les balises SDH (ex: [JOHN]:, (gasps)) avant traduction",
        "input_type": "select",
        "options": "true,false",
        "category": "subtitles",
    },
    # ── TMDB ───────────────────────────────────────
    {
        "key": "tmdb_api_key",
        "default": "",
        "description": "Clé API TMDB (optionnel, pour enrichir les métadonnées)",
        "input_type": "password",
        "category": "external",
    },
]


class SettingsService:
    """Read / write application settings from the database."""

    async def seed_if_empty(self, session: AsyncSession) -> None:
        """Populate settings table on first boot (idempotent)."""
        result = await session.execute(select(Setting))
        existing = result.scalars().first()
        if existing:
            return  # Already seeded

        for d in DEFAULTS:
            s = Setting(
                key=d["key"],
                value=d["default"],
                description=d.get("description", ""),
                input_type=d.get("input_type", "text"),
                options=d.get("options"),
                category=d.get("category", "general"),
            )
            session.add(s)
        await session.commit()
        logger.info("Settings seeded from defaults", count=len(DEFAULTS))

    async def get_all(self, session: AsyncSession) -> List[Setting]:
        result = await session.execute(select(Setting).order_by(Setting.category, Setting.key))
        return list(result.scalars().all())

    async def get(self, session: AsyncSession, key: str) -> str:
        s = await session.get(Setting, key)
        return s.value if s else ""

    async def get_int(self, session: AsyncSession, key: str) -> int:
        val = await self.get(session, key)
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    async def get_float(self, session: AsyncSession, key: str) -> float:
        val = await self.get(session, key)
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    async def get_bool(self, session: AsyncSession, key: str) -> bool:
        val = await self.get(session, key)
        return val.lower() in ("true", "1", "yes")

    async def update(self, session: AsyncSession, updates: Dict[str, str]) -> List[Setting]:
        """Bulk update settings. Returns updated list."""
        for key, value in updates.items():
            s = await session.get(Setting, key)
            if s:
                s.value = value
        await session.commit()
        return await self.get_all(session)

    async def test_ollama_connection(self, base_url: Optional[str] = None) -> dict:
        """Test connectivity to the Ollama server."""
        import aiohttp

        url = (base_url or await self.get_async("ollama_base_url")).rstrip("/")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}/api/tags", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = [m.get("name", "") for m in data.get("models", [])]
                        return {"ok": True, "models": models}
                    return {"ok": False, "error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # Async get without requiring an explicit session (creates its own)
    async def get_async(self, key: str) -> str:
        from app.core.database import async_session
        async with async_session() as session:
            return await self.get(session, key)


settings_service = SettingsService()