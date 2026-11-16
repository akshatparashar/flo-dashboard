"""Website knowledge pipeline for retrieval-augmented answers (RAG).

    scraper.py     fetch pages from the company website          (pending: needs the website URL)
    processor.py   clean text, pull out headings / FAQs, split into chunks
    store.py       save and load chunks (JSON file)
    retriever.py   find the chunks most relevant to a question (keyword / BM25 ranking, no extra dependencies)

The chat works without a knowledge base; it then says it has no company information instead of inventing it.
"""

from .models import Chunk, Page
from .processor import build_chunks, chunk_text, clean_text, extract_faqs
from .retriever import KeywordRetriever
from .store import KnowledgeStore

__all__ = ["Chunk", "Page", "KnowledgeStore", "KeywordRetriever", "build_chunks", "chunk_text", "clean_text",
           "extract_faqs"]
