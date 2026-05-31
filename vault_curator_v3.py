#!/usr/bin/env python3
"""Vault Curator v3 — CLI entry point.

Usage:
    python vault_curator_v3.py phase1 [--limit N] [--path /vault]
    python vault_curator_v3.py phase2 [--path /vault]
    python vault_curator_v3.py phase3 [--path /vault]
    python vault_curator_v3.py all [--path /vault] [--limit N]
    python vault_curator_v3.py status [--path /vault]
    python vault_curator_v3.py reset

Environment:
    OPENROUTER_API_KEY    Required for phases 1 and 2.
    VAULT_PATH            Override vault location (default: current directory).
    CURATOR_LOG_LEVEL     DEBUG|INFO|WARNING|ERROR (default: INFO).
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

import config
from phases.phase1_enrich import run_phase1
from phases.phase2_link import run_phase2
from phases.phase3_index import run_phase3
from services.state_manager import StateManager


def _setup_logging():
    level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_phase1(args):
    vault = Path(args.path) if args.path else config.VAULT_PATH
    if not vault.exists():
        print(f"ERROR: Vault path does not exist: {vault}", file=sys.stderr)
        sys.exit(1)
    stats = asyncio.run(run_phase1(vault, limit=args.limit))
    print(json.dumps(stats, indent=2))


def cmd_phase2(args):
    vault = Path(args.path) if args.path else config.VAULT_PATH
    if not vault.exists():
        print(f"ERROR: Vault path does not exist: {vault}", file=sys.stderr)
        sys.exit(1)
    stats = asyncio.run(run_phase2(vault))
    print(json.dumps(stats, indent=2))


def cmd_phase3(args):
    vault = Path(args.path) if args.path else config.VAULT_PATH
    if not vault.exists():
        print(f"ERROR: Vault path does not exist: {vault}", file=sys.stderr)
        sys.exit(1)
    stats = run_phase3(vault)
    state = StateManager(config.STATE_FILE if args.path is None else Path(args.path) / ".curator_state_v3.json")
    state.state["phase3_done"] = True
    state.save()
    print(json.dumps(stats, indent=2))


def cmd_all(args):
    vault = Path(args.path) if args.path else config.VAULT_PATH
    if not vault.exists():
        print(f"ERROR: Vault path does not exist: {vault}", file=sys.stderr)
        sys.exit(1)

    print("=== Phase 1: Enrichment ===")
    stats1 = asyncio.run(run_phase1(vault, limit=args.limit))
    print(json.dumps(stats1, indent=2))

    print("\n=== Phase 2: Semantic Linking ===")
    stats2 = asyncio.run(run_phase2(vault))
    print(json.dumps(stats2, indent=2))

    print("\n=== Phase 3: Index Generation ===")
    stats3 = run_phase3(vault)
    state = StateManager(config.STATE_FILE if args.path is None else Path(args.path) / ".curator_state_v3.json")
    state.state["phase3_done"] = True
    state.save()
    print(json.dumps(stats3, indent=2))


def cmd_status(args):
    vault = Path(args.path) if args.path else config.VAULT_PATH
    state = StateManager(config.STATE_FILE if args.path is None else Path(args.path) / ".curator_state_v3.json")
    md_count = len(list(vault.rglob("*.md")))
    p1_done = len(state.state.get("phase1_done", []))
    p1_failed = len(state.state.get("phase1_failed", []))
    p2_done = len(state.state.get("phase2_done", []))
    info = {
        "vault_path": str(vault),
        "total_md_files": md_count,
        "phase1_done": p1_done,
        "phase1_failed": p1_failed,
        "phase2_done": p2_done,
        "percent_phase1": round(p1_done / md_count * 100, 1) if md_count else 0,
    }
    print(json.dumps(info, indent=2))


def cmd_reset(args):
    state_file = config.STATE_FILE
    emb_file = config.EMBEDDINGS_FILE
    removed = []
    for f in [state_file, emb_file]:
        if f.exists():
            f.unlink()
            removed.append(str(f))
    if removed:
        print(f"Removed: {', '.join(removed)}")
    else:
        print("No state files to remove.")


def main():
    _setup_logging()
    parser = argparse.ArgumentParser(description="Vault Curator v3")
    sub = parser.add_subparsers(dest="command", required=True)

    # phase1
    p1 = sub.add_parser("phase1", help="Enrich frontmatter via OpenRouter")
    p1.add_argument("--path", help="Vault path")
    p1.add_argument("--limit", type=int, help="Max files to process")
    p1.set_defaults(func=cmd_phase1)

    # phase2
    p2 = sub.add_parser("phase2", help="Semantic linking via embeddings")
    p2.add_argument("--path", help="Vault path")
    p2.set_defaults(func=cmd_phase2)

    # phase3
    p3 = sub.add_parser("phase3", help="Generate MOC indexes")
    p3.add_argument("--path", help="Vault path")
    p3.set_defaults(func=cmd_phase3)

    # all
    pa = sub.add_parser("all", help="Run enrichment, semantic linking, and MOC indexes")
    pa.add_argument("--path", help="Vault path")
    pa.add_argument("--limit", type=int, help="Max files for phase1")
    pa.set_defaults(func=cmd_all)

    # status
    ps = sub.add_parser("status", help="Show curation progress")
    ps.add_argument("--path", help="Vault path")
    ps.set_defaults(func=cmd_status)

    # reset
    pr = sub.add_parser("reset", help="Remove state files (start fresh)")
    pr.set_defaults(func=cmd_reset)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()