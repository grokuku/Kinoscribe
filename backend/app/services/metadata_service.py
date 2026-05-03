"""
Movie metadata service — enriches film data from online sources.

Primary: Cinemagoer (formerly IMDbPY) — no API key needed.
Scrapes IMDb directly for title, year, director, plot, cast, poster, rating.

Fallback: TMDB API — requires an API key (stored in settings).
"""

import re
from typing import Optional, Dict, Any, List

from app.core.logging import get_logger

logger = get_logger(__name__)


class MovieMetadata:
    """Container for enriched movie metadata."""

    def __init__(self):
        self.title: Optional[str] = None
        self.year: Optional[int] = None
        self.director: Optional[str] = None
        self.plot: Optional[str] = None
        self.poster_url: Optional[str] = None
        self.rating: Optional[float] = None
        self.genres: List[str] = []
        self.cast: List[Dict[str, str]] = []  # [{name, role, headshot}]
        self.imdb_id: Optional[str] = None
        self.source: str = "unknown"


async def enrich_from_cinemagoer(title: str, year: Optional[int] = None) -> Optional[MovieMetadata]:
    """
    Enrich film metadata using Cinemagoer (IMDb scraper).
    No API key needed — scrapes IMDb directly.

    Args:
        title: Film title to search for.
        year: Optional year to narrow search.

    Returns:
        MovieMetadata object or None if not found.
    """
    try:
        from imdb import Cinemagoer as IMDb
    except ImportError:
        logger.warning("cinemagoer not installed — install with: pip install cinemagoer")
        return None

    import asyncio

    def _search():
        ia = IMDb()
        results = ia.search_movie(title)
        if not results:
            return None

        # Find best match
        best = None
        for movie in results[:10]:
            # Filter by year if provided
            movie_year = movie.get('year')
            if year and movie_year:
                try:
                    if abs(int(movie_year) - int(year)) > 1:
                        continue
                except (ValueError, TypeError):
                    pass

            best = movie
            break  # Take first good match

        if not best:
            return None

        # Get full details
        ia.update(best)
        result = MovieMetadata()
        result.title = best.get('title', title)
        result.year = best.get('year')
        result.imdb_id = best.get('imdbID') or f"tt{best.movieID}" if hasattr(best, 'movieID') else None
        result.source = 'cinemagoer'

        # Director
        directors = best.get('directors', [])
        if directors:
            result.director = ', '.join(str(d) for d in directors[:3])

        # Plot
        plot_list = best.get('plot', [])
        if plot_list:
            result.plot = plot_list[0].split('::')[0].strip() if isinstance(plot_list[0], str) else None

        # Rating
        result.rating = best.get('rating')

        # Genres
        result.genres = best.get('genres', [])

        # Poster
        cover_url = best.get('full-size cover url') or best.get('cover url')
        result.poster_url = cover_url

        # Cast
        cast_list = best.get('cast', [])[:10]
        for person in cast_list:
            role = ''
            if hasattr(person, 'currentRole'):
                role = str(person.currentRole) if person.currentRole else ''
            result.cast.append({
                'name': str(person),
                'role': role,
            })

        return result

    try:
        result = await asyncio.to_thread(_search)
        if result:
            logger.info("Cinemagoer enrichment successful", title=title, year=year, imdb_id=result.imdb_id)
        return result
    except Exception as e:
        logger.warning("Cinemagoer enrichment failed", title=title, error=str(e))
        return None


async def enrich_from_tmdb(title: str, year: Optional[int] = None, api_key: Optional[str] = None) -> Optional[MovieMetadata]:
    """
    Enrich film metadata using TMDB API.
    Requires an API key stored in settings.

    Args:
        title: Film title to search for.
        year: Optional year to narrow search.
        api_key: TMDB API key.

    Returns:
        MovieMetadata object or None if not found.
    """
    if not api_key:
        return None

    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            # Search for movie
            url = "https://api.themoviedb.org/3/search/movie"
            params = {
                'api_key': api_key,
                'query': title,
                'language': 'fr-FR',
            }
            if year:
                params['primary_release_year'] = str(year)

            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

            results = data.get('results', [])
            if not results:
                return None

            movie = results[0]
            movie_id = movie['id']

            # Get full details
            detail_url = f"https://api.themoviedb.org/3/movie/{movie_id}"
            detail_params = {'api_key': api_key, 'language': 'fr-FR', 'append_to_response': 'credits'}

            async with session.get(detail_url, params=detail_params) as resp:
                if resp.status != 200:
                    return None
                detail = await resp.json()

            result = MovieMetadata()
            result.title = detail.get('title', title)
            result.year = int(detail.get('release_date', '0')[:4]) if detail.get('release_date') else None
            result.plot = detail.get('overview')
            result.rating = detail.get('vote_average')
            result.genres = [g['name'] for g in detail.get('genres', [])]
            result.source = 'tmdb'

            if detail.get('poster_path'):
                result.poster_url = f"https://image.tmdb.org/t/p/w500{detail['poster_path']}"

            # Director
            crew = detail.get('credits', {}).get('crew', [])
            directors = [c['name'] for c in crew if c.get('job') == 'Director']
            if directors:
                result.director = ', '.join(directors[:3])

            # Cast
            result.cast = [{'name': c['name'], 'role': c.get('character', '')} for c in detail.get('credits', {}).get('cast', [])[:10]]

            result.imdb_id = detail.get('imdb_id')

            logger.info("TMDB enrichment successful", title=title, year=year, tmdb_id=movie_id)
            return result

    except Exception as e:
        logger.warning("TMDB enrichment failed", title=title, error=str(e))
        return None


async def enrich_film_metadata(
    title: str,
    year: Optional[int] = None,
    prefer_source: str = 'cinemagoer',
    tmdb_api_key: Optional[str] = None,
) -> Optional[MovieMetadata]:
    """
    Enrich film metadata using the best available source.

    Priority: cinemagoer (no API key) → tmdb (requires API key)

    Args:
        title: Film title.
        year: Optional year.
        prefer_source: 'cinemagoer' or 'tmdb'.
        tmdb_api_key: TMDB API key (optional).

    Returns:
        MovieMetadata or None.
    """
    if prefer_source == 'tmdb' and tmdb_api_key:
        result = await enrich_from_tmdb(title, year, tmdb_api_key)
        if result:
            return result

    # Fallback to Cinemagoer (no API key needed)
    result = await enrich_from_cinemagoer(title, year)
    if result:
        return result

    # Try TMDB if Cinemagoer failed and we have a key
    if tmdb_api_key and prefer_source != 'tmdb':
        result = await enrich_from_tmdb(title, year, tmdb_api_key)
        if result:
            return result

    return None