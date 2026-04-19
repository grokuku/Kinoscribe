"""
Translation service — the core translation engine.
Implements sliding-window contextual translation with glossary injection
and CPS-aware quality control.
"""

import json
from typing import List, Optional

from app.core.logging import get_logger
from app.models.database import Character, Film, GlossaryEntry, TranslationTask
from app.services.llm_provider import LLMProvider, Message
from app.services.subtitle_service import SubtitleLine, ParsedSubtitle, SubtitleService
from app.services.context_service import ContextService

logger = get_logger(__name__)


class TranslationService:
    """Context-aware subtitle translation engine."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        context_service: ContextService,
        subtitle_service: SubtitleService,
    ):
        self.llm = llm_provider
        self.context = context_service
        self.subtitle_service = subtitle_service

    async def translate_film_subtitles(
        self,
        task: TranslationTask,
        film: Film,
        parsed: ParsedSubtitle,
        window_size: int = 20,
        batch_size: int = 10,
        temperature: float = 0.3,
    ) -> List[SubtitleLine]:
        """
        Full translation pipeline with sliding window.
        Returns translated SubtitleLine objects.
        """
        target_lang = task.source_language or film.target_language
        characters = film.characters
        glossary = film.glossary_entries

        # Build static context parts (injected in every prompt)
        char_context = self._format_characters(characters)
        glossary_context = self._format_glossary(glossary)

        translated: List[SubtitleLine] = []

        total = len(parsed.lines)
        logger.info(
            "Starting translation",
            task_id=task.id,
            total_lines=total,
            target_lang=target_lang,
            batch_size=batch_size,
            window_size=window_size,
        )

        for i in range(0, total, batch_size):
            batch = parsed.lines[i:i + batch_size]
            # Previous translated lines as context window
            context_window = translated[-window_size:] if len(translated) > window_size else translated

            try:
                translated_batch = await self._translate_batch(
                    batch=batch,
                    context_window=context_window,
                    target_language=target_lang,
                    char_context=char_context,
                    glossary_context=glossary_context,
                    lore_summary=task.lore_summary or "",
                )
                translated.extend(translated_batch)
            except Exception as e:
                logger.error(
                    "Batch translation failed, keeping originals",
                    batch_start=i,
                    error=str(e),
                )
                # Fallback: keep original lines
                translated.extend(batch)

            # Update progress
            progress = int(((i + len(batch)) / total) * 100)
            task.progress_pct = min(progress, 99)  # Keep at 99 until fully done
            logger.debug("Translation progress", pct=task.progress_pct, lines_done=len(translated))

        # CPS check — flag dense translations for potential refinement
        cps_issues = self.subtitle_service.check_cps_issues(
            ParsedSubtitle(lines=translated, format=parsed.format)
        )
        if cps_issues:
            logger.warning(
                "CPS issues in translation",
                count=len(cps_issues),
                note="Refine pass recommended",
            )

        task.progress_pct = 100
        logger.info("Translation complete", task_id=task.id, lines=total)
        return translated

    async def _translate_batch(
        self,
        batch: List[SubtitleLine],
        context_window: List[SubtitleLine],
        target_language: str,
        char_context: str,
        glossary_context: str,
        lore_summary: str,
    ) -> List[SubtitleLine]:
        """Translate a batch of lines with full context injection."""

        # Format previous context
        ctx_text = ""
        if context_window:
            ctx_text = "\n".join(
                f"[{l.index}] {l.text}"
                for l in context_window[-10:]  # Last 10 translated lines
            )

        # Format lines to translate
        lines_text = "\n".join(
            f"[{l.index}] {l.text}"
            for l in batch
        )

        system_msg = (
            "You are an expert film subtitle translator specializing in cinematic localization.\n"
            "RULES:\n"
            "1. Maintain the original timing indices exactly.\n"
            "2. Preserve tone, personality, and register of each character.\n"
            "3. Respect character genders for grammatical agreement in the target language.\n"
            "4. Use the glossary for consistent translation of proper nouns and slang.\n"
            "5. Keep subtitle text concise — target under 25 characters per second.\n"
            "6. Return ONLY a JSON object with a 'lines' key containing a list of "
            "{'index': int, 'text': str} objects.\n"
            "7. Do NOT include any explanation or commentary."
        )

        user_parts = [f"Translate the following subtitle lines to {target_language}.\n"]

        if lore_summary:
            user_parts.append(f"STORY CONTEXT:\n{lore_summary}\n")
        if char_context:
            user_parts.append(f"CHARACTER PROFILES:\n{char_context}\n")
        if glossary_context:
            user_parts.append(f"GLOSSARY:\n{glossary_context}\n")
        if ctx_text:
            user_parts.append(f"PREVIOUS TRANSLATED LINES (for consistency):\n{ctx_text}\n")

        user_parts.append(f"LINES TO TRANSLATE:\n{lines_text}")

        messages = [
            Message(role="system", content=system_msg),
            Message(role="user", content="\n".join(user_parts)),
        ]

        raw = await self.llm.chat(messages, format_json=True, temperature=0.3)
        parsed_response = self._parse_json_response(raw)

        # Build translated lines map
        translated_map: dict[int, str] = {}
        for item in parsed_response.get("lines", []):
            try:
                idx = int(item.get("index", 0))
                translated_map[idx] = item.get("text", "")
            except (ValueError, TypeError):
                continue

        # Merge: use original SubtitleLine but replace text
        result = []
        for line in batch:
            new_text = translated_map.get(line.index, line.text)
            result.append(SubtitleLine(
                index=line.index,
                start_ms=line.start_ms,
                end_ms=line.end_ms,
                text=new_text,
                raw_text=new_text,
                style=line.style,
            ))
        return result

    # ─── Formatting helpers ─────────────────────────────────────────────

    @staticmethod
    def _format_characters(characters: List[Character]) -> str:
        if not characters:
            return ""
        lines = []
        for c in characters:
            desc = f" — {c.description}" if c.description else ""
            lines.append(f"- {c.name} ({c.gender}){desc}")
        return "\n".join(lines)

    @staticmethod
    def _format_glossary(glossary: List[GlossaryEntry]) -> str:
        if not glossary:
            return ""
        lines = []
        for g in glossary:
            note = f" ({g.notes})" if g.notes else ""
            lines.append(f"- {g.source_term} → {g.target_term}{note}")
        return "\n".join(lines)

    @staticmethod
    def _parse_json_response(raw: str) -> dict:
        """Extract JSON from potentially markdown-fenced LLM output."""
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse translation JSON", raw=raw[:300])
            return {}