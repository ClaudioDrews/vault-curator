"""Phase 1: LLM-powered frontmatter enrichment.

Reads each Markdown file, extracts a sample (head+tail), and calls OpenRouter
(model: deepseek/deepseek-v4-flash) to generate a summary and tags. Existing
frontmatter fields (title, date, type, existing summary, existing tags) are
preserved — only missing fields are added.
"""
import asyncio
import json
import logging
import re
import sys
import traceback
from pathlib import Path

import config
from phases.phase1_scope import get_scope, get_new_files
from services.openrouter import OpenRouterClient, OpenRouterError
from services.state_manager import StateManager

logger = logging.getLogger("curator.phase1")


# ── File reading ────────────────────────────────────────────────────────────

def _read_file_with_fallback(path: Path) -> str:
    """Read file with encoding fallback: utf-8 → latin-1."""
    for enc in ("utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Cannot read {path} with any encoding")


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from Markdown text.

    Returns (frontmatter_dict, body). If no frontmatter, returns ({}, text).
    """
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_text = parts[1].strip()
    body = parts[2].strip()
    frontmatter = {}
    for line in fm_text.split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val.startswith("[") and val.endswith("]"):
                val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",")]
            frontmatter[key] = val
    return frontmatter, body


def _extract_summary(text: str) -> str:
    """Extract a summary from file content using head+tail sampling."""
    fm, body = _split_frontmatter(text)
    if not body:
        return ""
    head = body[:config.PHASE1_HEAD_CHARS]
    tail = body[-config.PHASE1_TAIL_CHARS:] if len(body) > config.PHASE1_HEAD_CHARS else ""
    if tail:
        return f"{head}\n\n...\n\n{tail}"
    return head


# ── LLM interaction ─────────────────────────────────────────────────────────

_ENRICHMENT_SYSTEM = """You are a metadata curator for an Obsidian vault.

Given a Markdown file's content (truncated), produce a JSON object:
  {"summary": "1-2 sentence description in Portuguese", "tags": ["tag1", "tag2", ...]}

Rules:
- The summary MUST be in Portuguese (PT-BR).
- Tags should be lowercase, hyphenated, 1-3 words max.
- Include 3-7 tags covering: topic, format/type, project/scope.
- Return ONLY the JSON object, nothing else.
- If the content is unclear, use your best judgment."""


def _build_enrichment_prompt(path: Path, body: str) -> tuple[str, str]:
    """Build user prompt for frontmatter enrichment."""
    filename = path.stem
    sample = _extract_summary(body)
    return filename, (
        f"File: {filename}\n\n"
        f"Content (sample):\n{sample}\n\n"
        f"Generate summary and tags JSON."
    )


def _parse_enrichment_response(text: str) -> dict:
    """Parse LLM JSON response robustly."""
    if not text:
        return {}
    text = text.strip()
    # Try direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting JSON from markdown code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Try extracting first JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _merge_frontmatter(path: Path, existing_fm: dict, enrichment: dict) -> str:
    """Merge enrichment into file, preserving existing frontmatter."""
    text = _read_file_with_fallback(path)
    fm, body = _split_frontmatter(text)

    # Only add fields that don't exist
    updated = False
    if "summary" in enrichment and not fm.get("summary"):
        fm["summary"] = enrichment["summary"].replace('"', "'").replace("\n", " ")
        updated = True
    if "tags" in enrichment and not fm.get("tags"):
        fm["tags"] = enrichment["tags"]
        updated = True

    if not updated:
        return text

    # Rebuild frontmatter
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            items = ", ".join(f'"{x}"' for x in v)
            lines.append(f"{k}: [{items}]")
        else:
            lines.append(f"{k}: \"{v}\"")
    lines.append("---")
    lines.append("")
    lines.append(body)
    return "\n".join(lines)


async def _enrich_file(client: OpenRouterClient, path: Path, vault: Path) -> dict:
    """Enrich a single file."""
    try:
        text = _read_file_with_fallback(path)
        fm, body = _split_frontmatter(text)
        filename, prompt = _build_enrichment_prompt(path, text)
        response = await client.chat(
            messages=[
                {"role": "system", "content": _ENRICHMENT_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=512,
        )
        enrichment = _parse_enrichment_response(response)
        if not enrichment:
            return {"success": False, "reason": "empty_response"}
        new_text = _merge_frontmatter(path, fm, enrichment)
        path.write_text(new_text, encoding="utf-8")
        return {"success": True}
    except OpenRouterError as e:
        return {"success": False, "reason": str(e)[:100]}
    except Exception as e:
        logger.error("Unexpected error enriching %s: %s", path, e)
        traceback.print_exc(file=sys.stderr)
        return {"success": False, "reason": str(e)[:100]}


async def _enrich_batch(client: OpenRouterClient, batch: list[Path], vault: Path, sem: asyncio.Semaphore) -> list[dict]:
    """Process a batch of files concurrently with semaphore."""
    async def _limited(path):
        async with sem:
            return await _enrich_file(client, path, vault)
    return await asyncio.gather(*[_limited(p) for p in batch])


async def run_phase1(vault: Path, limit: int = 0) -> dict:
    """Run Phase 1: frontmatter enrichment."""
    state = StateManager()
    files = get_scope(vault)
    total = len(files)
    logger.info("Phase 1: %d markdown files found in %s", total, vault)

    # Filter to new files only
    files = get_new_files(files, vault, state)
    if limit and limit < len(files):
        files = files[:limit]
    to_process = len(files)
    if to_process == 0:
        logger.info("Phase 1: no new files to process")
        return {"total": total, "success": 0, "failed": 0, "skipped": total, "newly_done": 0}

    logger.info("Phase 1: %d files to process", to_process)
    client = OpenRouterClient()
    sem = asyncio.Semaphore(config.MAX_CONCURRENT_REQUESTS)

    success = 0
    failed = 0
    newly_done = 0

    for i in range(0, to_process, config.MAX_CONCURRENT_REQUESTS):
        batch = files[i : i + config.MAX_CONCURRENT_REQUESTS]
        results = await _enrich_batch(client, batch, vault, sem)
        for path, res in zip(batch, results):
            rel = str(path.relative_to(vault))
            if res["success"]:
                state.mark_phase1_done(rel)
                newly_done += 1
                success += 1
            else:
                failed += 1
                state.mark_phase1_failed(rel, res.get("reason", "unknown"))
        state.save()

    total_skipped = total - to_process
    logger.info("Phase 1 complete: success=%d, failed=%d, skipped=%d", success, failed, total_skipped)
    return {
        "total": total,
        "success": success,
        "failed": failed,
        "skipped": total_skipped,
        "newly_done": newly_done,
    }