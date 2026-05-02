# Kinoscribe — Contexte Technique

> Référence technique pour reprendre le développement.
> Documente l'état réel du code, les choix d'implémentation et les prochaines étapes.

---

## 1. État actuel — v0.4.1

**Phase 5+ complète** : Libraries + scan, sous-titres existants, Whisper, analyse contextuelle,
extraction pistes embarquées, gestion fichiers de travail, installation SRT dans source,
chiffrement SSH passwords, task runner persistant, SSE progress.

### Fichiers — ~8 000 lignes de code

```
backend/  (Python / FastAPI) — ~5 200 lignes
├── app/
│   ├── api/
│   │   ├── films.py          ~660l  CRUD + subs + poster + analyze + whisper + tracks + extract + work-files
│   │   ├── libraries.py      ~210l  CRUD libraries/sources + scan + progress + SSH test
│   │   ├── settings.py        ~65l  CRUD settings + test Ollama + fetch modèles
│   │   ├── tasks.py          ~420l  Upload, translate, start, progress, download, install + workflow
│   │   └── events.py          ~95l  SSE endpoint pour tâches temps réel
│   ├── core/
│   │   ├── config.py          ~48l  Pydantic Settings (SECRET_KEY, SSH_KNOWN_HOSTS, etc.)
│   │   ├── crypto.py           ~70l  Fernet encryption/decryption for SSH passwords
│   │   ├── database.py         ~70l  SQLAlchemy async + session factory + init_db() + auto-migration
│   │   └── logging.py         42l  structlog (JSON prod, console debug)
│   ├── models/
│   │   ├── database.py       ~230l  7 tables + TaskStatusEnum
│   │   └── schemas.py        ~175l  Pydantic v2 (API contract — séparé des modèles DB)
│   ├── services/
│   │   ├── scanner_service.py ~830l  FilesystemProvider ABC + Local + SSH + write_bytes, scan NFO/subs/posters
│   │   ├── llm_provider.py          215l  Abstraction LLMProvider + OllamaProvider
│   │   ├── subtitle_service.py     270l  Parse SRT/VTT/ASS, write SRT, CPS, SDH clean
│   │   ├── context_service.py      235l  Character profiling, lore summary, glossaire auto
│   │   ├── translation_service.py  340l  Sliding window, retry LLM, injection contexte, refine pass
│   │   ├── whisper_service.py       280l  Transcription + sync subtitles, async extraction audio
│   │   ├── media_service.py        360l  ffprobe track discovery + ffmpeg extract (subs + audio)
│   │   ├── install_service.py      160l  Copy translated SRT to source dir (local + SSH/SFTP)
│   │   ├── workdir.py              215l  Centralized work directory management (audio/subs/whisper/uploads/sync/output)
│   │   ├── task_runner.py           85l  Persistent task runner (async tracked tasks, recovery on boot)
│   │   ├── settings_service.py     ~230l  Seed defaults, CRUD, test Ollama, validation, fetch modèles
│   │   └── (metadata_service.py removed — unused)
│   └── main.py               ~130l  FastAPI app, lifespan + task recovery + SSH migration + auto-scan scheduler
│   └── scripts/
│       └── migrate_phase5.py        DB migration script

frontend/  (TypeScript / React / Vite / Tailwind) — ~3 200 lignes
├── src/
│   ├── api/client.ts         ~140l   All API calls + SSE support
│   ├── hooks/useApi.ts        ~140l  useFilms, useFilm, useTasks, useActiveTaskPolling, useTaskEvents (SSE)
│   ├── types/
│   │   ├── index.ts           ~110l   Film, Task, Character, ExistingSubtitle, TrackInfo, WorkFile, etc.
│   │   └── settings.ts          7l   Setting type
│   ├── components/
│   │   ├── Layout.tsx          92l   Sidebar nav + mobile top bar
│   │   ├── FilmCard.tsx        ~90l   Card film avec poster
│   │   ├── SubtitleUploader    ~75l   Drag & drop upload
│   │   ├── TaskStatus.tsx      52l   Badge + barre progression
│   │   └── CreateFilmModal    152l   Modal création film
│   ├── pages/
│   │   ├── FilmsPage.tsx      120l   Grille responsive
│   │   ├── FilmDetailPage    ~500l   2 onglets + embedded tracks + install button + work cleanup
│   │   ├── LibrariesPage     ~500l   CRUD libraries + sources + scan + SSH test
│   │   ├── TasksPage.tsx      164l   Tâches par statut
│   │   └── SettingsPage       ~382l   Paramètres + Ollama models
│   ├── App.tsx                20l   Routes
│   ├── main.tsx                9l   Point d'entrée
│   └── index.css            ~160l   Design system

docker-compose.yml                   Backend + Frontend (Ollama externe)
frontend/nginx.conf                  SPA fallback + proxy /api + gros buffers
backend/Dockerfile                   Python 3.11 slim + uv
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
--                   ssh_password (ENCRYPTED with enc: prefix), ssh_remote_path,
--                   enabled, scan_depth, last_scan_at, scan_status, scan_error, created_at, updated_at
```

**Seed** : 16 paramètres en 5 catégories (LLM, Translation, Subtitles, External, Security)

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                              │
│  /            FilmsPage      → grille films avec poster              │
│  /films/:id   FilmDetailPage → Fiche + Traduction + Pistes + Install│
│  /libraries   LibrariesPage  → CRUD bibliothèques + sources + scan   │
│  /tasks       TasksPage      → Tâches + download + install          │
│  /settings    SettingsPage   → Paramètres + modèles Ollama         │
└──────────────────────────────────────────────────────────────────────┘
                              │  /api/*  +  SSE /api/tasks/events
┌──────────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                                  │
│  /api/films/       CRUD + subs + tracks + extract + work-files       │
│  /api/libraries/   CRUD + sources + scan + progress + SSH test       │
│  /api/tasks/       Upload + translate + start + download + install  │
│  /api/settings/    CRUD + Ollama test + modèles                     │
│  /api/events/      SSE task progress                                 │
└──────────────────────────────────────────────────────────────────────┘
                              │
   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌───────────┐
   │ SQLite   │   │ Ollama   │   │ FFmpeg   │   │ SSH/SFTP  │
   │ (7 tbls) │   │ (/chat)  │   │ (media)  │   │ (scan+wr) │
   └──────────┘   └──────────┘   └──────────┘   └───────────┘
```

---

## 4. Flux principaux

### 4a. Répertoire de travail (workdir)

```
data/
  work/{film_id}/
    audio/          ← WAV extraits (ffmpeg pour Whisper)
    subs/           ← sous-titres embarqués extraits (ffprobe/ffmpeg)
    whisper/        ← sorties Whisper (transcription, sync)
    uploads/        ← fichiers uploadés par l'utilisateur
    sync/           ← fichiers synchronisés (futur)
  output/{film_id}/
    *.fr.srt        ← traduction finale uniquement
  cache/{source_id}/ ← cache SSH (posters, NFOs, fichiers)
```

**Principe** : Le dossier source du film est **read-only** sauf lors de l'installation explicite du SRT final.

### 4b. Installation du SRT final

```
POST /api/tasks/{id}/install → install_service
  ├─ Film local : shutil.copy2 → film.path/{video}.{lang}.srt
  └─ Film SSH : SFTP upload → remote_path/{video}.{lang}.srt
```

### 4c. Extraction pistes embarquées

```
GET /api/films/{id}/tracks → media_service.probe_tracks()
  ├─ ffprobe → JSON audio/subtitle/video tracks
  └─ Retourne codec, langue, canaux, défaut, forcé, extractable

POST /api/films/{id}/extract-subtitles → media_service.extract_all_subtitles()
  ├─ Pour chaque piste textuelle (SRT/ASS, pas PGS/VobSub)
  ├─ ffmpeg -i video -map 0:N → data/work/{id}/subs/extracted.{lang}.srt
  └─ Disponible dans GET /films/{id}/subtitles (source="extracted")

POST /api/films/{id}/extract-audio → media_service.extract_audio_track()
  └─ ffmpeg → data/work/{id}/audio/audio_{lang}.wav
```

### 4d. Traduction (pipeline complet)

```
Upload/post-scan → Task (pending) → Start → analyzing_context → translating → refining → completed
  ├─ Context analysis : LLM characters + lore + glossaire
  ├─ Translation : sliding window, retry (3×), SDH clean optionnel
  ├─ Refine pass (optionnel) : modèle différent, prompts d'édition
  ├─ Write SRT → data/output/{film_id}/{name}.{lang}.srt
  └─ Install (optionnel) → copie dans dossier source
```

### 4e. Task runner persistant

```
start_task(task_id, coro) → asyncio.create_task + in-process tracking
  ├─ Tasks recorded as 'pending' in DB before start
  ├─ On boot: recover stale tasks (→ failed) + restart pending tasks
  └─ SSE /api/tasks/events → real-time progress to frontend
```

### 4f. Sécurité

```
SSH passwords: encrypted with Fernet (cryptography library)
  ├─ Key derived from SECRET_KEY (SHA256 → Fernet key)
  ├─ Stored with 'enc:' prefix → auto-migrate cleartext on boot
  └─ Decrypted on read via scanner_service / install_service

SSH known_hosts: configurable
  ├─ 'none' (default, accept all — dev only)
  ├─ 'auto' (~/.ssh/known_hosts)
  └─ '/path/to/known_hosts' file
```

---

## 5. API Routes

```
# Films
GET    /api/films/                         → Liste films
POST   /api/films/                         → Créer film
GET    /api/films/{id}                     → Détail film
GET    /api/films/{id}/characters          → Personnages
GET    /api/films/{id}/glossary            → Glossaire
GET    /api/films/{id}/lore                → Lore summary
GET    /api/films/{id}/poster              → Poster (Cache-Control 24h)
GET    /api/films/{id}/subtitles           → Sous-titres (scanner + uploaded + extracted + transcribed)
POST   /api/films/{id}/analyze             → Analyse contextuelle (async)
POST   /api/films/{id}/transcribe          → Whisper transcription (async)
POST   /api/films/{id}/sync-subtitles      → Whisper sync (async)
GET    /api/films/{id}/tracks              → List embedded tracks (ffprobe)
POST   /api/films/{id}/extract-subtitles   → Extract embedded subs (ffmpeg)
POST   /api/films/{id}/extract-audio       → Extract audio track (ffmpeg)
GET    /api/films/{id}/work-files          → List work files by category
DELETE /api/films/{id}/work-files          → Clean work files (?category=all|audio|subs|...)
DELETE /api/films/{id}                     → Supprimer film + work + output

# Libraries
GET    /api/libraries/                     → Liste
POST   /api/libraries/                     → Créer
GET/PUT/DELETE /api/libraries/{id}        → CRUD
POST   /api/libraries/{id}/sources         → Ajouter source
PUT/DELETE /api/libraries/{id}/sources/{sid} → Modifier/supprimer source
POST   /api/libraries/{id}/scan            → Lancer scan (async)
GET    /api/libraries/{id}/scan-progress   → Progression temps réel
GET    /api/libraries/scan-progress/all    → Tout
POST   /api/libraries/test-ssh             → Test connexion SSH

# Tasks
POST   /api/tasks/{film_id}/upload                    → Upload sous-titre
POST   /api/tasks/{film_id}/translate-existing         → Traduire depuis sous-titre existant
POST   /api/tasks/{task_id}/start                      → Lancer traduction (task runner)
GET    /api/tasks/                                      → Liste
GET    /api/tasks/{id}                                  → Détail
GET    /api/tasks/{id}/progress                        → Progress
GET    /api/tasks/{id}/glossary                        → Glossaire
GET    /api/tasks/{id}/download                        → Télécharger SRT traduit
POST   /api/tasks/{id}/install                         → Installer SRT dans dossier source

# Events
GET    /api/tasks/events                                 → SSE stream (task progress)

# Settings
GET    /api/settings/                    → Liste
PUT    /api/settings/                    → Mise à jour groupée
POST   /api/settings/test-ollama        → Test connectivité
GET    /api/settings/ollama-models      → Modèles Ollama
```

---

## 6. Dettes techniques & bugs connus

| # | Problème | Gravité | Statut |
|---|---|---|---|
| D3 | BackgroundTasks sans queue | Élevé | ✅ **Résolu** — task_runner.py (asyncio.create_task + DB recovery) |
| D5 | pysubs2 `\\N` encoding | Mineur | ✅ **Résolu** — conditional logic dans write_srt |
| D7 | Pas de validation settings | Mineur | ✅ **Résolu** — VALIDATION dict + 422 errors |
| D10 | Whisper non testé en production | Moyen | Persistant — needs ffmpeg + faster-whisper in Docker |
| D11 | SSH scan avec gros répertoires | Moyen | Persistant — needs integration tests |
| D12 | known_hosts=None | Moyen | ✅ **Résolu** — configurable: none/auto/path |
| D13 | SSH passwords en clair | Élevé | ✅ **Résolu** — Fernet encryption + enc: prefix + auto-migration |
| D17 | CORS * + credentials | Moyen | ✅ **Résolu** — restricted to localhost |
| D18 | Suppression sans nettoyage | Mineur | ✅ **Résolu** — clean_all_for_film() |
| D23 | Settings validation | Mineur | ✅ **Résolu** — min/max bounds + URL + type validation |

---

## 7. Prochaines étapes

| # | Tâche | Priorité | Notes |
|---|---|---|---|
| 1 | **Whisper dans Docker** | 🟠 Haute | Décommenter faster-whisper + ffmpeg dans Dockerfile |
| 2 | **TMDB enrichment** | 🟡 Moyenne | `tmdb_api_key` setting existe, implémentation manquante |
| 3 | **WebSocket pour progress** | 🟢 Basse | SSE fait le job — WebSocket pour le futur |
| 4 | **SMB/NFS sources** | 🟢 Basse | FilesystemProvider ABC prêt, implémentation nécessaire |
| 5 | **Integration tests** | 🟡 Moyenne | Mock OllamaProvider, bout en bout |
| 6 | **Embedded subtitle extraction** | ✅ Fait | media_service.py + tracks/extract endpoints |
| 7 | **Work directory management** | ✅ Fait | workdir.py — audio/subs/whisper/uploads/sync/output |
| 8 | **Install SRT to source** | ✅ Fait | install_service.py — local + SSH |
| 9 | **SSH password encryption** | ✅ Fait | crypto.py — Fernet + enc: prefix + auto-migration |
| 10 | **SSH known_hosts** | ✅ Fait | Configurable: none/auto/path |
| 11 | **Persistent task runner** | ✅ Fait | task_runner.py — asyncio tasks + DB recovery |
| 12 | **SSE task progress** | ✅ Fait | events.py + useTaskEvents hook |

---

## 8. Conventions & choix techniques

- **Python** : async/await, type hints (Mapped[]), Python 3.11+
- **DB** : SQLAlchemy 2.0 (mapped_column, Mapped), async (aiosqlite)
- **Migration** : auto — `init_db()` crée tables + `_migrate_phase5()` ajoute colonnes
- **Schemas** : 2 couches — `models/database.py` (ORM) vs `models/schemas.py` (API)
- **Logging** : structlog — JSON prod, ConsoleRenderer debug
- **Config** : env vars → seed DB → UI modifie DB → services lisent DB
- **Security** : SECRET_KEY for encryption, SSH passwords encrypted at rest (Fernet), CORS restricted
- **Work directory** : `data/work/{id}/audio|subs|whisper|uploads|sync` + `data/output/{id}/` for finals
- **Task runner** : asyncio.create_task + DB status tracking, not FastAPI BackgroundTasks
- **Frontend** : Pas de state global. Hooks locaux. fetch natif. SSE pour progress.
- **Langue** : UI en français, code/commentaires en anglais, prompts LLM en anglais

---

## 9. Déploiement cible

```bash
# .env
SECRET_KEY=your-long-random-string-here
SSH_KNOWN_HOSTS=none  # or 'auto' or /path/to/known_hosts
OLLAMA_URL=http://192.168.x.x:11434

docker compose up -d
# → http://serveur:3000
```

Pour activer Whisper :
1. Décommenter `faster-whisper` dans `backend/requirements.txt`
2. Ajouter ffmpeg dans le Dockerfile : `RUN apt-get update && apt-get install -y ffmpeg`
3. Rebuild : `docker compose build backend && docker compose up -d`