"""Phase 1 (Scope): Enumerate markdown files in vault, apply global exclusions."""
import fnmatch
import logging
from pathlib import Path

import config

logger = logging.getLogger("curator.phase1_scope")


def _should_process(path: Path, vault: Path) -> bool:
    """Check if a markdown file should be processed."""
    if path.suffix != ".md":
        return False
    if config._is_globally_excluded(path, vault):
        return False
    return True


def get_scope(vault: Path) -> list[Path]:
    """Return sorted list of Markdown files to process, excluding global exclusions."""
    all_md = sorted(vault.rglob("*.md"))
    files = [f for f in all_md if _should_process(f, vault)]
    logger.info("Scope: %d Markdown files found (total %d in vault)", len(files), len(all_md))
    return files


def get_paths_to_process(vault: Path, file_list: list[Path]) -> list[Path]:
    """Filter a list of file paths, excluding global exclusions and non-.md files."""
    return [f for f in file_list if _should_process(f, vault)]


def get_new_files(files: list[Path], vault: Path, state_manager) -> list[Path]:
    """Return files not yet processed in any phase, sorted by modification time (newest first)."""
    new_files = []
    for f in files:
        rel = str(f.relative_to(vault))
        done_phase1 = state_manager.is_phase1_done(rel)
        done_phase2 = state_manager.is_phase2_done(rel)
        if not done_phase1 or not done_phase2:
            new_files.append(f)
    new_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return new_files


def apply_protection_rules(files: list[Path], vault: Path) -> tuple[list[Path], list[str]]:
    """Apply protection rules to file list.

    Returns (processed_files, warnings).
    Warnings are generated for files that match protection patterns.
    """
    processed = []
    warnings = []
    for f in files:
        rel = str(f.relative_to(vault))
        folder = rel.split("/")[0]
        if folder in config.GLOBAL_EXCLUDE_DIRS:
            warnings.append(f"Skipped (protected folder): {rel}")
            continue
        processed.append(f)
    return processed, warnings


def group_by_folder(files: list[Path], vault: Path) -> dict[str, list[Path]]:
    """Group files by their root folder for phase3 MOC generation."""
    groups = {}
    for f in files:
        try:
            rel = f.relative_to(vault)
        except ValueError:
            continue
        root = rel.parts[0] if rel.parts else "."
        groups.setdefault(root, []).append(f)
    return groups


def exclude_patterns(files: list[Path], vault: Path, patterns: list[str]) -> list[Path]:
    """Exclude files matching any fnmatch pattern."""
    result = []
    for f in files:
        try:
            rel = str(f.relative_to(vault))
        except ValueError:
            continue
        if any(fnmatch.fnmatch(rel, p) for p in patterns):
            continue
        result.append(f)
    return result