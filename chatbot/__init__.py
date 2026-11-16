"""FLO Assistant - company chatbot for the FLO dashboard.

Kept separate from the dashboard code in app.py. app.py only calls ``render_chatbot()`` inside its own tab.

Layout:
    config.py       settings from Streamlit secrets / environment variables
    errors.py       chatbot error types (shown to the user as friendly messages)
    history.py      conversation history + the context window sent to the model
    prompts.py      system prompt and knowledge-context formatting
    llm.py          Claude API client (Anthropic SDK, streaming)
    service.py      ChatService - the chatbot "backend API" used by the UI
    knowledge/      website knowledge pipeline (scrape -> clean -> chunk -> store -> retrieve) for RAG
    ui.py           Streamlit chat interface
"""

from .errors import ChatbotError, ConfigurationError, LLMError
from .history import Conversation
from .service import ChatService

__all__ = ["ChatService", "Conversation", "ChatbotError", "ConfigurationError", "LLMError"]
