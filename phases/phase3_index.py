"""Phase 3: MOC (Map of Content) index generation.

Creates or updates INDEX.md files in each vault folder, with alphabetized
links and frontmatter summaries pulled from existing metadata.
"""
import logging
from pathlib import Path

import config
from phases.phase1_scope import get_scope
from phases.phase2_link import _read_file_with_fallback, _split_frontmatter
from services.state_manager import StateManager

logger = logging.getLogger("curator.phase3")


def _make_index_entry(path: Path, vault: Path) -> str:
    """Generate a markdown index entry for a file.

    Format: "- **[[filename]]** — summary from frontmatter"
    """
    rel = path.relative_to(vault)
    stem = str(Path(rel).with_suffix(""))
    link = f"[[{stem}]]"

    # Try to get summary from frontmatter
    try:
        text = _read_file_with_fallback(path)
        fm, _ = _split_frontmatter(text)
        summary = fm.get("summary", "")
        if summary:
            return f"- **{link}** — {summary}"
    except Exception:
        pass
    return f"- {link}"


def _get_folder_name(vault: Path, folder: Path) -> str:
    """Get display name for a folder."""
    try:
        rel = folder.relative_to(vault)
    except ValueError:
        return folder.name
    return str(rel) if str(rel) != "." else "Root"


def _build_index_content(vault: Path, folder: Path, files: list[Path]) -> str:
    """Build INDEX.md content for a folder."""
    folder_name = _get_folder_name(vault, folder)
    lines = [f"# Índice — {folder_name}", "", f"_{len(files)} arquivos_", ""]
    for f in sorted(files):
        lines.append(_make_index_entry(f, vault))
    lines.append("")
    return "\n".join(lines)


def _generate_folder_index(vault: Path, folder: Path) -> tuple[bool, int]:
    """Generate INDEX.md for a single folder. Returns (created_or_updated, file_count)."""
    md_files = [f for f in folder.glob("*.md") if f.name != "INDEX.md" and not config._is_globally_excluded(f, vault)]
    if not md_files:
        return False, 0

    content = _build_index_content(vault, folder, md_files)
    index_path = folder / "INDEX.md"
    existing = ""
    if index_path.exists():
        try:
            existing = index_path.read_text(encoding="utf-8")
        except Exception:
            pass

    if existing == content:
        return False, len(md_files)

    index_path.write_text(content, encoding="utf-8")
    return True, len(md_files)


def _get_subfolders(vault: Path) -> list[Path]:
    """Get all subfolders containing markdown files, sorted by depth then name."""
    folders = set()
    for md in vault.rglob("*.md"):
        if config._is_globally_excluded(md, vault):
            continue
        parent = md.parent
        try:
            parent.relative_to(vault)
        except ValueError:
            continue
        folders.add(parent)
    return sorted(folders, key=lambda p: (len(p.relative_to(vault).parts), str(p)))


def _generate_root_index(vault: Path) -> tuple[bool, int]:
    """Generate a root-level INDEX.md linking to subfolder INDEX.md files."""
    subfolders = _get_subfolders(vault)
    root_files = []
    for sf in subfolders:
        idx = sf / "INDEX.md"
        if idx.exists():
            try:
                rel = sf.relative_to(vault)
            except ValueError:
                continue
            link = f"[[{str(rel)}/INDEX|{str(rel)}]]"
            md_count = len([f for f in sf.glob("*.md") if f.name != "INDEX.md" and not config._is_globally_excluded(f, vault)])
            root_files.append(f"- **{link}** — {md_count} arquivos")

    content = "# Índice Geral\n\n" + "\n".join(sorted(root_files)) + "\n"
    index_path = vault / "INDEX.md"
    existing = ""
    if index_path.exists():
        try:
            existing = index_path.read_text(encoding="utf-8")
        except Exception:
            pass

    if existing == content:
        return False, len(root_files)

    index_path.write_text(content, encoding="utf-8")
    return True, len(root_files)


def run_phase3(vault: Path) -> dict:
    """Run Phase 3: MOC index generation."""
    created = 0
    updated = 0
    errors = 0

    subfolders = _get_subfolders(vault)
    for folder in subfolders:
        try:
            changed, count = _generate_folder_index(vault, folder)
            if changed:
                created += 1
            else:
                updated += 1
        except Exception as e:
            logger.error("Failed to generate index for %s: %s", folder, e)
            errors += 1

    try:
        changed, _ = _generate_root_index(vault)
        if changed:
            created += 1
        else:
            updated += 1
    except Exception as e:
        logger.error("Failed to generate root index: %s", e)
        errors += 1

    logger.info("Phase 3 complete: created=%d, updated=%d, errors=%d", created, updated, errors)
    return {"created": created, "updated": updated, "errors": errors}