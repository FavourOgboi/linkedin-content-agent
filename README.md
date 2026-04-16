# LinkedIn Content Agent V1

This project generates one day-specific LinkedIn post package plus two backup ideas from public AI/data signals, then archives the run locally and emails it for human review.

## What It Does

- Collects compliant public signals from RSS, Hacker News, Reddit, and optional YouTube feeds
- Builds a topic dossier for shortlisted angles, including supporting or conflicting sources
- Assigns a truth profile so the draft knows whether it should sound like a builder, applied analyst, amplifier, or exploratory voice
- Uses the OpenAI Responses API with structured JSON outputs
- Runs deterministic and model-based anti-generic checks
- Runs separate truth-alignment and originality guards before anything ships
- Archives every run to JSONL, Markdown, JSON, and a rebuildable SQLite cache
- Captures review decisions through a dedicated CLI command

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

Artifacts are written locally to:

- `data/outputs/` for generated JSON and Markdown
- `data/prompts/` for saved prompt/context payloads
- `data/history/` for run and review history
- `data/artifacts/` for the rebuildable SQLite cache
- `data/run_notes/` for optional first-hand experiment notes

## Truth-Aligned Authority Engine

The agent now separates source retrieval from writing posture:

- `signal -> topic dossier -> truth profile -> authority mode -> post`
- Default automated posture is `applied_analyst`, not `builder`
- The draft must make provenance explicit whenever the evidence is second-hand or mixed
- Builder authority is only allowed when you have a matching run note in `data/run_notes/`

Reviewer-facing artifacts now include:

- selected topic dossier
- authority mode
- source ownership
- evidence strength
- risk and conflict level
- originality audit

The public-facing LinkedIn draft does not expose those reviewer labels.

## Optional Run Notes

If you want true Builder authority in the future, add a JSON note under `data/run_notes/` or point `LCA_RUN_NOTES_DIR` somewhere else.

Example:

```json
{
  "topic": "Political benchmark replication",
  "summary": "I tried to replicate the refusal claim on a smaller workflow.",
  "observations": [
    "The refusal pattern did not reproduce cleanly.",
    "The safety layer looked setup-dependent."
  ],
  "measured": false,
  "created_at": "2026-04-16T09:00:00+01:00"
}
```

If no matching run note exists, automated runs will stay in `applied_analyst`, `amplifier`, `exploratory`, or `light` modes.

## Scheduling

GitHub Actions workflow files are included under `.github/workflows/`. They expect:

- OpenAI credentials in repository secrets
- SMTP settings in repository secrets

In the current public-repo-safe setup, the scheduled workflow sends the email but does not commit generated runs, prompts, review history, or SQLite cache back into the repository. Local runs still write those files under `data/`, but they are gitignored so they stay out of the public repo.

If you want review records, use the local CLI command after a run:

```bash
python -m linkedin_content_agent.cli review --run-id RUN_ID --decision approved --notes "Good hook. Keep this angle."
```

## Windows Task Scheduler

If GitHub Actions is blocked by account billing, you can run the agent locally every day with Windows Task Scheduler.

1. Make sure your local `.env` is already filled in.
2. Run the registration script once:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register_daily_task.ps1 -Time 08:00
```

3. Windows will create a task named `LinkedIn Content Agent Daily` that runs the local agent script every day at `08:00` local time.
4. The runner script writes logs to `data/logs/`.

Useful local scheduler commands:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_daily_agent.ps1
```

```powershell
Start-ScheduledTask -TaskName "LinkedIn Content Agent Daily"
```

```powershell
Get-ScheduledTask -TaskName "LinkedIn Content Agent Daily"
```

This scheduler path does not depend on GitHub secrets or GitHub billing. It uses your local `.env` only.
