"""
Unit tests for SubtitleService — parsing, writing, SDH, CPS.
"""

import os
import tempfile

import pytest

from app.services.subtitle_service import (
    SubtitleService,
    SubtitleLine,
    ParsedSubtitle,
    extract_sdh_speakers,
    clean_sdh_tags,
)


class TestSubtitleParsing:
    """Tests for parse_file and parse_bytes."""

    def test_parse_valid_srt(self, sample_srt_content):
        svc = SubtitleService()
        tmp = tempfile.NamedTemporaryFile(suffix=".srt", mode="w", delete=False, encoding="utf-8")
        try:
            tmp.write(sample_srt_content)
            tmp.close()

            parsed = svc.parse_file(tmp.name)
            assert isinstance(parsed, ParsedSubtitle)
            assert parsed.format == "srt"
            assert len(parsed.lines) == 7
            assert parsed.lines[0].index == 1
            assert parsed.lines[0].start_ms == 1000
            assert parsed.lines[0].end_ms == 4500
            assert "parasite" in parsed.lines[0].text
        finally:
            os.unlink(tmp.name)

    def test_parse_empty_srt(self):
        svc = SubtitleService()
        tmp = tempfile.NamedTemporaryFile(suffix=".srt", mode="w", delete=False, encoding="utf-8")
        try:
            tmp.write("1\n00:00:01,000 --> 00:00:02,000\n\n")
            tmp.close()

            parsed = svc.parse_file(tmp.name)
            # Empty text lines and comments are skipped by pysubs2
            assert len(parsed.lines) == 0
        finally:
            os.unlink(tmp.name)

    def test_parse_bytes(self, sample_srt_content):
        svc = SubtitleService()
        content = sample_srt_content.encode("utf-8")

        parsed = svc.parse_bytes(content, "test.srt")
        assert len(parsed.lines) == 7
        assert parsed.format == "srt"

    def test_parse_file_not_found(self):
        svc = SubtitleService()
        with pytest.raises(FileNotFoundError):
            svc.parse_file("/nonexistent/file.srt")

    def test_parse_vtt(self):
        """VTT files should also be parseable via pysubs2."""
        svc = SubtitleService()
        vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nHello world\n"
        tmp = tempfile.NamedTemporaryFile(suffix=".vtt", mode="w", delete=False, encoding="utf-8")
        try:
            tmp.write(vtt_content)
            tmp.close()
            parsed = svc.parse_file(tmp.name)
            assert parsed.format == "vtt"
            assert len(parsed.lines) == 1
            assert parsed.lines[0].text == "Hello world"
        finally:
            os.unlink(tmp.name)


class TestSubtitleWriting:
    """Tests for write_srt."""

    def test_write_and_reparse_roundtrip(self):
        svc = SubtitleService()
        lines = [
            SubtitleLine(index=1, start_ms=1000, end_ms=4000, text="Hello", raw_text="Hello"),
            SubtitleLine(index=2, start_ms=5000, end_ms=8000, text="World", raw_text="World"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "output.srt")
            result = svc.write_srt(lines, out_path)
            assert result == out_path
            assert os.path.isfile(out_path)

            # Re-parse and verify timing + text preserved
            parsed = svc.parse_file(out_path)
            assert len(parsed.lines) == 2
            assert parsed.lines[0].start_ms == 1000
            assert parsed.lines[0].text == "Hello"
            assert parsed.lines[1].start_ms == 5000
            assert parsed.lines[1].text == "World"

    def test_write_creates_directories(self):
        svc = SubtitleService()
        lines = [SubtitleLine(index=1, start_ms=0, end_ms=1000, text="Hi", raw_text="Hi")]
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "sub", "deep", "test.srt")
            svc.write_srt(lines, out)
            assert os.path.isfile(out)


class TestSDHExtraction:
    """Tests for SDH speaker extraction and cleaning."""

    def test_extract_bracket_speaker(self):
        speakers = extract_sdh_speakers("[JOHN]: Hello there")
        assert "JOHN" in speakers

    def test_extract_paren_speaker(self):
        speakers = extract_sdh_speakers("(MARY): What did you say?")
        assert "MARY" in speakers

    def test_extract_multi_word_speaker(self):
        speakers = extract_sdh_speakers("FEMALE VOICE: Help me")
        assert "FEMALE VOICE" in speakers

    def test_extract_no_speaker(self):
        speakers = extract_sdh_speakers("Just a normal subtitle.")
        assert speakers == []

    def test_clean_sdh_brackets(self):
        result = clean_sdh_tags("[JOHN]: Hello [knocking on door] world")
        assert result == "Hello world"

    def test_clean_sdh_parentheses(self):
        result = clean_sdh_tags("(MARY): (gasps) I can't believe it")
        assert result == "I can't believe it"

    def test_clean_sdh_no_tags(self):
        result = clean_sdh_tags("Normal subtitle text.")
        assert result == "Normal subtitle text."

    def test_clean_sdh_sound_only(self):
        """A line that is ONLY a sound description should become empty."""
        result = clean_sdh_tags("[thunder rumbling]")
        assert result == ""

    def test_clean_sdh_from_parsed(self):
        svc = SubtitleService()
        lines = [
            SubtitleLine(index=1, start_ms=0, end_ms=1000, text="Hello", raw_text="[JOHN]: Hello"),
            SubtitleLine(index=2, start_ms=2000, end_ms=3000, text="normal", raw_text="normal text"),
            SubtitleLine(index=3, start_ms=4000, end_ms=5000, text="[bang]", raw_text="[bang]"),
        ]
        parsed = ParsedSubtitle(lines=lines, format="srt")
        cleaned = svc.clean_sdh_from_parsed(parsed)

        assert len(cleaned.lines) == 2  # empty line removed
        assert cleaned.lines[0].text == "Hello"
        assert cleaned.lines[1].text == "normal text"

    def test_extract_all_sdh_speakers_from_parsed(self):
        svc = SubtitleService()
        lines = [
            SubtitleLine(index=1, start_ms=0, end_ms=1000, text="a", raw_text="[JOHN]: Hello"),
            SubtitleLine(index=2, start_ms=1, end_ms=2, text="b", raw_text="(JOHN): Again"),
            SubtitleLine(index=3, start_ms=2, end_ms=3, text="c", raw_text="[MARY]: Hi"),
        ]
        parsed = ParsedSubtitle(lines=lines, format="srt")
        speakers = svc.extract_all_sdh_speakers(parsed)
        assert sorted(speakers) == ["JOHN", "MARY"]


class TestCPS:
    """Tests for Characters Per Second calculation and checking."""

    def test_cps_normal(self):
        line = SubtitleLine(index=1, start_ms=0, end_ms=2000, text="Hello", raw_text="Hello")
        # 5 chars / 2.0s = 2.5 cps
        assert line.cps == pytest.approx(2.5)

    def test_cps_zero_duration(self):
        """Duration of 0ms should be clamped to 1ms to avoid division by zero."""
        line = SubtitleLine(index=1, start_ms=1000, end_ms=1000, text="Hello", raw_text="Hello")
        # 5 chars / 0.001s = 5000 cps
        assert line.cps == 5000.0

    def test_cps_with_spaces(self):
        """Spaces and newlines are excluded from character count."""
        line = SubtitleLine(index=1, start_ms=0, end_ms=1000, text="H i\n", raw_text="H i\n")
        assert line.cps == 2.0  # only "Hi" = 2 chars

    def test_check_cps_issues(self):
        svc = SubtitleService(cps_limit=25)
        lines = [
            SubtitleLine(index=1, start_ms=0, end_ms=2000, text="OK", raw_text="OK"),
            SubtitleLine(index=2, start_ms=2000, end_ms=3000,
                         text="This line is way too long and exceeds the CPS limit easily",
                         raw_text="This line is way too long and exceeds the CPS limit easily"),
        ]
        parsed = ParsedSubtitle(lines=lines, format="srt")
        issues = svc.check_cps_issues(parsed)
        assert len(issues) == 1
        assert issues[0].index == 2

    def test_cps_limit_default(self):
        svc = SubtitleService()
        assert svc.cps_limit == 25
