"""Knowledge store: chunks saved as one JSON file (enough for a company website's worth of pages).

Swap for a vector database later without changing the retriever/service interface.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .models import Chunk

FORMAT_VERSION = 1


class KnowledgeStore:
    def __init__(self, path):
        self.path = Path(path)

    def exists(self):
        return self.path.is_file()

    def load(self):
        """Return the stored chunks; [] if the file is missing or unreadable."""
        if not self.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [Chunk.from_dict(c) for c in data.get("chunks", []) if c.get("text")]

    def save(self, chunks, source_url=""):
        """Write atomically (temp file + rename) so a half-written file is never read."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": FORMAT_VERSION,
            "source_url": source_url,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "chunks": [c.to_dict() for c in chunks],
        }
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
