"""Phase 2: Semantic linking via embedding cosine similarity.

Embeds all files via OpenRouter (Qwen3-Embedding-8B, 4096d), computes cosine
similarity matrix, and adds "Notas Relacionadas" sections with wikilinks to
the top-5 most similar files per document.
"""
import asyncio
import json
import logging
import re
import sys
import traceback
from pathlib import Path

import numpy as np

import config
from phases.phase1_scope import get_scope
from services.openrouter import OpenRouterClient, OpenRouterError
from services.state_manager import StateManager

logger = logging.getLogger("curator.phase2")


def _read_file_with_fallback(path: Path) -> str:
    for enc in ("utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Cannot read {path}")


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_text = parts[1].strip()
    body = parts[2].strip()
    fm = {}
    for line in fm_text.split("\n"):
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, body


def _extract_summary(text: str) -> str:
    fm, body = _split_frontmatter(text)
    if not body:
        return ""
    head = body[:config.PHASE1_HEAD_CHARS]
    tail = body[-config.PHASE1_TAIL_CHARS:] if len(body) > config.PHASE1_HEAD_CHARS else ""
    return f"{head}\n\n...\n\n{tail}" if tail else head


def _wikilink(path: Path, vault: Path) -> str:
    """Generate Obsidian wikilink from path."""
    rel = str(path.relative_to(vault))
    stem = str(Path(rel).with_suffix(""))
    return f"[[{stem}]]"


def _add_related_section(path: Path, vault: Path, linked: list[Path]) -> bool:
    """Add or update "Notas Relacionadas" section."""
    text = _read_file_with_fallback(path)
    section_header = "## Notas Relacionadas"

    # Build new section
    lines = [section_header, ""]
    for linked_path in linked:
        link = _wikilink(linked_path, vault)
        lines.append(f"- {link}")

    new_section = "\n".join(lines)

    # Replace existing section (including trailing newline before next ##) or append
    escaped = re.escape(section_header)
    pattern = rf"{escaped}\n(?:- .*\n?)*"
    if re.search(pattern, text):
        new_text = re.sub(pattern, new_section + "\n", text)
    else:
        new_text = text.rstrip() + "\n\n" + new_section + "\n"

    path.write_text(new_text, encoding="utf-8")
    return True


async def _embed_batch(client: OpenRouterClient, texts: list[str], batch_size: int = 10) -> list[list[float]]:
    """Embed texts in batches of batch_size (OpenRouter max is ~10 per call)."""
    all_vectors = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        vectors = await client.embed_batch(batch)
        all_vectors.extend(vectors)
        if i > 0 and i % 50 == 0:
            logger.info("Phase 2 embeddings: %d/%d batches processed", i // batch_size, (len(texts) + batch_size - 1) // batch_size)
    return all_vectors


async def run_phase2(vault: Path) -> dict:
    """Run Phase 2: semantic linking."""
    state = StateManager()
    all_files = get_scope(vault)
    total = len(all_files)
    logger.info("Phase 2: %d markdown files found", total)

    # Filter to files not yet processed
    files = [f for f in all_files if not state.is_phase2_done(str(f.relative_to(vault)))]
    if not files:
        logger.info("Phase 2: all files already processed")
        return {"total": total, "embedded": 0, "modified": 0, "unchanged": 0, "errors": 0}

    # Get or compute embeddings
    state_manager = StateManager()
    embeddings = state_manager.load_all_embeddings()
    to_embed = []
    for f in files:
        rel = str(f.relative_to(vault))
        if rel not in embeddings:
            to_embed.append(f)

    if to_embed:
        logger.info("Phase 2: %d files need embedding", len(to_embed))
        client = OpenRouterClient()
        texts = []
        for f in to_embed:
            text = _read_file_with_fallback(f)
            texts.append(_extract_summary(text))
        vectors = await _embed_batch(client, texts)
        for f, v in zip(to_embed, vectors):
            rel = str(f.relative_to(vault))
            state_manager.save_embedding(rel, v)
            embeddings[rel] = v

    # Reload full embeddings
    embeddings = state_manager.load_all_embeddings()
    logger.info("Phase 2: loaded %d cached embeddings", len(embeddings))

    # Build similarity matrix for all files that have embeddings
    file_list = [f for f in all_files if str(f.relative_to(vault)) in embeddings]
    n = len(file_list)
    matrix = np.zeros((n, config.EMBEDDING_DIMS), dtype=np.float32)
    for i, f in enumerate(file_list):
        rel = str(f.relative_to(vault))
        matrix[i] = np.array(embeddings[rel], dtype=np.float32)

    # Normalize
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    matrix = matrix / norms

    # Cosine similarity
    sim = matrix @ matrix.T
    np.fill_diagonal(sim, 0)

    logger.info("Phase 2: computed %d embeddings", n)

    # For each file, find top-k similar
    modified = 0
    unchanged = 0
    errors = 0
    for i, f in enumerate(file_list):
        rel = str(f.relative_to(vault))
        if state.is_phase2_done(rel):
            unchanged += 1
            continue
        top_k = min(config.MAX_LINKS_PER_FILE, n - 1)
        indices = np.argpartition(-sim[i], top_k)[:top_k]
        top_indices = indices[np.argsort(-sim[i][indices])]
        top_files = [file_list[j] for j in top_indices if sim[i][j] >= config.LINK_THRESHOLD]
        if not top_files:
            state.mark_phase2_done(rel)
            state.save()
            unchanged += 1
            continue
        try:
            _add_related_section(f, vault, top_files)
            state.mark_phase2_done(rel)
            state.save()
            modified += 1
        except Exception as e:
            logger.error("Failed to update %s: %s", rel, e)
            errors += 1

    logger.info("Phase 2 complete: modified=%d, unchanged=%d, errors=%d", modified, unchanged, errors)
    return {
        "total": total,
        "embedded": n,
        "modified": modified,
        "unchanged": unchanged,
        "errors": errors,
    }