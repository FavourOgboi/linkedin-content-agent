# LinkedIn Content Agent V1

This project generates one day-specific LinkedIn post package plus two backup ideas from public AI/data signals, then archives the run and emails it for human review.

## What It Does

- Collects compliant public signals from RSS, Hacker News, Reddit, and optional YouTube feeds
- Scores topics against a defined creator positioning
- Uses the OpenAI Responses API with structured JSON outputs
- Runs deterministic and model-based anti-generic checks
- Archives every run to JSONL, Markdown, JSON, and a rebuildable SQLite cache
- Captures review decisions through a dedicated CLI command and GitHub Actions workflow

## Quick Start

1. Create and activate a Python 3.11+ virtual environment.
2. Install the package:

```bash
pip install -e .
```

3. Copy `.env.example` to `.env` and fill in the required values.

```bash
copy .env.example .env
```

The CLI now loads `.env` automatically from the repo root.
4. Run the test suite:

```bash
python -m unittest discover -s tests -v
```

5. Run one manual content cycle:

```bash
python -m linkedin_content_agent.cli run --day Monday --topic "Using LLMs for data cleaning" --skip-email
```

6. Record a review decision:

```bash
python -m linkedin_content_agent.cli review --run-id RUN_ID --decision approved --notes "Strong hook, keep this angle."
```

## Minimum Local Setup

For a real content run, the only truly required key is:

- `OPENAI_API_KEY`

For email delivery, also provide:

- `LCA_SMTP_HOST`
- `LCA_SMTP_PORT`
- `LCA_SMTP_USERNAME`
- `LCA_SMTP_PASSWORD`
- `LCA_EMAIL_FROM`
- `LCA_EMAIL_TO`

If you only want to test generation without sending email, leave the SMTP fields blank and use `--skip-email`.

## Common Local Commands

Test the code without calling OpenAI:

```bash
python -m unittest discover -s tests -v
```

Generate one real post package but do not send email:

```bash
python -m linkedin_content_agent.cli run --day Monday --topic "Using LLMs for data cleaning" --skip-email
```

Generate one real post package and email it:

```bash
python -m linkedin_content_agent.cli run --day Monday --topic "Using LLMs for data cleaning"
```

Let the system auto-pick the topic for today:

```bash
python -m linkedin_content_agent.cli run --skip-email
```

Record your review decision after a run:

```bash
python -m linkedin_content_agent.cli review --run-id 20260415-070000-monday --decision approved --notes "Good hook. Keep this angle."
```

Artifacts are written to:

- `data/outputs/` for generated JSON and Markdown
- `data/prompts/` for saved prompt/context payloads
- `data/history/` for run and review history
- `data/artifacts/` for the rebuildable SQLite cache

## Scheduling

GitHub Actions workflow files are included under `.github/workflows/`. They expect:

- OpenAI credentials in repository secrets
- SMTP settings in repository secrets
- `contents: write` permission so the workflows can commit updated history files back to the repository

The runtime SQLite database is treated as a rebuildable cache and uploaded as a workflow artifact after each run. Human-readable history lives in `data/history/`.
