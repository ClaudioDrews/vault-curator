# Changelog

All notable changes to Vault Curator are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- `reset` now respects `--path` argument (previously always used `VAULT_PATH` or cwd)
- `status` now validates vault existence before scanning (previously raised `FileNotFoundError`)
- Early validation of `OPENROUTER_API_KEY` for `phase1`, `phase2`, and `all` commands (previously failed mid-execution with traceback)

### Added
- Trust Model section in README — what the system modifies, what it never touches, audit trail, rollback
- Safety section with backup recommendation and `--limit` guidance
- Tuning Semantic Linking section explaining threshold, dimensionality, and calibration
- Performance & Cost estimates per 1,000 files
- Pipeline diagram (ASCII) and before/after examples in README
- `pyyaml>=6.0` to `requirements.txt` (was an undeclared implicit dependency)

### Changed
- Rewrote README from single compressed line to structured multi-section document
- Updated repository description to be benefit-oriented

## [0.1.0] — 2026-05-31

### Added
- Initial release: Phase 1 (LLM frontmatter enrichment), Phase 2 (embedding-based semantic linking), Phase 3 (MOC index generation)
- OpenRouter integration with retry and rate-limit handling
- Atomic state management with resume capability
- Embedding cache for incremental Phase 2 runs
- Configurable concurrency, thresholds, and excluded folders
