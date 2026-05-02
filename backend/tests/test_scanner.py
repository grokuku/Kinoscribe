"""
Tests for scanner service — filename parsing, NFO parsing, language detection.
"""

import os
import tempfile

import pytest

from app.services.scanner_service import (
    parse_subtitle_filename,
    parse_nfo_content,
    is_gendered_language,
    SUBTITLE_PATTERN,
)


class TestSubtitleFilenameParsing:
    """Tests for parse_subtitle_filename."""

    def test_english_srt(self):
        result = parse_subtitle_filename("movie.en.srt")
        assert result["language"] == "en"
        assert result["is_sdh"] is False
        assert result["is_forced"] is False

    def test_french_sdh(self):
        result = parse_subtitle_filename("movie.fr.sdh.srt")
        assert result["language"] == "fr"
        assert result["is_sdh"] is True
        assert result["is_forced"] is False

    def test_spanish_forced(self):
        result = parse_subtitle_filename("movie.es.forced.srt")
        assert result["language"] == "es"
        assert result["is_sdh"] is False
        assert result["is_forced"] is True

    def test_german_sdh_forced(self):
        result = parse_subtitle_filename("movie.de.sdh.forced.ass")
        assert result["language"] == "de"
        assert result["is_sdh"] is True
        assert result["is_forced"] is True

    def test_no_language_code(self):
        result = parse_subtitle_filename("movie.srt")
        assert result["language"] == "und"
        assert result["is_sdh"] is False

    def test_not_a_subtitle(self):
        """Non-subtitle files should return None language."""
        result = parse_subtitle_filename("movie.mp4")
        assert result["language"] is None

    def test_language_in_path(self):
        """Language code embedded in directory path."""
        m = SUBTITLE_PATTERN.search("/movies/film.en.sdh.srt")
        assert m is not None
        assert m.group(1) == "en"


class TestGenderedLanguage:
    """Tests for is_gendered_language."""

    def test_french_is_gendered(self):
        assert is_gendered_language("fr") is True

    def test_english_not_gendered(self):
        assert is_gendered_language("en") is False

    def test_japanese_not_gendered(self):
        assert is_gendered_language("ja") is False

    def test_spanish_gendered(self):
        assert is_gendered_language("es") is True

    def test_empty_language(self):
        assert is_gendered_language("") is False

    def test_none_language(self):
        assert is_gendered_language(None) is False  # type: ignore


class TestNFOParsing:
    """Tests for parse_nfo_content."""

    def test_basic_nfo(self):
        nfo_xml = """<?xml version="1.0" encoding="utf-8"?>
<movie>
    <title>Inception</title>
    <year>2010</year>
    <director>Christopher Nolan</director>
    <plot>A thief who steals corporate secrets through dream-sharing.</plot>
    <genre>Science Fiction</genre>
    <genre>Action</genre>
    <studio>Warner Bros.</studio>
    <rating>8.8</rating>
    <mpaa>PG-13</mpaa>
    <tmdbid>27205</tmdbid>
    <actor>
        <name>Leonardo DiCaprio</name>
        <role>Cobb</role>
    </actor>
    <actor>
        <name>Joseph Gordon-Levitt</name>
        <role>Arthur</role>
    </actor>
</movie>"""
        result = parse_nfo_content(nfo_xml)
        assert result is not None
        assert result["title"] == "Inception"
        assert result["year"] == "2010"
        assert result["director"] == "Christopher Nolan"
        assert "Science Fiction" in result["genre"]
        assert result["mpaa"] == "PG-13"
        assert len(result["cast"]) == 2
        assert result["cast"][0]["name"] == "Leonardo DiCaprio"
        assert result["cast"][0]["role"] == "Cobb"
        assert result["tmdbid"] == "27205"

    def test_nfo_single_actor_dict(self):
        """When only one actor, xmltodict returns a dict instead of a list."""
        nfo_xml = """<?xml version="1.0"?>
<movie>
    <title>Solo</title>
    <actor>
        <name>One Actor</name>
        <role>Hero</role>
    </actor>
</movie>"""
        result = parse_nfo_content(nfo_xml)
        assert result is not None
        assert len(result["cast"]) == 1
        assert result["cast"][0]["name"] == "One Actor"

    def test_nfo_no_cast(self):
        nfo_xml = """<?xml version="1.0"?>
<movie>
    <title>No Cast Film</title>
</movie>"""
        result = parse_nfo_content(nfo_xml)
        assert result is not None
        assert result["cast"] == []

    def test_nfo_genre_is_string(self):
        """A single genre is a string, not a list."""
        nfo_xml = """<?xml version="1.0"?>
<movie>
    <title>Comedy</title>
    <genre>Comedy</genre>
</movie>"""
        result = parse_nfo_content(nfo_xml)
        assert result is not None
        assert "Comedy" in result["genre"]

    def test_nfo_invalid_xml(self):
        """Malformed XML should return None gracefully."""
        result = parse_nfo_content("this is not xml")
        assert result is None

    def test_nfo_empty(self):
        result = parse_nfo_content("")
        assert result is None

    def test_nfo_year_from_dirname_fallback(self):
        """When year is missing from NFO, external logic extracts from dirname — tested elsewhere."""
        pass  # This is handled in scan_single_directory, not in parse_nfo_content
