"""
Context analysis service — builds the "world model" for a film.
Responsibilities: character profiling, lore summarization, glossary building.
"""

import json
from typing import List, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.models.database import Character, Film
from app.models.schemas import Gender
from app.services.llm_provider import LLMProvider, Message
from app.services.subtitle_service import SubtitleService, ParsedSubtitle, extract_sdh_speakers

logger = get_logger(__name__)


# ─── Gender mapping ─────────────────────────────────────────────────────────

_GENDER_MAP = {
    "male": "male",
    "female": "female",
    "neutral": "neutral",
    "nonbinary": "neutral",
    "unknown": "unknown",
    "": "unknown",
}


def _normalise_gender(raw: str) -> str:
    """Normalise the gender string returned by the LLM."""
    return _GENDER_MAP.get(raw.lower().strip(), "unknown")


class ContextService:
    """Builds and maintains the contextual world model for a film."""

    def __init__(self, llm_provider: LLMProvider):
        self.llm = llm_provider

    # ─── Character profiling ───────────────────────────────────────────

    async def build_character_profiles(
        self,
        film: Film,
        parsed_subtitle: ParsedSubtitle,
        subtitle_service: SubtitleService,
    ) -> List[Character]:
        """
        Multi-source character profile builder:
          1. Cast from metadata
          2. SDH speaker extraction
          3. LLM analysis of dialogue for gender/personality
        """
        characters: dict[str, Character] = {}

        # Source 1: Cast from metadata
        # (cast info can come from TMDB later — for now from film.summary heuristic)
        # TODO: integrate TMDB cast list

        # Source 2: SDH speakers
        sdh_speakers = subtitle_service.extract_all_sdh_speakers(parsed_subtitle)
        for name in sdh_speakers:
            characters[name] = Character(
                film_id=film.id,
                name=name,
                gender="unknown",
                meta={"source": "sdh"},
            )
        logger.info("SDH speakers added", speakers=sdh_speakers)

        # Source 3: LLM analysis of a representative dialogue sample
        if parsed_subtitle.lines:
            sample = self._build_dialogue_sample(parsed_subtitle, max_lines=80)
            llm_profiles = await self._llm_character_analysis(sample)
            for profile in llm_profiles:
                name = profile.get("name", "")
                if not name:
                    continue
                if name in characters:
                    # Enrich existing with LLM info
                    characters[name].gender = _normalise_gender(profile.get("gender", "unknown"))
                    characters[name].description = profile.get("description", "")
                    characters[name].meta = {"source": "sdh+llm"}
                else:
                    characters[name] = Character(
                        film_id=film.id,
                        name=name,
                        gender=_normalise_gender(profile.get("gender", "unknown")),
                        description=profile.get("description", ""),
                        meta={"source": "llm"},
                    )

        result = list(characters.values())
        logger.info("Character profiles built", count=len(result))
        return result

    async def _llm_character_analysis(self, dialogue_sample: str) -> List[dict]:
        """Ask the LLM to identify characters and their gender from dialogue."""
        messages = [
            Message(
                role="system",
                content=(
                    "You are a linguistic expert analyzing film dialogue. "
                    "You identify speaking characters and determine their likely gender "
                    "and personality from how they speak and what they say. "
                    "Always respond in valid JSON."
                ),
            ),
            Message(
                role="user",
                content=(
                    f"Analyze the following dialogue sample and identify all speaking characters.\n"
                    f"For each character provide: name, gender (male/female/neutral/unknown), "
                    f"and a brief personality description.\n\n"
                    f"Return a JSON object with a 'characters' key containing a list "
                    f"of {{'name': str, 'gender': str, 'description': str}} objects.\n\n"
                    f"Dialogue:\n{dialogue_sample}"
                ),
            ),
        ]

        try:
            raw = await self.llm.chat(messages, format_json=True, temperature=0.2, think=False)
            return self._parse_json_response(raw).get("characters", [])
        except Exception as e:
            logger.error("LLM character analysis failed", error=str(e))
            return []

    # ─── Lore summarization ─────────────────────────────────────────────

    async def generate_lore_summary(
        self,
        parsed_subtitle: ParsedSubtitle,
        character_profiles: List[Character],
    ) -> str:
        """
        Generate a narrative summary (lore) from subtitle content + character info.
        This summary is injected into every translation prompt.
        """
        sample = self._build_dialogue_sample(parsed_subtitle, max_lines=120)
        char_desc = "\n".join(
            f"- {c.name} ({c.gender}): {c.description or 'No description'}"
            for c in character_profiles
        )

        messages = [
            Message(
                role="system",
                content=(
                    "You are a film critic and narrative analyst. "
                    "Analyze the following dialogue and produce a concise summary focusing on: "
                    "1) The story arc and setting, 2) Relationships between characters, "
                    "3) The overall emotional tone. "
                    "This summary will help a translator maintain consistency."
                ),
            ),
            Message(
                role="user",
                content=(
                    f"Characters:\n{char_desc}\n\n"
                    f"Dialogue:\n{sample}"
                ),
            ),
        ]

        try:
            summary = await self.llm.chat(messages, temperature=0.4, think=True)
            logger.info("Lore summary generated", length=len(summary))
            return summary
        except Exception as e:
            logger.error("Lore summary generation failed", error=str(e))
            return "No summary available."

    # ─── Glossary building ──────────────────────────────────────────────

    async def build_glossary(
        self,
        parsed_subtitle: ParsedSubtitle,
        target_language: str,
    ) -> List[dict]:
        """
        Ask the LLM to build a film-specific glossary of proper nouns,
        slang, and cultural references with their accepted translation.
        """
        sample = self._build_dialogue_sample(parsed_subtitle, max_lines=100)

        messages = [
            Message(
                role="system",
                content=(
                    f"You are a professional translator specializing in cinematic localization to {target_language}. "
                    f"Identify proper nouns, slang, cultural references, and neologisms in the dialogue. "
                    f"For each, provide the source term and its accepted {target_language} translation. "
                    f"Always respond in valid JSON."
                ),
            ),
            Message(
                role="user",
                content=(
                    f"Build a translation glossary from this dialogue:\n{sample}\n\n"
                    f"Return a JSON object with a 'glossary' key containing a list of "
                    f"{{'source': str, 'target': str, 'notes': str}} objects."
                ),
            ),
        ]

        try:
            raw = await self.llm.chat(messages, format_json=True, temperature=0.2, think=False)
            return self._parse_json_response(raw).get("glossary", [])
        except Exception as e:
            logger.error("Glossary build failed", error=str(e))
            return []

    async def build_idiom_glossary(
        self,
        parsed_subtitle: ParsedSubtitle,
        target_language: str,
        source_language: str = "en",
    ) -> List[dict]:
        """
        Detect idiomatic/figurative expressions and provide their natural
        equivalent in the target language.

        This is a specialized LLM call focused ONLY on idioms, metaphors,
        and culturally-specific expressions that should NOT be translated literally.
        """
        sample = self._build_dialogue_sample(parsed_subtitle, max_lines=120)

        messages = [
            Message(
                role="system",
                content=(
                    f"Tu es un traductologue expert. "
                    f"Identifie les EXPRESSIONS IDIOMATIQUES, figurées, métaphoriques ou culturelles "
                    f"dans le dialogue ci-dessous. Pour chaque expression détectée, donne son "
                    f"ÉQUIVALENT NATUREL en {target_language} — pas une traduction littérale.\n\n"
                    f"ATTENTION : ne liste QUE les vraies expressions idiomatiques. "
                    f"Ne traduit pas les phrases normales.\n\n"
                    f"Réponds UNIQUEMENT en JSON : "
                    f"{{\"idioms\": [{{\"source\": str, \"target\": str, \"notes\": str}}]}}"
                ),
            ),
            Message(
                role="user",
                content=(
                    f"Dialogue en {source_language.upper()} :\n{sample}\n\n"
                    f"Identifie les expressions idiomatiques et donne leur équivalent en {target_language}."
                ),
            ),
        ]

        try:
            raw = await self.llm.chat(messages, format_json=True, temperature=0.2, think=True)
            idioms = self._parse_json_response(raw).get("idioms", [])
            # Tag idiom entries for clarity
            for entry in idioms:
                if not entry.get("notes"):
                    entry["notes"] = "expression idiomatique"
            logger.info("Idiom glossary built", count=len(idioms))
            return idioms
        except Exception as e:
            logger.error("Idiom glossary build failed", error=str(e))
            return []

    # ─── Helpers ─────────────────────────────────────────────────────────

    def _build_dialogue_sample(self, parsed: ParsedSubtitle, max_lines: int = 80) -> str:
        """Build a text sample from the first N non-empty subtitle lines."""
        lines = [l for l in parsed.lines if not l.is_empty][:max_lines]
        return "\n".join(f"[{l.index}] {l.text}" for l in lines)

    def _parse_json_response(self, raw: str) -> dict:
        """Try to extract JSON from the LLM response (may contain markdown fences)."""
        text = raw.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last fence lines
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM JSON response", raw=raw[:200])
            return {}