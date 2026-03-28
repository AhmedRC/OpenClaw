"""
Tests for the scheduler entry point.
"""

import json
from unittest.mock import MagicMock, patch

import pytest


class TestRunDailyDigest:
    def _env(self, overrides=None):
        base = {
            "NEWS_API_KEY": "news-key",
            "OPENAI_API_KEY": "openai-key",
            "GOOGLE_SERVICE_ACCOUNT_JSON": json.dumps({"type": "service_account"}),
            "GOOGLE_DOCUMENT_ID": "doc-123",
            "NEWS_CATEGORIES": "technology,science",
            "NEWS_COUNTRY": "us",
            "NEWS_LANGUAGE": "en",
            "OPENAI_MODEL": "gpt-4o-mini",
        }
        if overrides:
            base.update(overrides)
        return base

    def test_pipeline_calls_all_components(self):
        mock_articles = [
            {
                "title": "Tech News",
                "description": "Desc",
                "content": "",
                "url": "https://a.com/1",
                "published_at": "2024-01-01",
                "source": "Tech",
            }
        ]
        with patch.dict("os.environ", self._env(), clear=False), \
             patch("scheduler.NewsFetcher") as MockFetcher, \
             patch("scheduler.AISummarizer") as MockSummarizer, \
             patch("scheduler.GoogleDocsWriter") as MockWriter:

            MockFetcher.return_value.fetch_top_headlines.return_value = mock_articles
            MockSummarizer.return_value.summarize.return_value = "Summary text"
            MockWriter.return_value.write.return_value = "doc-123"

            from scheduler import run_daily_digest
            run_daily_digest()

        MockFetcher.return_value.fetch_top_headlines.assert_called()
        MockSummarizer.return_value.summarize.assert_called_once()
        MockWriter.return_value.write.assert_called_once()

    def test_missing_env_var_raises(self):
        env = self._env()
        env.pop("NEWS_API_KEY")
        with patch.dict("os.environ", env, clear=True):
            from scheduler import run_daily_digest
            with pytest.raises(EnvironmentError, match="NEWS_API_KEY"):
                run_daily_digest()

    def test_deduplicates_articles(self):
        duplicate = {
            "title": "Dup",
            "description": "",
            "content": "",
            "url": "https://a.com/dup",
            "published_at": "2024-01-01",
            "source": "S",
        }
        with patch.dict("os.environ", self._env(), clear=False), \
             patch("scheduler.NewsFetcher") as MockFetcher, \
             patch("scheduler.AISummarizer") as MockSummarizer, \
             patch("scheduler.GoogleDocsWriter") as MockWriter:

            # Two categories return the same article (same URL)
            MockFetcher.return_value.fetch_top_headlines.return_value = [duplicate]
            MockSummarizer.return_value.summarize.return_value = "ok"
            MockWriter.return_value.write.return_value = "doc-123"

            from scheduler import run_daily_digest
            run_daily_digest()

        # summarize should have been called with deduplicated list (1 item, not 2)
        call_args = MockSummarizer.return_value.summarize.call_args
        passed_articles = call_args[0][0]
        assert len(passed_articles) == 1
