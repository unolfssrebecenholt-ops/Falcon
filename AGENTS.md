# Codex Local Notes

- Keep normal Codex chat, code editing, and completions on the provider configured in `~/.codex/config.toml`.
- When the user asks to use image2 for image generation or editing, read `~/.codex/image2.toml` and call `base_url` + `endpoint` with OpenAI-style Bearer auth.
- Do not route normal Codex requests through image2, and do not print the full image2 API key.
- Always use the GPT-5.5 model for this project in every scenario, including subagents, subprocesses, simple tasks, and any delegated or background work. Do not downgrade or switch to smaller/faster models unless the user explicitly overrides this rule.

## Dual-machine development rules

- The project is developed from both Windows and M1 Mac machines. GitHub is the shared source of truth.
- At the start of every development session, run `git pull`, then read this file, `README.md`, `docs/progress.md`, `docs/development-guide.md`, and `project.md`.
- If the user says only "开始工作", follow the start-work protocol below without asking them to paste the reading order again.
- Before committing, update `docs/progress.md` with current project progress, solved problems, known problems, next steps, validation results, and any Windows/Mac notes needed by the other machine.
- Every commit should leave the repository in a handoff-ready state: another machine should be able to `git pull` and continue from `docs/progress.md`.
- Do not commit local runtime data, generated reports, `.env`, real API keys, cache files, or machine-specific IDE settings.
- The project must remain runnable on both Windows and macOS. Prefer Python standard library code, cross-platform paths via `pathlib`, and commands that have Windows and macOS equivalents.
- If adding dependencies later, document installation commands for both Windows and macOS in `docs/development-guide.md`.

## Yingdao RPA rules

- Before answering, designing, debugging, or modifying anything related to 影刀/Yingdao RPA, first read the project Yingdao materials:
  - `docs/rpa-elements/yingdao-assistant-rules.md`
  - `docs/rpa-elements/yingdao-component-handbook.md`
  - `docs/rpa-elements/yingdao-hybrid-architecture-guide.md`
  - `docs/yingdao-runbook.md`
  - `docs/rpa-elements/current-yingdao-mainflow.md`
  - `docs/rpa-elements/xiaohongshu-workflow-draft.md`
- After reading them, answer Yingdao workflow questions in pseudo-workflow format, reuse the user's existing step names and variables, and prefer disabling nodes over deleting them when preserving line order matters.

## Start-work protocol

When the user says "开始工作":

1. Run `git pull`.
2. Read `AGENTS.md`.
3. Read `docs/progress.md`.
4. Read `docs/development-guide.md`.
5. Read `README.md` and `project.md` as needed for product context.
6. Run the baseline test command from `docs/development-guide.md`.
7. Check `git status -sb`.
8. Continue with the next item in `docs/progress.md` unless the user gives a newer priority.

## Commit handoff checklist

Before every commit:

1. Run the relevant tests or smoke workflow.
2. Update `docs/progress.md`.
3. Confirm `git status -sb` only includes intended files.
4. Commit with a clear message.
5. Push to GitHub so the other machine can continue.
