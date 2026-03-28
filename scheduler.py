"""
Scheduler - Entry point for the daily news digest pipeline.

Can be run directly (python scheduler.py) or invoked by the GitHub Actions
cron job defined in .github/workflows/daily_news.yml.

Environment variables required:
  NEWS_API_KEY        – NewsAPI.org API key
  OPENAI_API_KEY      – OpenAI API key
  GOOGLE_SERVICE_ACCOUNT_JSON – Contents of a Google service-account JSON key
  GOOGLE_DOCUMENT_ID  – (optional) existing Google Doc ID to append to

Optional:
  NEWS_LANGUAGE       – Language code for articles (default: 'en')
  NEWS_CATEGORIES     – Comma-separated list of categories (default: 'general')
  NEWS_COUNTRY        – Country code (default: 'us')
  OPENAI_MODEL        – OpenAI model name (default: 'gpt-4o-mini')
"""

import json
import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

from news_agent.news_fetcher import NewsFetcher
from news_agent.ai_summarizer import AISummarizer
from news_agent.google_docs_writer import GoogleDocsWriter

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{name}' is not set."
        )
    return value


def run_daily_digest() -> None:
    """
    Main pipeline:
      1. Fetch top headlines for each configured category.
      2. Ask OpenAI to produce a concise daily digest.
      3. Write the digest to Google Docs.
    """
    logger.info("=== Daily News Digest – %s ===", datetime.now(timezone.utc).date())

    news_api_key = _require_env("NEWS_API_KEY")
    openai_api_key = _require_env("OPENAI_API_KEY")
    service_account_json = _require_env("GOOGLE_SERVICE_ACCOUNT_JSON")

    document_id = os.getenv("GOOGLE_DOCUMENT_ID")
    language = os.getenv("NEWS_LANGUAGE", "en")
    categories_raw = os.getenv("NEWS_CATEGORIES", "general")
    categories = [c.strip() for c in categories_raw.split(",") if c.strip()]
    country = os.getenv("NEWS_COUNTRY", "us")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    service_account_info = json.loads(service_account_json)

    fetcher = NewsFetcher(api_key=news_api_key, language=language)
    summarizer = AISummarizer(api_key=openai_api_key, model=openai_model)
    writer = GoogleDocsWriter(
        service_account_info=service_account_info,
        document_id=document_id,
    )

    all_articles: list[dict] = []
    for category in categories:
        logger.info("Fetching headlines for category: %s", category)
        articles = fetcher.fetch_top_headlines(
            category=category if category != "general" else None,
            country=country,
        )
        logger.info("  → %d articles fetched.", len(articles))
        all_articles.extend(articles)

    seen_urls: set[str] = set()
    unique_articles = []
    for article in all_articles:
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            unique_articles.append(article)

    logger.info("Total unique articles: %d", len(unique_articles))

    summary = summarizer.summarize(unique_articles)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc_title = f"Daily News Digest – {date_str}"

    doc_id = writer.write(title=doc_title, content=summary)
    logger.info("Digest written to Google Doc: %s", doc_id)
    logger.info("=== Pipeline complete ===")


if __name__ == "__main__":
    run_daily_digest()
