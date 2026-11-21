"""Conversation memory for FLO Assistant: the last 15 messages (questions and answers) of each chat, kept on the server.

* Every chat has its own random id (uuid4, unguessable), created by the server on the first message. The browser keeps
  only that id, so a reload continues the same chat and "New chat" simply starts a new id.
* Each stored answer also keeps the assistant's working context (who / which figure / which months / which page), so a
  follow-up like "compare both" can look back over the earlier questions.
* Storage is a small SQLite file (Python's own sqlite3, nothing to install). Set ``CHAT_HISTORY_DB`` to move it; on
  Vercel it defaults to /tmp, which lasts as long as the server instance. Nothing here touches the dashboard's data.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import threading
import time
import uuid
from pathlib import Path

WINDOW = 15                      # messages kept per conversation (user + assistant together)
MAX_AGE_DAYS = 30                # conversations untouched this long are removed
_ID = re.compile(r"^[0-9a-f]{32}$")


def default_path() -> str:
    if os.environ.get("CHAT_HISTORY_DB"):
        return os.environ["CHAT_HISTORY_DB"]
    if os.environ.get("VERCEL"):
        return os.path.join(tempfile.gettempdir(), "flo-chat.sqlite3")
    return str(Path(__file__).resolve().parents[2] / ".chat" / "chat.sqlite3")


class ConversationStore:
    def __init__(self, path: str | None = None, window: int = WINDOW):
        self.path = path or default_path()
        self.window = window
        self._lock = threading.Lock()
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                conv TEXT NOT NULL, seq INTEGER NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL,
                context TEXT, meta TEXT, ts REAL NOT NULL, PRIMARY KEY (conv, seq));
            CREATE INDEX IF NOT EXISTS messages_ts ON messages (ts);
        """)
        self._db.commit()

    # ------------------------------------------------------------------------------------------------ ids
    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def valid(conv: str | None) -> bool:
        return bool(conv) and bool(_ID.match(conv))

    # ------------------------------------------------------------------------------------------------ write
    def add(self, conv: str, role: str, text: str, context: dict | None = None, meta: dict | None = None):
        """Appends one message and drops the oldest ones beyond the window."""
        with self._lock:
            cur = self._db.execute("SELECT COALESCE(MAX(seq), 0) FROM messages WHERE conv = ?", (conv,))
            seq = cur.fetchone()[0] + 1
            self._db.execute("INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (conv, seq, role, text[:4000], json.dumps(context) if context is not None else None,
                              json.dumps(meta) if meta else None, time.time()))
            self._db.execute("DELETE FROM messages WHERE conv = ? AND seq <= ?", (conv, seq - self.window))
            if seq % 50 == 1:                 # now and then, forget very old chats
                self._db.execute("DELETE FROM messages WHERE ts < ?", (time.time() - MAX_AGE_DAYS * 86400,))
            self._db.commit()

    def clear(self, conv: str):
        with self._lock:
            self._db.execute("DELETE FROM messages WHERE conv = ?", (conv,))
            self._db.commit()

    # ------------------------------------------------------------------------------------------------ read
    def messages(self, conv: str) -> list[dict]:
        """The conversation's kept messages, oldest first."""
        with self._lock:
            rows = self._db.execute("SELECT role, text, context, meta, ts FROM messages WHERE conv = ? ORDER BY seq",
                                    (conv,)).fetchall()
        out = []
        for role, text, ctx, meta, ts in rows:
            m = {"role": role, "text": text, "ts": ts}
            if ctx:
                m["context"] = json.loads(ctx)
            if meta:
                m.update(json.loads(meta))
            out.append(m)
        return out

    def contexts(self, conv: str) -> list[dict]:
        """The assistant's working context after each answer in the window, oldest first."""
        return [m["context"] for m in self.messages(conv) if m["role"] == "assistant" and m.get("context")]

    def last_context(self, conv: str) -> dict | None:
        ctxs = self.contexts(conv)
        return ctxs[-1] if ctxs else None
