"""
Subtitle parsing, writing and analysis service.

Uses pysubs2 under the hood for format-agnostic parsing (SRT, VTT, ASS).
Adds domain-specific logic: CPS calculation, SDH extraction, line grouping.
"""

import os
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import pysubs2
from pysubs2 import SSAFile, SSAEvent

from app.core.logging import get_logger

logger = get_logger(__name__)


# ─── Domain types ───────────────────────────────────────────────────────────

@dataclass
class SubtitleLine:
    """A single subtitle line — the atomic unit we work with."""
    index: int          # 1-based sequential index
    start_ms: int       # Start time in milliseconds
    end_ms: int         # End time in milliseconds
    text: str           # Cleaned text content
    raw_text: str       # Original text with all formatting
    style: str = "Default"

    @property
    def duration_ms(self) -> int:
        return max(self.end_ms - self.start_ms, 1)

    @property
    def duration_s(self) -> float:
        return self.duration_ms / 1000.0

    @property
    def cps(self) -> float:
        """Characters per second (excluding whitespace for accuracy)."""
        clean = self.text.replace(" ", "").replace("\n", "")
        return len(clean) / self.duration_s if self.duration_s > 0 else 0.0

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


@dataclass
class ParsedSubtitle:
    """Result of parsing a subtitle file."""
    lines: List[SubtitleLine] = field(default_factory=list)
    format: str = "srt"
    source_path: str = ""
    total_lines: int = 0

    def __post_init__(self):
        self.total_lines = len(self.lines)

    def get_batch(self, start: int, size: int) -> List[SubtitleLine]:
        """Get a slice of lines for batch processing."""
        return self.lines[start:start + size]

    def lines_with_context(
        self, window_size: int = 20
    ) -> List[Tuple[SubtitleLine, List[SubtitleLine]]]:
        """
        Yield (current_line, previous_N_lines) tuples for sliding window.
        """
        result = []
        for i, line in enumerate(self.lines):
            start = max(0, i - window_size)
            context = self.lines[start:i]
            result.append((line, context))
        return result


# ─── SDH Extraction ─────────────────────────────────────────────────────────

def extract_sdh_speakers(text: str) -> List[str]:
    """
    Extract speaker identifiers from SDH text.
    Patterns: [JOHN]:, (JOHN):, JOHN:, FEMALE VOICE:
    """
    import re
    speakers = []
    patterns = [
        r'\[([A-Z\s]+)\]\s*:',   # [JOHN]:
        r'\(([A-Z\s]+)\)\s*:',   # (JOHN):
        r'^([A-Z]{2,}(?:\s[A-Z]+)*)\s*:',  # JOHN: or FEMALE VOICE:
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            speaker = match.group(1).strip()
            if speaker and len(speaker) > 1:
                speakers.append(speaker)
    return speakers


def clean_sdh_tags(text: str) -> str:
    """Remove SDH notation from text for cleaner translation."""
    import re
    # Remove speaker tags [JOHN]: or (JOHN):
    text = re.sub(r'[\[(][A-Z\s]+[\])]:\s*', '', text)
    # Remove sound descriptions (thunder rumbling), [gasps], etc.
    text = re.sub(r'[\[(][^)\]]*[\])]', '', text)
    return text.strip()


# ─── Service ─────────────────────────────────────────────────────────────────

class SubtitleService:
    """Parse, analyze, and write subtitle files."""

    def __init__(self, cps_limit: int = 25):
        self.cps_limit = cps_limit

    # ── Parsing ──────────────────────────────────────────────────────────

    def parse_file(self, file_path: str) -> ParsedSubtitle:
        """
        Parse any supported subtitle file into our domain model.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Subtitle file not found: {file_path}")

        # Determine format from extension
        fmt = path.suffix.lstrip(".").lower()
        if fmt not in ("srt", "vtt", "ass", "ssa"):
            # Try SRT as fallback
            fmt = "srt"

        try:
            subs = pysubs2.load(file_path)
        except Exception as e:
            logger.error("Failed to parse subtitle file", path=file_path, error=str(e))
            raise

        lines = []
        for idx, event in enumerate(subs):
            if event.is_comment or not event.text.strip():
                continue
            line = SubtitleLine(
                index=idx + 1,
                start_ms=event.start,
                end_ms=event.end,
                text=event.text.replace("\\N", "\n").replace("\\n", "\n"),
                raw_text=event.text,
                style=event.style or "Default",
            )
            lines.append(line)

        parsed = ParsedSubtitle(
            lines=lines,
            format=fmt,
            source_path=str(file_path),
        )
        logger.info("Parsed subtitle file", path=file_path, lines=len(lines), format=fmt)
        return parsed

    def parse_bytes(self, content: bytes, filename: str) -> ParsedSubtitle:
        """Parse subtitle content from raw bytes (e.g. from upload)."""
        suffix = Path(filename).suffix or ".srt"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="wb") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            return self.parse_file(tmp_path)
        finally:
            os.unlink(tmp_path)

    # ── Writing ──────────────────────────────────────────────────────────

    def write_srt(
        self,
        lines: List[SubtitleLine],
        output_path: str,
    ) -> str:
        """
        Write lines back to an SRT file, preserving timing.
        """
        subs = SSAFile()
        for line in lines:
            event = SSAEvent(
                start=line.start_ms,
                end=line.end_ms,
                text=line.text.replace("\n", "\\N"),
                style=line.style,
            )
            subs.append(event)

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        subs.save(output_path, format_="srt")
        logger.info("Wrote SRT file", path=output_path, lines=len(lines))
        return output_path

    # ── Analysis ─────────────────────────────────────────────────────────

    def check_cps_issues(self, parsed: ParsedSubtitle) -> List[SubtitleLine]:
        """Return lines that exceed the CPS limit."""
        over_cps = [l for l in parsed.lines if l.cps > self.cps_limit]
        if over_cps:
            logger.warning(
                "CPS issues detected",
                count=len(over_cps),
                limit=self.cps_limit,
                worst=max(l.cps for l in over_cps),
            )
        return over_cps

    def extract_all_sdh_speakers(self, parsed: ParsedSubtitle) -> List[str]:
        """Collect all unique speaker identifiers from SDH subtitles."""
        speakers = set()
        for line in parsed.lines:
            for s in extract_sdh_speakers(line.raw_text):
                speakers.add(s)
        result = sorted(speakers)
        if result:
            logger.info("SDH speakers found", speakers=result)
        return result