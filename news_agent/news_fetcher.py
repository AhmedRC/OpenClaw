"""
News Fetcher Agent - Fetches the latest news articles from NewsAPI.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from newsapi import NewsApiClient

logger = logging.getLogger(__name__)


class NewsFetcher:
    """Agent responsible for fetching the latest news articles via NewsAPI."""

    def __init__(self, api_key: str, language: str = "en", page_size: int = 20):
        """
        Initialize the news fetcher.

        Args:
            api_key: NewsAPI API key.
            language: Language of articles to fetch (default: "en").
            page_size: Number of articles to fetch per request (max 100).
        """
        self.client = NewsApiClient(api_key=api_key)
        self.language = language
        self.page_size = page_size

    def fetch_top_headlines(
        self,
        category: Optional[str] = None,
        country: Optional[str] = None,
        query: Optional[str] = None,
    ) -> list[dict]:
        """
        Fetch top headline articles.

        Args:
            category: News category (e.g. 'technology', 'science', 'business').
            country: 2-letter ISO country code (e.g. 'us', 'gb').
            query: Keywords to filter headlines.

        Returns:
            List of article dicts with keys: title, description, url,
            publishedAt, source.
        """
        params: dict = {"language": self.language, "page_size": self.page_size}
        if category:
            params["category"] = category
        if country:
            params["country"] = country
        if query:
            params["q"] = query

        try:
            response = self.client.get_top_headlines(**params)
        except Exception as exc:
            logger.error("Failed to fetch top headlines: %s", exc)
            raise

        return self._parse_articles(response.get("articles", []))

    def fetch_everything(
        self,
        query: str,
        from_date: Optional[str] = None,
        sort_by: str = "publishedAt",
    ) -> list[dict]:
        """
        Search across all articles for a keyword query.

        Args:
            query: Keywords to search for.
            from_date: Earliest date for articles (ISO 8601, e.g. '2024-01-01').
                       Defaults to yesterday.
            sort_by: Sort order – 'relevancy', 'popularity', or 'publishedAt'.

        Returns:
            List of article dicts.
        """
        if from_date is None:
            yesterday = datetime.now(timezone.utc) - timedelta(days=1)
            from_date = yesterday.strftime("%Y-%m-%d")

        try:
            response = self.client.get_everything(
                q=query,
                from_param=from_date,
                sort_by=sort_by,
                language=self.language,
                page_size=self.page_size,
            )
        except Exception as exc:
            logger.error("Failed to fetch articles for query '%s': %s", query, exc)
            raise

        return self._parse_articles(response.get("articles", []))

    def _parse_articles(self, raw_articles: list[dict]) -> list[dict]:
        """Extract and normalise relevant fields from raw API articles."""
        articles = []
        for article in raw_articles:
            if not article.get("title") or article["title"] == "[Removed]":
                continue
            articles.append(
                {
                    "title": article.get("title", ""),
                    "description": article.get("description") or "",
                    "content": article.get("content") or "",
                    "url": article.get("url", ""),
                    "published_at": article.get("publishedAt", ""),
                    "source": (article.get("source") or {}).get("name", ""),
                }
            )
        return articles
