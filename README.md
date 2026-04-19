# Kinoscribe

*Kino* (cinéma) + *scribe* (celui qui écrit) — traduction locale et contextualisée de sous-titres par IA.

## ✨ Features

- 🎯 **Traduction contextualisée** — Lore narratif, profils de personnages et glossaire injectés dans chaque prompt
- 👤 **Résolution de genre** — SDH + LLM pour lever les ambiguïtés (ex: EN → FR accord en genre)
- 📜 **Fenêtre glissante** — Chaque batch connaît les N lignes précédentes traduites
- 📊 **Monitoring CPS** — Détecte les sous-titres trop denses pour leur timing
- 📖 **Glossaire automatique** — Noms propres, argot et néologismes traduits de façon cohérente
- 🔒 **Local-first** — Tout tourne en local via Ollama, zéro donnée dans le cloud
- 🐳 **Docker** — `docker compose up` et c'est parti

## 🚀 Quick Start

```bash
# Set your Ollama server URL
export OLLAMA_URL=http://192.168.1.50:11434    # your existing Ollama server

# Check prerequisites (connectivity + model)
./setup.sh

# Launch
docker compose up -d

# Open http://localhost:3000
```

## 📖 Workflow

1. **Créer un film** — Titre, langue source/cible
2. **Uploader un .srt** — SRT, VTT ou ASS
3. **Lancer la traduction** — Kinoscribe :
   - Analyse les SDH pour identifier les locuteurs
   - Construit les profils de personnages (genre, personnalité)
   - Génère un résumé narratif (lore)
   - Construit un glossaire film-spécifique
   - Traduit par batch avec fenêtre glissante
   - Vérifie le CPS et écrit le fichier de sortie
4. **Télécharger le résultat**

## 🏗️ Architecture

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Frontend (Nginx)│────▶│  Backend (FastAPI)│────▶│  Ollama server   │
│  :3000           │◀────│  :8000           │◀────│  (existing)      │
└──────────────────┘     └──────────────────┘     └──────────────────┘
     Volume: dist/           Volume: data/          On your network
```
                               │
                          SQLite (data/)
```

## ⚙️ Configuration

| Variable | Défaut | Description |
|---|---|---|
| `OLLAMA_MODEL` | `llama3` | Modèle LLM Ollama |
| `OLLAMA_URL` | `http://host.docker.internal:11434` | URL of your existing Ollama server |
| `TARGET_LANG` | `fr` | Langue cible par défaut |
| `CPS_LIMIT` | `25` | Limite caractères/seconde |
| `SLIDING_WINDOW_SIZE` | `20` | Lignes de contexte glissant |

## 🛠️ Dev (sans Docker)

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## 📋 Roadmap

- [x] Parser SRT/VTT/ASS + écriture
- [x] SDH speaker extraction
- [x] Profilage de personnages (LLM + SDH)
- [x] Sliding window contextual translation
- [x] Glossaire automatique
- [x] Frontend React
- [x] Docker Compose
- [ ] API TMDB (cast, metadata auto)
- [ ] Cross-lingual gender analysis
- [ ] Multi-provider (OpenAI, Anthropic)
- [ ] Two-pass translation (Draft → Refine)
- [ ] WebSocket suivi temps réel
- [ ] Radarr/Sonarr integration
- [ ] Tests

## License

MIT