"""
Integration tests for Films API endpoints.
"""

import pytest
import pytest_asyncio


class TestFilmsCRUD:
    """Test create, read, update, delete lifecycle for films."""

    async def test_create_film(self, async_client):
        resp = await async_client.post("/api/films/", json={
            "title": "Inception",
            "year": 2010,
            "director": "Christopher Nolan",
            "source_language": "en",
            "target_language": "fr",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Inception"
        assert data["year"] == 2010
        assert data["source_language"] == "en"
        assert data["target_language"] == "fr"
        assert "id" in data
        assert "characters" in data  # empty list by default

    async def test_create_film_minimal(self, async_client):
        """Only title is required, rest get defaults."""
        resp = await async_client.post("/api/films/", json={
            "title": "Minimal Film",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Minimal Film"
        assert data["source_language"] == "en"
        assert data["target_language"] == "fr"

    async def test_list_films(self, async_client, sample_film):
        resp = await async_client.get("/api/films/")
        assert resp.status_code == 200
        films = resp.json()
        assert isinstance(films, list)
        assert len(films) >= 1
        titles = [f["title"] for f in films]
        assert "Inception" in titles

    async def test_get_film(self, async_client, sample_film):
        resp = await async_client.get(f"/api/films/{sample_film.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == sample_film.id
        assert data["title"] == "Inception"
        assert data["year"] == 2010

    async def test_get_film_not_found(self, async_client):
        resp = await async_client.get("/api/films/nonexistent-id")
        assert resp.status_code == 404

    async def test_delete_film(self, async_client, sample_film):
        resp = await async_client.delete(f"/api/films/{sample_film.id}")
        assert resp.status_code == 204

        # Verify it's gone
        resp = await async_client.get(f"/api/films/{sample_film.id}")
        assert resp.status_code == 404

    async def test_delete_film_not_found(self, async_client):
        resp = await async_client.delete("/api/films/nonexistent")
        assert resp.status_code == 404

    async def test_get_film_characters(self, async_client, sample_film):
        resp = await async_client.get(f"/api/films/{sample_film.id}/characters")
        assert resp.status_code == 200
        chars = resp.json()
        assert isinstance(chars, list)
        # Initially no characters
        assert chars == []

    async def test_get_film_glossary(self, async_client, sample_film):
        resp = await async_client.get(f"/api/films/{sample_film.id}/glossary")
        assert resp.status_code == 200
        glossary = resp.json()
        assert isinstance(glossary, list)
        assert glossary == []

    async def test_get_film_lore(self, async_client, sample_film):
        resp = await async_client.get(f"/api/films/{sample_film.id}/lore")
        assert resp.status_code == 200
        data = resp.json()
        assert data["lore_summary"] is None
        assert data["task_id"] is None

    async def test_get_film_poster_no_poster(self, async_client, sample_film):
        """When film has no poster_path, return 404."""
        resp = await async_client.get(f"/api/films/{sample_film.id}/poster")
        assert resp.status_code == 404

    async def test_get_film_subtitles_empty(self, async_client, sample_film):
        resp = await async_client.get(f"/api/films/{sample_film.id}/subtitles")
        assert resp.status_code == 200
        subtitles = resp.json()
        assert isinstance(subtitles, list)
        assert subtitles == []  # No uploaded or scanner subtitles


class TestTasksAPI:
    """Tests for the tasks endpoints."""

    async def test_list_tasks_empty(self, async_client):
        resp = await async_client.get("/api/tasks/")
        assert resp.status_code == 200
        tasks = resp.json()
        assert tasks == []

    async def test_get_task_not_found(self, async_client):
        resp = await async_client.get("/api/tasks/nonexistent")
        assert resp.status_code == 404

    async def test_upload_subtitle_film_not_found(self, async_client):
        """Uploading to a non-existent film returns 404."""
        resp = await async_client.post(
            "/api/tasks/nonexistent/upload",
            files={"file": ("test.srt", b"1\n00:00:01,000 --> 00:00:02,000\nHello\n")},
        )
        assert resp.status_code == 404

    async def test_translate_existing_film_not_found(self, async_client):
        resp = await async_client.post(
            "/api/tasks/nonexistent/translate-existing",
            json={"subtitle_path": "/some/file.srt"},
        )
        assert resp.status_code == 404
