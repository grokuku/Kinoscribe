# Design Document: Kinoscribe

> **Last updated:** 2026-04-19 — Phase 1 complete, frontend + Docker added
> **Current status:** Foundation solid, core engine + UI + Docker operational

## 1. Project Vision

**Kinoscribe** — from *Kino* (cinema) + *scribe* (writer) — is an intelligent, high-fidelity subtitle translation system that moves beyond word-for-word translation to provide true **localization**. The system leverages all available metadata and linguistic signals to resolve ambiguities (such as gender and tone) while respecting the temporal and spatial constraints of film subtitles.

## 2. Core Principles

*   **Quality over Speed:** The primary goal is semantic and cultural accuracy. We prioritize the use of Large Language Models (LLMs) that can understand nuance.
*   **Local-First & Privacy-Centric:** Defaulting to local LLM execution (via Ollama) to ensure user privacy and eliminate API costs.
*   **Extensibility by Design:** The architecture must allow seamless switching between providers (Ollama, OpenAI, Anthropic, etc.) via a standardized provider interface.
*   **Contextual Intelligence:** The system does not treat subtitles as isolated strings. It treats them as a continuous narrative, using metadata, multi-language cues, and SDH signals to build a "world model" before translating.

## 3. Technical Stack

*   **Backend:** Python with **FastAPI**. Chosen for its high performance, excellent support for asynchronous tasks, and robust ecosystem for AI/Data processing.
*   **Frontend:** **React** (Vite + TypeScript + Tailwind). Modern, fast, lightweight SPA for monitoring tasks and managing films.
*   **LLM Orchestration:** **Ollama** (Primary) with an abstraction layer for OpenAI-compatible APIs.
*   **Data Management:** **SQLite** (aiosqlite + SQLAlchemy async) for lightweight, local storage of film metadata, character profiles, glossary and translation task states.
*   **Integration:** API-driven approach to allow "Pull" (scanning Radarr/Sonarr libraries) or "Push" (webhooks) workflows.

## 4. Key Technical Strategies

### 4.1. Gender & Identity Resolution (The "Ambiguity Killer")
To solve the English → French gender problem, the system employs a multi-layered approach:
1.  **Metadata Extraction:** Parsing `.nfo` files and scraping IMDb/TMDB to build a `Character Profile` (Name → Gender → Role).
2.  **Cross-Lingual Signal Analysis:** If available, analyzing subtitles in "gendered" languages (Spanish, German, etc.) to extract gendered pronouns/adjectives.
3.  **SDH Analysis:** Scanning Subtitles for the Deaf and Hard of Hearing for speaker identifiers (e.g., `[JOHN]:` or `(FEMALE VOICE)`).
4.  **LLM Character Profiling:** Using the LLM with structured JSON output to identify characters and infer gender from dialogue patterns.
5.  **Prompt Injection:** Injecting these profiles directly into the LLM system prompt to guide grammatical choices.

### 4.2. Contextual Narrative Management
To maintain consistency in tone and relationship evolution:
*   **Narrative Summarization:** Using the LLM to generate a "Lore Summary" at the start of a task.
*   **Stateful Translation (Sliding Window):** Instead of independent blocks, the system passes a "contextual state" (the last N translated lines) to the LLM when translating the current batch.
*   **Glossary Auto-Build:** The LLM identifies proper nouns, slang and neologisms, producing a film-specific glossary that is injected into every translation prompt for consistency.
*   **Large Context Utilization:** Leveraging the expanding context windows of modern LLMs to include the entire film's "essence" in the translation prompt.

### 4.3. Constraint Enforcement
*   **CPS (Characters Per Second) Monitoring:** Automatically calculating reading speed and flagging/requesting "concise" versions from the LLM if a translation is too dense for its timing.
*   **Format Preservation:** Strict parsing and re-assembly of `.srt`, `.vtt`, and `.ass` files to ensure timing and styling remain intact.

## 5. Architecture Overview

```text
[ Frontend (React/Vite/TS) ]  ✅ Port 3000
       │
       ▼ (nginx proxy /api → backend)
[ FastAPI Backend ]            ✅ Port 8000
       │
       +── [ API Routes ]           ✅ /api/films, /api/tasks
       │      ├── films.py            (CRUD + characters)
       │      ├── tasks.py            (upload, start, progress, download, glossary)
       │      └── (settings.py)       TODO
       │
       +── [ Service Layer ]
       │      ├── [ Subtitle Service ] ✅ SRT/VTT/ASS parse+write, CPS, SDH
       │      ├── [ Metadata Service ] 🟡 NFO only, TMDB TODO
       │      ├── [ Context Service ]  ✅ Character profiling (LLM+SDH), Lore, Glossary
       │      ├── [ Translation Svc ]  ✅ Sliding window, context injection, JSON output
       │      └── [ LLM Provider ]     ✅ /api/chat (Ollama), multi-provider ready
       │
       +── [ Data Layer ]
       │      ├── SQLite (aiosqlite)  ✅ 4 tables: films, characters, glossary_entries, translation_tasks
       │      └── SQLAlchemy async    ✅
       │
       +── [ Core ]
              ├── [ Config ]  ✅ .env + pydantic-settings
              └── [ Logging ] ✅ structlog (JSON in prod, console in debug)
```

### Docker Deployment

```text
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Frontend (Nginx)│────▶│  Backend (FastAPI)│────▶│  Ollama server   │
│  :3000           │◀────│  :8000           │◀────│  (existing)      │
└──────────────────┘     └──────────────────┘     └──────────────────┘
     Volume: dist/           Volume: data/          On user's network
```

Ollama is NOT containerized — Kinoscribe connects to an existing Ollama
instance on the user's network via `OLLAMA_URL`.

## 6. Changelog

### v0.2.0 — 2026-04-19 — Renamed to Kinoscribe + Frontend + Docker

**New:**
- React frontend (Vite + TypeScript + Tailwind)
  - Films CRUD, file upload (drag & drop), task management, progress polling
  - Download translated subtitles
- Docker Compose (backend + frontend + ollama)
  - Backend: Python 3.11 slim + uv
  - Frontend: Node 20 build → Nginx alpine (SPA + API proxy)
  - Ollama: official image with volume persistence
- Setup script for first-run Ollama model pull
- Download endpoint (`GET /tasks/{id}/download`)
- Nginx config with API proxy + SPA fallback

### v0.1.0 — 2026-04-19 — Phase 1 Backend

**New:**
- SQLite persistence via SQLAlchemy async (4 tables)
- Full SRT/VTT/ASS parser + writer (pysubs2)
- SDH speaker extraction (`[JOHN]:`, `(MARY):`)
- CPS (Characters Per Second) monitoring
- Sliding-window contextual translation
- Character profiling via LLM + SDH (JSON structured output)
- Lore summarization (injected into every translation prompt)
- Glossary auto-building (proper nouns, slang → target language)
- Migration from Ollama `/api/generate` → `/api/chat` (proper system/user/assistant roles)
- Config via `.env` + pydantic-settings
- Structured logging via structlog
- Subtitle upload endpoint + automatic task creation
- Full translation workflow (parse → context → translate → write output SRT)

**Changed:**
- Removed in-memory dicts → SQLite
- Removed old `llm_provider_ollama.py` → unified `llm_provider.py`
- Translation prompts now use JSON structured output
- Schemas split: DB models (`database.py`) vs API schemas (`schemas.py`)

**Remaining (Phase 2+):**
- TMDB API integration for cast/metadata
- Cross-lingual gender analysis (ES/DE subtitles as signal)
- Multi-provider (OpenAI, Anthropic)
- Two-pass translation (Draft → Refine)
- WebSocket real-time progress
- Radarr/Sonarr integration
- Tests