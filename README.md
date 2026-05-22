# Falcon Agent

Falcon is being rebuilt as a local, human-confirmed content operations agent for `AI出图助手`.

The new direction is simple: Falcon should own the workflow. It should collect public platform signals through a real browser, structure the data and assets locally, use GPT-5.5 for analysis and writing, use Image2 for visual generation, and prepare execution previews that a human can review before anything is posted or sent.

The old external collection paths have been removed from this branch so the project can focus on the agent architecture.

![Falcon Agent 架构图](docs/assets/falcon-agent-architecture.png)

## Target Workflow

```text
Falcon Browser Collector
  -> Local data and asset store
  -> GPT-5.5 analysis
  -> Trend, intent, and comment insight
  -> GPT-5.5 copywriting + Image2 assets
  -> Recommendation queue
  -> Browser execution preview
  -> Human edit or confirmation
```

## Product Principles

- Falcon owns runtime collection. Codex is only a development assistant, not the production collection mechanism.
- Collection uses a real browser session with human-like navigation, scrolling, clicking, and pauses.
- Login, verification codes, risk controls, and final publishing decisions stay human-confirmed.
- Platform URLs, cookies, tokens, and verification codes are not stored as durable product data.
- Falcon does not automatically batch comment, private-message, or publish.
- Local runtime data, generated reports, browser profiles, and secrets stay out of Git.

## Target Modules

- `collector`: starts or connects to a browser, runs platform adapters, pauses for login or risk-control events, and emits normalized collection records.
- `asset store`: saves images, videos, screenshots, raw evidence, and collection logs under local ignored runtime directories.
- `normalizer`: maps platform-specific posts, comments, authors, media, metrics, and keywords into Falcon models.
- `dedupe`: performs weak pre-click filtering and strong post-detail content fingerprinting.
- `analysis`: uses rules and GPT-5.5 to identify intent, pain points, trends, and usable topics.
- `generation`: uses GPT-5.5 for copy and Image2 for covers or supporting assets.
- `workbench`: presents collection status, insights, generated drafts, assets, and review queues.
- `execution preview`: opens platform pages, fills drafts and assets, then waits for human confirmation.

## Current Branch State

This branch is a reboot branch. It keeps the reusable Falcon core and removes old collection baggage.

Kept:

- SQLite repository and domain models.
- Heuristic analysis.
- GPT-5.5 relay client.
- Image2 relay client and architecture-image command.
- Markdown report builder.
- Local FastAPI/Jinja workbench shell.
- Keyword planning utilities.
- Human review and outreach task queue primitives.

Removed:

- External workflow-builder materials and records.
- Old XLSX/CSV import adapters.
- Old daily-run commands and tests.
- Codex-conversation collection guide and helper scripts.
- Outdated prototypes tied to the old collection path.

## Quick Start

Install dependencies:

```bash
python3 -m pip install -e .
```

Windows PowerShell:

```powershell
py -3 -m pip install -e .
```

Initialize a local database:

```bash
python3 -m falcon --db data/falcon.sqlite3 init-db
```

Windows PowerShell:

```powershell
py -3 -m falcon --db data\falcon.sqlite3 init-db
```

Generate a keyword plan:

```bash
python3 -m falcon write-keyword-pool data/collection_keywords.csv --theme "生图小程序"
```

Windows PowerShell:

```powershell
py -3 -m falcon write-keyword-pool data\collection_keywords.csv --theme "生图小程序"
```

Run analysis on existing local records:

```bash
python3 -m falcon --db data/falcon.sqlite3 analyze --drafts template
python3 -m falcon --db data/falcon.sqlite3 report --output reports/daily-report.md
```

Windows PowerShell:

```powershell
py -3 -m falcon --db data\falcon.sqlite3 analyze --drafts template
py -3 -m falcon --db data\falcon.sqlite3 report --output reports\daily-report.md
```

Start the local workbench:

```bash
python3 -m falcon web --host 127.0.0.1 --port 8765 --db data/falcon.sqlite3
```

Windows PowerShell:

```powershell
py -3 -m falcon web --host 127.0.0.1 --port 8765 --db data\falcon.sqlite3
```

Open:

```text
http://127.0.0.1:8765
```

## GPT-5.5 And Image2

Copy `.env.example` to local `.env` and fill your relay settings. `.env` is ignored by Git.

GPT-5.5:

```text
FALCON_GPT_BASE_URL=
FALCON_GPT_ENDPOINT=/v1/chat/completions
FALCON_GPT_API_KEY=
FALCON_GPT_MODEL=gpt-5.5
FALCON_GPT_TIMEOUT=60
```

Image2:

```text
FALCON_IMAGE2_PRIMARY_BASE_URL=
FALCON_IMAGE2_PRIMARY_API_KEY=
FALCON_IMAGE2_FALLBACK_BASE_URL=
FALCON_IMAGE2_FALLBACK_API_KEY=
FALCON_IMAGE2_ENDPOINT=/v1/images/generations
FALCON_IMAGE2_MODEL=gpt-image-2
FALCON_IMAGE2_TIMEOUT=90
FALCON_IMAGE2_SIZE=1536x1024
```

Generate the architecture image:

```bash
python3 -m falcon generate-architecture-image --output reports/falcon-agent-architecture.png
```

Windows PowerShell:

```powershell
py -3 -m falcon generate-architecture-image --output reports\falcon-agent-architecture.png
```

## Development

Baseline tests:

```bash
python3 -m unittest discover -s tests
```

Windows PowerShell:

```powershell
py -3 -m unittest discover -s tests
```

Project rules live in `AGENTS.md` and `docs/development-guide.md`.
