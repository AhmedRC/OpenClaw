"""
Tests for NewsFetcher.
"""

from unittest.mock import MagicMock, patch

import pytest

from news_agent.news_fetcher import NewsFetcher


@pytest.fixture
def fetcher():
    return NewsFetcher(api_key="test-key", language="en", page_size=5)


class TestParsesArticles:
    def test_normal_article_is_kept(self, fetcher):
        raw = [
            {
                "title": "Test News",
                "description": "A test article.",
                "content": "Full content.",
                "url": "https://example.com/news",
                "publishedAt": "2024-01-01T00:00:00Z",
                "source": {"name": "Example"},
            }
        ]
        result = fetcher._parse_articles(raw)
        assert len(result) == 1
        assert result[0]["title"] == "Test News"
        assert result[0]["source"] == "Example"

    def test_removed_article_is_skipped(self, fetcher):
        raw = [{"title": "[Removed]", "url": "https://example.com/gone"}]
        result = fetcher._parse_articles(raw)
        assert result == []

    def test_article_without_title_is_skipped(self, fetcher):
        raw = [{"title": None, "url": "https://example.com/notitle"}]
        result = fetcher._parse_articles(raw)
        assert result == []

    def test_missing_optional_fields_default_to_empty_string(self, fetcher):
        raw = [{"title": "Only title"}]
        result = fetcher._parse_articles(raw)
        assert len(result) == 1
        assert result[0]["description"] == ""
        assert result[0]["source"] == ""
        assert result[0]["url"] == ""


class TestFetchTopHeadlines:
    def test_returns_parsed_articles(self, fetcher):
        mock_response = {
            "articles": [
                {
                    "title": "Headline 1",
                    "description": "Desc",
                    "content": "",
                    "url": "https://example.com/1",
                    "publishedAt": "2024-01-01T00:00:00Z",
                    "source": {"name": "Source"},
                }
            ]
        }
        with patch.object(
            fetcher.client, "get_top_headlines", return_value=mock_response
        ):
            articles = fetcher.fetch_top_headlines(country="us")
        assert len(articles) == 1
        assert articles[0]["title"] == "Headline 1"

    def test_raises_on_api_error(self, fetcher):
        with patch.object(
            fetcher.client, "get_top_headlines", side_effect=Exception("API error")
        ):
            with pytest.raises(Exception, match="API error"):
                fetcher.fetch_top_headlines()


class TestFetchEverything:
    def test_uses_yesterday_as_default_from_date(self, fetcher):
        mock_response = {"articles": []}
        with patch.object(
            fetcher.client, "get_everything", return_value=mock_response
        ) as mock_get:
            fetcher.fetch_everything(query="AI")
        call_kwargs = mock_get.call_args.kwargs
        assert "from_param" in call_kwargs
        # Should be in YYYY-MM-DD format
        from datetime import datetime
        datetime.strptime(call_kwargs["from_param"], "%Y-%m-%d")

    def test_raises_on_api_error(self, fetcher):
        with patch.object(
            fetcher.client, "get_everything", side_effect=Exception("fail")
        ):
            with pytest.raises(Exception, match="fail"):
                fetcher.fetch_everything(query="test")
