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

## Codex data collection rules

- The default new collection path is Codex-driven browser collection, not Yingdao. Yingdao/ShadowBlade is now a legacy/fallback collection path: keep the existing module, docs, adapters, and tests for now, but do not make Yingdao the default path for new data collection work unless the user explicitly asks for it.
- When the user says a phrase like `开始采集：平台=小红书；关键词=ai头像,小红书封面；每个关键词=30条`, first read `docs/codex-collection-guide.md`, then read the matching file in `docs/collection-platforms/`.
- Version 1 only creates local collection asset bundles. Do not run Falcon analysis, reports, outreach tasks, or Web analysis after collection unless the user explicitly asks for a later data-use step.
- Supported platform slugs and profile docs:
  - `小红书` / `xiaohongshu`: `docs/collection-platforms/xiaohongshu.md`
  - `抖音` / `douyin`: `docs/collection-platforms/douyin.md`
  - `闲鱼` / `xianyu`: `docs/collection-platforms/xianyu.md`
  - `微博` / `weibo`: `docs/collection-platforms/weibo.md`
- For verified platforms, use real browser interactions for content access: mouse movement, coordinate click, wheel scroll, keyboard input, and ESC/close controls. Do not use JavaScript click to open content cards. Do not directly visit transient detail links as the normal card-entry path. Do not save transient platform links in the v1 CSV.
- Store collection output under `datas/{platform_slug}/{keyword}_{yyyyMMddHHmm}/` with `{keyword}_{yyyyMMddHHmm}.csv`, `assets/`, `collection_steps.md`, and optional `extra.jsonl`. Write a run summary to `datas/{platform_slug}/run_summary_{yyyyMMddHHmm}.json`.
- The v1 CSV header is fixed as `platform,title,content,published_at,like_count,collect_count,comment_count,cover_asset_name,asset_names`.
- Use the shared scripts under `scripts/collection/core/` for paths, CSV writing, asset writing, summaries, text cleaning, dedupe, and login flow. Keep platform-specific behavior under `scripts/collection/platforms/`.
- Semi-automatic login is the default. Reuse the current browser session first. If login is required, choose phone login, enter `17630962337`, request the verification code, then stop and wait for the user to send the code in chat. The verification code is only used in the current conversation and must never be written to CSV, logs, summaries, docs, or any local file. In local logs, mask the phone as `176****2337`.
- For unverified platform profiles, only perform small-scale probing and write findings. Do not promise or run bulk collection until the profile has a verified card-entry, detail-read, asset-extraction, and close/scroll loop.
