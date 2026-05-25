# Collector Evidence Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Falcon collector manual-action and failure states produce durable evidence: screenshot when possible, JSON state snapshot always, and event payloads that explain the exact detection signal.

**Architecture:** The Node sidecar owns browser-state evidence capture because it has the live Playwright page. It emits ordinary `evidence` records so the existing Python ingest path can persist them, and the Web run detail page renders those evidence records as part of the existing evidence summary.

**Tech Stack:** Node.js ESM, Playwright, Python unittest, FastAPI/Jinja, SQLite repository.

---

## File Map

- Modify `sidecar/collector/xiaohongshu.mjs`: capture manual-action snapshots and screenshots, include matched signal metadata, expose small helpers for tests.
- Modify `sidecar/collector/index.mjs`: attach failure evidence to `run_failed` when errors provide partial records.
- Modify `tests/test_sidecar_contract.py`: TDD coverage for manual-action screenshot + JSON snapshot, screenshot failure fallback, and failure evidence partial records.
- Modify `falcon/collector.py`: only if ingest needs a small compatibility adjustment for evidence scopes; existing generic evidence ingest should usually be enough.
- Modify `falcon/web/templates/collector_run.html`: render manual-action/failure evidence payload details clearly.
- Modify `tests/test_collector_service.py`: verify evidence records with the new scopes are ingested.
- Modify `tests/test_web_app.py`: verify run detail displays evidence chain fields.
- Modify `docs/progress.md`: handoff summary after implementation and validation.

---

### Task 1: Sidecar Manual-Action Evidence

**Owner:** Gibbs subagent

**Files:**
- Modify: `sidecar/collector/xiaohongshu.mjs`
- Test: `tests/test_sidecar_contract.py`

- [ ] **Step 1: Write the failing test for successful screenshot + snapshot evidence**

Add a sidecar contract test near existing `manualActionRecords` coverage:

```python
def test_xiaohongshu_manual_action_records_snapshot_and_screenshot_evidence(self):
    script = r"""
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { manualActionRecords, normalizeCollectorRequest } from "./sidecar/collector/xiaohongshu.mjs";

const events = [];
const assetsPath = mkdtempSync(join(tmpdir(), "falcon-manual-evidence-"));
const page = {
  url() { return "https://www.xiaohongshu.com/explore"; },
  async title() { return "XHS warning"; },
  locator(selector) {
    return {
      async count() { return selector === "body" ? 1 : 0; },
      first() { return this; },
      nth() { return this; },
      async all() { return [this]; },
      async boundingBox() { return { x: 0, y: 0, width: 800, height: 600 }; },
      async innerText() { return "账号违规预警：检测到第三方工具或自动浏览脚本"; },
      async textContent() { return "账号违规预警：检测到第三方工具或自动浏览脚本"; },
    };
  },
  async screenshot(options) {
    await import("node:fs/promises").then(({ writeFile }) => writeFile(options.path, "png"));
  },
};
const records = await manualActionRecords({
  page,
  request: normalizeCollectorRequest({ run_id: "manual-evidence-run", platform: "xiaohongshu" }),
  assetsPath,
  events: { write(level, scope, event, message, payload) { events.push({ level, scope, event, message, payload }); } },
  reason: "account_risk_warning",
  detail: "检测到账号违规预警",
  matchedSignals: ["账号违规预警"],
});
const snapshot = records.find((record) => record.scope === "manual_action_snapshot");
const screenshot = records.find((record) => record.scope === "manual_action_screenshot");
console.log(JSON.stringify({
  event: events[0],
  scopes: records.map((record) => record.scope),
  snapshotPayload: snapshot?.payload,
  snapshotFile: JSON.parse(readFileSync(snapshot.path, "utf8")),
  screenshotPath: screenshot?.path || "",
}));
rmSync(assetsPath, { recursive: true, force: true });
"""
    result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False)
    self.assertEqual(result.returncode, 0, result.stderr)
    payload = json.loads(result.stdout)
    self.assertIn("manual_action_snapshot", payload["scopes"])
    self.assertIn("manual_action_screenshot", payload["scopes"])
    self.assertEqual(payload["snapshotPayload"]["reason"], "account_risk_warning")
    self.assertIn("账号违规预警", payload["event"]["payload"]["matched_signals"])
    self.assertTrue(payload["screenshotPath"].endswith(".png"))
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
py -3 -m unittest tests.test_sidecar_contract.SidecarContractTests.test_xiaohongshu_manual_action_records_snapshot_and_screenshot_evidence -v
```

Expected: fail because `manual_action_snapshot` is not emitted yet.

- [ ] **Step 3: Implement minimal sidecar support**

Add helpers in `sidecar/collector/xiaohongshu.mjs`:

```js
async function captureEvidenceSnapshot(page, { reason, detail, matchedSignals = [], screenshotError = "" } = {}) {
  return {
    reason,
    detail,
    matched_signals: matchedSignals,
    screenshot_error: screenshotError,
    url: safePageUrl(page),
    title: await safePageTitle(page),
    visible_text: await visibleTextForSelectors(page, ["body"], 4000),
    blocking_text: await visibleTextForSelectors(
      page,
      ["[role='dialog']", "[class*='login']", "[class*='captcha']", "[class*='verify']", "[class*='modal']"],
      2500,
      { minimumSize: 40 },
    ),
    captured_at: new Date().toISOString(),
  };
}
```

Update `manualActionRecords` to:
- accept `matchedSignals = []`
- write `manual-action-<reason>-snapshot.json`
- emit `manual_action_snapshot` evidence record
- rename screenshot evidence scope to `manual_action_screenshot`
- include `snapshot`, `matched_signals`, and `screenshot_error` in event payload

- [ ] **Step 4: Run red test again to verify green**

Run the same focused unittest. Expected: PASS.

- [ ] **Step 5: Run adjacent sidecar tests**

Run:

```powershell
py -3 -m unittest tests.test_sidecar_contract.SidecarContractTests.test_xiaohongshu_manual_action_survives_closed_page_screenshot_failure tests.test_sidecar_contract.SidecarContractTests.test_xiaohongshu_account_risk_warning_triggers_manual_action -v
node --check sidecar\collector\xiaohongshu.mjs
```

Expected: PASS and no syntax output from `node --check`.

---

### Task 2: Sidecar Failure Evidence

**Owner:** Gibbs subagent

**Files:**
- Modify: `sidecar/collector/xiaohongshu.mjs`
- Modify: `sidecar/collector/index.mjs`
- Test: `tests/test_sidecar_contract.py`

- [ ] **Step 1: Write the failing test for run_failed partial evidence**

Add a test that creates an error with `partialRecords` containing a `failure_snapshot` evidence record and verifies `index.mjs` preserves it when writing partial records.

- [ ] **Step 2: Run the focused test and confirm red**

Run:

```powershell
py -3 -m unittest tests.test_sidecar_contract.SidecarContractTests.test_sidecar_run_failed_preserves_failure_evidence -v
```

Expected: fail until catch path preserves failure evidence consistently.

- [ ] **Step 3: Implement minimal failure helper**

Add a helper in `xiaohongshu.mjs`:

```js
export async function failureEvidenceRecords({ page, request, assetsPath, reason, error }) {
  const snapshotPath = join(assetsPath, `failure-${reason}-snapshot.json`);
  const payload = await captureEvidenceSnapshot(page, {
    reason,
    detail: error?.message || String(error || ""),
  });
  await writeFile(snapshotPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  return [
    evidenceRecord({
      request,
      evidenceId: `${request.run_id}-failure-${reason}-snapshot`,
      scope: "failure_snapshot",
      path: snapshotPath,
      payload,
    }),
  ];
}
```

Use it only where a live `page` is available before throwing. `index.mjs` should continue to write `error.partialRecords` with `writePartialRecordsOnError`.

- [ ] **Step 4: Verify focused and sidecar suite**

Run:

```powershell
py -3 -m unittest tests.test_sidecar_contract -v
```

Expected: all sidecar contract tests pass.

---

### Task 3: Python Ingest and Run Detail Display

**Owner:** Sagan subagent

**Files:**
- Modify if needed: `falcon/collector.py`
- Modify: `falcon/web/templates/collector_run.html`
- Test: `tests/test_collector_service.py`
- Test: `tests/test_web_app.py`

- [ ] **Step 1: Write the failing ingest test**

Add a test in `tests/test_collector_service.py` that writes `records.jsonl` containing:

```json
{"type":"evidence","run_id":"evidence-run","platform":"xiaohongshu","evidence_id":"evidence-run-manual-action-snapshot","scope":"manual_action_snapshot","path":"runtime/collector/evidence-run/assets/manual-action-account_risk_warning-snapshot.json","payload":{"reason":"account_risk_warning","url":"https://www.xiaohongshu.com/explore","title":"XHS warning","matched_signals":["账号违规预警"]}}
```

Expected assertion:

```python
evidences = repo.list_evidences("evidence-run")
self.assertEqual(evidences[0].scope, "manual_action_snapshot")
self.assertIn("account_risk_warning", evidences[0].payload_json)
```

- [ ] **Step 2: Run focused ingest test and confirm red or existing support**

Run:

```powershell
py -3 -m unittest tests.test_collector_service.CollectorServiceTest.test_ingest_manual_action_evidence_chain_records -v
```

If it already passes, no production ingest change is needed.

- [ ] **Step 3: Write the failing Web display test**

Add a test in `tests/test_web_app.py` that creates a manual-action run and saves two evidences with scopes `manual_action_snapshot` and `manual_action_screenshot`, then GETs `/collector/runs/<run_id>` and asserts:

```python
self.assertIn("manual_action_snapshot", response.text)
self.assertIn("account_risk_warning", response.text)
self.assertIn("https://www.xiaohongshu.com/explore", response.text)
self.assertIn("manual_action_screenshot", response.text)
```

- [ ] **Step 4: Update template minimally**

In `falcon/web/templates/collector_run.html`, make each evidence row/card show:
- `evidence.scope`
- local `evidence.path`
- compact payload fields when present: `reason`, `url`, `title`, `matched_signals`, `screenshot_error`

Do not make external platform links clickable.

- [ ] **Step 5: Verify focused Web tests**

Run:

```powershell
py -3 -m unittest tests.test_collector_service.CollectorServiceTest.test_ingest_manual_action_evidence_chain_records tests.test_web_app.WebAppTest.test_collector_run_detail_shows_manual_action_evidence_chain -v
```

Expected: PASS.

---

### Task 4: Integration, Handoff, and Validation

**Owner:** main agent

**Files:**
- Modify: `docs/progress.md`

- [ ] **Step 1: Review subagent changes**

Check:

```powershell
git diff -- sidecar\collector\xiaohongshu.mjs sidecar\collector\index.mjs tests\test_sidecar_contract.py
git diff -- falcon\collector.py falcon\web\templates\collector_run.html tests\test_collector_service.py tests\test_web_app.py
```

- [ ] **Step 2: Resolve conflicts without reverting unrelated edits**

Keep existing worktree changes unless they directly conflict with this feature.

- [ ] **Step 3: Run verification**

Run:

```powershell
node --check sidecar\collector\xiaohongshu.mjs
node --check sidecar\collector\index.mjs
py -3 -m unittest tests.test_sidecar_contract -v
py -3 -m unittest tests.test_collector_service -v
py -3 -m unittest tests.test_web_app -v
py -3 -m unittest discover -s tests
py -3 -m compileall falcon
```

- [ ] **Step 4: Update progress handoff**

Add a dated section to `docs/progress.md` with:
- implemented evidence-chain behavior
- tests run and results
- known limitations: no video/trace, screenshots may still fail if browser already closed, JSON snapshot remains fallback
- Windows/Mac notes: no new dependencies

- [ ] **Step 5: Final status**

Report:
- changed files
- verification commands and exact pass/fail status
- whether current run `xiaohongshu-20260525-152703-0952d0` can be retroactively proven (it cannot; only future runs get stronger evidence)
