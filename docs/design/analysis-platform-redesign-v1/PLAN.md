# Analysis Platform Redesign V1

## Summary

This archive records the next analysis-layer direction for Falcon: move the current analysis UI from a backend-management feeling into an AI creation platform workflow. The production `/analysis` page is not changed in this handoff. The goal is to leave a clear visual reference and implementation plan so the next machine can pull the repo and continue without reconstructing the brief from chat history.

## Design Assets

- Local fallback mockup: `analysis-platform-redesign-v1.png`
- Intended image2 prompt: see `Image2 Prompt` below.
- Image2 status on 2026-05-29: attempted but not completed because the configured relay returned `403 Forbidden error code: 1010`, TLS/EOF, and empty HTTP responses from this Mac. The API key was read from `~/.codex/image2.toml` and was not printed or stored.

The checked-in PNG is a deterministic local fallback mockup generated from HTML/CSS and Playwright so the handoff still has a visual target. Replace it with a true image2 output when the relay is reachable from the next machine.

## Product Direction

The analysis layer should feel like a focused AI creation platform, not an admin dashboard. The page should help the user assemble a data package, create or continue probes, run analysis, audit the stream, and resume historical work.

Core principles:

- Keep the analysis queue independent from the collector queue.
- Let users multi-select completed collection tasks into one data package.
- Treat every probe-analysis attempt as a resumable history item.
- Make stream progress understandable at a glance; keep raw model output available but secondary.
- Size controls for real work instead of filling the screen with oversized cards.

## Information Architecture

Top creation area:

- Page title: `分析工作台`.
- Medium-height analysis intent input for the current brief.
- Current data package summary with selected task count, post count, total likes, total saves, and total comments.
- Primary action `新建分析`, plus secondary actions such as `保存草稿` and `继续编辑`.

Main left area:

- Multi-select collection-task list used only for choosing data-package inputs.
- Each row shows: keyword, post count, total likes, total saves, total comments.
- Only completed collection tasks should be selectable for production analysis packages.
- Row density should support comparison. Avoid giant cards for every task.

Main right area:

- Data package summary with dedupe status, selected task count, sample count, date range, and topic tags.
- Probe module with saved-probe entry points: `生成探针`, `打开已保存`, `继续编辑`, `删除`.
- Probe text area should be readable but not huge. It should show the current probe goal, matching logic, positive signals, and exclusion signals.

Bottom or side area:

- History progress cards, one per previous probe-analysis task.
- Each card must show three phases: `数据包阶段`, `探针生成`, `分析完成`.
- Each card should expose one clear recovery action: `继续编辑`, `继续分析`, or `恢复到结果`.
- Avoid stacking many equal-weight buttons on history cards.

Independent analysis execution queue:

- This queue shows only work that has entered the execution/analysis-data phase.
- It must not mix collection tasks or collector runtime states.
- It should show task name, queue state, progress, sample count, and an estimate when available.

## Stream UX

Current GPT-5.5 generation uses a stream interface, but raw token output alone is hard to read. Use a hybrid model:

- Default view: stage progress first.
- Stages for probe creation: connect model, generate probe, validate JSON, save probes.
- Stages for analysis execution: lock data package, run probe matching, persist evidence, summarize result.
- Raw realtime output: collapsed drawer named `实时输出`.
- Errors: high-priority toast/dialog that stays above all panels and overlays.
- On completion: convert stream panel into a compact result summary with `查看结果` or `继续编辑`.

## Size And Layout Rules

- Do not stretch modules just to fill the viewport.
- Use a medium-height textarea for analysis intent; it should invite a brief, not a full report.
- Use medium-density rows for collection tasks so metrics remain comparable.
- Keep probe editing comfortable, but smaller than the data table and history combined.
- Use compact history cards optimized for scanning and recovery.
- Prefer one strong primary action per module; secondary actions should be quieter.
- Use color intentionally: teal primary, dark confirm/continue, amber pending/review, red delete/destructive.
- Add `?` help affordances to analysis modules so users can understand each block without leaving the page.

## Data And Backend Implications

Likely production changes:

- Add or formalize an analysis data-package concept independent from collector run records.
- Persist selected collection run ids and aggregate metrics at package creation time.
- Persist probe drafts separately from execution results so saved probes can be opened or continued later.
- Track analysis history state with phase fields: package, probe, result.
- Keep analysis execution queue records separate from collection queue records.
- Store stream events or summarized stream checkpoints when useful for recovery/debugging.

Suggested minimal state model:

```text
analysis_package
  id, platform, title, intent, selected_run_ids, post_count, like_count, save_count, comment_count, dedupe_summary, created_at, updated_at

analysis_probe_session
  id, package_id, status, current_phase, probes_json, draft_notes, stream_summary, created_at, updated_at

analysis_execution
  id, probe_session_id, status, progress_current, progress_total, result_summary, error_message, created_at, updated_at
```

## Implementation Roadmap

1. Add read models for completed collection runs with aggregate metrics.
2. Add data-package creation and update endpoints.
3. Add saved probe open/continue/delete actions.
4. Split analysis execution queue from collector queue in repository and templates.
5. Redesign `/analysis` around the archived layout.
6. Update streaming UI to phase-first display with a collapsible raw output drawer.
7. Add high-z-index toast/dialog styling so prompts and errors are never covered by panels.
8. Add focused tests for package selection metrics, resumable history phases, probe actions, and independent queue filtering.

## Validation Plan

After implementation, run:

```bash
python3 -m unittest discover -s tests
git diff --check
```

When the local workbench is running, smoke test:

```text
/analysis
```

Manual checks:

- Multi-select collection tasks updates package metrics.
- Saved probes can be opened, continued, and deleted.
- Probe count equals real saved data, not an untested display number.
- History cards restore the correct phase state.
- Analysis queue excludes collector queue items.
- Stream output shows stage progress first and keeps raw output collapsible.
- High-priority prompts and error boxes render above all other panels.

## Image2 Prompt

```text
High-fidelity desktop UI mockup, 1536x1024, for Falcon Agent analysis layer redesigned as an AI creation platform.
Only show the analysis layer, not collector pages. Light teal-gray workspace, restrained glass panels, dark crisp text, teal primary accent, tiny amber status accent, no purple gradients.
Layout: top compact creation area with title 分析工作台, medium-height analysis intent input, data package summary, primary button 新建分析. Main left: medium-density selectable collection-run list with columns 关键词, 帖子, 喜欢, 收藏, 评论. Main right: 数据包 summary and 意向探针 module with 生成探针, 打开已保存, 继续编辑, 删除 actions. Lower/right rail: 历史进度 cards with three clear phases 数据包阶段, 探针生成, 分析完成 and resume buttons. Separate section 分析执行队列 showing only analysis execution tasks. Hybrid streaming component: phase progress visible, collapsed 实时输出 drawer.
Sizing: practical input heights, compact rows, readable textareas, no oversized cards, no components stretched just to fill screen. Coordinated for operation, review, and audit. Chinese labels should be legible. Avoid admin dashboard feeling, marketing hero, decorative illustration, fake browser chrome, text overlap.
```

## Handoff Notes

On the next machine:

```bash
git pull
python3 -m unittest discover -s tests
```

Continue from this file. If image2 works there, regenerate `analysis-platform-redesign-v1.png` with the prompt above and commit the replacement before production UI work.
