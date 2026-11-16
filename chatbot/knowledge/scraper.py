"""Website scraper - PENDING.

Not implemented yet on purpose: the company website URL (and whether any pages need a login) has not been
confirmed, and the scraper must be written against the real site structure rather than guessed.

Planned behaviour once the URL is provided:
  1. Start from the configured ``website_url`` (``[chatbot] website_url`` in secrets or ``FLO_WEBSITE_URL``).
  2. Respect robots.txt, stay on the same domain, rate-limit requests, cap the number of pages.
  3. For each page, extract title, headings, main text, FAQs, and product / service details -> ``Page``.
  4. ``processor.build_chunks(pages)`` -> ``KnowledgeStore(config.knowledge_path).save(chunks, source_url)``.
  5. The dashboard's chatbot picks the new knowledge up automatically (the retriever is rebuilt when the
     knowledge file changes).

Run (after implementation):  python -m chatbot.knowledge.scraper
"""

from ..config import ChatbotConfig
from ..errors import ConfigurationError


class WebsiteScraper:
    def __init__(self, base_url, max_pages=200, delay_seconds=1.0):
        if not base_url:
            raise ConfigurationError("website_url is not configured",
                                     "Company website URL is not configured for the knowledge base.")
        self.base_url = base_url
        self.max_pages = max_pages
        self.delay_seconds = delay_seconds

    def crawl(self):
        """Return a list of ``Page`` objects for the site."""
        raise NotImplementedError(
            "Website scraping is pending: confirm the company website URL (and any login needs) first."
        )


def main():
    cfg = ChatbotConfig.load()
    WebsiteScraper(cfg.website_url).crawl()


if __name__ == "__main__":
    main()
