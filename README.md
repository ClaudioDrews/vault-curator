# Vault Curator v3

Automated enrichment, semantic linking, and index generation for Obsidian vaults.

## What it does

1. **Phase 1 — Enrichment**: Adds `summary` and `tags` to Markdown frontmatter via LLM (OpenRouter). Existing frontmatter is preserved.
2. **Phase 2 — Semantic Linking**: Embeds all files (Qwen3-Embedding-8B, 4096d), computes cosine similarity matrix, and adds `## Notas Relacionadas` sections with wikilinks to top-5 similar files.
3. **Phase 3 — Index Generation**: Creates or updates `INDEX.md` files in each vault folder with alphabetized links and frontmatter summaries.

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Set required env var
export OPENROUTER_API_KEY="***

# Point to your vault
export VAULT_PATH="/path/to/your/obsidian/vault"

# Run all phases
python vault_curator_v3.py all

# Or run individually
python vault_curator_v3.py phase1 --limit 10   # pilot mode
python vault_curator_v3.py phase2
python vault_curator_v3.py phase3

# Check progress
python vault_curator_v3.py status
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VAULT_PATH` | `.` | Path to Obsidian vault root |
| `OPENROUTER_API_KEY` | (required) | OpenRouter API key |
| `CURATOR_ENRICHMENT_MODEL` | `deepseek/deepseek-v4-flash` | Model for frontmatter enrichment |
| `CURATOR_EMBEDDING_MODEL` | `qwen/qwen3-embedding-8b` | Model for embeddings |
| `CURATOR_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## Excluded folders

By default, these vault folders are skipped:
- `fabric/` — agent-owned, frontmatter must not be overwritten
- `.trash/` — deleted files
- `.obsidian/` — Obsidian config

Edit `GLOBAL_EXCLUDE_DIRS` in `config.py` to customize.

## State

Progress is tracked in `.curator_state_v3.json` and `.curator_embeddings_v3.jsonl` at the vault root. Each file is processed once per phase — re-running is safe and skips already-processed files.

## Requirements

- Python 3.11+
- OpenRouter API key (with access to embedding and chat models)
- ~200 MB disk for embedding cache (2,400 files × 4096d)

## License

MIT