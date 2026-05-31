"""Vault Curator v3 — Configuration.

All paths and credentials come from environment variables.
Set VAULT_PATH to point to your Obsidian vault root.
"""

import os
from pathlib import Path

# --- Paths ---
VAULT_PATH = Path(os.environ.get("VAULT_PATH", "."))
STATE_FILE = VAULT_PATH / ".curator_state_v3.json"
EMBEDDINGS_FILE = VAULT_PATH / ".curator_embeddings_v3.jsonl"

# --- OpenRouter ---
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
ENRICHMENT_MODEL = os.environ.get("CURATOR_ENRICHMENT_MODEL", "deepseek/deepseek-v4-flash")
EMBEDDING_MODEL = os.environ.get("CURATOR_EMBEDDING_MODEL", "qwen/qwen3-embedding-8b")
EMBEDDING_DIMS = 4096

# --- HTTP ---
HTTP_TIMEOUT = 60
MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]  # seconds

# --- Concurrency ---
MAX_CONCURRENT_REQUESTS = 5
BATCH_DELAY = 0

# --- Linkage ---
LINK_THRESHOLD = 0.55
MAX_LINKS_PER_FILE = 5

# --- Content Sampling ---
PHASE1_HEAD_CHARS = 1500
PHASE1_TAIL_CHARS = 500

# --- Folders excluded from ALL phases (global) ---
GLOBAL_EXCLUDE_DIRS = {
    "fabric",
    ".trash",
    ".obsidian",
}


def _is_globally_excluded(file_path: Path, vault: Path) -> bool:
    """Return True if *file_path* lives inside a globally excluded directory."""
    try:
        rel = file_path.relative_to(vault)
    except ValueError:
        return False
    return rel.parts[0] in GLOBAL_EXCLUDE_DIRS if rel.parts else False


# --- Logging ---
LOG_LEVEL = os.environ.get("CURATOR_LOG_LEVEL", "INFO")