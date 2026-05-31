# Vault Curator v3

> Transform large Obsidian vaults into self-organizing knowledge systems using LLM metadata enrichment, embedding-based semantic linking, and automatic MOC generation.

## What it does

```
                   ┌──────────────────┐
                   │   Your Vault     │
                   │   (markdown)     │
                   └────────┬─────────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
        Phase 1         Phase 2        Phase 3
     Enrichment    Semantic Link    MOC Indexes
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │ LLM adds │   │ Embed ➔  │   │ INDEX.md │
    │ summary  │   │ cosine ➔ │   │ per       │
    │ + tags   │   │ Notas    │   │ folder +  │
    │ to fm    │   │ Relacion.│   │ root      │
    └──────────┘   └──────────┘   └──────────┘
```

1. **Phase 1 — Enrichment**: Reads each file, extracts a content sample, and calls an LLM (OpenRouter) to generate a `summary` and `tags`. Only missing frontmatter fields are added — existing metadata is **never** overwritten.

2. **Phase 2 — Semantic Linking**: Embeds all files (Qwen3-Embedding-8B, 4096d), computes a cosine similarity matrix, and adds a `## Notas Relacionadas` section with wikilinks to the top-5 most similar files. Files below the similarity threshold are skipped.

3. **Phase 3 — Index Generation**: Creates or updates `INDEX.md` in every vault folder (and at the root), with alphabetized links and frontmatter summaries.

### Before / After

**Before Phase 1:**
```markdown
---
title: My Research Note
date: 2026-05-15
---

## Introduction
Long-form research content here...
```

**After Phase 1:**
```markdown
---
title: My Research Note
date: 2026-05-15
summary: Explora a relação entre arquitetura de memória e agentes autônomos
tags: ["memoria", "agentes-ia", "arquitetura", "qdrant", "pesquisa"]
---

## Introduction
Long-form research content here...
```

**After Phase 2 (appended at end of file):**
```markdown
## Notas Relacionadas

- [[concepts/memory-architecture]]
- [[concepts/llm-wiki]]
- [[raw/NousResearch/hermes-agent-roadmap]]
```

**After Phase 3 (generated INDEX.md):**
```markdown
# Índice — concepts

_165 arquivos_

- **[[context-enhancer]]** — Sistema de injeção automática de contexto via pre_llm_call
- **[[memory-architecture]]** — Visão geral das 4 camadas de memória do Hermes Agent
- **[[qdrant-management]]** — Gestão de coleções Qdrant com named vectors
...
```

## Quick Start

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set required environment variables
export OPENROUTER_API_KEY="<your-openrouter-api-key>"
export VAULT_PATH="/path/to/your/obsidian/vault"

# Run a pilot first (test on 10 files, review results)
python vault_curator_v3.py phase1 --limit 10

# If satisfied, run all phases
python vault_curator_v3.py all

# Check progress
python vault_curator_v3.py status
```

## Trust Model

### What the system MODIFIES

| Phase | Modifies | Mechanism |
|-------|----------|-----------|
| Phase 1 | Frontmatter — adds `summary` and `tags` | Only when field is **missing**. Never overwrites existing. |
| Phase 2 | Appends `## Notas Relacionadas` section | Replaces existing section if present; leaves rest of file intact. |
| Phase 3 | Creates/updates `INDEX.md` files | Generated from frontmatter summaries. Safe to delete and regenerate. |

### What the system NEVER modifies

- File content (body text)
- Existing frontmatter fields (`title`, `date`, `type`, existing `summary`, existing `tags`)
- Files in excluded folders (`fabric/`, `.trash/`, `.obsidian/` by default)
- Non-markdown files

### Audit trail

Every execution logs to stdout with timestamps. Phase 1 reports per-file success/failure. Phase 2 reports files modified. Phase 3 reports indexes created/updated. State files (`.curator_state_v3.json`, `.curator_embeddings_v3.jsonl`) track exactly which files have been processed.

### Rollback

The system is **incremental and additive** — it only adds metadata. To undo:
- Delete `.curator_state_v3.json` and `.curator_embeddings_v3.jsonl` to reset state
- Use `git diff` on your vault to inspect changes
- Use `git checkout` to revert individual files

## Safety

> ⚠️ **Recommended before first execution:**
> - Backup your vault (or use Git)
> - Test Phase 1 with `--limit 10` and review the generated summaries
> - Review the generated `## Notas Relacionadas` links for quality before large-scale Phase 2
> - Phase 1 uses an LLM — summaries are usually good but can occasionally be generic or misaligned

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VAULT_PATH` | `.` | Path to Obsidian vault root |
| `OPENROUTER_API_KEY` | (required) | OpenRouter API key |
| `CURATOR_ENRICHMENT_MODEL` | `deepseek/deepseek-v4-flash` | Model for frontmatter enrichment |
| `CURATOR_EMBEDDING_MODEL` | `qwen/qwen3-embedding-8b` | Model for embeddings |
| `CURATOR_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## Excluded folders

By default, these vault folders are skipped by all phases:
- `fabric/` — agent-owned, frontmatter must not be overwritten
- `.trash/` — deleted files
- `.obsidian/` — Obsidian config

Edit `GLOBAL_EXCLUDE_DIRS` in `config.py` to customize.

## Tuning Semantic Linking

| Parameter | Default | Effect |
|---|---|---|
| `LINK_THRESHOLD` | 0.55 | Minimum cosine similarity for a link to be created. Lower = more links (higher recall, more noise). Higher = fewer links (higher precision, may miss valid connections). |
| `MAX_LINKS_PER_FILE` | 5 | Maximum links added to `## Notas Relacionadas`. Prevents link spam. |

**Why 4096d?** Qwen3-Embedding-8B outputs 4096-dimensional embeddings natively. We use the full dimensionality — no Matryoshka truncation.

**Why threshold 0.55?** Empirically calibrated: 0.55 captures meaningful conceptual overlap without flooding pages with marginal links. Adjust based on your vault density.

**Embedding model:** Configurable via `CURATOR_EMBEDDING_MODEL` env var. Any OpenRouter embedding model works.

## State

Progress is tracked in `.curator_state_v3.json` and `.curator_embeddings_v3.jsonl` at the vault root. Each file is processed once per phase — re-running is safe and skips already-processed files.

To reset state and re-process everything:
```bash
python vault_curator_v3.py reset
```

## Performance & Cost

| Phase | Bottleneck | ~1,000 files |
|-------|-----------|-------------|
| Phase 1 | LLM API (deepseek-v4-flash) | ~10-15 min, ~$0.05-0.10 USD |
| Phase 2 | Embedding API + numpy | ~5-10 min (cached after first run), ~$0.02 USD |
| Phase 3 | Local file I/O | ~1 min |

**Embedding cache:** Phase 2 stores embeddings in `.curator_embeddings_v3.jsonl` (~200 MB for 2,400 files). Subsequent runs are near-instant for already-embedded files.

**Concurrency:** `MAX_CONCURRENT_REQUESTS = 5` in `config.py`. Adjust based on your OpenRouter tier.

**Tested on:** Linux (Python 3.11+), macOS should work. Windows untested.

## Requirements

- Python 3.11+
- OpenRouter API key (with access to embedding and chat models)
- ~200 MB disk for embedding cache (2,400 files × 4096d)
- `httpx` for async HTTP, `numpy` for similarity matrix

## License

MIT