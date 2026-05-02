"""
Settings API routes: read, update, test connections.
"""

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.logging import get_logger
from app.models.schemas import SettingOut, SettingsUpdate
from app.services.settings_service import settings_service

logger = get_logger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/", response_model=List[SettingOut])
async def list_settings(
    session: AsyncSession = Depends(get_session),
):
    """Get all application settings."""
    # Ensure seeded
    await settings_service.seed_if_empty(session)
    return await settings_service.get_all(session)


@router.put("/", response_model=List[SettingOut])
async def update_settings(
    body: SettingsUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Bulk update settings."""
    updated = await settings_service.update(session, body.updates)
    logger.info("Settings updated", keys=list(body.updates.keys()))
    return updated


@router.post("/test-ollama")
async def test_ollama():
    """Test connectivity to the configured Ollama server."""
    result = await settings_service.test_ollama_connection()
    if result["ok"]:
        logger.info("Ollama connection OK", models=result.get("models", []))
    else:
        logger.warning("Ollama connection failed", error=result.get("error"))
    return result


@router.get("/ollama-models")
async def list_ollama_models(
    base_url: str = Query(..., description="Ollama server URL to query"),
):
    """Fetch the list of available models from a specific Ollama server URL."""
    result = await settings_service.test_ollama_connection(base_url)
    if result["ok"]:
        return {"ok": True, "models": result.get("models", [])}
    return {"ok": False, "models": [], "error": result.get("error", "")}