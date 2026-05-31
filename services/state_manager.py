"""Atomic state management with resume capability."""
import json
import logging
import os
from pathlib import Path

import config

logger = logging.getLogger("curator.state")


class StateManager:
    def __init__(self, state_file: Path | None = None):
        self.state_file = state_file or config.STATE_FILE
        self.state = self._load()

    def _load(self) -> dict:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.error("State file corrupt, starting fresh: %s", e)
        return {
            "phase1_done": [],
            "phase1_failed": [],
            "phase2_done": [],
            "phase3_done": False,
            "version": "3.0",
        }

    def save(self) -> None:
        tmp = self.state_file.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.state_file)
        except OSError as e:
            logger.error("Failed to save state: %s", e)

    def is_phase1_done(self, path: str) -> bool:
        return path in self.state.get("phase1_done", [])

    def mark_phase1_done(self, path: str) -> None:
        done = self.state.setdefault("phase1_done", [])
        if path not in done:
            done.append(path)

    def mark_phase1_failed(self, path: str, reason: str) -> None:
        failed = self.state.setdefault("phase1_failed", [])
        entry = {"path": path, "reason": reason}
        if not any(f.get("path") == path for f in failed):
            failed.append(entry)

    def is_phase2_done(self, path: str) -> bool:
        return path in self.state.get("phase2_done", [])

    def mark_phase2_done(self, path: str) -> None:
        done = self.state.setdefault("phase2_done", [])
        if path not in done:
            done.append(path)

    def get_embedding(self, path: str) -> list[float] | None:
        if not config.EMBEDDINGS_FILE.exists():
            return None
        try:
            with open(config.EMBEDDINGS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    obj = json.loads(line)
                    if obj.get("path") == path:
                        return obj.get("vector")
        except (json.JSONDecodeError, OSError):
            pass
        return None

    def save_embedding(self, path: str, vector: list[float]) -> None:
        entries = []
        if config.EMBEDDINGS_FILE.exists():
            try:
                with open(config.EMBEDDINGS_FILE, "r", encoding="utf-8") as f:
                    entries = [json.loads(line) for line in f if line.strip()]
            except (json.JSONDecodeError, OSError):
                entries = []
        found = False
        for entry in entries:
            if entry.get("path") == path:
                entry["vector"] = vector
                found = True
                break
        if not found:
            entries.append({"path": path, "vector": vector})
        tmp = config.EMBEDDINGS_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        os.replace(tmp, config.EMBEDDINGS_FILE)

    def load_all_embeddings(self) -> dict[str, list[float]]:
        result = {}
        if not config.EMBEDDINGS_FILE.exists():
            return result
        try:
            with open(config.EMBEDDINGS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    result[obj["path"]] = obj["vector"]
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load embeddings: %s", e)
        return result