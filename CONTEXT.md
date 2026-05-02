# Kinoscribe — Contexte Technique

> Ce fichier est la référence technique pour reprendre le développement.
> Plus détaillé que DESIGN_DOC.md, il documente l'état réel du code,
> les choix d'implémentation, les dettes et les prochaines étapes.

---

## 1. État actuel — v0.4.0

**Phase 5 en cours** : libraries + scan Jellyfin, sous-titres existants, analyse contextuelle manuelle,
Whisper transcription/sync, scan automatique, suppression cascade.

### Fichiers — ~6 500 lignes de code

```
backend/  (Python / FastAPI) — ~3 600 lignes
├── app/
│   ├── api/
│   │   ├── films.py          ~420l  CRUD + characters + glossary + lore + poster + subtitles + analyze + whisper + sync
│   │   ├── libraries.py      ~175l  CRUD libraries/sources + scan + progress + SSH test
│   │   ├── settings.py        ~58l  Lecture/écriture/test-ollama + modèles ollama
│   │   └── tasks.py          ~380l  Upload, translate-existing, start, progress, download + workflow background (SDH clean + refine pass)
│   ├── core/
│   │   ├── config.py          41l  Pydantic Settings (env vars → defaults DB au premier boot)
│   │   ├── database.py        ~70l  SQLAlchemy async + session factory + init_db() + auto-migration colonnes films
│   │   └── logging.py         42l  structlog (JSON prod, console debug)
│   ├── models/
│   │   ├── database.py       ~210l  7 tables : films, characters, glossary_entries, translation_tasks, settings, libraries, library_sources
│   │   └── schemas.py        ~155l  Pydantic v2 (API contract — séparé des modèles DB)
│   ├── services/
│   │   ├── scanner_service.py ~770l  FilesystemProvider ABC + Local + SSH, scan NFO/subs/posters, progress, poster cache SSH
│   │   ├── llm_provider.py          215l  Abstraction LLMProvider + OllamaProvider (/api/chat, think, streaming, format_json)
│   │   ├── subtitle_service.py     245l  Parse SRT/VTT/ASS (pysubs2), write SRT, CPS, SDH extraction/clean + clean_sdh_from_parsed()
│   │   ├── context_service.py      235l  Character profiling (LLM+SDH, think=True/False), lore summary, glossaire auto
│   │   ├── translation_service.py  340l  Sliding window, retry LLM (3 tentatives+backoff), injection contexte, JSON output, refine pass (draft → refine)
│   │   ├── whisper_service.py       270l  Transcription (faster-whisper) + sync subtitles, audio extraction (ffmpeg)
│   │   ├── settings_service.py     ~215l  Seed defaults (15 paramètres), CRUD, test Ollama, fetch modèles
│   │   └── metadata_service.py      53l  Parse NFO (xmltodict), TMDB TODO
│   └── main.py               ~100l  FastAPI app, lifespan + auto-scan scheduler (v0.4.0)
│   └── tests/                        ✅ Nouveau — 52 tests (pytest + pytest-asyncio + httpx)
│       ├── conftest.py                Fixtures : DB isolée par test, client HTTP, données sample
│       ├── test_subtitle_service.py   Parsing SRT/VTT, writing, SDH extraction/clean, CPS
│       ├── test_scanner.py            Filename parsing, NFO parsing, gendered language detection
│       └── test_api_films.py          CRUD films endpoints, tasks endpoints, 404 handling
│       └── pytest.ini                 Configuration (asyncio_mode=auto)

frontend/  (TypeScript / React / Vite / Tailwind) — ~2 900 lignes
├── src/
│   ├── api/client.ts         ~100l   fetch proxy /api → backend + posters + subtitles + analyze + whisper
│   ├── hooks/useApi.ts         83l   useFilms, useFilm, useTasks, useTaskPolling
│   ├── types/
│   │   ├── index.ts           ~80l   Film, Task, Character, GlossaryEntry, ExistingSubtitle, TaskStatus…
│   │   └── settings.ts         7l   Setting (key/value/input_type/category)
│   ├── components/
│   │   ├── Layout.tsx         92l   Sidebar nav full-width + mobile top bar + Bibliothèques
│   │   ├── FilmCard.tsx       ~90l   Card film avec poster 2/3 ratio + lazy load
│   │   ├── SubtitleUploader   ~75l   Drag & drop (langue auto-détectée, plus de dropdown)
│   │   ├── TaskStatus.tsx     52l   Badge status + barre progression gradient
│   │   └── CreateFilmModal   152l   Modal création film (formulaire complet)
│   ├── pages/
│   │   ├── FilmsPage.tsx     120l   Grille responsive 1-5 colonnes + recherche
│   │   ├── FilmDetailPage   ~460l   2 onglets : Fiche film + Traduction (subs list + upload + tools)
│   │   ├── LibrariesPage    ~500l   CRUD libraries + sources (local/SSH) + scan progress + SSH test
│   │   ├── TasksPage.tsx     164l   Tâches par statut + stat cards
│   │   └── SettingsPage     ~382l   Paramètres 2 colonnes + dropdowns Ollama + think toggles
│   ├── App.tsx                20l   Routes React Router (/libraries ajouté)
│   ├── main.tsx                9l   Point d'entrée React
│   └── index.css            ~160l   Design system + scan-progress-bar

docker-compose.yml                   Backend + Frontend (Ollama externe)
frontend/nginx.conf                  SPA fallback + proxy /api + gros buffers pour posters
backend/Dockerfile                   Python 3.11 slim + uv
backend/requirements.txt             asyncssh, faster-whisper (commenté), pysubs2, xmltodict…
CLOUD_MODELS.md                     Liste 36 modèles cloud Ollama + recommandations
DESIGN_PHASE5.md                    Design libraries + context enrichment
```

---

## 2. Base de données — 7 tables

```sql
-- films : id, title, year, director, summary, source_language, target_language,
--          raw_metadata(JSON), library_id(FK libraries.id ON DELETE SET NULL),
--          path, video_path, poster_path, has_existing_subs,
--          created_at, updated_at
-- characters : id, film_id(FK), name, gender, description, meta(JSON)
-- glossary_entries : id, film_id(FK), source_term, target_term, notes
-- translation_tasks : id, film_id(FK), source_filename, source_format, source_path, source_language,
--                    target_filename, target_path, status, progress_pct, error_message, lore_summary, created_at, updated_at
-- settings : key(PK), value, description, input_type, options, category
-- libraries : id, name, description, created_at, updated_at
-- library_sources : id, library_id(FK), source_type(local|ssh), path,
--                   ssh_host, ssh_port, ssh_username, ssh_auth_type, ssh_private_key_path,
--                   ssh_password, ssh_remote_path, enabled, scan_depth, last_scan_at,
--                   scan_status(idle|scanning|error), scan_error, created_at, updated_at
```

**Migration auto** : `init_db()` ajoute les colonnes `library_id`, `path`, `video_path`, `poster_path`,
`has_existing_subs` à la table `films` si elles n'existent pas. Les tables `libraries` et `library_sources`
sont créées par `create_all()`.

**Seed** : 15 paramètres en 4 catégories :

| Catégorie | Paramètres |
|---|---|
| LLM | `ollama_base_url`, `ollama_model`, `ollama_refine_model`, `llm_temperature`, `draft_think`, `refine_think` |
| Translation | `default_target_language`, `auto_scan_enabled`, `auto_scan_interval_hours`, `sliding_window_size`, `batch_size` |
| Subtitles | `cps_limit`, `auto_clean_sdh` |
| External | `tmdb_api_key` |

**Note** : `default_source_language` supprimé de l'UI (masqué via `hiddenKeys`). La langue source est auto-détectée.

---

## 3. Architecture — Vue d'ensemble

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                              │
│  /            FilmsPage      → grilles films avec poster             │
│  /films/:id   FilmDetailPage → Fiche film + Traduction              │
│  /libraries   LibrariesPage  → CRUD bibliothèques + sources + scan   │
│  /tasks       TasksPage      → Tâches                               │
│  /settings    SettingsPage   → Paramètres + modèles Ollama          │
└──────────────────────────────────────────────────────────────────────┘
                              │  /api/*
┌──────────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                                  │
│  /api/films/       CRUD + subtitles + poster + analyze + whisper      │
│  /api/libraries/   CRUD + sources + scan + progress + SSH test      │
│  /api/tasks/       Upload + translate-existing + start + download    │
│  /api/settings/    CRUD + Ollama test + fetch modèles                │
└──────────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                       │
   ┌────▼─────┐    ┌────────▼────────┐    ┌─────────▼────────┐
   │ SQLite   │    │  Ollama Cloud   │    │  Filesystem       │
   │ (7 tables)│    │  (API /api/chat)│    │  (local + SSH)    │
   └──────────┘    └─────────────────┘    └──────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Whisper (faster-  │
                    │  whisper + ffmpeg) │
                    └───────────────────┘
```

---

## 4. Flux principaux

### 4a. Scan de bibliothèque

```
1. POST /api/libraries/{id}/scan
2. BackgroundTasks → scanner_service.scan_library(library_id)
3. ScanProgress en mémoire (poll GET /api/libraries/{id}/scan-progress)
   ├─ Phase 1 : Lister sous-dossiers → progress.total_dirs
   ├─ Phase 2 : Pour chaque dossier :
   │   ├─ Lister fichiers (vidéo, NFO, images, sous-titres)
   │   ├─ Parser NFO (_sanitize_nfo_value pour JSON-safe)
   │   ├─ Commit film en DB (session individuelle → visible en temps réel)
   │   ├─ Si SSH : cache poster dans data/posters/{film_id}.ext
   │   └─ Mettre à jour progress (scanned_dirs, current_dir, films_found)
4. status=completed
```

### 4b. Traduction depuis un sous-titre existant

```
1. GET /api/films/{id}/subtitles → liste tous les .srt trouvés
   ├─ Scanner : fichiers du dossier film (local ou cached SSH)
   └─ Uploaded : fichiers dans data/uploads/{film_id}/
2. POST /api/tasks/{film_id}/translate-existing
   ├─ Body: { subtitle_path, source_language? }
   ├─ Auto-détect langue depuis le nom de fichier
   └─ Copie dans data/uploads/ + crée Task
3. POST /api/tasks/{task_id}/start → traduction classique
```

### 4c. Analyse contextuelle manuelle

```
POST /api/films/{id}/analyze → background task
  ├─ Utilise le 1er sous-titre disponible
  ├─ LLM character profiling (think=False)
  ├─ LLM lore summary (think=True)
  └─ LLM glossaire auto (think=False)
```

### 4d. Whisper transcription

```
POST /api/films/{id}/transcribe → background task
  ├─ ffmpeg -i video → audio.wav (16kHz mono)
  ├─ faster-whisper transcribe (model_size, VAD filter, int8 CPU)
  └─ Save → data/uploads/{film_id}/whisper_{lang}.srt
```

### 4e. Whisper sync

```
POST /api/films/{id}/sync-subtitles → background task
  ├─ ffmpeg extract audio
  ├─ faster-whisper transcribe (pour les timestamps)
  ├─ Parse SRT original → entries[]
  ├─ Nearest-neighbor align (start timestamp matching)
  └─ Save → data/uploads/{film_id}/{name}.synced.srt
```

### 4f. Scan automatique

```
_lifespan → asyncio.create_task(_auto_scan_scheduler)
  ├─ Lit auto_scan_enabled + auto_scan_interval_hours
  ├─ Si enabled : scan toutes les libraries (skip si déjà scanning)
  └─ Sleep interval_hours*3600 (min 300s)
```

---

## 5. Services — détails

### Scanner Service (`scanner_service.py`) — ~770 lignes

**FilesystemProvider (ABC)** : 6 méthodes (`listdir`, `is_dir`, `is_file`, `read_text`, `read_bytes`, `exists`)

| Provider | Implémentation |
|---|---|
| `LocalFilesystem` | `os.listdir()`, `open()`, `os.path.exists()` |
| `SSHFilesystem` | `asyncssh.connect()` + `/api/chat` SFTP, read_text (bytes→str), read_bytes |
| Futur : `SMBFilesystem`, `NFSFilesystem` | Ajouter 6 méthodes + `source_type` |

**NFO parsing** :
- `_sanitize_nfo_value()` — récursif, convertit tout en primitives JSON
- `genre`, `studio`, `director` — normalisés si liste → string join virgules
- Tous les champs `str()` explicites, `or []` / `or ''` pour éliminer None/OrderedDict

**Poster cache** :
- `cache_poster_locally(fs, remote_path, film_id)` — download via SFTP → `data/posters/{film_id}.{ext}`
- Utilisé pendant le scan SSH pour servir les posters via `GET /films/{id}/poster`

**ScanProgress** (in-memory) :
- `to_dict()` → retourné par `GET /libraries/{id}/scan-progress`
- Champs : status, total_dirs, scanned_dirs, current_dir, films_found/created/updated, errors[], started_at, completed_at

### Whisper Service (`whisper_service.py`) — ~270 lignes

- `transcribe_video()` : ffmpeg extract audio → faster-whisper → SRT
- `sync_with_whisper()` : ffmpeg + whisper + nearest-neighbor align
- `check_ffmpeg_available()` : test si ffmpeg est installé
- Modèles : tiny/base/small/medium/large (medium recommandé CPU)
- VAD filter activé, beam_size=5, int8 quantization

### LLM Provider (`llm_provider.py`)
- `think` param : True/False/None → `{"think": bool}` dans l'API Ollama
- Cloud models via suffixe `-cloud`
- Streaming filtre les thinking tokens

### Settings Service (`settings_service.py`)
- 15 paramètres en 4 catégories
- `default_source_language` supprimé de l'UI (existe encore en DB, caché via `hiddenKeys`)
- Nouveaux : `auto_scan_enabled`, `auto_scan_interval_hours`

---

## 6. API Routes — mapping complet

```
# Films
GET    /api/films/                           → Liste films
POST   /api/films/                             → Créer film
GET    /api/films/{id}                         → Détail film
GET    /api/films/{id}/characters               → Personnages
GET    /api/films/{id}/glossary                 → Glossaire
GET    /api/films/{id}/lore                     → Lore summary
GET    /api/films/{id}/poster                   → Servir poster (Cache-Control 24h)
GET    /api/films/{id}/subtitles                → Liste sous-titres existants (scanner + uploaded)
POST   /api/films/{id}/analyze                  → Analyse contextuelle (background)
POST   /api/films/{id}/transcribe               → Whisper transcription (background)
POST   /api/films/{id}/sync-subtitles           → Whisper sync (background)
DELETE /api/films/{id}                          → Supprimer film

# Libraries
GET    /api/libraries/                          → Liste bibliothèques
POST   /api/libraries/                          → Créer bibliothèque
GET    /api/libraries/{id}                      → Détail bibliothèque
PUT    /api/libraries/{id}                      → Modifier bibliothèque
DELETE /api/libraries/{id}                      → Supprimer bibliothèque (+ films par défaut)
POST   /api/libraries/{id}/sources              → Ajouter source
PUT    /api/libraries/{id}/sources/{sid}         → Modifier source
DELETE /api/libraries/{id}/sources/{sid}         → Supprimer source (+ films par défaut)
POST   /api/libraries/{id}/scan                  → Lancer scan (background)
GET    /api/libraries/{id}/scan-progress          → Progression temps réel
GET    /api/libraries/scan-progress/all           → Progression tous les scans
POST   /api/libraries/test-ssh                   → Test connexion SSH

# Tasks
POST   /api/tasks/{film_id}/upload              → Upload sous-titre (langue auto-détectée)
POST   /api/tasks/{film_id}/translate-existing   → Traduire depuis sous-titre existant
POST   /api/tasks/{task_id}/start                → Lancer traduction
GET    /api/tasks/                                → Liste tâches
GET    /api/tasks/{id}                            → Détail tâche
GET    /api/tasks/{id}/progress                   → Progress (polling)
GET    /api/tasks/{id}/glossary                   → Glossaire
GET    /api/tasks/{id}/download                   → Télécharger SRT traduit

# Settings
GET    /api/settings/                             → Liste tous les settings
PUT    /api/settings/                             → Mise à jour groupée
POST   /api/settings/test-ollama                 → Test connectivité
GET    /api/settings/ollama-models?base_url=     → Modèles Ollama (dropdowns)
```

---

## 7. Frontend — structure

- **Router** : `/` (Films), `/films/:id` (FilmDetail), `/libraries` (Libraries), `/tasks` (Tasks), `/settings` (Settings)
- **Design system** : glassmorphism, gradient borders, noise texture, poster 2/3 aspect ratio
- **FilmDetail** : 2 onglets — "Fiche film" (profile, personnages, glossaire, lore) + "Traduction"
  - Sous-titres existants listés avec badges (langue, SDH, Genre, Forced)
  - Bouton "Traduire" sur chaque sous-titre
  - Upload optionnel (auto-détect langue)
  - Sidebar outils : Analyse contextuelle, Whisper (choix modèle), Stats
- **LibrariesPage** : CRUD bibliothèques + sources (local/SSH)
  - Formulaire SSH avec test connexion, show/hide password
  - Barre de progression scan (scanned_dirs/total_dirs, current_dir)
  - Scan result summary (créés, mis à jour, erreurs)
- **FilmCard** : poster 2/3 ratio avec lazy load, fallback icône, meta bar
- **SubtitleUploader** : auto-détect langue (plus de dropdown), texte d'aide mis à jour
- **Settings** : `default_source_language` caché, `auto_scan_enabled` + `auto_scan_interval_hours` ajoutés
- **API client** : `getFilmSubtitles()`, `translateExistingSubtitle()`, `analyzeFilm()`, `transcribeFilm()`, `syncSubtitles()`

---

## 8. Modèles Ollama Cloud — Configuration cible

Voir `CLOUD_MODELS.md` pour la liste complète des 36 modèles cloud.

**Configuration recommandée (serveur sans GPU)** :
- **Draft** : `qwen3.5:397b-cloud` — 119+ langues, `/no_think` pour la rapidité, MoE efficient
- **Refine** : `deepseek-v3.2:671b-cloud` — raisonnement puissant, `/think` pour l'affinage
- **Alternative rapide** : `gpt-oss:20b-cloud` (draft économique)
- **Alternative premium** : `mistral-large-3:675b-cloud` (refine, excellent en français)

---

## 9. Docker

```bash
OLLAMA_URL=http://192.168.x.x:11434 docker compose up -d
```

- **backend** : port 8000, volume `backend-data` → `/app/data` (DB + uploads + outputs + posters)
- **frontend** : port 3000 → Nginx:80, proxy `/api/` → `backend:8000`
  - Buffers agrandis pour les posters (4×512k pour `/api/films/`)
- **Ollama** : EXTERNE — configuré via `OLLAMA_URL` dans `.env` ou l'UI
- **ffmpeg** : Nécessaire pour Whisper — à installer dans le conteneur backend si besoin
- **faster-whisper** : Commenté dans requirements.txt — décommenter + rebuild pour activer

---

## 10. Dettes techniques & bugs connus

| # | Problème | Gravité | Localisation |
|---|---|---|---|
| D1 | ~~`auto_clean_sdh` setting existant mais pas utilisé dans le pipeline~~ ✅ **résolu** (2026-04-27) | - | `tasks.py`, `subtitle_service.py` |
| D2 | ~~Pas de retry LLM~~ ✅ **résolu** (2026-04-27) — 3 tentatives avec backoff exponentiel | - | `translation_service.py` |
| D3 | **BackgroundTasks sans queue**. Si le process redémarre, les tâches en cours sont perdues. | Élevé | `tasks.py` |
| D4 | **Pas de tests** → 🟡 **partiel** (2026-04-27) — 52 tests créés (subtitle, scanner, API films/tasks) | Moyen | `tests/` |
| D5 | **`pysubs2` write SRT** convertit `\n` → `\\N` → au re-parse les retours à la ligne sont `\\N`. | Mineur | `subtitle_service.py` |
| D6 | **Services instanciés manuellement** dans `_build_services_from_settings()`. Pas de DI. | Mineur | `tasks.py` |
| D7 | **Pas de validation backend des settings**. L'UI permet n'importe quelle valeur. | Mineur | `settings_service.py` |
| D8 | **Pas de gestion des uploads orphelins**. Si un upload est fait puis le film supprimé, le fichier reste. | Mineur | `tasks.py` |
| D9 | ~~Passe Refine pas implémentée~~ ✅ **résolu** (2026-04-27) — `refine_translation()` avec prompts d'édition + retry | - | `translation_service.py`, `tasks.py` |
| D10 | **Whisper non testé en conditions réelles**. Le service est écrit mais faster-whisper pas encore installé. | Moyen | `whisper_service.py` |
| D11 | **SSH scanning testé partiellement**. La connexion fonctionne, le listing aussi, mais le poster cache SSH non testé avec gros répertoires. | Moyen | `scanner_service.py` |
| D12 | **`known_hosts=None` dans SSH**. Accepte toutes les clés hôtes — risque de MITM en production. | Moyen | `SSHFilesystem.connect()` |
| D13 | **Mots de passe SSH stockés en clair** en DB (sqlite3). Il faudrait chiffrer au repos. | Élevé | `library_sources.ssh_password` |
| D14 | **`target_lang = task.source_language`** — la traduction utilisait la langue source comme cible. ✅ **résolu** (2026-04-27) | - | `translation_service.py:48` |
| D15 | **`_run_analysis()` méthodes inexistantes** — `analyze_characters`, `get_value`, signatures incorrectes. ✅ **résolu** (2026-04-27) | - | `films.py:197-226` |
| D16 | **Progression jamais commitée pendant la traduction** — polling renvoyait 0% jusqu'à la fin. ✅ **résolu** (2026-04-27) | - | `tasks.py`, `translation_service.py` |
| D17 | **CORS `*` + `credentials=True` invalide** — bloqué par les navigateurs. ✅ **résolu** (2026-04-27) | - | `main.py:107` |
| D18 | **Suppression film sans nettoyage des fichiers** — uploads/outputs/posters orphelins. ✅ **résolu** (2026-04-27) | - | `films.py:130-155` |
| D19 | **Version incohérente** `0.3.0` dans main.py vs `0.4.0` dans CONTEXT.md. ✅ **résolu** (2026-04-27) | - | `main.py:99,125` |
| D20 | **`list_film_subtitles` cassé pour films SSH** — `PermissionError` uniquement attrapé. ✅ **résolu** (2026-04-27) | - | `films.py:239` |

---

## 11. Prochaines étapes — priorité

### Phase 5 — Context Enrichment (suite)

| # | Tâche | Priorité | Notes |
|---|---|---|---|
| 5.1 | **Libraries + scanner** | ✅ | Implémenté — CRUD + scan + SSH + progress |
| 5.2 | **Sous-titres existants listés** | ✅ | `GET /films/{id}/subtitles` + UI |
| 5.3 | **Traduire depuis sous-titre existant** | ✅ | `POST /tasks/{film_id}/translate-existing` |
| 5.4 | **Analyse contextuelle manuelle** | ✅ | `POST /films/{id}/analyze` |
| 5.5 | **Whisper transcription** | ✅ | `POST /films/{id}/transcribe` |
| 5.6 | **Whisper sync** | ✅ | `POST /films/{id}/sync-subtitles` |
| 5.7 | **Scan automatique** | ✅ | `auto_scan_enabled` + `auto_scan_interval_hours` settings + scheduler |
| 5.8 | **Suppression cascade** | ✅ | Supprimer source/library → supprime les films associés |
| 5.9 | **Langue source auto-détectée** | ✅ | `parse_subtitle_filename()` réutilisé, dropdown supprimé |
| 5.10 | **Cross-lingual gender analysis** (ES/DE/IT/PT) | 🟡 | Utiliser sous-titres existants comme signal de genre |
| 5.11 | **Speech pattern analysis** (LLM) | 🟡 | Tics de langage, registre, contractions |
| 5.12 | **Relationship & formality detection** (LLM) | 🟡 | Tu/vous, évolution dans le temps |
| 5.13 | **Context merge** (résolution de conflits genre) | 🟡 | Priorité : NFO cast > gendered lang > SDH > LLM |
| 5.14 | **Enriched translation prompt** | 🔴 | Injecter tous les contextes dans le prompt système |
| 5.15 | **Deux passes Draft → Refine** | ✅ | Draft avec `ollama_model` + `draft_think`, Refine avec `ollama_refine_model` + `refine_think` — implémenté via `refine_translation()` |
| 5.16 | **Table existing_subtitles + flags** | 🟡 | useful_for_gender, useful_for_speakers en DB |
| 5.17 | **TMDB API pour cast/gendre** | 🟡 | Quand NFO pas disponible |
| 5.18 | **Embedded subtitle extraction** (ffprobe/mkv) | 🟡 | Extraire pistes .mkv embarquées |
| 5.19 | **SSH password encryption** | 🔴 | Chiffrer les mots de passe en DB |
| 5.20 | **known_hosts verification SSH** | 🟡 | Accepter host key au 1er connect puis vérifier |

---

## 12. Conventions & choix techniques

- **Python** : async/await partout, type hints (Mapped[]), Python 3.11+
- **DB** : SQLAlchemy 2.0 style (mapped_column, Mapped), async (aiosqlite)
- **Migration** : auto — `init_db()` crée les tables + `_migrate_phase5()` ajoute colonnes films
- **Schemas** : 2 couches — `models/database.py` (ORM) vs `models/schemas.py` (API). Pas de mix.
- **Logging** : structlog — JSON en prod, ConsoleRenderer en debug. Pas de `print()`.
- **Config** : env vars → seed DB au premier boot → UI modifie la DB → services lisent la DB.
- **Frontend** : pas de state global. Hooks locaux. fetch natif. Pas de SSR.
- **Design system** : glassmorphism (bg-white/[0.03]), gradient borders, noise texture, animations CSS
- **Layout** : Sidebar 256px fixe (lg+) + contenu full-width max-[1800px]
- **Nommage** : fichiers kebab-case, composants PascalCase, fonctions snake_case
- **Langue** : UI en français, code/commentaires en anglais, prompts LLM en anglais
- **Ollama Cloud** : modèles `-cloud` routés via l'API Ollama, paramètres `think` pour mode réflexion
- **SSH** : asyncssh pour le scanning, SFTP pour lecture fichiers/posters, `known_hosts=None` (dev only)
- **Whisper** : faster-whisper + ffmpeg, CPU int8, VAD filter, modèles tiny→large
- **Sources** : type `local` + `ssh`, extensible pour `smb`, `nfs` (ajouter FilesystemProvider + source_type)

---

## 13. Déploiement cible

```bash
OLLAMA_URL=http://192.168.x.x:11434 docker compose up -d
# Ouvrir http://serveur:3000
# → Bibliothèques → Ajouter → Source SSH (host, user, clé) → Tester la connexion → Scanner
# → Films affichés avec posters → Sélectionner sous-titre → Traduire
```

Pour activer Whisper :
1. Décommenter `faster-whisper` dans `backend/requirements.txt`
2. Ajouter ffmpeg dans le Dockerfile backend : `RUN apt-get update && apt-get install -y ffmpeg`
3. Rebuild : `docker compose build backend && docker compose up -d`

---

## 14. Changelog

### 2026-04-27 — Bug fixes + Tests

**Bugs critiques corrigés (4)** :
- 🔴 `target_lang = task.source_language` → `film.target_language` — la traduction utilisait la langue source comme cible
- 🔴 `_run_analysis()` crasherait avec `AttributeError` — méthodes `analyze_characters`/`get_value` inexistantes, signatures incorrectes → réécrit avec appels corrects à `build_character_profiles()`, `generate_lore_summary()`, `build_glossary()` + sauvegarde en DB
- 🔴 `settings_service.get_value()` n'existait pas → remplacé par `get()` avec fallback `or`
- 🔴 Progression jamais commitée pendant la traduction → ajout du paramètre `db_session` à `translate_film_subtitles()` avec commit après chaque batch

**Bugs moyens corrigés (8)** :
- 🟠 `auto_clean_sdh` jamais utilisé → ajout de `clean_sdh_from_parsed()` + appel conditionnel dans le workflow
- 🟠 Pas de retry LLM → 3 tentatives avec backoff exponentiel (1.5s, 3s, échec+fallback)
- 🟠 Passe Refine inactive → implémentation de `refine_translation()` avec prompts d'édition, appelée si `refine_model` configuré
- 🟠 `list_film_subtitles` cassé pour films SSH → `except PermissionError` élargi à `except Exception`
- 🟠 Suppression film sans nettoyage fichiers → suppression récursive de `data/uploads/{id}/`, `data/output/{id}/`, poster
- 🟠 CORS `*` + `credentials=True` invalide → restreint à `localhost:3000, localhost:5173`
- 🟠 Version incohérente `0.3.0` → `0.4.0` dans `main.py`
- 🟠 `translate-existing` copy sur soi-même → déjà géré (vérification existait)

**Infrastructure de tests** :
- ✅ `pytest.ini` avec `asyncio_mode=auto`
- ✅ `conftest.py` : DB SQLite isolée par test, client HTTP async, données sample
- ✅ `test_subtitle_service.py` — 18 tests : parsing SRT/VTT, écriture+roundtrip, SDH extraction/clean, CPS
- ✅ `test_scanner.py` — 19 tests : filename parsing, NFO parsing (cast, genres, XML invalide), langues genrées
- ✅ `test_api_films.py` — 15 tests : CRUD films, tâches, 404 handling
- 📦 Dépendances ajoutées : `pytest>=8.0`, `pytest-asyncio`, `httpx>=0.27`

**Prochaines étapes recommandées** :
1. Tests workflow traduction (mock OllamaProvider, bout en bout)
2. Tests scanner (arborescence temporaire avec vrais fichiers)
3. Persistance des tâches d'arrière-plan (queue au lieu de BackgroundTasks)
4. Chiffrement mots de passe SSH
5. WebSocket pour progression temps réel