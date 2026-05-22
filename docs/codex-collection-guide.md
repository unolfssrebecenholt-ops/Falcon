# Codex Data Collection Guide

This guide defines the Falcon v1 Codex collection path. It replaces Yingdao as the default path for new collection work, while keeping the existing Yingdao module as legacy/fallback material.

## Trigger

Use this format to start a collection task:

```text
开始采集：平台=小红书；关键词=ai头像,小红书封面；每个关键词=30条
```

Codex must read this guide and then the matching platform profile before collecting.

Supported platform names:

| User name | Slug | Profile |
| --- | --- | --- |
| 小红书 | `xiaohongshu` | `docs/collection-platforms/xiaohongshu.md` |
| 抖音 | `douyin` | `docs/collection-platforms/douyin.md` |
| 闲鱼 | `xianyu` | `docs/collection-platforms/xianyu.md` |
| 微博 | `weibo` | `docs/collection-platforms/weibo.md` |

## V1 Boundary

- V1 creates local collection asset bundles only.
- Do not run Falcon analysis, reports, outreach tasks, or Web analysis after collection unless the user explicitly asks for a later data-use step.
- Do not delete Yingdao docs, adapters, tests, or prototypes. They are legacy/fallback material until the Codex path is stable.
- Do not commit local collection data. `datas/` is local runtime output.

## Output Layout

Each keyword gets its own folder:

```text
datas/{platform_slug}/{keyword}_{yyyyMMddHHmm}/
  {keyword}_{yyyyMMddHHmm}.csv
  assets/
  collection_steps.md
  extra.jsonl        # optional, platform-specific fields

datas/{platform_slug}/run_summary_{yyyyMMddHHmm}.json
```

Use the same timestamp for all keyword folders in one run.

## CSV Contract

The v1 CSV header is fixed:

```csv
platform,title,content,published_at,like_count,collect_count,comment_count,cover_asset_name,asset_names
```

Rules:

- `platform` is the platform slug.
- `title` is the visible title. If a platform has no title, use a short stable text fallback.
- `content` is the main body, description, product text, or post text.
- `published_at` is the visible platform time string.
- `like_count`, `collect_count`, and `comment_count` are visible interaction counts when available.
- `cover_asset_name` is the first main asset saved locally.
- `asset_names` contains the remaining asset filenames joined by `|`.
- Do not include transient platform links in this CSV.

Platform-specific fields go to `extra.jsonl`, one JSON object per collected CSV row:

```json
{"row_index":1,"platform":"xianyu","price":"99","location":"上海","seller":"example"}
```

## Browser Interaction Rules

- Use real browser interaction for content access: mouse movement, coordinate click, wheel scroll, keyboard input, and ESC/close buttons.
- Do not use JavaScript click to open content cards.
- Do not directly visit transient detail links as the normal card-entry path.
- DOM reads are allowed for observing visible state and extracting fields after the page has been reached through human-like interaction.
- Scroll waterfalls in rounds: read current visible cards, process them, discard stale card references, then scroll and re-read.
- Use low-frequency waits between interactions.

## Semi-Automatic Login

Default phone: `17630962337`.

Flow:

1. Reuse the current browser login state first.
2. If login is required, open or locate the login dialog.
3. Select phone login.
4. Enter `17630962337`.
5. Click the verification-code button.
6. Stop collection and ask the user to send the code in chat.
7. Enter the code and submit.
8. Continue collection after login succeeds.

Safety rules:

- Never write the verification code to CSV, `collection_steps.md`, `run_summary.json`, `extra.jsonl`, screenshots, docs, or local config.
- In logs, mask the phone as `176****2337`.
- Do not export or persist cookies, tokens, or localStorage.
- If extra authorization, device verification, captcha, or risk-control challenges appear, stop and ask the user.
- Retry login at most twice.

## Failure Handling

Record failures in `collection_steps.md` and `run_summary.json` without sensitive values.

Common reasons:

- `login_required`
- `waiting_for_verification_code`
- `captcha_or_risk_control`
- `detail_not_opened`
- `empty_detail`
- `asset_download_failed`
- `no_new_cards`
- `browser_connection_timeout`

For verified platforms, continue after non-fatal item failures until the target count is reached or the platform profile stop condition is met.

For unverified platforms, only run probing. Do not bulk collect until the platform profile has a verified search, card-entry, detail-read, asset-extraction, close, and scroll loop.

## Script Layout

Shared helpers:

```text
scripts/collection/core/
  paths.mjs
  csv_writer.mjs
  asset_writer.mjs
  summary_writer.mjs
  text_cleaner.mjs
  dedupe.mjs
  login_flow.mjs
```

Platform profiles:

```text
scripts/collection/platforms/
  xiaohongshu.mjs
  douyin.mjs
  xianyu.mjs
  weibo.mjs
```

The shared layer handles how to save. Platform profiles handle how to collect.
