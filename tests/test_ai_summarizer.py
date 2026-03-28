"""
Tests for AISummarizer.
"""

from unittest.mock import MagicMock, patch

import pytest

from news_agent.ai_summarizer import AISummarizer


@pytest.fixture
def summarizer():
    return AISummarizer(api_key="test-key", model="gpt-4o-mini")


SAMPLE_ARTICLES = [
    {
        "title": "AI Breakthrough",
        "description": "Scientists make a major AI discovery.",
        "content": "",
        "url": "https://example.com/ai",
        "published_at": "2024-01-01T00:00:00Z",
        "source": "Tech News",
    },
    {
        "title": "Stock Markets Rise",
        "description": "Global markets hit record highs.",
        "content": "",
        "url": "https://example.com/stocks",
        "published_at": "2024-01-01T00:00:00Z",
        "source": "Finance Daily",
    },
]


class TestBuildUserMessage:
    def test_includes_article_titles(self, summarizer):
        msg = summarizer._build_user_message(SAMPLE_ARTICLES)
        assert "AI Breakthrough" in msg
        assert "Stock Markets Rise" in msg

    def test_includes_source_names(self, summarizer):
        msg = summarizer._build_user_message(SAMPLE_ARTICLES)
        assert "Tech News" in msg
        assert "Finance Daily" in msg

    def test_includes_descriptions(self, summarizer):
        msg = summarizer._build_user_message(SAMPLE_ARTICLES)
        assert "Scientists make a major AI discovery." in msg

    def test_includes_urls(self, summarizer):
        msg = summarizer._build_user_message(SAMPLE_ARTICLES)
        assert "https://example.com/ai" in msg


class TestSummarize:
    def _mock_openai_response(self, text: str):
        choice = MagicMock()
        choice.message.content = text
        response = MagicMock()
        response.choices = [choice]
        return response

    def test_returns_summary_text(self, summarizer):
        expected = "Today's top stories include AI and finance news."
        mock_resp = self._mock_openai_response(expected)
        with patch.object(
            summarizer.client.chat.completions,
            "create",
            return_value=mock_resp,
        ):
            result = summarizer.summarize(SAMPLE_ARTICLES)
        assert result == expected

    def test_empty_articles_returns_no_articles_message(self, summarizer):
        result = summarizer.summarize([])
        assert "No articles" in result

    def test_raises_on_openai_error(self, summarizer):
        with patch.object(
            summarizer.client.chat.completions,
            "create",
            side_effect=Exception("quota exceeded"),
        ):
            with pytest.raises(Exception, match="quota exceeded"):
                summarizer.summarize(SAMPLE_ARTICLES)

    def test_system_prompt_sent_to_openai(self, summarizer):
        mock_resp = self._mock_openai_response("summary")
        with patch.object(
            summarizer.client.chat.completions,
            "create",
            return_value=mock_resp,
        ) as mock_create:
            summarizer.summarize(SAMPLE_ARTICLES)
        messages = mock_create.call_args.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert "news editor" in messages[0]["content"].lower()
