"""Chatbot tests. Run: python -m unittest discover -s tests -v

No network calls: the model is replaced by a fake LLM client, and the Anthropic SDK by a fake stream.
"""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx2 as httpx

from chatbot import ChatService, Conversation
from chatbot.config import ChatbotConfig
from chatbot.errors import ConfigurationError, EmptyMessageError, LLMError, MessageTooLongError
from chatbot.knowledge import Chunk, KeywordRetriever, KnowledgeStore, Page, build_chunks, chunk_text, clean_text
from chatbot.knowledge.scraper import WebsiteScraper
from chatbot.llm import AnthropicLLM
from chatbot.prompts import SYSTEM_PROMPT


class FakeLLM:
    def __init__(self, replies=None, fail_with=None):
        self.replies = list(replies or ["Hello!"])
        self.fail_with = fail_with
        self.calls = []

    def stream_reply(self, system, messages):
        self.calls.append({"system": system, "messages": [dict(m) for m in messages]})
        if self.fail_with:
            raise self.fail_with
        reply = self.replies.pop(0) if self.replies else "ok"
        for word in reply.split(" "):
            yield word + " "


# ---------------------------------------------------------------- service / history
class ChatServiceTests(unittest.TestCase):
    def test_send_and_receive(self):
        llm, conv = FakeLLM(["Fabric PO tab shows purchase orders"]), Conversation()
        reply = ChatService(llm).reply(conv, "  What is Fabric PO?  ")
        self.assertEqual(reply.strip(), "Fabric PO tab shows purchase orders")
        self.assertEqual([m.role for m in conv.messages], ["user", "assistant"])
        self.assertEqual(conv.messages[0].content, "What is Fabric PO?")
        self.assertEqual(llm.calls[0]["system"], SYSTEM_PROMPT)

    def test_streams_in_pieces(self):
        pieces = list(ChatService(FakeLLM(["a b c"])).stream_reply(Conversation(), "hi"))
        self.assertEqual(len(pieces), 3)

    def test_conversation_context_is_sent(self):
        llm, conv = FakeLLM(["Hi Rekha", "Your name is Rekha"]), Conversation()
        svc = ChatService(llm)
        svc.reply(conv, "My name is Rekha")
        svc.reply(conv, "What is my name?")
        sent = llm.calls[1]["messages"]
        self.assertEqual([m["role"] for m in sent], ["user", "assistant", "user"])
        self.assertEqual(sent[0]["content"], "My name is Rekha")
        self.assertEqual(sent[1]["content"].strip(), "Hi Rekha")
        self.assertEqual(sent[2]["content"], "What is my name?")
        self.assertEqual(len(conv), 4)

    def test_history_window_is_bounded(self):
        llm, conv = FakeLLM(["r"] * 10), Conversation()
        svc = ChatService(llm, history_turns=2)
        for i in range(6):
            svc.reply(conv, f"q{i}")
        sent = llm.calls[-1]["messages"]
        self.assertEqual(len(sent), 5)                       # 2 pairs + new question
        self.assertEqual(sent[0]["content"], "q3")
        self.assertEqual(len(conv), 12)                      # full history still kept for display

    def test_empty_and_too_long_messages_rejected(self):
        svc, conv = ChatService(FakeLLM(), max_input_chars=10), Conversation()
        with self.assertRaises(EmptyMessageError):
            svc.reply(conv, "   ")
        with self.assertRaises(MessageTooLongError):
            svc.reply(conv, "x" * 11)
        self.assertEqual(len(conv), 0)

    def test_llm_error_marks_turn_failed_and_is_not_resent(self):
        conv = Conversation()
        with self.assertRaises(LLMError) as ctx:
            ChatService(FakeLLM(fail_with=LLMError("boom", "Service down"))).reply(conv, "first")
        self.assertEqual(ctx.exception.user_message, "Service down")
        self.assertTrue(conv.messages[0].failed)
        self.assertTrue(conv.messages[1].error)
        self.assertEqual(conv.messages[1].content, "Service down")

        llm = FakeLLM(["fine"])
        ChatService(llm).reply(conv, "second")
        self.assertEqual(llm.calls[0]["messages"], [{"role": "user", "content": "second"}])

    def test_unexpected_exception_becomes_llm_error(self):
        conv = Conversation()
        with self.assertRaises(LLMError):
            ChatService(FakeLLM(fail_with=RuntimeError("bug"))).reply(conv, "hi")
        self.assertTrue(conv.messages[-1].error)

    def test_clear(self):
        conv = Conversation()
        ChatService(FakeLLM()).reply(conv, "hi")
        conv.clear()
        self.assertEqual(len(conv), 0)


# ---------------------------------------------------------------- RAG
class KnowledgeTests(unittest.TestCase):
    CHUNKS = [
        Chunk(id="1", title="Shipping", url="https://example.test/shipping", text="Orders ship within 5 days."),
        Chunk(id="2", title="Fabrics", url="https://example.test/fabrics", text="We use cotton and rayon fabric."),
    ]

    def test_retrieved_knowledge_is_attached_to_latest_turn(self):
        llm, conv = FakeLLM(), Conversation()
        svc = ChatService(llm, retriever=KeywordRetriever(self.CHUNKS))
        svc.reply(conv, "Which fabric do you use?")
        content = llm.calls[0]["messages"][-1]["content"]
        self.assertIn("<company_knowledge>", content)
        self.assertIn("cotton and rayon", content)
        self.assertNotIn("ship within", content)
        self.assertEqual(conv.messages[0].content, "Which fabric do you use?")    # history keeps raw question
        self.assertEqual(conv.messages[1].sources[0]["url"], "https://example.test/fabrics")

    def test_no_match_sends_plain_question(self):
        llm = FakeLLM()
        ChatService(llm, retriever=KeywordRetriever(self.CHUNKS)).reply(Conversation(), "hello there")
        self.assertEqual(llm.calls[0]["messages"][-1]["content"], "hello there")

    def test_broken_retriever_does_not_block_chat(self):
        class Broken:
            def search(self, q, k):
                raise RuntimeError("index corrupt")
        self.assertTrue(ChatService(FakeLLM(), retriever=Broken()).reply(Conversation(), "hi"))

    def test_clean_text(self):
        raw = "Home\n  Our   Products \nOur Products\n Kurta sets\nAll rights reserved 2026\n"
        self.assertEqual(clean_text(raw), "Our Products\nKurta sets")

    def test_chunk_text_respects_size(self):
        text = "\n".join(f"Sentence number {i} is here." for i in range(200))
        chunks = chunk_text(text, max_chars=300, overlap=50)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 300 for c in chunks))

    def test_build_chunks_extracts_faqs(self):
        page = Page(url="https://example.test/faq", title="FAQ",
                    text="Do you ship abroad?\nYes, to selected countries.\nWhat is MOQ?\n100 pieces.")
        texts = [c.text for c in build_chunks([page])]
        self.assertIn("Q: Do you ship abroad?\nA: Yes, to selected countries.", texts)
        self.assertIn("Q: What is MOQ?\nA: 100 pieces.", texts)

    def test_store_roundtrip_and_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            store = KnowledgeStore(Path(d) / "kb" / "knowledge.json")
            self.assertEqual(store.load(), [])
            store.save(self.CHUNKS, source_url="https://example.test")
            self.assertEqual([c.text for c in store.load()], [c.text for c in self.CHUNKS])

    def test_scraper_requires_url_and_is_pending(self):
        with self.assertRaises(ConfigurationError):
            WebsiteScraper("")
        with self.assertRaises(NotImplementedError):
            WebsiteScraper("https://example.test").crawl()


# ---------------------------------------------------------------- config
class ConfigTests(unittest.TestCase):
    def test_secrets_section_wins_over_env(self):
        cfg = ChatbotConfig.load({"chatbot": {"anthropic_api_key": "k1", "model": "m1"}},
                                 env={"ANTHROPIC_API_KEY": "k2"})
        self.assertEqual((cfg.api_key, cfg.model), ("k1", "m1"))

    def test_env_fallback_and_defaults(self):
        cfg = ChatbotConfig.load(None, env={"ANTHROPIC_API_KEY": "k2", "FLO_CHATBOT_HISTORY_TURNS": "bad"})
        self.assertTrue(cfg.is_configured)
        self.assertEqual(cfg.model, "claude-opus-5-5")
        self.assertEqual(cfg.history_turns, 12)

    def test_unconfigured(self):
        self.assertFalse(ChatbotConfig.load(None, env={}).is_configured)
        with self.assertRaises(ConfigurationError):
            AnthropicLLM(api_key="", model="m")

    def test_secrets_object_that_raises(self):
        class Raising:
            def keys(self):
                raise FileNotFoundError("no secrets.toml")
        self.assertFalse(ChatbotConfig.load(Raising(), env={}).is_configured)


# ---------------------------------------------------------------- Anthropic client wrapper
class _FakeStream:
    def __init__(self, texts, stop_reason="end_turn", error=None):
        self.texts, self.stop_reason, self.error = texts, stop_reason, error

    def __enter__(self):
        if self.error:
            raise self.error
        return self

    def __exit__(self, *a):
        return False

    @property
    def text_stream(self):
        return iter(self.texts)

    def get_final_message(self):
        return SimpleNamespace(stop_reason=self.stop_reason)


class _FakeClient:
    def __init__(self, stream):
        self.kwargs = None
        outer = self

        class _Messages:
            def stream(self, **kwargs):
                outer.kwargs = kwargs
                return stream
        self.beta = SimpleNamespace(messages=_Messages())


def _status_error(cls, code):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("err", response=httpx.Response(code, request=req), body=None)


class AnthropicLLMTests(unittest.TestCase):
    def _llm(self, stream):
        client = _FakeClient(stream)
        return AnthropicLLM(api_key="", model="claude-opus-5-5", client=client), client

    def test_streams_text_and_sends_expected_request(self):
        llm, client = self._llm(_FakeStream(["Hel", "lo"]))
        out = "".join(llm.stream_reply("sys", [{"role": "user", "content": "hi"}]))
        self.assertEqual(out, "Hello")
        self.assertEqual(client.kwargs["model"], "claude-opus-5-5")
        self.assertEqual(client.kwargs["system"], "sys")
        self.assertEqual(client.kwargs["fallbacks"], "default")
        self.assertNotIn("thinking", client.kwargs)

    def test_refusal(self):
        llm, _ = self._llm(_FakeStream([], stop_reason="refusal"))
        with self.assertRaises(LLMError):
            list(llm.stream_reply("s", []))

    def test_max_tokens_adds_note(self):
        llm, _ = self._llm(_FakeStream(["partial"], stop_reason="max_tokens"))
        self.assertIn("cut short", "".join(llm.stream_reply("s", [])))

    def test_api_errors_map_to_friendly_messages(self):
        cases = [(_status_error(anthropic.RateLimitError, 429), "rate limit"),
                 (_status_error(anthropic.AuthenticationError, 401), "API key is invalid"),
                 (_status_error(anthropic.InternalServerError, 500), "AI service had a problem"),
                 (anthropic.APIConnectionError(request=httpx.Request("POST", "https://x")), "Could not reach")]
        for err, expected in cases:
            llm, _ = self._llm(_FakeStream([], error=err))
            with self.assertRaises(LLMError) as ctx:
                list(llm.stream_reply("s", []))
            self.assertIn(expected, ctx.exception.user_message)


if __name__ == "__main__":
    unittest.main()
