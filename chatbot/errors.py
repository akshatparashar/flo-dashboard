"""Chatbot error types. Every error carries a short message that is safe to show in the dashboard."""


class ChatbotError(Exception):
    """Base error. ``user_message`` is safe to display; ``str(err)`` may hold technical detail."""

    user_message = "Kuch galat ho gaya. Please try again."

    def __init__(self, detail="", user_message=None):
        super().__init__(detail or self.user_message)
        if user_message:
            self.user_message = user_message


class ConfigurationError(ChatbotError):
    """The chatbot is not set up (e.g. missing API key)."""

    user_message = ("FLO Assistant is not configured yet. Add `ANTHROPIC_API_KEY` to Streamlit secrets "
                    "(or the environment) to enable it.")


class LLMError(ChatbotError):
    """The model call failed (network, rate limit, server error, refusal...)."""

    user_message = "FLO Assistant could not answer right now. Please try again in a moment."


class EmptyMessageError(ChatbotError):
    user_message = "Please type a message."


class MessageTooLongError(ChatbotError):
    user_message = "Message is too long. Please shorten it and try again."
