"""
Metadata extraction service — NFO parsing + future TMDB integration.
"""

import xmltodict
from typing import Any, Dict, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


class MetadataService:
    """Extracts film metadata from various sources."""

    async def parse_nfo(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Parse an NFO file (XML format) and return raw dict."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                xml_content = f.read()
            data = xmltodict.parse(xml_content)
            logger.info("NFO parsed", path=file_path)
            return data
        except Exception as e:
            logger.error("NFO parse error", path=file_path, error=str(e))
            return None

    async def extract_film_metadata(self, nfo_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform raw NFO data into a flat metadata dict."""
        movie = nfo_data.get("movie", {})
        cast_raw = movie.get("actor", [])
        if isinstance(cast_raw, dict):
            cast_raw = [cast_raw]
        cast_names = [
            a.get("name", "") if isinstance(a, dict) else str(a)
            for a in cast_raw
        ]
        return {
            "title": movie.get("title", "Unknown Title"),
            "year": movie.get("year"),
            "director": movie.get("director"),
            "cast": [n for n in cast_names if n],
            "summary": movie.get("plot"),
        }

    # ─── Future: TMDB integration ──────────────────────────────────────

    async def fetch_tmdb_metadata(self, title: str, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Fetch metadata from TMDB API.
        TODO: implement when TMDB_API_KEY is configured.
        """
        logger.info("TMDB fetch not yet implemented", title=title)
        return None