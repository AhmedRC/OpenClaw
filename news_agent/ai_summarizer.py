"""
AI Summarizer Agent - Uses OpenAI to summarize a list of news articles.
"""

import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

_DEFAULT_SYSTEM_PROMPT = (
    "You are a professional news editor. "
    "Given a list of today's news articles, write a concise, well-structured "
    "daily digest in the same language as the articles. "
    "Group related topics together, highlight the most important stories first, "
    "and keep each item to 2-3 sentences."
)


class AISummarizer:
    """Agent that uses OpenAI to summarise news articles into a daily digest."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        system_prompt: str = _DEFAULT_SYSTEM_PROMPT,
        max_tokens: int = 2048,
        temperature: float = 0.4,
    ):
        """
        Initialize the summarizer.

        Args:
            api_key: OpenAI API key.
            model: Chat completion model to use.
            system_prompt: System instruction for the model.
            max_tokens: Maximum tokens for the summary response.
            temperature: Sampling temperature (0 = deterministic).
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.temperature = temperature

    def summarize(self, articles: list[dict]) -> str:
        """
        Summarise a list of article dicts into a daily news digest.

        Args:
            articles: List of article dicts as returned by NewsFetcher.

        Returns:
            A string containing the AI-generated daily digest.
        """
        if not articles:
            logger.warning("No articles provided for summarisation.")
            return "No articles available for today's digest."

        user_content = self._build_user_message(articles)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
        except Exception as exc:
            logger.error("OpenAI request failed: %s", exc)
            raise

        summary = response.choices[0].message.content or ""
        logger.info(
            "Summary generated (%d chars) using model '%s'.", len(summary), self.model
        )
        return summary

    def _build_user_message(self, articles: list[dict]) -> str:
        """Format the list of articles into a prompt string."""
        lines = ["Here are today's news articles:\n"]
        for idx, article in enumerate(articles, start=1):
            lines.append(f"{idx}. **{article['title']}** ({article['source']})")
            if article.get("description"):
                lines.append(f"   {article['description']}")
            if article.get("url"):
                lines.append(f"   URL: {article['url']}")
            lines.append("")
        lines.append(
            "\nPlease write a comprehensive daily news digest based on the above articles."
        )
        return "\n".join(lines)
