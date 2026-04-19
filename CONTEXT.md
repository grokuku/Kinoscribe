# Kinoscribe — Contexte Technique

> Ce fichier est la référence technique pour reprendre le développement.
> Plus détaillé que DESIGN_DOC.md, il documente l'état réel du code,
> les choix d'implémentation, les dettes et les prochaines étapes.

---

## 1. État actuel — v0.2.0

**Phase 1 complète** : fondations solides, moteur fonctionnel, UI + Docker opérationnels.
Le projet n'a **jamais été testé de bout en bout** avec un vrai Ollama — uniquement validé par
imports Python et build Vite. La première vraie validation aura lieu sur le serveur cible.

### Fichiers — ~3 070 lignes de code

```
backend/  (Python / FastAPI)
├── app/
│   ├── api/
│   │   ├── films.py          88l   CRUD films + personnages
│   │   ├── settings.py       48l   Lecture/écriture/test-ollama
│   │   └── tasks.py          284l  Upload, start, progress, download, glossaire + workflow background
│   ├── core/
│   │   ├── config.py         41l   Pydantic Settings (env vars → defaults DB au premier boot)
│   │   ├── database.py       37l   SQLAlchemy async engine + session factory + init_db()
│   │   └── logging.py        42l   structlog (JSON prod, console debug)
│   ├── models/
│   │   ├── database.py       161l  5 tables SQLAlchemy : films, characters, glossary_entries, translation_tasks, settings
│   │   └── schemas.py        120l  Pydantic v2 (API contract, séparé des modèles DB)
│   ├── services/
│   │   ├── llm_provider.py           172l  Abstraction LLMProvider + OllamaProvider (/api/chat, rôles natifs, streaming, format_json)
│   │   ├── subtitle_service.py       225l  Parse SRT/VTT/ASS (pysubs2), write SRT, CPS, SDH extraction/clean
│   │   ├── context_service.py        235l  Character profiling (LLM+SDH), lore summary, glossaire auto (JSON structuré)
│   │   ├── translation_service.py   224l  Sliding window, injection contexte, JSON output, fallback lignes originales
│   │   ├── settings_service.py      190l  Seed defaults, CRUD, test connectivité Ollama, get typés (int/float/bool)
│   │   └── metadata_service.py       53l  Parse NFO (xmltodict), TMDB TODO
│   └── main.py               ~45l   FastAPI app, lifespan (init DB + seed settings), routes montées

frontend/  (TypeScript / React / Vite / Tailwind)
├── src/
│   ├── api/client.ts         65l   fetch proxy /api → backend
│   ├── hooks/useApi.ts       83l   useFilms, useFilm, useTasks, useTaskPolling
│   ├── types/
│   │   ├── index.ts          66l   Film, Task, Character, GlossaryEntry, TaskStatus…
│   │   └── settings.ts        7l   Setting (key/value/input_type/category)
│   ├── components/
│   │   ├── Layout.tsx         55l   Navbar (Films, Tâches, Paramètres) + footer
│   │   ├── FilmCard.tsx       45l   Card film avec langues, personnages
│   │   ├── SubtitleUploader  65l   Drag & drop + select langue source
│   │   ├── TaskStatus.tsx     48l   Badge status + barre progression animée
│   │   └── CreateFilmModal  139l   Modal création film (formulaire complet)
│   ├── pages/
│   │   ├── FilmsPage.tsx      80l   Liste films + bouton créer
│   │   ├── FilmDetailPage   206l   Détail, personnages, upload, tâches, download
│   │   ├── TasksPage.tsx     108l   Tâches groupées (en cours / en attente / terminées)
│   │   └── SettingsPage     182l   Paramètres groupés par catégorie + test Ollama
│   ├── App.tsx                ~20l   Routes React Router
│   └── main.tsx                8l   Point d'entrée React

docker-compose.yml                   Backend + Frontend (Ollama externe)
frontend/nginx.conf                  SPA fallback + proxy /api → backend:8000
frontend/Dockerfile                  Node 20 build → Nginx alpine
backend/Dockerfile                   Python 3.11 slim + uv
setup.sh                             Test connectivité Ollama + vérif modèle
```

---

## 2. Base de données — 5 tables

```sql
-- films : id, title, year, director, summary, source_language, target_language, raw_metadata(JSON), created_at, updated_at
-- characters : id, film_id(FK), name, gender, description, meta(JSON)
-- glossary_entries : id, film_id(FK), source_term, target_term, notes
-- translation_tasks : id, film_id(FK), source_filename, source_format, source_path, source_language,
--                    target_filename, target_path, status, progress_pct, error_message, lore_summary, created_at, updated_at
-- settings : key(PK), value, description, input_type, options, category
```

**Seed** : au premier boot, `settings_service.seed_if_empty()` peuple la table `settings`
depuis les env vars / defaults. Les env vars ne servent plus que de fallback initial.
Au runtime, TOUT est lu depuis la DB.

---

## 3. Flux de traduction (workflow complet)

```
1. POST /api/films/                                   → Créer film (title, languages)
2. POST /api/tasks/{film_id}/upload (multipart)       → Uploader .srt → crée tâche (status=pending)
3. POST /api/tasks/{task_id}/start                    → Lance en background :
   │
   ├─ Phase 1 : Parse SRT (pysubs2) → ParsedSubtitle.lines[]
   ├─ Phase 2 : Analyse contexte
   │   ├─ SDH extraction → speakers (ex: JOHN, MARY)
   │   ├─ LLM character profiling → JSON structuré (nom, genre, description)
   │   ├─ LLM lore summary → résumé narratif
   │   └─ LLM glossaire auto → {source, target, notes}[]
   ├─ Phase 3 : Traduction par batch
   │   ├─ Sliding window : N lignes précédentes traduites injectées
   │   ├─ Contexte injecté dans chaque prompt : lore + characters + glossaire + lignes précédentes
   │   ├─ Format JSON structuré en sortie (pas de fragile "Index|Text")
   │   ├─ Fallback : si un batch échoue, on garde les lignes originales
   │   └─ Progress mis à jour (progress_pct)
   └─ Phase 4 : Write output SRT → data/output/{film_id}/{name}.fr.srt
   → status=completed, target_path enregistré
4. GET /api/tasks/{task_id}/download                  → Télécharger le .srt traduit
```

**Important** : le workflow tourne dans FastAPI BackgroundTasks. Pas de queue externe (pas de Celery/Redis).
Pour une utilisation mono-utilisateur c'est suffisant. Si multi-utilisateur → il faudra une vraie task queue.

---

## 4. Services — détails d'implémentation

### LLM Provider (`llm_provider.py`)
- **Abstraction** : `LLMProvider` ABC avec `chat()`, `chat_stream()`, `generate_text()`
- **OllamaProvider** : utilise `/api/chat` (pas `/api/generate`) → rôles system/user/assistant natifs
- `format_json=True` → passe `{"format": "json"}` à Ollama pour forcer du JSON valide
- `generate_text()` = legacy convenience (1-2 messages), utilisé nulle part dans le workflow principal
- **Streaming** : `chat_stream()` fonctionne token par token
- **À faire** : `OpenAIProvider`, `AnthropicProvider` (même interface)

### Subtitle Service (`subtitle_service.py`)
- **pysubs2** pour le parsing (SRT, VTT, ASS, SSA)
- `SubtitleLine` dataclass : index, start_ms, end_ms, text, raw_text, style + propriétés cps, duration
- `extract_sdh_speakers()` : regex pour `[JOHN]:`, `(MARY):`, `FEMALE VOICE:`
- `clean_sdh_tags()` : supprime les tagues SDH du texte pour la traduction
- `check_cps_issues()` : flag les lignes > CPS_LIMIT
- `write_srt()` : reconstruit un .srt depuis les SubtitleLine (via pysubs2)
- **À faire** : write VTT/ASS, clean SDH intégré dans le workflow (actuellement le flag auto_clean_sdh existe dans les settings mais n'est pas utilisé dans le pipeline)

### Context Service (`context_service.py`)
- `_build_dialogue_sample()` : prend les N premières lignes non vides
- `_llm_character_analysis()` : prompt JSON → parse les personnages + genre
- `_parse_json_response()` : gère les markdown fences ```json...```
- `build_glossary()` : identifie noms propres, argot, néologismes → traduction cible
- **À faire** : cross-lingual gender analysis (analyser sous-titres ES/DE comme signal de genre)

### Translation Service (`translation_service.py`)
- `translate_film_subtitles()` : boucle principale, itère par batch de `batch_size` lignes
- Sliding window : `context_window = translated[-window_size:]`
- Prompt injecté : system (règles strictes) + user (lore + characters + glossaire + lignes précédentes + lignes à traduire)
- **Fallback** : si un batch échoue → conserve les lignes originales (pas de crash)
- **À faire** : deux passes (Draft avec modèle léger → Refine avec modèle lourd), retry sur échec LLM, concision automatique si CPS trop élevé

### Settings Service (`settings_service.py`)
- 11 paramètres en 4 catégories (llm, translation, subtitles, external)
- `seed_if_empty()` : au boot, peuple depuis env vars/defaults (idempotent)
- `test_ollama_connection()` : GET /api/tags → liste modèles disponibles
- `get_async()` : helper sans session explicite (pour usage hors request scope)
- **À faire** : ajout settings TMDB, validation côté backend (bornes, types)

---

## 5. API Routes — mapping complet

```
GET    /                           → Status message
GET    /health                     → Health check
GET    /docs                      → Swagger UI

GET    /api/films/                 → Liste films
POST   /api/films/                → Créer film
GET    /api/films/{id}            → Détail film
GET    /api/films/{id}/characters  → Personnages du film
DELETE /api/films/{id}            → Supprimer film + cascade

POST   /api/tasks/{film_id}/upload     → Upload .srt → crée tâche (multipart)
POST   /api/tasks/{task_id}/start       → Lance traduction (background)
GET    /api/tasks/                       → Liste toutes les tâches
GET    /api/tasks/{id}                   → Détail tâche
GET    /api/tasks/{id}/progress          → Progress léger (polling)
GET    /api/tasks/{id}/glossary          → Glossaire du film
GET    /api/tasks/{id}/download          → Télécharger SRT traduit

GET    /api/settings/              → Liste tous les settings
PUT    /api/settings/              → Mise à jour groupée
POST   /api/settings/test-ollama   → Test connectivité Ollama
```

---

## 6. Frontend — structure

- **Router** : `/` (Films), `/films/:id` (FilmDetail), `/tasks` (Tasks), `/settings` (Settings)
- **State** : pas de store global (pas de Redux/Zustand). Hooks locaux + polling par tâche
- **API client** : `fetch()` natif, proxy Vite (`/api` → `backend:8000`) en dev, Nginx en prod
- **Polling** : `useTaskPolling(taskId, 2000ms)` → s'arrête auto sur completed/failed
- **I18n** : interface en français, prompts LLM en anglais (standard)

---

## 7. Docker

```bash
OLLAMA_URL=http://192.168.x.x:11434 docker compose up -d
```

- **backend** : port 8000, volume `backend-data` → `/app/data` (DB + uploads + outputs)
- **frontend** : port 3000 → Nginx:80, proxy `/api/` → `backend:8000`
- **Ollama** : EXTERNE — configuré via `OLLAMA_URL` dans `.env` ou l'UI
- `extra_hosts: host.docker.internal:host-gateway` — permet d'atteindre Ollama sur le réseau hôte
- `setup.sh` : vérifie la connectivité Ollama et la disponibilité du modèle

---

## 8. Dettes techniques & bugs connus

| # | Problème | Gravité | Localisation |
|---|---|---|---|
| D1 | **`auto_clean_sdh` setting existant mais pas utilisé dans le pipeline**. Le texte est envoyé avec les tags SDH au LLM. | Moyen | `translation_service.py` |
| D2 | **Pas de retry LLM**. Si un appel Ollama échoue, le batch est gardé en anglais (fallback silencieux). | Moyen | `translation_service.py` |
| D3 | **BackgroundTasks sans queue**. FastAPI BackgroundTasks n'est pas persistant — si le process redémarre, les tâches en cours sont perdues sans mise à jour du status. | Élevé | `tasks.py` |
| D4 | **Pas de tests**. Zéro test unitaire ou d'intégration. | Élevé | Partout |
| D5 | **`pysubs2` write SRT** convertit `\n` → `\\N` → au re-parse les retours à la ligne sont `\\N` au lieu de vrais `\n`. | Mineur | `subtitle_service.py` |
| D6 | **Services instanciés manuellement** dans `_get_services()` / `_build_services_from_settings()`. Pas de DI, instanciés à chaque appel de workflow. | Mineur | `tasks.py` |
| D7 | **Pas de validation backend des settings**. L'UI permet n'importe quelle valeur (CPS=-5, URL vide, etc.). | Mineur | `settings_service.py` |
| D8 | **Pas de gestion des uploads orphelins**. Si un upload est fait puis le film supprimé, le fichier reste sur disque. | Mineur | `tasks.py` |

---

## 9. Prochaines étapes — priorité

### Phase 2 — Le cœur du système (2-3 semaines)

| # | Tâche | Priorité | Notes |
|---|---|---|---|
| 2.1 | **Brancher `auto_clean_sdh` dans le pipeline** | 🔴 | D1 — envoyer texte nettoyé au LLM, garder raw pour le profilage |
| 2.2 | **Retry LLM** (3 tentatives, backoff) | 🔴 | D2 — ne pas silently garder les lignes originales |
| 2.3 | **Deux passes Draft → Refine** | 🟡 | Draft avec modèle léger/rapide, Refine avec contexte complet |
| 2.4 | **CPS auto-correction** | 🟡 | Si traduction trop dense, demander au LLM une version concise |
| 2.5 | **TMDB API** | 🟡 | Enrichir les profils personnages avec le cast TMDB |
| 2.6 | **Cross-lingual gender analysis** | 🟢 | Utiliser des sous-titres ES/DE comme signal de genre |

### Phase 3 — Robustesse (1-2 semaines)

| # | Tâche | Priorité | Notes |
|---|---|---|---|
| 3.1 | **Task queue** (remplacer BackgroundTasks) | 🔴 | D3 — Celery + Redis ou arq + Redis |
| 3.2 | **Tests unitaires** | 🔴 | D4 — parser, SDH, LLM response parsing, settings CRUD |
| 3.3 | **Validation settings backend** | 🟡 | D7 — bornes, types, URL validation |
| 3.4 | **Multi-provider** | 🟡 | `OpenAIProvider`, `AnthropicProvider` |
| 3.5 | **WebSocket progression** | 🟡 | Remplacer polling par push temps réel |

### Phase 4 — Intégrations (2-3 semaines)

| # | Tâche | Priorité |
|---|---|---|
| 4.1 | **Radarr/Sonarr scan** | 🟢 |
| 4.2 | **Upload de sous-titres existants comme hints** | 🟢 |
| 4.3 | **Éditeur de sous-titres in-browser** | 🟢 |
| 4.4 | **Détection auto langue source** | 🟢 |

---

## 10. Conventions & choix techniques

- **Python** : async/await partout, type hints (Mapped[]), Python 3.11+
- **DB** : SQLAlchemy 2.0 style (mapped_column, Mapped), async (aiosqlite)
- **Schemas** : 2 couches — `models/database.py` (ORM) vs `models/schemas.py` (API). Pas de mix.
- **Logging** : structlog — JSON en prod, ConsoleRenderer en debug. Pas de `print()`.
- **Config** : env vars → seed DB au premier boot → UI modifie la DB → services lisent la DB. Les env vars ne sont plus lus au runtime.
- **Frontend** : pas de state global. Hooks locaux. fetch natif (pas d'axios). Pas de SSR.
- **Nommage** : fichiers kebab-case, composants PascalCase, fonctions snake_case
- **Langue** : UI en français, code/commentaires en anglais, prompts LLM en anglais

---

## 11. Déploiement cible

L'utilisateur final fait :
```bash
docker compose up -d          # 2 conteneurs : backend + frontend
# Ouvrir http://serveur:3000 → Paramètres → Configurer Ollama URL → OK
```

Volume unique à mapper : `backend-data:/app/data` (contient la DB SQLite + uploads + outputs).
Tout le reste est configuré depuis l'UI.