# Modèles Cloud Ollama — Kinoscribe

> Dernière mise à jour : 19 avril 2026  
> Source : API Ollama (`/v1/models`, `/api/tags`) + page [ollama.com/search?c=cloud](https://ollama.com/search?c=cloud)

---

## 1. Liste complète des modèles cloud Ollama

### Titans — MoE 600B+

| Modèle | Famille | Params totaux | Params actifs | Quant. | Spécialités | Tags |
|---|---|---|---|---|---|---|
| `deepseek-v3.2` | DeepSeek 3.2 | 671B | 37B | FP8 | Raisonnement, multilingue, agentic | thinking, tools, cloud |
| `deepseek-v3.1:671b` | DeepSeek 2 | 671B | 37B | FP8 | Raisonnement, agents, outils | thinking, tools, cloud |
| `cogito-2.1:671b` | DeepSeek2 fork | 671B | 37B | FP8 | Raisonnement réflexif | thinking, cloud |
| `mistral-large-3:675b` | Mistral 3 | 675B | 41B | FP8 | Multilingue, production, multimodal | vision, tools, cloud |
| `glm-5.1` | GLM 5.1 | 756B | — | FP8 | Agentic, code | thinking, tools, cloud |
| `glm-4.6` | GLM 4.6 | 696B | — | FP8 | Agents | tools, cloud |
| `glm-4.7` | GLM 4.7 | — | — | — | Agentic | tools, cloud |

### Grands — MoE 100B–500B

| Modèle | Famille | Params totaux | Params actifs | Quant. | Spécialités | Tags |
|---|---|---|---|---|---|---|
| `qwen3.5:397b` | Qwen 3.5 | 397B | MoE | BF16 | Multilingue (119+ langues), vision, code | vision, thinking, tools, cloud |
| `qwen3-coder:480b` | Qwen3 Coder | 480B | MoE | — | Code spécialisé | tools, cloud |
| `qwen3-vl:235b` | Qwen3-VL | 235B | MoE | — | Vision + multilingue | vision, cloud |
| `qwen3-vl:235b-instruct` | Qwen3-VL | 235B | MoE | — | Vision + instruction-following | vision, cloud |
| `kimi-k2.5` | Kimi K2 | 1T | 32B | INT4 | Agents, long contexte, multimodal | thinking, tools, vision, cloud |
| `kimi-k2:1t` | Kimi K2 | 1T | 32B | FP8 | Agents, multimodal | tools, vision, cloud |
| `kimi-k2-thinking` | Kimi K2 | 1T | 32B | — | Raisonnement | thinking, cloud |
| `minimax-m2.7` | MiniMax M2 | 481B | MoE | NVFP4 | Code, généraliste | cloud |
| `minimax-m2.5` | MiniMax M2 | 230B | 10B | — | Code (SWE-bench 80.2%) | tools, cloud |
| `minimax-m2.1` | MiniMax M2 | 230B | MoE | — | Généraliste | cloud |
| `minimax-m2` | MiniMax M2 | 230B | MoE | — | Généraliste | cloud |
| `nemotron-3-super` | Nemotron | 120B | MoE | NVFP4 | NVIDIA, généraliste | cloud |
| `devstral-2:123b` | Devstral | 128B | MoE | — | Code, agents | tools, cloud |
| `gpt-oss:120b` | GPT-OSS | 117B | 5.1B | MXFP4 | Instructions, structuré, thinking | thinking, tools, cloud |

### Moyens — 20B–100B

| Modèle | Famille | Params totaux | Params actifs | Quant. | Spécialités | Tags |
|---|---|---|---|---|---|---|
| `qwen3-coder-next` | Qwen3 Coder | 81B | MoE | — | Code agentic | tools, cloud |
| `qwen3-next:80b` | Qwen3 Next | 80B | MoE | FP8 | Code, agents | tools, cloud |
| `gpt-oss:20b` | GPT-OSS | 21B | ~3.5B | MXFP4 | Rapide, thinking | thinking, tools, cloud |
| `devstral-small-2:24b` | Devstral | 51.6B | — | — | Code compact | tools, cloud |
| `nemotron-3-nano:30b` | Nemotron | 30B | 30B | — | Compact NVIDIA | cloud |

### Compacts — <20B

| Modèle | Famille | Params totaux | Params actifs | Quant. | Spécialités | Tags |
|---|---|---|---|---|---|---|
| `gemma4:31b` | Gemma 4 | 32.7B | 32.7B | BF16 | Multimodal, créatif | vision, cloud |
| `gemma3:27b` | Gemma 3 | 55B | 55B | — | Créatif, prose | cloud |
| `gemma3:12b` | Gemma 3 | 24B | 24B | — | Créatif, rapide | cloud |
| `gemma3:4b` | Gemma 3 | 8.6B | 8.6B | — | Ultra-compact | cloud |
| `gemini-3-flash-preview` | Google | — | — | — | Google preview | cloud |
| `ministral-3:14b` | Mistral 3 mini | 15.7B | — | — | Compact Mistral | cloud |
| `ministral-3:8b` | Mistral 3 mini | 10.4B | — | — | Compact, rapide | cloud |
| `ministral-3:3b` | Mistral 3 mini | 4.7B | — | — | Ultra-compact | cloud |
| `rnj-1:8b` | ? | 16B | — | — | Inconnu | cloud |

---

## 2. Recommandations Kinoscribe

### Contexte

- **Serveur Ollama sans GPU** → utilisation exclusive des modèles cloud
- Workflow Kinoscribe : **Draft** (traduction brute rapide) → **Refine** (affinage contextuel avec lore, personnages, glossaire, CPS)
- Langues principales : **EN → FR** (mais extensible à ES, DE, IT, PT, JA, KO, ZH)

### 🏆 Choix recommandés

#### Passe Draft — `qwen3.5:397b-cloud`

| Critère | Détail |
|---|---|
| **Multilingue** | 119+ langues — meilleure couverture de tous les modèles cloud |
| **Architecture** | MoE — efficace, seuls les experts pertinents sont activés |
| **Thinking mode** | ✅ `/no_think` pour le draft = réponses directes, rapides |
| **Vision** | ✅ potentiels futurs (analyse de captures de sous-titres) |
| **Génération** | Qwen 3.5 > Qwen 3 sur tous les benchmarks multilingues |
| **Utilisation** | `ollama run qwen3.5:397b-cloud` |

Pour le draft, on veut de la **vitesse** et de la **qualité idiomatique** dès la première passe. Le mode `/no_think` de Qwen 3.5 supprime le raisonnement interne et répond directement — exactement ce qu'il faut pour traduire des batches de 10 lignes rapidement.

#### Passe Refine — `deepseek-v3.2:671b-cloud`

| Critère | Détail |
|---|---|
| **Raisonnement** | Le plus puissant en thinking disponible en cloud Ollama |
| **Params actifs** | 37B — massif maisMoE = efficient |
| **Thinking mode** | ✅ natif — réfléchit avant de répondre |
| **Outils** | ✅ tool calling possible pour pipeline futur |
| **Multilingue** | Fort EN→FR, pré-entraînement massif multilingue |
| **JSON structuré** | Excellent en sortie structurée (format Kinoscribe) |
| **Utilisation** | `ollama run deepseek-v3.2:671b-cloud` |

Pour le refine, on veut du **raisonnement** : analyser le contexte (genre des personnages, ton, registre, glossaire, CPS), puis produire une traduction affinée. Le thinking mode de DeepSeek V3.2 est exactement conçu pour ça.

### 📊 Tableau comparatif des choix

| | Draft (1ère passe) | Refine (2ème passe) |
|---|---|---|
| **🏆 Top pick** | `qwen3.5:397b-cloud` | `deepseek-v3.2:671b-cloud` |
| Langues couvertes | 119+ | Multilingue (excellent EN→FR) |
| Thinking mode | ✅ `/no_think` (rapide) | ✅ `/think` (raisonné) |
| Tools | ✅ | ✅ |
| Vision | ✅ | ❌ |
| **Alternative rapide** | `gpt-oss:20b-cloud` | `mistral-large-3:675b-cloud` |
| **Alternative économique** | `gpt-oss:120b-cloud` | `gpt-oss:120b-cloud` (thinking) |
| **Alternative monstre** | `kimi-k2.5:1t-cloud` | `kimi-k2.5:1t-cloud` |

### 🔁 Alternatives détaillées

| Alternative | Pour quoi | Pourquoi |
|---|---|---|
| **`gpt-oss:20b-cloud`** | Draft rapide/économique | 5.1B actifs, thinking mode, très rapide, bon rapport qualité/coût |
| **`mistral-large-3:675b-cloud`** | Refine multilingue | 41B actifs, Mistral = entreprise **française** → excellent en français, vision, tools |
| **`gpt-oss:120b-cloud`** | Les deux passes si budget limité | Un seul modèle, thinking medium pour refine, thinking low pour draft |
| **`kimi-k2.5:1t-cloud`** | Long contexte extrême | 1T params, 32B actifs, agents, vision — overkill mais redoutable |
| **`minimax-m2.5-cloud`** | Si focus code/technique | SWE-bench 80.2%, bon en instruction-following |

### ❌ Pourquoi pas les autres ?

| Modèle | Raison |
|---|---|
| `qwen3:30b-a3b` (local) | Pas de GPU → inutilisable |
| `translategemma:12b` (local) | Pas de GPU → inutilisable |
| `gemma3/4` | Prose créative OK, maismoins fort en traduction multilingue que Qwen/DeepSeek |
| `minimax-m2` | Orienté code, pas traduction |
| `glm-5.1` | Orienté agentic/code, documentation multilingue limitée |
| `cogito-2.1` | Fork DeepSeek V2 → préférer V3.2 plus récent |
| `nemotron-3` | Modèles NVIDIA orientés généraliste/code |
| `ministral-3` | Trop petits pour de la traduction de qualité |
| `devstral` | Orienté code uniquement |

---

## 3. Tarification Ollama Cloud

| Plan | Prix | Utilisation | Cloud models simultanés |
|---|---|---|---|
| **Free** | $0/mois | Usage léger (évaluation, chat ponctuel) | 1 |
| **Pro** | $20/mois | Usage quotidien | 3 |
| **Max** | $100/mois | Usage intensif (agents, longues sessions) | 10 |

L'utilisation est mesurée en **temps GPU** (pas en tokens). Les sessions se renouvellent toutes les 5h, les limites hebdomadaires toutes les 7h.

Pour Kinoscribe avec un usage régulier (traductions de films), le plan **Pro** ($20/mois) devrait être suffisant.

---

## 4. Commandes de démarrage

```bash
# Se connecter à Ollama Cloud
ollama signin

# Pull les modèles recommandés
ollama pull qwen3.5:397b-cloud
ollama pull deepseek-v3.2:671b-cloud

# Tester une traduction rapide (draft)
ollama run qwen3.5:397b-cloud

# Tester un affinage (refine avec thinking)
ollama run deepseek-v3.2:671b-cloud
```