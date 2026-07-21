"""
Settings API routes: read, update, test connections.
Supports both legacy Ollama and new OpenAI-compatible providers.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
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
    await settings_service.seed_if_empty(session)
    return await settings_service.get_all(session)


@router.put("/", response_model=List[SettingOut])
async def update_settings(
    body: SettingsUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Bulk update settings with validation."""
    try:
        updated = await settings_service.update(session, body.updates)
        logger.info("Settings updated", keys=list(body.updates.keys()))
        return updated
    except ValueError as e:
        raise HTTPException(422, str(e))



@router.post("/test-openai")
async def test_openai():
    """Test connectivity to the configured OpenAI-compatible API."""
    result = await settings_service.test_openai_connection()
    if result["ok"]:
        logger.info("OpenAI connection OK", models_count=len(result.get("models", [])))
    else:
        logger.warning("OpenAI connection failed", error=result.get("error"))
    return result


@router.get("/openai-models")
async def list_openai_models(
    base_url: str = Query(..., description="API base URL to query"),
    api_key: str = Query("", description="Optional API key for authentication"),
):
    """Fetch the list of available models from an OpenAI-compatible API."""
    result = await settings_service.test_openai_connection(
        base_url=base_url,
        api_key=api_key or None,
    )
    if result["ok"]:
        return {"ok": True, "models": result.get("models", [])}
    return {"ok": False, "models": [], "error": result.get("error", "")}
