# Kinoscribe — Contexte Technique

> Référence technique pour reprendre le développement.
> Documente l'état réel du code, les choix d'implémentation et les prochaines étapes.
>
> **Note** : ce document a été audité et corrigé le 2026-05-08 (voir §10 « Audit »).
> Plusieurs inexactitudes ont été corrigées (metadata_service, comptes de settings,
> port frontend, statut Whisper, routes manquantes, etc.).

**Phase 5+ complète** : Libraries + scan, sous-titres existants, Whisper, analyse contextuelle,
extraction pistes embarquées, gestion fichiers de travail, installation SRT dans source,
chiffrement SSH passwords, task runner persistant, SSE progress.

### Fichiers — ~8 000 lignes de code

```
backend/  (Python / FastAPI) — ~5 200 lignes
├── app/
│   ├── api/
│   │   ├── films.py         ~1190l  CRUD + subs + poster + video-stream + analyze + whisper + tracks + extract + work-files + rescan + enrich + translations + install
│   │   ├── libraries.py      ~280l  CRUD libraries/sources + scan + progress + SSH test + mount/unmount
│   │   ├── settings.py        ~65l  CRUD settings + test Ollama + fetch modèles
│   │   ├── tasks.py         ~1060l  Upload, translate-existing, start, progress, download, install + 4 workflows (translation/improve/pipeline/sync)
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
│   │   ├── settings_service.py     ~230l  Seed defaults, CRUD, test Ollama, validation, fetch modèles (17 settings en 5 catégories)
│   │   ├── metadata_service.py     235l  Enrichissement Cinemagoer (IMDb) + TMDB — utilisé par /films/{id}/enrich
│   │   └── (metadata_service.py est BIEN PRÉSENT et utilisé — ne pas supprimer)
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

**Seed** : 17 paramètres en 5 catégories (LLM, Translation, Subtitles, Security, External)

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
GET    /api/films/{id}/video-stream        → Stream vidéo (HTML5, local + monté)
GET    /api/films/{id}/subtitles           → Sous-titres (scanner + uploaded + extracted + transcribed)
POST   /api/films/{id}/analyze             → Analyse contextuelle (async)
POST   /api/films/{id}/rescan              → Rescan dossier film (async, maj metadata)
POST   /api/films/{id}/enrich              → Enrichissement Cinemagoer/TMDB (async)
POST   /api/films/{id}/transcribe          → Whisper transcription (async)
POST   /api/films/{id}/sync-subtitles      → Whisper sync (async)
GET    /api/films/{id}/tracks              → List embedded tracks (ffprobe)
POST   /api/films/{id}/extract-subtitles   → Extract embedded subs (ffmpeg)
POST   /api/films/{id}/extract-audio       → Extract audio track (ffmpeg)
GET    /api/films/{id}/work-files          → List work files by category
DELETE /api/films/{id}/work-files          → Clean work files (?category=all|audio|subs|...)
GET    /api/films/{id}/translations        → List versions traduites (data/output/{id}/)
POST   /api/films/{id}/translations/install → Installer une version spécifique dans le dossier source
DELETE /api/films/{id}                     → Supprimer film + work + output + poster

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
POST   /api/libraries/{id}/sources/{sid}/mount   → Monter source (SSHFS/CIFS)
POST   /api/libraries/{id}/sources/{sid}/unmount → Démonter source

# Tasks
POST   /api/tasks/{film_id}/upload                    → Upload sous-titre
POST   /api/tasks/{film_id}/translate-existing         → Traduire depuis sous-titre existant (ou pipeline)
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
| D10 | Whisper non testé en production | Moyen | ✅ **Résolu** — faster-whisper dans requirements.txt + ffmpeg dans Dockerfile (build best-effort) |
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
| 1 | **Whisper dans Docker** | ✅ Fait | `faster-whisper` dans requirements.txt (install best-effort), `ffmpeg` dans Dockerfile. WhisperX reste commenté (optionnel) |
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
# → http://serveur:15000  (port hôte mappé dans docker-compose.yml ; 15000:80)
#   ⚠️ README + setup.sh mentionnent encore :3000 — voir §10 Audit (B-DOC-3)
```

Pour activer WhisperX (alignement word-level, optionnel) :
1. Décommenter `whisperx` dans `backend/requirements.txt`
2. Rebuild : `docker compose build backend && docker compose up -d`

(Whisper de base et ffmpeg sont **déjà** inclus dans le Dockerfile — ne sont plus à activer.)

---

## 10. Audit — bugs, incohérences et bizarreries (2026-05-08)

> Compte rendu d'analyse complète du code. Les bugs sont classés par gravité.
> Corriger idéalement dans l'ordre : critiques d'abord, puis majeurs, puis mineurs.

### 10.1. Bugs critiques (cassent une fonctionnalité à l'exécution)

| ID | Fichier | Description | Impact |
|---|---|---|---|
| **B-CRIT-1** | `app/api/tasks.py:160-172` (`translate_existing_subtitle`) | Branche `task_type == "pipeline"` : la variable `dest_path` n'est **jamais définie** dans le `else`, mais utilisée ensuite à la ligne 172 (`source_path=dest_path`). | **NameError** → 500 HTTP systématique quand on crée une tâche pipeline depuis le frontend (`api.pipelineFilm` envoie `task_type: 'pipeline'`). La fonctionnalité « Pipeline complet » de l'UI est totalement cassée. |
| **B-CRIT-2** | `app/api/tasks.py:765` (`_run_pipeline_workflow`) | Appel `extract_all_subtitles(video_path, subs_dir)` — la signature réelle est `(video_path, film_id, text_only=True)`. On passe donc `subs_dir` (un chemin `"data/work/{id}/subs"`) comme `film_id`. | À l'intérieur de `extract_all_subtitles`, `extract_subtitle_track(... film_id=subs_dir ...)` construit `data/work/{subs_dir}/subs/extracted.{lang}.srt` → chemin absurde imbriqué. L'extraction embarquée dans le pipeline écrit dans un mauvais dossier et les fichiers ne sont pas retrouvés ensuite par `_list_film_subtitles_raw`. Pipeline cassé même si B-CRIT-1 est corrigé. |
| **B-CRIT-3** | `app/services/scanner_service.py:658-666` (`scan_library`) | Pour les sources SSH **montées** (`is_ssh=True` mais `fs` est un `LocalFilesystem` via mount point), la logique de poster fait : `if is_ssh and entry.get('poster_file'): pass` puis un `elif` non atteint. Donc `poster_local` reste `None` et `film.poster_path = ''`. Le bloc post-commit `if is_ssh and isinstance(fs, SSHFilesystem) and ...` n'est pas non plus exécuté (fs est Local). | Les films scannés depuis une source SSH montée n'ont **jamais de poster**. Le poster existe bien sur le mount (`/app/data/mounts/{sid}/Film/folder.jpg`) mais n'est jamais enregistré. |
| **B-CRIT-4** | `app/api/tasks.py:1029-1055` (`_run_sync_workflow`) | Plusieurs erreurs cumulées :<br>(a) `extract_audio_track(film.video_path, task.source_language or 'und')` — signature réelle `(video_path, film_id, track_index=None, language="und")`. `task.source_language` est passé comme `film_id`, et `language` reste `"und"`. L'audio est écrit dans `data/work/{lang}/audio/audio_und.wav` au lieu de `data/work/{film.id}/audio/audio_{lang}.wav`.<br>(b) `output_path` n'est défini qu'à l'intérieur du `if result_path and os.path.isfile(result_path):`. Si la condition est fausse, `output_path` est **indéfini** → `NameError` sur `logger.info("Sync workflow complete", ..., output=output_path)` ligne 1055.<br>(c) `ollama_url` est lu puis jamais utilisé (dead code).<br>(d) `whisperx_enabled` n'est **pas lu** et `use_whisperx` n'est **pas passé** à `sync_with_whisper` (contrairement à `/transcribe` et au pipeline qui le gèrent). | Workflow sync ( tâches `task_type='sync'`) : écrit dans un mauvais dossier, crash `NameError` si Whisper ne produit pas de sortie, ignore le réglage WhisperX. |

### 10.2. Bugs majeurs (comportement incorrect silencieux)

| ID | Fichier | Description | Impact |
|---|---|---|---|
| **B-MAJ-1** | `app/api/tasks.py:398-403` (`_run_translation_workflow`) | Les personnages (`Character`) sont ajoutés via `session.add(c)` + `film.characters = characters` **sans supprimer les personnages existants**. Comparer avec `_run_improve_workflow` (lignes 596-605) qui supprime d'abord les anciens. | Re-lancer une traduction sur un film déjà analysé → **doublons de personnages** (et doublons de glossaire, voir B-MAJ-2). |
| **B-MAJ-2** | `app/api/tasks.py:408-421` (`_run_translation_workflow`) et `app/api/tasks.py:851-861` (`_run_pipeline_workflow`) | Les entrées `GlossaryEntry` sont ajoutées en bloc sans nettoyer celles existantes. Le workflow `_run_improve_workflow` fait un dédoublonnage par `source_term` mais pas les deux autres. | Re-lancer traduction/pipeline → glossaire gonflé avec des doublons, ce qui allonge les prompts et peut générer des entrées contradictoires. |
| **B-MAJ-3** | `app/api/tasks.py:840-845` (`_run_pipeline_workflow`) | Même problème que B-MAJ-1 pour le pipeline (pas de nettoyage des personnages existants avant ajout). | Doublons de personnages après un 2e pipeline. |
| **B-MAJ-4** | `app/services/translation_service.py:118, 220` (`translate_film_subtitles` / `_translate_batch`) | Le paramètre `temperature` est accepté et lu depuis les settings (`llm_temperature`) mais **jamais transmis** à `self.llm.chat` — un `temperature=0.3` codé en dur est utilisé dans `_translate_batch` et `refine_translation`. | Le réglage « Température de génération » dans l'UI n'a **aucun effet** sur la traduction. |
| **B-MAJ-5** | `app/services/task_runner.py:79-92` (`recover_pending_tasks`) | Ne gère pas le `task_type == 'pipeline'` : le `else` par défaut renvoie vers `_run_translation_workflow`, qui ne sait pas gérer une tâche pipeline (pas d'extract/transcribe, et `source_path` vide). De plus les `pipeline_steps` ne sont évidemment pas restaurés. | Une tâche pipeline en `pending` au moment d'un redémarrage se « réveille » comme une traduction simple et échoue ou produit un résultat partiel. (Actuellement masqué par B-CRIT-1 qui empêche de créer des pipeline tasks — mais à corriger avec B-CRIT-1.) |
| **B-MAJ-6** | `app/main.py:160` (`root()`) | `return {"version": "0.4.0"}` alors que `app = FastAPI(version="0.4.1")` et que CONTEXT.md indique v0.4.1. | L'endpoint racine renvoie un numéro de version obsolète (incohérence interne). |
| **B-MAJ-7** | `app/api/films.py:712` (`analyze_film_context`) | Fallback `ollama_model = await settings_service.get(s, "ollama_model") or "qwen3.5:397b-cloud"`. Le défaut de `ollama_model` dans `config.py` et `settings_service.DEFAULTS` est `"llama3"`. | Si la settings table est vide, l'analyse utilise `qwen3.5:397b-cloud` (modèle cloud qui n'existe probablement pas sur un serveur Ollama local), au lieu du défaut attendu. Incohérence de fallback. |
| **B-MAJ-8** | `app/services/scanner_service.py:718-728` (`scan_library`) | Bloc de création de `Character` depuis le cast NFO présent **deux fois** : une fois dans la branche `if film:` (film existant) et une fois après le `commit/refresh` (pour new films, mais le `if` s'applique aux deux). Fonctionne grâce au `not film.characters` qui devient False après refresh, mais le code est confus et fragile. | Pas un bug fonctionnel aujourd'hui, mais un facteur de risque pour toute modification future. |

### 10.3. Bugs mineurs / bizarreries

| ID | Fichier | Description |
|---|---|---|
| **B-MIN-1** | `frontend/src/hooks/useApi.ts:124` (`useActiveTaskPolling`) | `hasActive` ne couvre que `['analyzing_context', 'translating', 'refining', 'pending']` — oublie `extracting`, `transcribing`, `syncing`, `rescanning`. Une tâche pipeline/sync en cours peut ne pas être considérée « active » côté polling. |
| **B-MIN-2** | `frontend/src/api/client.ts:135` (`pipelineFilm`) | Envoie `subtitle_path: ''` qui déclenche B-CRIT-1 côté backend. À corriger en même temps que B-CRIT-1. |
| **B-MIN-3** | `app/services/metadata_service.py:103` | `result.imdb_id = best.get('imdbID') or f"tt{best.movieID}" if hasattr(best, 'movieID') else None` — précédence d'opérateur déroutante (fonctionne mais illisible). |
| **B-MIN-4** | `app/api/films.py:265-270` (`delete_film`) | `paths_to_clean` est construit avec le poster mais `clean_all_for_film(film_id)` est appelé juste après sans utiliser cette liste. La boucle de suppression finale gère le poster, mais le nom `paths_to_clean` et le commentaire sont trompeurs. |
| **B-MIN-5** | `backend/Dockerfile` | Installe `fuse3` mais `mount_service.unmount_path` appelle `fusermount` (binaire du paquet `fuse` / fuse2). Sur Debian slim, `fuse3` fournit `fusermount3` (et parfois `fusermount` via symlink, mais pas garanti). Risque : `fusermount -uz` introuvable → fallback sur `umount -l` (qui existe). Pas bloquant mais à vérifier. |
| **B-MIN-6** | `backend/Dockerfile` ENV | `OLLAMA_BASE_URL=http://ollama:11434` par défaut, mais il n'y a **aucun service `ollama`** dans `docker-compose.yml`. Fonctionne en compose (l'env de compose override), mais l'image standalone ne se connecte à rien. |
| **B-MIN-7** | `app/api/films.py` `_list_film_subtitles_raw` | Pour les films SSH **non montés**, met en cache les sous-titres lus via SFTP dans `extracted_subs_dir(film_id)` (le dossier des sous-titres *extraits*), avec `source: "ssh_cache"`. Mélange de sémantique : un sous-titre côté-source distant se retrouve classé avec les sous-titres extraits embarqués. |
| **B-MIN-8** | `projects/Kinoscribe/frontend/src/pages/FilmDetailPage.tsx` | Fichier **en double** et obsolète (523 lignes) vs `frontend/src/pages/FilmDetailPage.tsx` (662 lignes). Le dossier `projects/Kinoscribe/` ne sert à rien et contient une vieille révision. À supprimer pour éviter la confusion. |

### 10.4. Incohérences de documentation (CONTEXT vs projet)

> Les corrections factuelles ci-dessous ont **déjà été appliquées** à CONTEXT.md (sections 1-9).

| ID | Document | Problème | Action |
|---|---|---|---|
| **B-DOC-1** | CONTEXT §1 | `metadata_service.py removed — unused` — **FAUX** : le fichier existe (235 lignes) et est utilisé par `POST /films/{id}/enrich`. | ✅ Corrigé dans §1. |
| **B-DOC-2** | CONTEXT §2 | « 16 paramètres en 5 catégories » — il y en a **17** (6 LLM + 7 Translation + 2 Subtitles + 1 Security + 1 External). | ✅ Corrigé dans §2. |
| **B-DOC-3** | CONTEXT §9, README, setup.sh, docker-compose.yml | docker-compose mappe `15000:80` mais **tous** les docs disent `http://localhost:3000`. Le port exposé est en réalité 15000. | ✅ Corrigé dans §9. **README.md et setup.sh restent à corriger** (port 3000 → 15000). |
| **B-DOC-4** | CONTEXT §1 (compte de lignes) | `films.py ~660l`, `tasks.py ~420l`, `libraries.py ~210l` — valeurs obsolètes (réalité : ~1190 / ~1060 / ~280). | ✅ Corrigé dans §1. |
| **B-DOC-5** | CONTEXT §5 | Routes manquantes : `rescan`, `enrich`, `video-stream`, `translations`, `translations/install`, `sources/{sid}/mount`, `sources/{sid}/unmount`. | ✅ Corrigé dans §5. |
| **B-DOC-6** | CONTEXT §7 #1 et §6 D10 | « Whisper dans Docker : décommenter faster-whisper + ffmpeg » — c'est **déjà fait** dans `requirements.txt` et `Dockerfile`. Seul `whisperx` reste commenté (optionnel). | ✅ Corrigé dans §6 et §7. |
| **B-DOC-7** | `DESIGN_DOC.md` | « Last updated 2026-04-19 — Phase 1 complete », « 4 tables », « Ollama: official image with volume persistence » dans le changelog. Document entièrement obsolète : on est en Phase 5+, 7 tables, Ollama est externe (pas de service dans docker-compose). | **À mettre à jour** ou archiver. Pas corrigé ici (hors périmètre CONTEXT.md). |
| **B-DOC-8** | `DESIGN_PHASE5.md` | Propose `existing_subtitles` (table), `character_relationships` (table) et colonnes `register`, `speech_patterns`, `gender_confidence`, `gender_sources` sur `characters`. **Aucune** de ces additions n'est implémentée (le contexte multi-source NFO/SDH/ES-DE n'est qu'esquissé dans `context_service.py`). CONTEXT dit « Phase 5+ complète » — c'est optimiste : seul le volet « Libraries + scan + NFO + SSH » est fait, pas le volet « Context Enrichment ». | **À nuancer** dans CONTEXT. Document de design à garder comme proposition. |
| **B-DOC-9** | `README.md` | Roadmap obsolète : « Two-pass translation », « WebSocket », « Tests » listés en TODO alors que la passe refine + SSE + tests backend existent. Workflow ne mentionne pas les libraries ni le scan. | **À mettre à jour**. |
| **B-DOC-10** | `CLOUD_MODELS.md` | Recommande `qwen3.5:397b-cloud` mais le tableau liste `qwen3.5:397b` (tag `cloud`). La forme exacte du tag Ollama Cloud (`-cloud` suffix) doit être confirmée. | Mineur — à vérifier empiriquement. |

### 10.5. Résumé des priorités de correction

1. **B-CRIT-1** + **B-MIN-2** : corriger la création de tâche pipeline (définir `dest_path=""` dans la branche `else` de `translate_existing_subtitle`).
2. **B-CRIT-2** : remplacer `extract_all_subtitles(video_path, subs_dir)` par `extract_all_subtitles(video_path, film.id, text_only=True)`.
3. **B-CRIT-3** : pour SSH monté, traiter `poster_file` comme un chemin local (le mount le rend accessible) — supprimer la branche `if is_ssh: pass`.
4. **B-CRIT-4** : corriger `_run_sync_workflow` (signature `extract_audio_track`, définir `output_path` dans tous les cas, lire + passer `whisperx_enabled`, supprimer `ollama_url` mort).
5. **B-MAJ-1/2/3** : aligner `_run_translation_workflow` et `_run_pipeline_workflow` sur `_run_improve_workflow` (nettoyage personnages + glossaire avant réajout).
6. **B-MAJ-4** : propager `temperature` jusqu'à `llm.chat` dans `_translate_batch` et `refine_translation`.
7. **B-MAJ-5** : gérer `pipeline` dans `recover_pending_tasks` (et persister `pipeline_steps` si on veut une vraie reprise).
8. **B-MAJ-6/7** : aligner les versions/fallbacks de modèle (`0.4.1` partout, `llama3` comme fallback uniforme).
9. **B-DOC-3/7/9** : mettre à jour README, setup.sh, DESIGN_DOC pour le port 15000 et la phase courante.
10. **B-MIN-8** : supprimer `projects/Kinoscribe/`.

### 10.6. Note sur la cohérence CONTEXT ↔ projet

Après corrections (§1, §2, §5, §6, §7, §9), CONTEXT.md est désormais **aligné avec l'état réel du code** pour ce qui est :
- de la liste et du rôle des fichiers du backend (§1) ;
- du schéma de base de données et du seed (§2) ;
- de la liste des routes API (§5) ;
- du statut des dettes techniques et des « prochaines étapes » (§6, §7) ;
- du port de déploiement (§9).

Restent à traiter (hors CONTEXT.md, voir B-DOC-7/8/9) : `DESIGN_DOC.md` et `README.md` sont obsolètes, et `DESIGN_PHASE5.md` décrit des fonctionnalités non implémentées (existing_subtitles, character_relationships, enrichment colonnes) qui ne devraient pas être présentées comme « Phase 5 complète ».