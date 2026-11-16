"""Streamlit chat interface for FLO Assistant. app.py calls ``render_chatbot()`` inside its own tab.

Uses Streamlit's built-in chat elements so it follows the dashboard's existing theme; the only markup reused
is the dashboard's own ``dash-title`` header class.
"""

import json
from itertools import chain

import streamlit as st

from .config import ChatbotConfig
from .errors import ChatbotError, ConfigurationError
from .history import ASSISTANT, Conversation
from .knowledge import KeywordRetriever, KnowledgeStore
from .llm import AnthropicLLM
from .service import ChatService

# Session-state keys start with "_" so app.py's _keep_widget_state() leaves them alone.
STATE_KEY = "_flo_chat_conversation"
INPUT_KEY = "_flo_chat_input"
CLEAR_KEY = "_flo_chat_clear"
AVATARS = {"user": "🧑", "assistant": "🤖"}
CHAT_HEIGHT = 520


def _stretch_kwargs():
    """Full-width kwarg for old and new Streamlit (same rule as app.py)."""
    try:
        major, minor = (int(p) for p in st.__version__.split(".")[:2])
    except Exception:
        return {"use_container_width": True}
    return {"width": "stretch"} if (major, minor) >= (1, 50) else {"use_container_width": True}


_STRETCH = _stretch_kwargs()


def _secrets():
    try:
        return st.secrets
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def _llm(api_key, model, effort, max_tokens):
    return AnthropicLLM(api_key=api_key, model=model, effort=effort, max_tokens=max_tokens)


@st.cache_resource(show_spinner=False)
def _retriever(path, mtime):
    """Rebuilt only when the knowledge file changes (mtime is part of the cache key)."""
    chunks = KnowledgeStore(path).load()
    return KeywordRetriever(chunks) if chunks else None


def _knowledge(cfg):
    store = KnowledgeStore(cfg.knowledge_path)
    if not store.exists():
        return None
    try:
        mtime = cfg.knowledge_path.stat().st_mtime
    except OSError:
        return None
    return _retriever(str(cfg.knowledge_path), mtime)


def _conversation():
    conv = st.session_state.get(STATE_KEY)
    if not isinstance(conv, Conversation):
        conv = Conversation()
        st.session_state[STATE_KEY] = conv
    return conv


def _show_sources(sources):
    if sources:
        links = " · ".join(f"[{s['title']}]({s['url']})" if s.get("url") else s["title"] for s in sources)
        st.caption(f"Sources: {links}")


def _show_message(msg):
    with st.chat_message(msg.role, avatar=AVATARS.get(msg.role)):
        if msg.error:
            st.error(msg.content, icon="⚠️")
        else:
            st.markdown(msg.content)
            _show_sources(msg.sources)


def _stream_with_spinner(gen):
    """Show a spinner until the first piece of the reply arrives, then stream the rest."""
    with st.spinner("FLO Assistant is thinking…"):
        first = next(gen, None)
    return st.write_stream(chain([first] if first else [], gen))


def render_chatbot():
    cfg = ChatbotConfig.load(_secrets())
    st.markdown('<div class="dash-title"><span class="t">🤖 FLO Assistant</span>'
                '<span class="chip">Beta</span></div>', unsafe_allow_html=True)
    st.caption("Ask about the dashboards, how to read a metric, or where to find something. "
               "English, Hindi or Hinglish - all fine.")

    if not cfg.is_configured:
        st.info(ConfigurationError.user_message, icon="🔑")
        return

    conv = _conversation()
    retriever = _knowledge(cfg)

    left, mid, right = st.columns([3, 1, 1])
    with left:
        if retriever is None:
            st.caption("📚 Company website knowledge: not loaded yet - company-specific questions can't be answered.")
        else:
            st.caption(f"📚 Company website knowledge: {len(retriever)} sections loaded.")
    with mid:
        st.download_button("⬇️ History", data=json.dumps(conv.to_dicts(), ensure_ascii=False, indent=1),
                           file_name="flo_assistant_chat.json", mime="application/json",
                           key="dl_flo_chat_history", disabled=not len(conv), **_STRETCH)
    with right:
        if st.button("🗑️ Clear chat", key=CLEAR_KEY, disabled=not len(conv), **_STRETCH):
            conv.clear()
            st.rerun()

    box = st.container(height=CHAT_HEIGHT, border=True)
    with box:
        if not len(conv):
            with st.chat_message(ASSISTANT, avatar=AVATARS[ASSISTANT]):
                st.markdown("Namaste! I'm **FLO Assistant**. How can I help you with the dashboard today?")
        for msg in conv.messages:
            _show_message(msg)

    prompt = st.chat_input("Ask FLO Assistant…", key=INPUT_KEY, max_chars=cfg.max_input_chars)
    if not prompt:
        return

    service = ChatService(llm=None, retriever=retriever, history_turns=cfg.history_turns,
                          max_input_chars=cfg.max_input_chars)
    with box:
        with st.chat_message("user", avatar=AVATARS["user"]):
            st.markdown(prompt)
        with st.chat_message(ASSISTANT, avatar=AVATARS[ASSISTANT]):
            try:
                service.llm = _llm(cfg.api_key, cfg.model, cfg.effort, cfg.max_tokens)
                _stream_with_spinner(service.stream_reply(conv, prompt))
                _show_sources(service.last_sources)
            except ChatbotError as e:
                st.error(e.user_message, icon="⚠️")
