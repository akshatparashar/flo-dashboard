"""Conversation history.

The full history is kept for display. Only the last N exchanges (and never failed turns) are sent to the model,
which keeps the conversation context bounded.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

USER, ASSISTANT = "user", "assistant"


@dataclass
class ChatMessage:
    role: str
    content: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    error: bool = False          # assistant bubble that shows an error (never sent to the model)
    failed: bool = False         # user message whose reply failed (never sent to the model)
    sources: list = field(default_factory=list)   # knowledge-base sources used for this reply

    def to_dict(self):
        return {"role": self.role, "content": self.content, "created_at": self.created_at,
                "error": self.error, "failed": self.failed, "sources": list(self.sources)}


@dataclass
class Conversation:
    messages: list = field(default_factory=list)

    def add_user(self, text):
        msg = ChatMessage(USER, text)
        self.messages.append(msg)
        return msg

    def add_assistant(self, text, sources=None):
        msg = ChatMessage(ASSISTANT, text, sources=list(sources or []))
        self.messages.append(msg)
        return msg

    def add_error(self, text):
        """Mark the last user message as failed and show an error bubble."""
        for m in reversed(self.messages):
            if m.role == USER:
                m.failed = True
                break
        msg = ChatMessage(ASSISTANT, text, error=True)
        self.messages.append(msg)
        return msg

    def clear(self):
        self.messages.clear()

    def __len__(self):
        return len(self.messages)

    def context_window(self, max_turns):
        """Successful user/assistant pairs, newest ``max_turns`` of them, in API message format."""
        pairs, pending_user = [], None
        for m in self.messages:
            if m.error or m.failed:
                pending_user = None
                continue
            if m.role == USER:
                pending_user = m
            elif m.role == ASSISTANT and pending_user is not None:
                pairs.append((pending_user, m))
                pending_user = None
        if max_turns is not None and max_turns >= 0:
            pairs = pairs[-max_turns:] if max_turns else []
        out = []
        for u, a in pairs:
            out.append({"role": USER, "content": u.content})
            out.append({"role": ASSISTANT, "content": a.content})
        return out

    def to_dicts(self):
        return [m.to_dict() for m in self.messages]
