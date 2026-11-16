"""Chatbot settings.

Read from Streamlit secrets first (``[chatbot]`` section, or a top-level ``ANTHROPIC_API_KEY``), then from
environment variables. Never hard-code keys here.

Example ``.streamlit/secrets.toml`` (this file is git-ignored):

    ANTHROPIC_API_KEY = "sk-ant-..."

    [chatbot]
    model = "claude-opus-5-5"        # optional
    effort = "low"                   # optional: low | medium | high
    website_url = ""                 # company website, used later for the knowledge base
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "low"            # chat replies: fast and cheap; raise to "medium"/"high" if answers need more depth
DEFAULT_MAX_TOKENS = 4000
DEFAULT_HISTORY_TURNS = 12        # user+assistant pairs sent back to the model as conversation context
DEFAULT_MAX_INPUT_CHARS = 4000
DEFAULT_KNOWLEDGE_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge_base.json"


@dataclass(frozen=True)
class ChatbotConfig:
    api_key: str = ""
    model: str = DEFAULT_MODEL
    effort: str = DEFAULT_EFFORT
    max_tokens: int = DEFAULT_MAX_TOKENS
    history_turns: int = DEFAULT_HISTORY_TURNS
    max_input_chars: int = DEFAULT_MAX_INPUT_CHARS
    website_url: str = ""
    knowledge_path: Path = field(default=DEFAULT_KNOWLEDGE_PATH)

    @property
    def is_configured(self):
        return bool(self.api_key)

    @classmethod
    def load(cls, secrets=None, env=None):
        """Build the config. ``secrets`` is a mapping like ``st.secrets``; ``env`` defaults to ``os.environ``."""
        env = os.environ if env is None else env
        top = _as_dict(secrets)
        section = _as_dict(top.get("chatbot"))

        def pick(name, env_name, default=""):
            for value in (section.get(name), top.get(env_name), env.get(env_name)):
                if value not in (None, ""):
                    return value
            return default

        return cls(
            api_key=str(pick("anthropic_api_key", "ANTHROPIC_API_KEY")),
            model=str(pick("model", "FLO_CHATBOT_MODEL", DEFAULT_MODEL)),
            effort=str(pick("effort", "FLO_CHATBOT_EFFORT", DEFAULT_EFFORT)),
            max_tokens=_to_int(pick("max_tokens", "FLO_CHATBOT_MAX_TOKENS"), DEFAULT_MAX_TOKENS),
            history_turns=_to_int(pick("history_turns", "FLO_CHATBOT_HISTORY_TURNS"), DEFAULT_HISTORY_TURNS),
            max_input_chars=_to_int(pick("max_input_chars", "FLO_CHATBOT_MAX_INPUT_CHARS"), DEFAULT_MAX_INPUT_CHARS),
            website_url=str(pick("website_url", "FLO_WEBSITE_URL")),
            knowledge_path=Path(pick("knowledge_path", "FLO_KNOWLEDGE_PATH", DEFAULT_KNOWLEDGE_PATH)),
        )


def _as_dict(obj):
    """st.secrets raises if no secrets file exists - treat that as empty."""
    if obj is None:
        return {}
    try:
        return {k: obj[k] for k in obj.keys()}
    except Exception:
        return {}


def _to_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
