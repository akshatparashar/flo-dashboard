"""Claude API client used by the chatbot.

``LLMClient`` is the small interface the service depends on, so tests (or another provider later) can swap it.
``AnthropicLLM`` streams replies from Claude with the official Anthropic SDK.
"""

from typing import Iterator, Protocol

from .errors import ConfigurationError, LLMError

# Server-side refusal fallback: if the model declines for a safety reason, the API re-runs the request on a
# suitable fallback model inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMClient(Protocol):
    def stream_reply(self, system: str, messages: list) -> Iterator[str]:
        """Yield the reply text in pieces. Raise ``LLMError`` on failure."""
        ...


class AnthropicLLM:
    def __init__(self, api_key, model, effort="low", max_tokens=4000, timeout=60.0, client=None):
        if client is None:
            if not api_key:
                raise ConfigurationError("ANTHROPIC_API_KEY is not set")
            import anthropic
            client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)
        self._client = client
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens

    def stream_reply(self, system, messages):
        import anthropic

        try:
            with self._client.beta.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=messages,
                output_config={"effort": self.effort},
                cache_control={"type": "ephemeral"},     # caches the growing conversation prefix between turns
                betas=[FALLBACK_BETA],
                fallbacks="default",
            ) as stream:
                produced = False
                for text in stream.text_stream:
                    if text:
                        produced = True
                        yield text
                final = stream.get_final_message()
        except anthropic.AuthenticationError as e:
            raise LLMError(str(e), "FLO Assistant's API key is invalid. Please ask the admin to check it.") from e
        except anthropic.PermissionDeniedError as e:
            raise LLMError(str(e), "FLO Assistant's API key does not have access to this model.") from e
        except anthropic.NotFoundError as e:
            raise LLMError(str(e), f"The configured model `{self.model}` was not found.") from e
        except anthropic.RateLimitError as e:
            raise LLMError(str(e), "FLO Assistant is busy right now (rate limit). Please wait a minute and retry.") from e
        except anthropic.BadRequestError as e:
            raise LLMError(str(e), "The request could not be processed. Try clearing the chat and asking again.") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"{e.status_code}: {e}", "The AI service had a problem. Please try again shortly.") from e
        except anthropic.APIConnectionError as e:
            raise LLMError(str(e), "Could not reach the AI service. Check the internet connection and retry.") from e

        if final.stop_reason == "refusal":
            raise LLMError("refusal", "FLO Assistant can't help with that request.")
        if final.stop_reason == "max_tokens" and produced:
            yield "\n\n_(Reply was cut short. Ask me to continue.)_"
        elif not produced:
            raise LLMError(f"empty reply (stop_reason={final.stop_reason})")
