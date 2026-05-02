# Kinoscribe — Phase 5 : Libraries + Context Enrichment

> Design document — 19 avril 2026  
> Status : **Proposal** — à valider avant implémentation

---

## 1. Film Libraries (Scan Jellyfin)

### 1.1 Problème

Actuellement, chaque film est créé manuellement via l'UI. L'utilisateur a une médiathèque Jellyfin avec cette structure :

```
/mnt/media/Films/
├── The Shawshank Redemption (1994)/
│   ├── The Shawshank Redemption (1994).mkv
│   ├── The Shawshank Redemption (1994).nfo
│   ├── folder.jpg                           ← poster
│   ├── backdrop.jpg                         ← fanart
│   ├── logo.png
│   └── subtitles/
│       ├── The Shawshank Redemption (1994).en.srt
│       ├── The Shawshank Redemption (1994).en.forced.srt
│       ├── The Shawshank Redemption (1994).fr.srt        ← déjà FR
│       ├── The Shawshank Redemption (1994).es.srt        ← ES = langue genrée !
│       ├── The Shawshank Redemption (1994).de.srt        ← DE = langue genrée !
│       └── The Shawshank Redemption (1994).en.sdh.srt     ← SDH avec noms !
├── Pulp Fiction (1994)/
│   ├── Pulp Fiction (1994).mkv
│   ├── ...
```

On veut scanner ces dossiers automatiquement.

### 1.2 Modèle de données

```sql
-- Nouvelle table : libraries
CREATE TABLE libraries (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,              -- "Films", "Séries", etc.
    path        TEXT NOT NULL UNIQUE,       -- "/mnt/media/Films"
    scan_depth  INTEGER DEFAULT 2,          -- 1 = plat, 2 = un niveau de sous-dossiers (Jellyfin)
    auto_scan   BOOLEAN DEFAULT false,      -- scan automatique périodique
    last_scan   TIMESTAMP,
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

-- Modification table films : ajouter library_id + path
ALTER TABLE films ADD COLUMN library_id TEXT REFERENCES libraries(id);
ALTER TABLE films ADD COLUMN path TEXT;            -- chemin absolu du dossier du film
ALTER TABLE films ADD COLUMN video_path TEXT;      -- chemin du fichier vidéo
ALTER TABLE films ADD COLUMN nfo_parsed JSON;      -- données NFO structurées
ALTER TABLE films ADD COLUMN poster_path TEXT;     -- chemin du poster
ALTER TABLE films ADD COLUMN has_existing_subs BOOLEAN DEFAULT false;

-- Nouvelle table : existing_subtitles (sous-titres déjà présents, sources contextuelles)
CREATE TABLE existing_subtitles (
    id          TEXT PRIMARY KEY,
    film_id     TEXT REFERENCES films(id) ON DELETE CASCADE,
    language    TEXT NOT NULL,              -- "en", "fr", "es", "de", "en.sdh"
    is_sdh      BOOLEAN DEFAULT false,      -- sous-titres pour malentendants ?
    is_forced   BOOLEAN DEFAULT false,      -- forced (narration, signage)
    file_path   TEXT NOT NULL,
    format      TEXT DEFAULT 'srt',
    line_count  INTEGER DEFAULT 0,
    source_type TEXT DEFAULT 'embedded',    -- "embedded" | "sidecar" | "extracted"
    -- Flags d'utilité pour la traduction
    useful_for_gender   BOOLEAN DEFAULT false,  -- langue genrée (ES, DE, IT, PT, FR...)
    useful_for_speakers BOOLEAN DEFAULT false,  -- contient des noms de personnages (SDH)
    scanned     BOOLEAN DEFAULT false,      -- le contenu a-il été parsé ?
);
```

### 1.3 API Routes

```
# Libraries CRUD
GET    /api/libraries/                   Liste les bibliothèques
POST   /api/libraries/                   Créer une bibliothèque {name, path, scan_depth}
GET    /api/libraries/{id}               Détail d'une bibliothèque
PUT    /api/libraries/{id}               Modifier
DELETE /api/libraries/{id}               Supprimer (+ option cascade films)

# Scan
POST   /api/libraries/{id}/scan          Lancer un scan (background task)
GET    /api/libraries/{id}/scan-status   État du scan en cours

# Films — enrichi
GET    /api/films/{id}/subtitles/existing   Liste les sous-titres existants du film
POST   /api/films/{id}/scan-subtitles      Scanner le dossier du film pour trouver les .srt
```

### 1.4 Logique de Scan

```
scan_library(library):
  1. Lister les sous-dossiers de library.path (depth=scan_depth)
  2. Pour chaque sous-dossier :
     a. Chercher le .nfo → parser → titre, année, réalisateur, acteur, plot
     b. Chercher les fichiers vidéo (.mkv, .mp4, .avi, .webm)
     c. Chercher les images (.jpg, .png) → poster_path
     d. Chercher les sous-titres (.srt, .vtt, .ass) → existing_subtitles
        - Déduire la langue du nom de fichier : 
          "film.en.srt", "film.en.sdh.srt", "film.en.forced.srt"
          Convention Jellyfin : {title}.{lang}.srt, {title}.{lang}.sdh.srt
     e. Vérifier si le film existe déjà (par titre+année ou par path) → upsert
  3. Marquer les films du dossier qui ne sont plus présents (optionnel)
```

### 1.5 Parsing des noms de fichiers sous-titres

Convention Jellyfin / Emby :
```
Movie.Name.1994.en.srt         → lang=en, sdh=false
Movie.Name.1994.en.sdh.srt     → lang=en, sdh=true
Movie.Name.1994.en.forced.srt  → lang=en, forced=true
Movie.Name.1994.fr.srt         → lang=fr
Movie.Name.1994.es.srt         → lang=es (langue genrée !)
```

Regex :
```python
pattern = r'\.([a-z]{2,3}(?:-[a-zA-Z]{2,4})?)(?:\.(sdh|hi|cc))?(?:\.(forced))?\.(srt|vtt|ass|ssa)$'
```

---

## 2. Context Enrichment (Sources multiples pour la traduction)

### 2.1 Problème

Actuellement, le contexte est construit à partir de :
- SDH du fichier source (noms des personnages)
- LLM analysis (genre, description)
- Lore summary (résumé narratif)
- Glossaire auto

C'est insuffisant. Le LLM a besoin de **beaucoup plus** pour :
- Choisir le bon **genre grammatical** (il/elle, vouvoiement/tutoiement)
- Adapter le **ton et le registre** (formel/familier, tutoiement/vouvoiement)
- Détecter les **évolutions de relation** (vous → tu au fil du film)
- Comprendre les **tics de langage** et expressions idiomatiques

### 2.2 Sources de contexte disponibles

| Source | Données | Fiabilité | Disponibilité |
|---|---|---|---|
| **NFO / TMDB** | Casting, personnage → acteur → genre réel | 🟢 Haute (faits) | Si NFO présent |
| **Sous-titres SDH** | Noms des personnages qui parlent | 🟢 Haute | Si SDH dispo |
| **Sous-titres langues genrées (ES, DE, IT, PT)** | Genre grammatical des personnages | 🟢 Haute | Si ES/DE/IT/PT dispo |
| **Sous-titres existants FR** | Traduction de référence (déjà faite) | 🟡 Moyenne | Si FR dispo |
| **Dialogue source (EN)** | Tics de langage, registre | 🟡 Moyenne | Toujours |
| **LLM analysis** | Interprétation du dialogue | 🟡 Moyenne | Toujours |

### 2.3 Architecture du Context Enrichment

```
                    ┌──────────────────┐
                    │  Film Directory   │
                    └────────┬─────────┘
                             │
            ┌────────────────┼────────────────────┐
            │                │                     │
     ┌──────▼──────┐  ┌─────▼─────┐  ┌───────────▼──────────┐
     │  NFO Parse  │  │  Video    │  │  Subtitle Files       │
     │  (metadata) │  │  (future) │  │  (.en.srt, .es.srt...) │
     └──────┬──────┘  └───────────┘  └───────────┬──────────┘
            │                                     │
            │         ┌───────────────────────────┤
            │         │           │               │
     ┌──────▼──────┐  │    ┌──────▼──────┐  ┌─────▼─────────┐
     │ Cast/Gender │  │    │ SDH Parse   │  │ Gendered Lang │
     │ from NFO    │  │    │ (speakers)  │  │ Parse (ES/DE) │
     └──────┬──────┘  │    └──────┬──────┘  └──────┬────────┘
            │         │           │                │
            └─────────┼───────────┼────────────────┘
                      │           │
              ┌───────▼───────────▼──────────────┐
              │     CONTEXT BUILDER              │
              │     (multi-source merge)         │
              │                                  │
              │  1. Merge character identities    │
              │     (NFO cast + SDH + gendered)  │
              │  2. Resolve gender conflicts      │
              │  3. Build relationship map        │
              │  4. Detect register/formality     │
              │  5. Extract speech patterns       │
              │  6. Build relationship timeline   │
              └──────────────┬────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  ENRICHED CONTEXT │
                    │                  │
                    │  • Characters    │
                    │    - gender     │
                    │    - register   │
                    │    - speech     │
                    │    - confidence │
                    │  • Relationships│
                    │    - type       │
                    │    - evolution  │
                    │  • Glossary     │
                    │  • Lore         │
                    │  • Speech map   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  TRANSLATION     │
                    │  (draft → refine)│
                    └─────────────────┘
```

### 2.4 Modèle de données enrichi

```sql
-- Characters enrichi
ALTER TABLE characters ADD COLUMN register TEXT DEFAULT 'unknown';
    -- "formal", "informal", "mixed", "unknown"
    -- Comment ce personnage s'exprime typiquement

ALTER TABLE characters ADD COLUMN speech_patterns JSON;
    -- {"tics": ["you know", "I mean"], "vocabulary": "casual", 
    --  "sentence_length": "short", "contractions": true}

ALTER TABLE characters ADD COLUMN gender_confidence TEXT DEFAULT 'low';
    -- "high" = confirmé par NFO/casting ou langue genrée
    -- "medium" = confirmé par SDH + LLM
    -- "low" = LLM seulement

ALTER TABLE characters ADD COLUMN gender_sources JSON;
    -- ["nfo_cast", "sdh_es", "llm_analysis"]
    -- Traçabilité de la source du genre

-- Nouvelle table : character_relationships
CREATE TABLE character_relationships (
    id              TEXT PRIMARY KEY,
    film_id         TEXT REFERENCES films(id) ON DELETE CASCADE,
    character_a     TEXT NOT NULL,            -- nom personnage A
    character_b     TEXT NOT NULL,            -- nom personnage B
    relationship    TEXT DEFAULT 'unknown',   -- "friends", "colleagues", "family", "couple", 
                                              -- "stranger", "authority", "subordinate"
    formality       TEXT DEFAULT 'unknown',  -- "tutoiement", "vouvoiement", "mixed"
    evolution       TEXT DEFAULT 'none',       -- "stable", "formal_to_informal", "informal_to_formal"
    evolution_line  INTEGER,                  -- ligne approximative du changement
    confidence      TEXT DEFAULT 'low',       -- "high", "medium", "low"
    meta            JSON                     -- détails, preuves
);
```

### 2.5 Pipeline de Context Enrichment

Le workflow devient :

```
Phase 1 : Parse ──────────────────────────────────
  • Parse source subtitle (.en.srt)

Phase 2 : Scan existing resources ─────────────────
  • Scan le dossier du film pour les fichiers .srt/.vtt existants
  • Parse le .nfo → cast, acteurs, synopsis
  • Pour chaque sous-titre existant :
    - Identifier la langue (+ SDH, forced)
    - Si langue genrée (ES, DE, IT, PT, FR) → flag useful_for_gender
    - Si SDH → flag useful_for_speakers
    - Compter les lignes

Phase 3 : Multi-source context analysis ───────────
  3a. NFO/TMDB → Character gender from cast
      - Pour chaque acteur du cast → chercher le genre (M/F)
      - Assigner gender_confidence = "high" pour les matchs NFO
      - Source : "nfo_cast"

  3b. Gendered subtitles → Cross-lingual gender analysis
      - Parser les sous-titres ES/DE/IT
      - LLM : "Dans ces sous-titres espagnols, identifie le genre 
        grammatical de chaque personnage à partir des adjectifs/
        pronoms/accords (él/ella, der/die, il/elle équivalents)"
      - Source : "gendered_es", "gendered_de"

  3c. SDH subtitles → Speaker identification + gender
      - Extraire les noms [JOHN]:, (MARY):
      - Corréler avec le cast NFO
      - Source : "sdh"

  3d. Source dialogue (EN) → LLM deep analysis
      - Analyse du dialogue pour :
        • Tics de langage ("you know what I mean", "basically")
        • Registre (formel/informel)
        • Contractions (don't vs do not)
        • Longueur des phrases
        • Vocabulaire caractéristique
      - Source : "llm_speech"

  3e. Relationship detection
      - LLM analyse les patterns de dialogue entre paires de personnages
      - Détecte le registre de chaque paire (A tutoie B ? B vouvoie A ?)
      - Détecte les évolutions (changement de vouvoiement à tutoiement)
      - Source : "llm_relationships"

  3f. Lore summary (inchangé)
      - Résumé narratif du film

  3g. Glossary (enrichi)
      - Ajout des termes issus des NFO (lieux, noms d'œuvres mentionnées)

Phase 4 : Context merge ──────────────────────────
  • Merge tous les personnages (NFO + SDH + ES/DE/IT + LLM)
  • Résoudre les conflits de genre :
    - NFO cast > gendered lang > SDH correlation > LLM guess
    - En cas de conflit → garder le genre avec la plus haute confiance
    - Logger les conflits
  • Construire le relationship map
  • Construire le speech pattern map

Phase 5 : Translation (draft → refine) ───────────
  • System prompt enrichi avec TOUT le contexte :
    - Personnages + genre + confidence
    - Relations + formality + evolution
    - Speech patterns
    - Glossary
    - Lore
    - Instructions pour gérer le vouvoiement/tutoiement
```

### 2.6 Prompts LLM enrichis

#### Cross-lingual Gender Analysis (depuis sous-titres ES/DE)

```python
CROSS_GENDER_PROMPT = """
You are a linguistic expert analyzing film subtitles in {source_lang}.
For each speaking character, determine their grammatical gender from
{source_lang} linguistic markers:

- Spanish: él/ella, un/una, -o/-a endings, adjective agreement
- German: der/die/das, -er/-e endings, adjective declension  
- Italian: il/la, -o/-a endings, participle agreement
- Portuguese: o/a, -o/-a endings

For each character found, return:
{{
  "characters": [
    {{
      "name": "character name",
      "gender": "male|female|neutral|unknown",
      "evidence": "the specific linguistic markers that indicate this gender",
      "confidence": "high|medium|low"
    }}
  ]
}}

Subtitles ({source_lang}):
{subtitle_sample}
"""
```

#### Speech Pattern Analysis

```python
SPEECH_PATTERN_PROMPT = """
You are a dialogue analyst examining film subtitles.
For each recurring character, analyze their speech patterns:

1. Register: Do they speak formally, casually, or mixed?
2. Verbal tics: Repeated phrases, filler words, catchphrases
3. Contractions: Do they use contractions (don't, can't) or full forms?
4. Sentence length: Short/punchy or long/complex?
5. Vocabulary level: Simple, technical, poetic, slang-heavy?
6. Emotional range: Calm, excitable, sarcastic, warm?

Return JSON:
{{
  "characters": [
    {{
      "name": "...",
      "register": "formal|informal|mixed",
      "tics": ["you know", "I mean"],
      "contractions": true,
      "sentence_length": "short|medium|long",
      "vocabulary": "simple|technical|poetic|slang",
      "emotional_tone": "calm|excitable|sarcastic|warm|cold",
      "sample_quotes": ["quote1", "quote2"]
    }}
  ]
}}
"""
```

#### Relationship & Formality Analysis

```python
RELATIONSHIP_PROMPT = """
You are analyzing character relationships in a film through their dialogue patterns.
Examine how characters address each other:

1. Formality level: Do they use formal or informal address?
   (In English: title+lastname vs firstname, "sir/ma'am" vs casual)
   (This will inform French tu/vous choices)

2. Relationship type: What kind of relationship do they have?
   (friends, colleagues, family, couple, authority/subordinate, stranger)

3. Evolution: Does their relationship change over the course of the film?
   (e.g., they start formal and become close friends)

For each PAIR of characters who interact, return:
{{
  "relationships": [
    {{
      "character_a": "name",
      "character_b": "name",
      "relationship": "friends|colleagues|family|couple|authority|subordinate|stranger",
      "formality": "formal|informal|mixed",
      "evolution": "stable|formal_to_informal|informal_to_formal",
      "evidence": "brief quote showing the formality level",
      "evolution_evidence": "brief evidence of change if any"
    }}
  ]
}}

Characters known:
{character_list}

Dialogue (chronological):
{dialogue_sample}
"""
```

### 2.7 System Prompt de Traduction Enrichi

Le prompt système pour la traduction devient beaucoup plus riche :

```
You are an expert film subtitle translator specializing in cinematic localization.

RULES:
1. Maintain the original timing indices exactly.
2. Preserve tone, personality, and register of each character.
3. Respect character genders for grammatical agreement in the target language.
4. Use the glossary for consistent translation of proper nouns and slang.
5. Keep subtitle text concise — target under 25 characters per second.
6. Return ONLY a JSON object with a 'lines' key containing a list of {'index': int, 'text': str} objects.
7. Do NOT include any explanation or commentary.

CRITICAL — FORMALITY RULES:
- Character relationships define the formality level (tu/vous in French)
- If a relationship EVOLVES (e.g., formal→informal), mirror this in the translation
- Relationship evolution details are provided below — follow them closely

CHARACTER SPEECH PATTERNS:
- Each character has a distinct voice — match their register, tics, and vocabulary level
- Do NOT make all characters sound the same

{character_profiles_with_speech_patterns}
{relationship_map_with_formality}
{glossary}
{lore}
```

---

## 3. Ordre d'implémentation

### Sprint 1 — Libraries (1-2 semaines)
1. Table `libraries` + migrations
2. CRUD API libraries
3. Scanner de dossiers (scan_depth, NFO, images, vidéo, sous-titres)
4. Frontend : page Libraries + scan button + résultats
5. Intégration dans le layout (nav)

### Sprint 2 — Existing Subtitles Scan (1 semaine)
1. Table `existing_subtitles`
2. Parse des noms de fichiers (langue, SDH, forced)
3. Frontend : affichage des sous-titres existants par film
4. Flag automatique des sous-titres "utiles" (langues genrées, SDH)

### Sprint 3 — Multi-source Context (2 semaines)
1. NFO parsing → cast gender (high confidence)
2. Cross-lingual gender analysis (ES/DE/IT subtitles → LLM)
3. SDH speaker → character correlation
4. Speech pattern analysis (LLM on dialogue)
5. Relationship & formality detection (LLM)
6. Context merge algorithm (conflict resolution)
7. Enriched translation prompt

### Sprint 4 — Relationship Evolution (1 semaine)
1. Detection des changements de registre au fil du film
2. Injection dans le prompt de traduction (avec line number hints)
3. Validation visuelle dans l'UI (timeline de relations ?)

---

## 4. Questions ouvertes

- **TMDB** : faut-il une intégration TMDB pour enrichir le genre des acteurs ? (L'API gratuite permet 50 req/jour)
- **Embedded subtitles** : doit-on extraire les sous-titres embarqués dans les .mkv via ffprobe/ffmpeg ? C'est plus complexe mais donne accès à PLUS de pistes
- **Relationship UI** : comment visualiser les relations entre personnages dans l'UI ? Un graphe interactif ? Un tableau ?
- **Conflict resolution UI** : quand 2 sources contradictoires donnent un genre différent pour un personnage, faut-il une UI de résolution manuelle ?
- **Scan automatique** : doit-on scanner les bibliothèques automatiquement (cron) ou uniquement manuellement ?