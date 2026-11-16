"""ChatService - the chatbot backend API used by the UI (and by tests).

    service = ChatService(llm, retriever=retriever, history_turns=12)
    for piece in service.stream_reply(conversation, "Fabric PO dashboard kya dikhata hai?"):
        ...

``stream_reply`` validates the input, records the user message, retrieves website knowledge (RAG), sends the
recent conversation to the model, streams the answer and records it in the conversation. On failure the turn
is marked failed (so it is not resent as context) and a ``ChatbotError`` is raised.
"""

from .errors import ChatbotError, EmptyMessageError, LLMError, MessageTooLongError
from .prompts import SYSTEM_PROMPT, build_user_turn


class ChatService:
    def __init__(self, llm, retriever=None, history_turns=12, max_input_chars=4000, top_k=4,
                 system_prompt=SYSTEM_PROMPT):
        self.llm = llm
        self.retriever = retriever
        self.history_turns = history_turns
        self.max_input_chars = max_input_chars
        self.top_k = top_k
        self.system_prompt = system_prompt
        self.last_sources = []

    def validate(self, text):
        text = (text or "").strip()
        if not text:
            raise EmptyMessageError("empty message")
        if len(text) > self.max_input_chars:
            raise MessageTooLongError(f"{len(text)} > {self.max_input_chars} chars")
        return text

    def retrieve(self, question):
        if self.retriever is None:
            return []
        try:
            return list(self.retriever.search(question, k=self.top_k))
        except Exception:
            return []          # knowledge lookup is optional - never block the chat on it

    def build_messages(self, conversation, question, chunks):
        """Recent context + the new user turn (with knowledge attached). The new turn is not in history yet."""
        messages = conversation.context_window(self.history_turns)
        messages.append({"role": "user", "content": build_user_turn(question, chunks)})
        return messages

    def stream_reply(self, conversation, text):
        question = self.validate(text)
        chunks = self.retrieve(question)
        messages = self.build_messages(conversation, question, chunks)
        conversation.add_user(question)
        self.last_sources = _sources(chunks)

        parts = []
        try:
            for piece in self.llm.stream_reply(self.system_prompt, messages):
                parts.append(piece)
                yield piece
        except ChatbotError as e:
            conversation.add_error(e.user_message)
            raise
        except Exception as e:                    # unexpected bug - still keep the chat usable
            err = LLMError(repr(e))
            conversation.add_error(err.user_message)
            raise err from e
        conversation.add_assistant("".join(parts), sources=self.last_sources)

    def reply(self, conversation, text):
        """Non-streaming helper: returns the full reply text."""
        return "".join(self.stream_reply(conversation, text))


def _sources(chunks):
    seen, out = set(), []
    for ch in chunks:
        key = ch.url or ch.title
        if key and key not in seen:
            seen.add(key)
            out.append({"title": ch.title or ch.url, "url": ch.url})
    return out
