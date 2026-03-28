# OpenClaw – Daily AI News Digest

A fully automated scheduling system that **fetches the latest news**, **summarises it with AI**, and **writes the digest to a Google Document** every day.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  GitHub Actions Cron (daily @ 07:00 UTC)                        │
│                                                                  │
│  scheduler.py                                                    │
│    │                                                             │
│    ├─► NewsFetcher  ──► NewsAPI.org       (fetch headlines)      │
│    │                                                             │
│    ├─► AISummarizer ──► OpenAI API        (summarise articles)   │
│    │                                                             │
│    └─► GoogleDocsWriter ──► Google Docs   (write daily digest)   │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/AhmedRC/OpenClaw.git
cd OpenClaw
pip install -r requirements.txt
```

### 2. Set environment variables

Copy the template and fill in your credentials:

```bash
cp .env.example .env   # edit .env with your keys
```

| Variable | Required | Description |
|---|---|---|
| `NEWS_API_KEY` | ✅ | [NewsAPI.org](https://newsapi.org) API key |
| `OPENAI_API_KEY` | ✅ | OpenAI API key |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | ✅ | Full JSON content of a Google service-account key |
| `GOOGLE_DOCUMENT_ID` | ⬜ | Existing Google Doc ID to append to (creates a new doc each run if omitted) |
| `NEWS_LANGUAGE` | ⬜ | Article language code (default: `en`) |
| `NEWS_CATEGORIES` | ⬜ | Comma-separated categories (default: `general`) |
| `NEWS_COUNTRY` | ⬜ | 2-letter country code for top headlines (default: `us`) |
| `OPENAI_MODEL` | ⬜ | OpenAI model name (default: `gpt-4o-mini`) |

### 3. Run manually

```bash
python scheduler.py
```

## Automated Daily Scheduling

The included GitHub Actions workflow (`.github/workflows/daily_news.yml`) runs the pipeline automatically every day at **07:00 UTC**.

### Setting up secrets in GitHub

Go to **Settings → Secrets and variables → Actions** in your repository and add:

- `NEWS_API_KEY`
- `OPENAI_API_KEY`
- `GOOGLE_SERVICE_ACCOUNT_JSON` (paste the entire JSON key file content)
- `GOOGLE_DOCUMENT_ID` (optional – the Google Doc to write into)

### Manual trigger

You can also trigger the workflow manually from the **Actions** tab in GitHub, optionally specifying categories and country.

## Google Service Account Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project.
2. Enable the **Google Docs API**.
3. Create a **Service Account** and download the JSON key.
4. If using an existing Google Doc, share it with the service account email (`...@...iam.gserviceaccount.com`) as **Editor**.

## Project Structure

```
OpenClaw/
├── news_agent/
│   ├── __init__.py
│   ├── news_fetcher.py       # Fetches headlines from NewsAPI
│   ├── ai_summarizer.py      # Summarises articles with OpenAI
│   └── google_docs_writer.py # Writes digest to Google Docs
├── tests/
│   ├── test_news_fetcher.py
│   ├── test_ai_summarizer.py
│   ├── test_google_docs_writer.py
│   └── test_scheduler.py
├── .github/workflows/
│   └── daily_news.yml        # GitHub Actions cron workflow
├── scheduler.py              # Main pipeline entry point
├── requirements.txt
└── README.md
```

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

## News Categories

Supported categories for `NEWS_CATEGORIES`:

`general`, `business`, `entertainment`, `health`, `science`, `sports`, `technology`
