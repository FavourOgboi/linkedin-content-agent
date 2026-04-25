# LinkedIn Content Agent V1

This project generates one creator-first LinkedIn post package plus two backup ideas from public tech/data signals, then archives the run locally and emails it for human review.

## What It Does

- Collects compliant public signals from RSS, Hacker News, Reddit, and optional YouTube feeds
- Selects a creator post type (`insight`, `relatable`, `commentary`, `teaching`, `inspiration`) with stable day-based weighting
- Selects a content format (`text`, `photo`, `screenshot`, `carousel`, `infographic`) with stable day-based weighting
- Builds a topic dossier for shortlisted angles, including supporting or conflicting sources
- Assigns a truth profile so the draft knows whether it should sound like a builder, applied analyst, amplifier, exploratory voice, or light reflection
- Uses the OpenAI Responses API with structured JSON outputs
- Loads a tracked voice profile from `config/voice_profile.json`
- Runs deterministic and model-based anti-generic checks
- Runs separate truth-alignment and originality guards before anything ships
- Enforces creator-post length on the public-facing copy instead of letting drafts sprawl
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

You can also force the creator post type for a run:

```bash
python -m linkedin_content_agent.cli run --day Tuesday --post-type teaching --skip-email
```

You can also force the content format for a run:

```bash
python -m linkedin_content_agent.cli run --day Tuesday --post-type teaching --format carousel --skip-email
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

Let the system auto-pick the topic, but force a creator mode:

```bash
python -m linkedin_content_agent.cli run --post-type commentary --skip-email
```

Force both a creator post type and a format:

```bash
python -m linkedin_content_agent.cli run --post-type teaching --format infographic --skip-email
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

## Creator-First Strategy

The agent now separates weekday tone, creator post type, and content format:

- Weekday contracts still exist, but they act as a soft bias instead of a hard writing cage
- The main content system is now:
  - `insight`
  - `relatable`
  - `commentary`
  - `teaching`
  - `inspiration`
- The post type is selected deterministically from the day plus recent history unless you override it with `--post-type`
- The format is selected deterministically from the day plus recent history unless you override it with `--format`
- Manual-required formats always include a fallback plain-text post so you are never blocked
- Source selection is broader by default now, with stable feeds across data engineering, Python/backend, ML/AI, and practical learning topics
- Release-chasing LLM benchmark topics are penalized instead of dominating the queue

## Content Format Layer

Each run now chooses **how** the idea should show up, not just **what** it should say.

- `text`
  - A normal LinkedIn text post
- `photo`
  - A caption post plus a concrete brief for what to photograph
- `screenshot`
  - A caption post plus an exact screenshot brief, including what to crop or hide
- `carousel`
  - A slide-by-slide outline plus the caption that goes with it
- `infographic`
  - A visual brief plus the caption that goes with it

For non-text formats, the run output includes:

- the main caption/public copy
- a structured format plan
- a backup plain-text post in case you do not want to create the asset that day

The email subject now includes the selected format, for example:

- `Tuesday - teaching - CAROUSEL`
- `Friday - relatable - SCREENSHOT`
- `Saturday - inspiration - PHOTO`

## Truth-Aligned Authority Engine

The agent now separates source retrieval from writing posture:

- `signal -> topic dossier -> truth profile -> authority mode -> post`
- Default automated posture is `applied_analyst`, not `builder`
- First-person perspective is allowed, but fake experiments and unsupported metrics are still blocked
- Provenance is enforced where the post type and truth profile genuinely require it, not in every post
- Builder authority is only allowed when you have a matching run note in `data/run_notes/`

Reviewer-facing artifacts now include:

- selected topic dossier
- creator post type
- topic pillar
- authority mode
- source ownership
- evidence strength
- risk and conflict level
- originality audit

The public-facing LinkedIn draft does not expose those reviewer labels.

## Length Governance

The agent now enforces length on the actual public-facing post copy only:

- `hook`
- `draft_post`

It does **not** count reviewer metadata such as:

- `core_idea`
- `why_this_works`
- truth/originality review notes

Length rules are post-type-aware:

- `insight`
  - standard max `140` words, extended max `220`, max `12` non-empty lines
- `relatable`
  - standard max `70` words, no extended mode, max `6` non-empty lines
- `commentary`
  - standard max `160` words, extended max `250`, max `14` non-empty lines
- `teaching`
  - standard max `170` words, extended max `280`, max `16` non-empty lines
- `inspiration`
  - standard max `90` words, no extended mode, max `7` non-empty lines

Important rules:

- `extended` length is allowed only for `insight`, `commentary`, and `teaching`
- if the model requests `extended`, it must provide a one-sentence reason
- there is no minimum-word filler rule; brevity is allowed if the post lands cleanly
- hashtag-only lines are ignored for word-count enforcement

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

## Voice Profile

The creator voice is tracked in:

- `config/voice_profile.json`

That file defines:

- base writing rules
- banned corporate words
- hook patterns
- per-post-type notes

You can tune the voice there without changing the pipeline logic.

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
