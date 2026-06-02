import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIDECAR = ROOT / "sidecar" / "collector" / "index.mjs"
SIDECAR_PACKAGE = ROOT / "sidecar" / "collector" / "package.json"


def read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class SidecarContractTests(unittest.TestCase):
    def test_sidecar_package_documents_playwright_dependency(self):
        package = json.loads(SIDECAR_PACKAGE.read_text(encoding="utf-8"))

        self.assertEqual(package["type"], "module")
        self.assertIn("playwright", package["dependencies"])
        self.assertIn("dry-run", package["scripts"])

    def test_xiaohongshu_normalizer_canonicalizes_dedupes_and_cleans_card_fields(self):
        script = r"""
import {
  canonicalPostId,
  canonicalPostUrl,
  normalizeSearchCard,
  normalizeSearchCards,
} from "./sidecar/collector/xiaohongshu-normalize.mjs";

const first = normalizeSearchCard({
  href: "https://www.xiaohongshu.com/search_result/65abc123?xsec_token=one",
  text: "内容运营复盘技巧\n何花说升学\n04-04\n1.2万",
  title: "",
  author: "何花说升学04-04",
  likesText: "1.2万",
});
const duplicate = normalizeSearchCards(
  [
    first,
    {
      href: "https://www.xiaohongshu.com/explore/65abc123?xsec_token=two",
      text: "内容运营复盘技巧\n何花说升学\n04-04\n1.2万",
      title: "内容运营复盘技巧",
      author: "何花说升学",
      likesText: "1.2万",
    },
  ],
  5,
);

console.log(JSON.stringify({
  firstId: first.postId,
  secondId: canonicalPostId("https://www.xiaohongshu.com/explore/65abc123?xsec_token=two"),
  canonicalUrl: canonicalPostUrl(first.href),
  title: first.title,
  author: first.author,
  publishedAt: first.published_at,
  likes: first.metrics.likes,
  duplicateCount: duplicate.length,
}));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["firstId"], "xiaohongshu:65abc123")
        self.assertEqual(payload["secondId"], payload["firstId"])
        self.assertEqual(payload["canonicalUrl"], "https://www.xiaohongshu.com/explore/65abc123")
        self.assertEqual(payload["title"], "内容运营复盘技巧")
        self.assertEqual(payload["author"], "何花说升学")
        self.assertEqual(payload["publishedAt"], "04-04")
        self.assertEqual(payload["likes"], 12000)
        self.assertEqual(payload["duplicateCount"], 1)

    def test_xiaohongshu_normalizer_preserves_full_search_card_dates(self):
        script = r"""
import { normalizeSearchCard } from "./sidecar/collector/xiaohongshu-normalize.mjs";

const card = normalizeSearchCard({
  href: "https://www.xiaohongshu.com/explore/68c66840000000001c03f6ef",
  text: "账号增长工具的一些靠谱用法【附流程】\n运营工具箱\n2025-09-14\n162",
  title: "账号增长工具的一些靠谱用法【附流程】",
  author: "运营工具箱",
  likesText: "162",
});

console.log(JSON.stringify({
  title: card.title,
  author: card.author,
  publishedAt: card.published_at,
  likes: card.metrics.likes,
}));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["title"], "账号增长工具的一些靠谱用法【附流程】")
        self.assertEqual(payload["author"], "运营工具箱")
        self.assertEqual(payload["publishedAt"], "2025-09-14")
        self.assertEqual(payload["likes"], 162)

    def test_xiaohongshu_detail_screenshot_uses_viewport_fallback_not_full_page(self):
        script = r"""
import { captureDetailScreenshot } from "./sidecar/collector/xiaohongshu.mjs";

const calls = [];
const page = {
  locator() {
    return {
      first() { return this; },
      async count() { return 0; },
    };
  },
  viewportSize() {
    return { width: 1366, height: 900 };
  },
  async screenshot(options) {
    calls.push(options);
  },
};

const result = await captureDetailScreenshot(page, "detail.png");
console.log(JSON.stringify({ result, screenshot: calls[0] }));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["result"]["mode"], "viewport")
        self.assertEqual(payload["screenshot"]["path"], "detail.png")
        self.assertFalse(payload["screenshot"]["fullPage"])

    def test_xiaohongshu_search_screenshot_extends_timeout_and_falls_back_to_viewport(self):
        script = r"""
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { captureSearchResultsScreenshot } from "./sidecar/collector/xiaohongshu.mjs";

const calls = [];
const events = [];
const assetsPath = mkdtempSync(join(tmpdir(), "falcon-search-screenshot-"));
const screenshotPath = join(assetsPath, "search.png");
const page = {
  async screenshot(options) {
    calls.push(options);
    if (calls.length === 1) {
      throw new Error("full page timeout");
    }
    writeFileSync(options.path, "viewport screenshot");
  },
};
const result = await captureSearchResultsScreenshot(page, screenshotPath, {
  request: { run_id: "search-shot-run", platform: "xiaohongshu" },
  events: {
    write(level, scope, event, message, payload) {
      events.push({ level, scope, event, message, payload });
    },
  },
});
const payload = { result, calls, events, exists: existsSync(screenshotPath) };
console.log(JSON.stringify(payload));
rmSync(assetsPath, { recursive: true, force: true });
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["result"]["mode"], "viewport")
        self.assertEqual(payload["calls"][0]["timeout"], 90000)
        self.assertTrue(payload["calls"][0]["fullPage"])
        self.assertEqual(payload["calls"][1]["timeout"], 15000)
        self.assertFalse(payload["calls"][1]["fullPage"])
        self.assertTrue(payload["exists"])
        self.assertEqual(payload["events"][0]["event"], "search_screenshot_fallback")
        self.assertIn("full page timeout", payload["events"][0]["payload"]["full_page_error"])

    def test_xiaohongshu_search_screenshot_total_failure_is_nonfatal(self):
        script = r"""
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { captureSearchResultsScreenshot } from "./sidecar/collector/xiaohongshu.mjs";

const calls = [];
const events = [];
const assetsPath = mkdtempSync(join(tmpdir(), "falcon-search-screenshot-failed-"));
const screenshotPath = join(assetsPath, "search.png");
const page = {
  async screenshot(options) {
    calls.push(options);
    throw new Error(calls.length === 1 ? "full page timeout" : "viewport timeout");
  },
};
const result = await captureSearchResultsScreenshot(page, screenshotPath, {
  request: { run_id: "search-shot-run", platform: "xiaohongshu" },
  events: {
    write(level, scope, event, message, payload) {
      events.push({ level, scope, event, message, payload });
    },
  },
});
console.log(JSON.stringify({ result, calls, events }));
rmSync(assetsPath, { recursive: true, force: true });
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["result"]["mode"], "failed")
        self.assertEqual(payload["result"]["path"], "")
        self.assertEqual(payload["calls"][0]["timeout"], 90000)
        self.assertEqual(payload["calls"][1]["timeout"], 15000)
        self.assertEqual(payload["events"][0]["event"], "search_screenshot_failed")
        self.assertIn("full page timeout", payload["events"][0]["payload"]["full_page_error"])
        self.assertIn("viewport timeout", payload["events"][0]["payload"]["viewport_error"])

    def test_xiaohongshu_collector_static_respects_browser_boundary(self):
        source = (ROOT / "sidecar" / "collector" / "xiaohongshu.mjs").read_text(encoding="utf-8")

        for forbidden in [
            "page.evaluate",
            ".$eval",
            ".$$eval",
            "context().request",
            "request.get",
            "fetch(",
            "downloadImage",
            "media_download_failed",
        ]:
            self.assertNotIn(forbidden, source)
        self.assertNotIn("search_result?keyword", source)
        self.assertNotRegex(source, r"\.goto\([^)]*(?:explore|search_result)")
        self.assertEqual(source.count('page.goto("https://www.xiaohongshu.com/"'), 1)

    def test_xiaohongshu_search_confirmation_rejects_stale_home_feed(self):
        script = r"""
import { verifySearchResultsReady } from "./sidecar/collector/xiaohongshu.mjs";

function emptyCollection() {
  return {
    first() { return emptyLocator(); },
    nth() { return emptyLocator(); },
    async count() { return 0; },
    async all() { return []; },
  };
}
function collection(items) {
  return {
    first() { return items[0] || emptyLocator(); },
    nth(index) { return items[index] || emptyLocator(); },
    async count() { return items.length; },
    async all() { return items; },
  };
}
function emptyLocator() {
  return makeLocator({ box: null });
}
function makeLocator({ text = "", href = "", box = { x: 100, y: 100, width: 240, height: 80 }, children = {} } = {}) {
  return {
    first() { return this; },
    nth() { return this; },
    async count() { return box ? 1 : 0; },
    async all() { return box ? [this] : []; },
    async scrollIntoViewIfNeeded() {},
    async boundingBox() { return box; },
    async innerText() { return text; },
    async textContent() { return text; },
    async getAttribute(name) { return name === "href" ? href : ""; },
    async fill(value) { calls.push(["fill", value]); },
    async pressSequentially(value) { calls.push(["type", value]); },
    async press(key) { calls.push(["press", key]); },
    locator(selector) {
      return children[selector] ? collection([children[selector]]) : emptyCollection();
    },
  };
}

const staleCard = makeLocator({
  text: "旧首页推荐内容\n作者\n1.1万",
  href: "https://www.xiaohongshu.com/explore/stale123",
  box: { x: 80, y: 220, width: 260, height: 180 },
});
const page = {
  url() { return "https://www.xiaohongshu.com/"; },
  title() { return Promise.resolve("小红书 首页"); },
  viewportSize() { return { width: 1366, height: 900 }; },
  locator(selector) {
    if (selector === "body") return collection([makeLocator({ text: "首页 发现 直播 发布", box: { x: 0, y: 0, width: 1000, height: 800 } })]);
    if (selector.includes(".note-item") || selector.includes("a[href*='/explore/']")) return collection([staleCard]);
    return emptyCollection();
  },
};
const request = {
  run_id: "search-confirmation-run",
  platform: "xiaohongshu",
  keyword: "AI氛围感",
  search_confirmation_timeout_ms: 0,
};
const result = await verifySearchResultsReady(page, request);
console.log(JSON.stringify(result));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["reason"], "search_not_confirmed")

    def test_xiaohongshu_search_confirmation_rejects_previous_keyword_results(self):
        script = r"""
import { verifySearchResultsReady } from "./sidecar/collector/xiaohongshu.mjs";

function emptyCollection() {
  return {
    first() { return emptyLocator(); },
    nth() { return emptyLocator(); },
    async count() { return 0; },
    async all() { return []; },
  };
}
function collection(items) {
  return {
    first() { return items[0] || emptyLocator(); },
    nth(index) { return items[index] || emptyLocator(); },
    async count() { return items.length; },
    async all() { return items; },
  };
}
function emptyLocator() {
  return makeLocator({ box: null });
}
function makeLocator({ text = "", href = "", box = { x: 100, y: 100, width: 240, height: 80 }, children = {} } = {}) {
  return {
    first() { return this; },
    nth() { return this; },
    async count() { return box ? 1 : 0; },
    async all() { return box ? [this] : []; },
    async scrollIntoViewIfNeeded() {},
    async boundingBox() { return box; },
    async innerText() { return text; },
    async textContent() { return text; },
    async getAttribute(name) { return name === "href" ? href : ""; },
    locator(selector) {
      return children[selector] ? collection([children[selector]]) : emptyCollection();
    },
  };
}

const oldResultCard = makeLocator({
  text: "小红书封面设计技巧\n作者\n900",
  href: "https://www.xiaohongshu.com/search_result/old123",
  box: { x: 80, y: 220, width: 260, height: 180 },
});
const page = {
  url() { return "https://www.xiaohongshu.com/search_result?keyword=%E5%B0%8F%E7%BA%A2%E4%B9%A6%E5%B0%81%E9%9D%A2&type=51"; },
  title() { return Promise.resolve("小红书封面 - 搜索"); },
  locator(selector) {
    if (selector === "body") return collection([makeLocator({ text: "小红书封面 搜索结果", box: { x: 0, y: 0, width: 1000, height: 800 } })]);
    if (selector === "a[href*='/search_result/']") return collection([oldResultCard]);
    return emptyCollection();
  },
};
const result = await verifySearchResultsReady(page, {
  run_id: "search-confirmation-run",
  platform: "xiaohongshu",
  keyword: "AI氛围感",
  search_confirmation_timeout_ms: 0,
});
console.log(JSON.stringify(result));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["reason"], "search_not_confirmed")

    def test_xiaohongshu_search_not_confirmed_error_is_failed_run_not_manual_action(self):
        script = r"""
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createSearchNotConfirmedError, searchNotConfirmedFailureRecords } from "./sidecar/collector/xiaohongshu.mjs";

function collection(items) {
  return {
    first() { return items[0]; },
    nth(index) { return items[index]; },
    async count() { return items.length; },
    async all() { return items; },
  };
}
const body = {
  first() { return this; },
  nth() { return this; },
  async count() { return 1; },
  async all() { return [this]; },
  async boundingBox() { return { x: 0, y: 0, width: 1000, height: 800 }; },
  async innerText() { return "首页 发现 直播 发布"; },
  async textContent() { return "首页 发现 直播 发布"; },
};
const assetsPath = mkdtempSync(join(tmpdir(), "falcon-search-failure-"));
const page = {
  url() { return "https://www.xiaohongshu.com/explore"; },
  async title() { return "小红书 首页"; },
  locator(selector) {
    return selector === "body" ? collection([body]) : collection([]);
  },
  async screenshot(options) {
    writeFileSync(options.path, "failure-state-screenshot");
  },
};
const searchReady = {
  reason: "search_not_confirmed",
  detail: "已输入关键词，但页面没有进入搜索结果。",
  url: "https://www.xiaohongshu.com/explore",
  title: "小红书 首页",
  searchLinkCount: 0,
  bodyText: "首页 发现 直播 发布",
};
const evidence = await searchNotConfirmedFailureRecords({
  page,
  request: {
    run_id: "search-confirmation-run",
    platform: "xiaohongshu",
    profile: "default",
    keyword: "AI氛围感",
  },
  assetsPath,
  searchReady,
});
const error = createSearchNotConfirmedError(
  searchReady,
  evidence,
);
const snapshot = JSON.parse(readFileSync(evidence.find((record) => record.scope === "failure_snapshot").path, "utf8"));
console.log(JSON.stringify({
  message: error.message,
  code: error.code,
  partialRecords: error.partialRecords,
  failurePayload: error.failurePayload,
  snapshot,
  screenshotBody: readFileSync(evidence.find((record) => record.scope === "failure_screenshot").path, "utf8"),
}));
rmSync(assetsPath, { recursive: true, force: true });
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["code"], "SEARCH_NOT_CONFIRMED")
        self.assertIn("没有进入搜索结果", payload["message"])
        self.assertEqual([record["scope"] for record in payload["partialRecords"]], ["failure_snapshot", "failure_screenshot"])
        self.assertEqual(payload["partialRecords"][0]["payload"]["keyword"], "AI氛围感")
        self.assertEqual(payload["failurePayload"]["reason"], "search_not_confirmed")
        self.assertEqual(payload["failurePayload"]["matched_signals"][0]["source"], "search_confirmation")
        self.assertEqual(payload["snapshot"]["body_text"], "首页 发现 直播 发布")
        self.assertEqual(payload["screenshotBody"], "failure-state-screenshot")

    def test_xiaohongshu_pace_defaults_wait_rest_and_scroll_in_safe_ranges(self):
        script = r"""
import { normalizeCollectorRequest, restBetweenCards, scrollSearchResults } from "./sidecar/collector/xiaohongshu.mjs";

const originalRandom = Math.random;
const waits = [];
const wheels = [];
const events = [];
const page = {
  viewportSize() { return { width: 1366, height: 1000 }; },
  mouse: {
    async wheel(x, y) { wheels.push([x, y]); },
  },
  async waitForTimeout(ms) { waits.push(ms); },
};
const request = normalizeCollectorRequest({
  run_id: "pace-run",
  platform: "xiaohongshu",
});

Math.random = () => 0;
const minScroll = await scrollSearchResults(page, request);
const paceState = { attemptedSinceBatchRest: 0, nextBatchRestAfter: 1 };
await restBetweenCards(page, request, {
  write(level, scope, event, message, payload) {
    events.push({ level, scope, event, message, payload });
  },
}, paceState);

Math.random = () => 0.999999;
const maxScroll = await scrollSearchResults(page, request);
Math.random = originalRandom;

console.log(JSON.stringify({
  minScroll,
  maxScroll,
  wheels,
  waits,
  events,
  paceState,
  pace: request.pace,
}));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["pace"]["detail_delay_range_seconds"], [8, 18])
        self.assertEqual(payload["pace"]["scroll_delay_range_seconds"], [5, 12])
        self.assertEqual(payload["pace"]["batch_rest_after_cards_range"], [5, 11])
        self.assertEqual(payload["pace"]["batch_rest_seconds_range"], [6, 10])
        self.assertEqual(payload["pace"]["comment_scroll_delay_range_seconds"], [4, 9])
        self.assertEqual(payload["pace"]["reply_expand_delay_range_seconds"], [5, 8])
        self.assertEqual(payload["minScroll"], 450)
        self.assertEqual(payload["maxScroll"], 850)
        self.assertIn(5000, payload["waits"])
        self.assertIn(8000, payload["waits"])
        self.assertIn(6000, payload["waits"])
        self.assertIn("collector_batch_rest", [event["event"] for event in payload["events"]])

    def test_xiaohongshu_checkpoint_resume_skips_completed_cards(self):
        script = r"""
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { collectWaterfallRecords, normalizeCollectorRequest } from "./sidecar/collector/xiaohongshu.mjs";

function emptyCollection() {
  return {
    first() { return emptyLocator(); },
    nth() { return emptyLocator(); },
    async count() { return 0; },
    async all() { return []; },
  };
}

function collection(items) {
  return {
    first() { return items[0] || emptyLocator(); },
    nth(index) { return items[index] || emptyLocator(); },
    async count() { return items.length; },
    async all() { return items; },
  };
}

function emptyLocator() {
  return makeLocator({ box: null });
}

function makeLocator({ text = "", box = { x: 100, y: 200, width: 260, height: 180 }, children = {}, lists = {} } = {}) {
  return {
    first() { return this; },
    nth() { return this; },
    async count() { return box ? 1 : 0; },
    async all() { return box ? [this] : []; },
    async scrollIntoViewIfNeeded() {},
    async boundingBox() { return box; },
    async innerText() { return text; },
    async textContent() { return text; },
    async getAttribute() { return ""; },
    locator(selector) {
      if (children[selector]) return collection([children[selector]]);
      if (lists[selector]) return collection(lists[selector]);
      return emptyCollection();
    },
  };
}

const runRoot = mkdtempSync(join(tmpdir(), "falcon-checkpoint-"));
const assetsPath = join(runRoot, "assets");
mkdirSync(assetsPath, { recursive: true });
const first = {
  postId: "xiaohongshu:first123",
  url: "https://www.xiaohongshu.com/explore/first123",
  title: "already done",
};
const second = {
  postId: "xiaohongshu:second123",
  url: "https://www.xiaohongshu.com/explore/second123",
  title: "needs collection",
};
writeFileSync(join(runRoot, "checkpoint.json"), JSON.stringify({
  run_id: "checkpoint-run",
  platform: "xiaohongshu",
  collected_ids: ["xiaohongshu:first123"],
  skipped_ids: [],
  failed_ids: [],
  pending_posts: [first, second],
  attempted_since_batch_rest: 0,
  next_batch_rest_after: 99,
}, null, 2));

const calls = [];
const events = [];
let opened = false;
const card = makeLocator();
const detailRoot = makeLocator({
  box: { x: 0, y: 0, width: 900, height: 700 },
  children: {
    "#detail-title": makeLocator({ text: "second title", box: { x: 20, y: 20, width: 300, height: 40 } }),
    "#detail-desc": makeLocator({ text: "second body", box: { x: 20, y: 80, width: 420, height: 80 } }),
    "a[href*='/user/profile']": makeLocator({ text: "author", box: { x: 20, y: 160, width: 160, height: 32 } }),
  },
  lists: {
    "img": [],
    ".comment-item, [class*='comment-item'], [class*='reply-item']": [],
  },
});
const searchPage = {
  viewportSize() { return { width: 1366, height: 900 }; },
  locator(selector) {
    calls.push(["locator", selector, opened]);
    if (opened && selector === "#noteContainer") return collection([detailRoot]);
    if (!opened && selector.includes("second123")) return collection([card]);
    return emptyCollection();
  },
  waitForEvent() { return Promise.resolve(null); },
  mouse: {
    async move() {},
    async click() { opened = true; calls.push(["click", "second123"]); },
    async wheel() { calls.push(["wheel"]); },
  },
  keyboard: {
    async press(key) { calls.push(["press", key]); },
  },
  async waitForLoadState() {},
  async waitForTimeout() {},
  async screenshot(options) { writeFileSync(options.path, "screenshot"); },
  async goBack() { opened = false; calls.push(["goBack"]); },
  url() {
    return opened
      ? "https://www.xiaohongshu.com/explore/second123"
      : "https://www.xiaohongshu.com/search_result?keyword=test";
  },
};
const request = normalizeCollectorRequest({
  run_id: "checkpoint-run",
  platform: "xiaohongshu",
  keyword: "test",
  max_posts: 2,
  max_comments_per_post: 0,
  pace: {
    detail_delay_range_seconds: [0, 0],
    scroll_delay_range_seconds: [0, 0],
    batch_rest_after_cards_range: [99, 99],
    batch_rest_seconds_range: [0, 0],
    click_delay_range_ms: [0, 0],
  },
});

const outcome = await collectWaterfallRecords({
  context: {},
  searchPage,
  request,
  assetsPath,
  events: {
    write(level, scope, event, message, payload) {
      events.push({ level, scope, event, message, payload });
    },
  },
  initialPosts: [first, second],
});
const checkpoint = JSON.parse(readFileSync(join(runRoot, "checkpoint.json"), "utf8"));
console.log(JSON.stringify({ outcome, calls, events, checkpoint }));
rmSync(runRoot, { recursive: true, force: true });
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        post_records = [record for record in payload["outcome"]["records"] if record["type"] == "post"]
        self.assertEqual([record["post_id"] for record in post_records], ["xiaohongshu:second123"])
        self.assertEqual(payload["calls"].count(["click", "second123"]), 1)
        self.assertIn("xiaohongshu:first123", payload["checkpoint"]["collected_ids"])
        self.assertIn("xiaohongshu:second123", payload["checkpoint"]["collected_ids"])
        self.assertEqual(payload["checkpoint"]["pending_posts"], [])

    def test_xiaohongshu_opens_detail_with_mouse_click_not_direct_url(self):
        script = r"""
import { openDetailFromSearchCard } from "./sidecar/collector/xiaohongshu.mjs";

const calls = [];
const detailPage = {
  async waitForLoadState(state, options) { calls.push(["detail-load", state, options.timeout]); },
  async waitForTimeout(ms) { calls.push(["detail-wait", ms]); },
  url() { return "https://www.xiaohongshu.com/explore/65abc123"; },
};
const locator = {
  first() { return this; },
  async count() { calls.push(["count"]); return 1; },
  async scrollIntoViewIfNeeded(options) { calls.push(["scroll", options.timeout]); },
  async boundingBox() { calls.push(["box"]); return { x: 100, y: 200, width: 260, height: 180 }; },
};
const page = {
  locator(selector) { calls.push(["locator", selector]); return locator; },
  context() {
    return {
      async waitForEvent(event, options) {
        calls.push(["waitForEvent", event, options.timeout]);
        return detailPage;
      },
    };
  },
  mouse: {
    async move(x, y, options) { calls.push(["move", Math.round(x), Math.round(y), options.steps]); },
    async click(x, y, options) { calls.push(["click", Math.round(x), Math.round(y), options.delay]); },
  },
  async waitForTimeout(ms) { calls.push(["page-wait", ms]); },
  async waitForLoadState() { calls.push(["page-load"]); },
  url() { return "https://www.xiaohongshu.com/search_result?keyword=test"; },
  async goto(url) { calls.push(["goto", url]); },
};

const opened = await openDetailFromSearchCard({
  searchPage: page,
  searchPost: {
    postId: "xiaohongshu:65abc123",
    url: "https://www.xiaohongshu.com/explore/65abc123",
    title: "sample",
  },
  index: 0,
});
console.log(JSON.stringify({ mode: opened.mode, calls }));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        call_names = [call[0] for call in payload["calls"]]
        self.assertEqual(payload["mode"], "popup")
        self.assertIn("move", call_names)
        self.assertIn("click", call_names)
        self.assertNotIn("goto", call_names)

    def test_xiaohongshu_prefers_visible_hit_tested_card_link_over_hidden_match(self):
        script = r"""
import { openDetailFromSearchCard } from "./sidecar/collector/xiaohongshu.mjs";

const calls = [];
let opened = false;

function makeLocator(name, box) {
  return {
    name,
    first() { return this; },
    async count() { calls.push(["count", name]); return box ? 1 : 0; },
    async scrollIntoViewIfNeeded(options) { calls.push(["scroll", name, options.timeout]); },
    async boundingBox() { calls.push(["box", name]); return box; },
  };
}

function makeCollection(name, items) {
  const empty = makeLocator(`${name}-empty`, null);
  return {
    first() { return items[0] || empty; },
    nth(index) { return items[index] || empty; },
    async count() { calls.push(["collection-count", name]); return items.length; },
    async all() { calls.push(["all", name]); return items; },
  };
}

const hiddenExplore = makeLocator("hidden-explore", null);
const visibleTitle = makeLocator(
  "visible-title",
  { x: 100, y: 180, width: 220, height: 40 },
);
const offscreenNote = makeLocator("offscreen-note", { x: 100, y: -556, width: 244, height: 429 });

const page = {
  locator(selector) {
    calls.push(["locator", selector]);
    if (selector.includes("65abc123")) {
      return makeCollection("matching-links", [hiddenExplore, visibleTitle]);
    }
    if (selector.includes(".note-item") || selector === "section" || selector === "article") {
      return makeCollection("generic-note", [offscreenNote]);
    }
    return makeCollection("empty", []);
  },
  context() {
    return {
      pages() { return []; },
      async waitForEvent(event, options) {
        calls.push(["context-waitForEvent", event, options.timeout]);
        return null;
      },
    };
  },
  mouse: {
    async move(x, y, options) { calls.push(["move", Math.round(x), Math.round(y), options.steps]); },
    async click(x, y, options) {
      calls.push(["click", Math.round(x), Math.round(y), options.delay]);
      if (x >= 0 && y >= 0) {
        opened = true;
      }
    },
  },
  async waitForTimeout(ms) { calls.push(["page-wait", ms]); },
  async waitForLoadState() { calls.push(["page-load"]); },
  url() {
    return opened
      ? "https://www.xiaohongshu.com/explore/65abc123?xsec_token=token"
      : "https://www.xiaohongshu.com/search_result?keyword=test";
  },
  async goto(url) { calls.push(["goto", url]); },
};

const openedHandle = await openDetailFromSearchCard({
  searchPage: page,
  searchPost: {
    postId: "xiaohongshu:65abc123",
    url: "https://www.xiaohongshu.com/explore/65abc123",
    title: "sample",
  },
  index: 0,
});
console.log(JSON.stringify({ mode: openedHandle.mode, calls }));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "same_page")
        click_calls = [call for call in payload["calls"] if call[0] == "click"]
        self.assertEqual(len(click_calls), 1)
        self.assertGreaterEqual(click_calls[0][2], 0)
        self.assertNotIn("evaluate", [call[0] for call in payload["calls"]])

    def test_xiaohongshu_scrolls_waterfall_to_relocate_expected_card(self):
        script = r"""
import { openDetailFromSearchCard } from "./sidecar/collector/xiaohongshu.mjs";

const calls = [];
let scrolls = 0;
let opened = false;

const targetLocator = {
  first() { return this; },
  async count() { calls.push(["target-count"]); return 1; },
  async all() { calls.push(["target-all"]); return [this]; },
  async scrollIntoViewIfNeeded(options) { calls.push(["target-scroll", options.timeout]); },
  async boundingBox() { calls.push(["target-box"]); return { x: 120, y: 220, width: 260, height: 180 }; },
};
const empty = {
  first() { return this; },
  nth() { return this; },
  async count() { calls.push(["empty-count"]); return 0; },
  async all() { calls.push(["empty-all"]); return []; },
};
const targetCollection = {
  first() { return targetLocator; },
  nth() { return targetLocator; },
  async count() { return 1; },
  async all() { return [targetLocator]; },
};
const page = {
  locator(selector) {
    calls.push(["locator", selector, scrolls]);
    if (selector.includes("target123") && scrolls >= 2) {
      return targetCollection;
    }
    return empty;
  },
  waitForEvent(event, options) {
    calls.push(["waitForEvent", event, options.timeout]);
    return Promise.resolve(null);
  },
  mouse: {
    async move(x, y) { calls.push(["move", Math.round(x), Math.round(y)]); },
    async click(x, y) {
      calls.push(["click", Math.round(x), Math.round(y)]);
      opened = true;
    },
    async wheel(x, y) {
      calls.push(["wheel", x, y]);
      scrolls += 1;
    },
  },
  async waitForTimeout(ms) { calls.push(["wait", ms]); },
  async waitForLoadState(state, options) { calls.push(["load", state, options?.timeout]); },
  url() {
    return opened
      ? "https://www.xiaohongshu.com/explore/target123"
      : "https://www.xiaohongshu.com/search_result?keyword=test";
  },
};

const openedHandle = await openDetailFromSearchCard({
  searchPage: page,
  searchPost: {
    postId: "xiaohongshu:target123",
    url: "https://www.xiaohongshu.com/explore/target123",
    title: "target",
    cardIndex: 70,
  },
  index: 17,
});

console.log(JSON.stringify({ mode: openedHandle.mode, scrolls, calls }));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "same_page")
        self.assertGreaterEqual(payload["scrolls"], 2)
        self.assertIn(["click", 245, 303], payload["calls"])

    def test_xiaohongshu_retries_when_note_load_failed_toast_disappears(self):
        script = r"""
import { openDetailFromSearchCard } from "./sidecar/collector/xiaohongshu.mjs";

const calls = [];
let clickCount = 0;
let opened = false;

const locator = {
  first() { return this; },
  async count() { return 1; },
  async all() { return [this]; },
  async scrollIntoViewIfNeeded(options) { calls.push(["scroll", options.timeout]); },
  async boundingBox() { return { x: 120, y: 220, width: 260, height: 180 }; },
};
const toastLocator = {
  first() { return this; },
  nth() { return this; },
  async count() { return clickCount === 1 ? 1 : 0; },
  async all() { return clickCount === 1 ? [this] : []; },
  async boundingBox() { return clickCount === 1 ? { x: 10, y: 10, width: 240, height: 40 } : null; },
  async innerText() { return "笔记加载失败"; },
  async textContent() { return "笔记加载失败"; },
};
const empty = {
  first() { return this; },
  nth() { return this; },
  async count() { return 0; },
  async all() { return []; },
};
const collection = {
  first() { return locator; },
  nth() { return locator; },
  async count() { return 1; },
  async all() { return [locator]; },
};
const page = {
  locator(selector) {
    calls.push(["locator", selector]);
    if (selector === "body" || selector.includes("toast") || selector.includes("message") || selector.includes("notify")) {
      return toastLocator;
    }
    return selector.includes("retry123") ? collection : empty;
  },
  waitForEvent(event, options) {
    calls.push(["waitForEvent", event, options.timeout]);
    return Promise.resolve(null);
  },
  mouse: {
    async move() {},
    async click() {
      clickCount += 1;
      calls.push(["click", clickCount]);
      if (clickCount >= 2) opened = true;
    },
  },
  keyboard: {
    async press(key) { calls.push(["press", key]); },
  },
  async waitForTimeout(ms) { calls.push(["wait", ms]); },
  async waitForLoadState() {},
  url() {
    return opened
      ? "https://www.xiaohongshu.com/explore/retry123"
      : "https://www.xiaohongshu.com/search_result?keyword=test";
  },
};

const openedHandle = await openDetailFromSearchCard({
  searchPage: page,
  searchPost: {
    postId: "xiaohongshu:retry123",
    url: "https://www.xiaohongshu.com/explore/retry123",
    title: "retry target",
  },
  index: 0,
});

console.log(JSON.stringify({ mode: openedHandle.mode, clickCount, calls }));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "same_page")
        self.assertEqual(payload["clickCount"], 2)
        self.assertIn(["press", "Escape"], payload["calls"])

    def test_xiaohongshu_skips_card_after_repeated_note_load_failure(self):
        script = r"""
import { collectDetailRecords } from "./sidecar/collector/xiaohongshu.mjs";

const calls = [];
const events = [];
let clickCount = 0;

const locator = {
  first() { return this; },
  async count() { return 1; },
  async all() { return [this]; },
  async scrollIntoViewIfNeeded() {},
  async boundingBox() { return { x: 120, y: 220, width: 260, height: 180 }; },
};
const toastLocator = {
  first() { return this; },
  nth() { return this; },
  async count() { return 1; },
  async all() { return [this]; },
  async boundingBox() { return { x: 10, y: 10, width: 240, height: 40 }; },
  async innerText() { return "笔记加载失败"; },
  async textContent() { return "笔记加载失败"; },
};
const empty = {
  first() { return this; },
  nth() { return this; },
  async count() { return 0; },
  async all() { return []; },
};
const collection = {
  first() { return locator; },
  nth() { return locator; },
  async count() { return 1; },
  async all() { return [locator]; },
};
const searchPage = {
  locator(selector) {
    if (selector === "body" || selector.includes("toast") || selector.includes("message") || selector.includes("notify")) {
      return toastLocator;
    }
    return selector.includes("fail123") ? collection : empty;
  },
  waitForEvent() { return Promise.resolve(null); },
  mouse: {
    async move() {},
    async click() {
      clickCount += 1;
      calls.push(["click", clickCount]);
    },
  },
  keyboard: {
    async press(key) { calls.push(["press", key]); },
  },
  async waitForTimeout() {},
  async waitForLoadState() {},
  async screenshot(options) { calls.push(["screenshot", options.path]); },
  url() { return "https://www.xiaohongshu.com/search_result?keyword=test"; },
};

const outcome = await collectDetailRecords({
  context: {},
  searchPage,
  request: {
    run_id: "note-load-failed-run",
    platform: "xiaohongshu",
    keyword: "avatar",
    max_comments_per_post: 1,
  },
  assetsPath: ".",
  events: {
    write(level, scope, event, message, payload) {
      events.push({ level, scope, event, message, payload });
    },
  },
  posts: [
    {
      postId: "xiaohongshu:fail123",
      url: "https://www.xiaohongshu.com/explore/fail123",
      title: "fail target",
    },
  ],
  total: 3,
});

console.log(JSON.stringify({ outcome, events, calls, clickCount }));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["outcome"]["skipped"])
        self.assertFalse(payload["outcome"]["stopped"])
        self.assertEqual(payload["events"][-1]["event"], "detail_open_skipped")
        self.assertEqual(payload["events"][-1]["payload"]["reason"], "note_load_failed")
        self.assertEqual(payload["clickCount"], 2)
        self.assertEqual(payload["outcome"]["records"][0]["scope"], "detail_error_screenshot")

    def test_xiaohongshu_does_not_fallback_to_index_when_expected_post_id_is_missing(self):
        script = r"""
import { openDetailFromSearchCard } from "./sidecar/collector/xiaohongshu.mjs";

const calls = [];
const genericCard = {
  first() { return this; },
  async count() { calls.push(["generic-count"]); return 1; },
  async all() { calls.push(["generic-all"]); return [this]; },
  async scrollIntoViewIfNeeded() { calls.push(["generic-scroll"]); },
  async boundingBox() { calls.push(["generic-box"]); return { x: 100, y: 200, width: 260, height: 180 }; },
};
const empty = {
  first() { return this; },
  nth() { return this; },
  async count() { calls.push(["empty-count"]); return 0; },
  async all() { calls.push(["empty-all"]); return []; },
};
const page = {
  locator(selector) {
    calls.push(["locator", selector]);
    if (selector === ".note-item, .feeds-page .note-card, section, article") {
      return {
        nth() { return genericCard; },
        first() { return genericCard; },
        async count() { calls.push(["generic-collection-count"]); return 1; },
      };
    }
    return empty;
  },
  context() {
    return {
      pages() { return []; },
      async waitForEvent() { return null; },
    };
  },
  mouse: {
    async move() { calls.push(["move"]); },
    async click() { calls.push(["click"]); },
    async wheel() { calls.push(["wheel"]); },
  },
  async waitForTimeout() {},
  async waitForLoadState() {},
  url() { return "https://www.xiaohongshu.com/discovery/item"; },
};

let message = "";
try {
  await openDetailFromSearchCard({
    searchPage: page,
    searchPost: {
      postId: "xiaohongshu:expected123",
      url: "https://www.xiaohongshu.com/explore/expected123",
      title: "expected",
    },
    index: 16,
  });
} catch (error) {
  message = error.message;
}
console.log(JSON.stringify({ message, calls }));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("expected", payload["message"])
        self.assertIn("未找到", payload["message"])
        self.assertNotIn("click", [call[0] for call in payload["calls"]])
        self.assertNotIn(["generic-evaluate"], payload["calls"])

    def test_xiaohongshu_close_same_page_detail_does_not_leave_search_results(self):
        script = r"""
import { closeDetailAfterCollection } from "./sidecar/collector/xiaohongshu.mjs";

const calls = [];
let currentUrl = "https://www.xiaohongshu.com/search_result?keyword=%E5%89%AF%E4%B8%9A&source=web_search_result_notes";
const page = {
  keyboard: {
    async press(key) { calls.push(["press", key]); },
  },
  async waitForTimeout(ms) { calls.push(["wait", ms]); },
  async goBack() {
    calls.push(["goBack"]);
    currentUrl = "https://www.xiaohongshu.com/explore";
  },
  async goto(url) {
    calls.push(["goto", url]);
    currentUrl = url;
  },
  url() { return currentUrl; },
  locator() {
    return {
      first() { return this; },
      async count() { return 0; },
    };
  },
};

await closeDetailAfterCollection({
  page,
  mode: "same_page",
  searchPage: page,
  beforeUrl: "https://www.xiaohongshu.com/search_result?keyword=%E5%89%AF%E4%B8%9A&source=web_search_result_notes",
});

console.log(JSON.stringify({ currentUrl, calls }));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["currentUrl"], "https://www.xiaohongshu.com/search_result?keyword=%E5%89%AF%E4%B8%9A&source=web_search_result_notes")
        self.assertIn(["press", "Escape"], payload["calls"])
        self.assertNotIn(["goBack"], payload["calls"])

    def test_sidecar_writes_partial_records_when_run_fails_after_collecting_some_posts(self):
        script = r"""
import { writePartialRecordsOnError } from "./sidecar/collector/index.mjs";
import { readFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const path = join(tmpdir(), `falcon-partial-records-${Date.now()}.jsonl`);
rmSync(path, { force: true });
const error = new Error("detail failed");
error.partialRecords = [
  { type: "post", run_id: "partial-run", post_id: "post-1" },
  { type: "evidence", run_id: "partial-run", evidence_id: "evidence-1" },
];
const count = await writePartialRecordsOnError(path, error);
const lines = readFileSync(path, "utf8").trim().split("\n").map((line) => JSON.parse(line));
rmSync(path, { force: true });
console.log(JSON.stringify({ count, lines }));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["lines"][0]["post_id"], "post-1")

    def test_xiaohongshu_manual_action_survives_closed_page_screenshot_failure(self):
        script = r"""
import { manualActionRecords } from "./sidecar/collector/xiaohongshu.mjs";
import { existsSync, readFileSync, rmSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const events = [];
const assetsPath = mkdtempSync(join(tmpdir(), "falcon-manual-action-"));
const records = await manualActionRecords({
  page: {
    async screenshot() {
      throw new Error("Target page, context or browser has been closed");
    },
    url() {
      throw new Error("Target page closed");
    },
  },
  request: {
    run_id: "manual-closed-page",
    platform: "xiaohongshu",
  },
  assetsPath,
  events: {
    write(level, scope, event, message, payload) {
      events.push({ level, scope, event, message, payload });
    },
  },
  reason: "app_scan_required",
  matchedSignals: [
    { reason: "app_scan_required", signal: "扫码查看", source: "body" },
  ],
  detail: "需要人工处理",
});

const snapshotPath = events[0].payload.snapshot;
const snapshot = existsSync(snapshotPath) ? JSON.parse(readFileSync(snapshotPath, "utf8")) : null;
console.log(JSON.stringify({ records, event: events[0], snapshot }));
rmSync(assetsPath, { recursive: true, force: true });
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["event"]["event"], "manual_action_required")
        self.assertEqual(payload["event"]["payload"]["screenshot"], "")
        self.assertIn("screenshot_error", payload["event"]["payload"])
        self.assertIn("snapshot", payload["event"]["payload"])
        self.assertEqual(payload["event"]["payload"]["matched_signals"][0]["signal"], "扫码查看")
        self.assertEqual(len(payload["records"]), 1)
        self.assertEqual(payload["records"][0]["scope"], "manual_action_snapshot")
        self.assertEqual(payload["records"][0]["path"], payload["event"]["payload"]["snapshot"])
        self.assertEqual(payload["snapshot"]["reason"], "app_scan_required")
        self.assertEqual(payload["snapshot"]["matched_signals"][0]["source"], "body")

    def test_xiaohongshu_manual_action_records_snapshot_and_screenshot_evidence(self):
        script = r"""
import { manualActionRecords } from "./sidecar/collector/xiaohongshu.mjs";
import { existsSync, readFileSync, rmSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

function collection(items) {
  return {
    first() { return items[0]; },
    nth(index) { return items[index]; },
    async count() { return items.length; },
    async all() { return items; },
  };
}

const body = {
  first() { return this; },
  nth() { return this; },
  async count() { return 1; },
  async all() { return [this]; },
  async boundingBox() { return { x: 0, y: 0, width: 900, height: 500 }; },
  async innerText() { return "账号违规预警：检测到第三方工具或自动浏览脚本"; },
  async textContent() { return "账号违规预警：检测到第三方工具或自动浏览脚本"; },
};
const empty = {
  first() { return this; },
  nth() { return this; },
  async count() { return 0; },
  async all() { return []; },
  async boundingBox() { return null; },
  async innerText() { return ""; },
  async textContent() { return ""; },
};

const events = [];
const assetsPath = mkdtempSync(join(tmpdir(), "falcon-manual-action-success-"));
const records = await manualActionRecords({
  page: {
    async screenshot(options) {
      writeFileSync(options.path, "png");
    },
    url() {
      return "https://www.xiaohongshu.com/explore";
    },
    async title() {
      return "XHS warning";
    },
    locator(selector) {
      return selector === "body" ? collection([body]) : collection([empty]);
    },
  },
  request: {
    run_id: "manual-action-success",
    platform: "xiaohongshu",
    profile: "default",
    keyword: "content ops",
  },
  assetsPath,
  events: {
    write(level, scope, event, message, payload) {
      events.push({ level, scope, event, message, payload });
    },
  },
  reason: "account_risk_warning",
  matchedSignals: [
    { reason: "account_risk_warning", signal: "账号违规预警", source: "body" },
  ],
  detail: "检测到账号违规预警",
});

const snapshotRecord = records.find((record) => record.scope === "manual_action_snapshot");
const screenshotRecord = records.find((record) => record.scope === "manual_action_screenshot");
const snapshot = existsSync(snapshotRecord?.path || "") ? JSON.parse(readFileSync(snapshotRecord.path, "utf8")) : null;
console.log(JSON.stringify({
  records,
  event: events[0],
  snapshot,
  screenshotExists: existsSync(screenshotRecord?.path || ""),
}));
rmSync(assetsPath, { recursive: true, force: true });
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        scopes = [record["scope"] for record in payload["records"]]
        self.assertIn("manual_action_snapshot", scopes)
        self.assertIn("manual_action_screenshot", scopes)
        self.assertTrue(payload["screenshotExists"])
        self.assertEqual(payload["event"]["payload"]["evidence_chain_path"], payload["event"]["payload"]["snapshot"])
        self.assertEqual(payload["snapshot"]["reason"], "account_risk_warning")
        self.assertEqual(payload["snapshot"]["matched_signals"][0]["signal"], "账号违规预警")

    def test_xiaohongshu_profile_launch_conflict_is_detected_from_playwright_logs(self):
        script = r"""
import { isPersistentProfileLaunchConflict } from "./sidecar/collector/xiaohongshu.mjs";

const busy = new Error(`browserType.launchPersistentContext: Target page, context or browser has been closed
Browser logs:
<launching> chrome.exe --user-data-dir=browser-profiles/xiaohongshu/default --remote-debugging-pipe about:blank
<launched> pid=49380
[pid=49380] <process did exit: exitCode=0, signal=null>`);
const unrelated = new Error("Playwright is required for real-mode collection.");

console.log(JSON.stringify({
  busy: isPersistentProfileLaunchConflict(busy),
  unrelated: isPersistentProfileLaunchConflict(unrelated),
}));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["busy"])
        self.assertFalse(payload["unrelated"])

    def test_xiaohongshu_profile_launch_conflict_keeps_run_manual_action(self):
        env = {
            **dict(os.environ),
            "FALCON_COLLECTOR_FORCE_PROFILE_LAUNCH_CONFLICT": "1",
        }
        result, events_path, records_path, assets_dir = self.run_sidecar(
            {
                "schema_version": 1,
                "run_id": "run-profile-launch-conflict",
                "platform": "xiaohongshu",
                "profile": "default",
                "keyword": "账号增长",
                "max_posts": 1,
                "max_comments_per_post": 0,
                "headed": True,
                "dry_run": False,
            },
            env=env,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(assets_dir.is_dir())
        self.assertTrue(records_path.exists())

        events = read_jsonl(events_path)
        self.assertEqual(events[-1]["event"], "manual_action_required")
        self.assertEqual(events[-1]["payload"]["reason"], "profile_window_busy")
        self.assertIn("Profile", events[-1]["message"])
        self.assertNotIn("launchPersistentContext", events[-1]["message"])

    def test_xiaohongshu_early_browser_close_keeps_run_manual_action(self):
        env = {
            **dict(os.environ),
            "FALCON_COLLECTOR_FORCE_EARLY_BROWSER_CLOSE": "1",
        }
        result, events_path, records_path, assets_dir = self.run_sidecar(
            {
                "schema_version": 1,
                "run_id": "run-early-browser-close",
                "platform": "xiaohongshu",
                "profile": "default",
                "keyword": "账号增长",
                "max_posts": 1,
                "max_comments_per_post": 0,
                "headed": True,
                "dry_run": False,
            },
            env=env,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(assets_dir.is_dir())
        self.assertTrue(records_path.exists())

        events = read_jsonl(events_path)
        records = read_jsonl(records_path)
        self.assertEqual(events[-1]["event"], "manual_action_required")
        self.assertEqual(events[-1]["payload"]["reason"], "browser_closed_early")
        self.assertIn("窗口状态", events[-1]["message"])
        self.assertIn("manual_action_snapshot", {record.get("scope") for record in records})
        self.assertNotIn("run_failed", {event["event"] for event in events})

    def test_xiaohongshu_selects_existing_platform_page_over_blank_tab(self):
        script = r"""
import { selectUsableBrowserPage } from "./sidecar/collector/xiaohongshu.mjs";

const calls = [];
const blankPage = {
  name: "blank",
  url() { return "about:blank"; },
  async bringToFront() { calls.push("blank-front"); },
};
const xhsPage = {
  name: "xhs",
  url() { return "https://www.xiaohongshu.com/explore"; },
  async bringToFront() { calls.push("xhs-front"); },
};
const context = {
  pages() { return [blankPage, xhsPage]; },
  async newPage() {
    calls.push("new-page");
    return blankPage;
  },
};

const selected = await selectUsableBrowserPage(context, { preferredHost: "xiaohongshu.com" });
console.log(JSON.stringify({ selected: selected.name, calls }));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["selected"], "xhs")
        self.assertEqual(payload["calls"], ["xhs-front"])

    def test_xiaohongshu_selects_new_page_when_context_has_no_pages(self):
        script = r"""
import { selectUsableBrowserPage } from "./sidecar/collector/xiaohongshu.mjs";

const calls = [];
const createdPage = {
  name: "created",
  url() { return "about:blank"; },
  async bringToFront() { calls.push("created-front"); },
};
const context = {
  pages() { return []; },
  async newPage() {
    calls.push("new-page");
    return createdPage;
  },
};

const selected = await selectUsableBrowserPage(context, { preferredHost: "xiaohongshu.com" });
console.log(JSON.stringify({ selected: selected.name, calls }));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["selected"], "created")
        self.assertEqual(payload["calls"], ["new-page", "created-front"])

    def test_xiaohongshu_usable_locator_skips_aria_hidden_input_clone(self):
        script = r"""
import { firstUsableLocator } from "./sidecar/collector/xiaohongshu.mjs";

const hiddenClone = {
  name: "hidden-clone",
  async boundingBox() { return { x: 100, y: 20, width: 300, height: 40 }; },
  async getAttribute(name) {
    return { "aria-hidden": "true", tabindex: "-1" }[name] ?? "";
  },
};
const realInput = {
  name: "real-input",
  async boundingBox() { return { x: 100, y: 20, width: 300, height: 40 }; },
  async getAttribute(name) {
    return { id: "search-input", tabindex: "", "aria-hidden": "" }[name] ?? "";
  },
};
const collection = {
  async count() { return 2; },
  nth(index) { return index === 0 ? hiddenClone : realInput; },
};
const page = {
  locator(selector) {
    if (selector !== "input") throw new Error(`unexpected selector ${selector}`);
    return collection;
  },
};

const selected = await firstUsableLocator(page, ["input"]);
console.log(JSON.stringify({ selected: selected.name }));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["selected"], "real-input")

    def test_xiaohongshu_detail_target_closed_becomes_manual_action(self):
        script = r"""
import { collectDetailRecords, isPlaywrightTargetClosedError } from "./sidecar/collector/xiaohongshu.mjs";

const calls = [];
const events = [];
const detailPage = {
  async waitForLoadState() { calls.push(["detail-load"]); },
  async waitForTimeout(ms) { calls.push(["detail-wait", ms]); },
  locator() { return empty; },
  async screenshot() {
    throw new Error("Target page closed");
  },
  async close() { calls.push(["detail-close"]); },
};
const locator = {
  async scrollIntoViewIfNeeded() { calls.push(["scroll"]); },
  async boundingBox() { calls.push(["box"]); return { x: 100, y: 180, width: 240, height: 180 }; },
};
const collection = {
  first() { return locator; },
  nth() { return locator; },
  async count() { calls.push(["count"]); return 1; },
  async all() { calls.push(["all"]); return [locator]; },
};
const empty = {
  first() { return this; },
  nth() { return this; },
  async count() { return 0; },
  async all() { return []; },
  async boundingBox() { return null; },
  async innerText() { return ""; },
  async textContent() { return ""; },
};
const searchPage = {
  locator(selector) { calls.push(["locator", selector]); return collection; },
  waitForEvent(event, options) { calls.push(["waitForEvent", event, options.timeout]); return Promise.resolve(detailPage); },
  mouse: {
    async move(x, y) { calls.push(["move", Math.round(x), Math.round(y)]); },
    async click(x, y) { calls.push(["click", Math.round(x), Math.round(y)]); },
  },
  async waitForTimeout(ms) { calls.push(["search-wait", ms]); },
  async waitForLoadState() { calls.push(["search-load"]); },
  url() { return "https://www.xiaohongshu.com/search_result?keyword=avatar"; },
};

const outcome = await collectDetailRecords({
  context: {},
  searchPage,
  request: {
    run_id: "closed-detail-run",
    platform: "xiaohongshu",
    keyword: "avatar",
    max_comments_per_post: 1,
  },
  assetsPath: ".",
  events: {
    write(level, scope, event, message, payload) {
      events.push({ level, scope, event, message, payload });
    },
  },
  posts: [
    {
      postId: "xiaohongshu:closed123",
      url: "https://www.xiaohongshu.com/explore/closed123",
      title: "sample",
    },
  ],
});

console.log(JSON.stringify({
  targetClosed: isPlaywrightTargetClosedError(new Error("Target page, context or browser has been closed")),
  unrelated: isPlaywrightTargetClosedError(new Error("normal detail parse failure")),
  stopped: outcome.stopped,
  records: outcome.records,
  events,
  calls,
}));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["targetClosed"])
        self.assertFalse(payload["unrelated"])
        self.assertTrue(payload["stopped"])
        self.assertEqual(payload["records"], [])
        self.assertEqual(payload["events"][-1]["event"], "manual_action_required")
        self.assertEqual(payload["events"][-1]["payload"]["reason"], "browser_closed_mid_run")
        self.assertIn("closed123", payload["events"][-1]["payload"]["url"])
        self.assertIn(["detail-close"], payload["calls"])

    def test_xiaohongshu_missing_waterfall_target_returns_skip_without_manual_scene(self):
        script = r"""
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { collectDetailRecords } from "./sidecar/collector/xiaohongshu.mjs";

const assetsPath = mkdtempSync(join(tmpdir(), "falcon-waterfall-target-"));
const calls = [];
const events = [];
const empty = {
  first() { return this; },
  nth() { return this; },
  locator() { return this; },
  async count() { return 0; },
  async all() { return []; },
  async boundingBox() { return null; },
  async innerText() { return ""; },
  async textContent() { return ""; },
};
const searchPage = {
  viewportSize() { return { width: 1366, height: 900 }; },
  locator(selector) { calls.push(["locator", selector]); return empty; },
  waitForEvent(event, options) { calls.push(["waitForEvent", event, options.timeout]); return Promise.resolve(null); },
  mouse: {
    async move() {},
    async click() {},
    async wheel(_x, y) { calls.push(["wheel", y]); },
  },
  keyboard: { async press(key) { calls.push(["press", key]); } },
  async waitForLoadState() {},
  async waitForTimeout() {},
  async screenshot(options) { writeFileSync(options.path, "screenshot"); },
  async title() { return "小红书搜索"; },
  url() { return "https://www.xiaohongshu.com/search_result?keyword=avatar"; },
};

const outcome = await collectDetailRecords({
  context: {},
  searchPage,
  request: {
    run_id: "waterfall-target-run",
    platform: "xiaohongshu",
    profile: "default",
    keyword: "avatar",
    max_comments_per_post: 0,
    pace: {
      max_relocate_scrolls: 1,
      scroll_delay_range_seconds: [0, 0],
      click_delay_range_ms: [0, 0],
    },
  },
  assetsPath,
  events: {
    write(level, scope, event, message, payload) {
      events.push({ level, scope, event, message, payload });
    },
  },
  posts: [
    {
      postId: "xiaohongshu:missing123",
      url: "https://www.xiaohongshu.com/explore/missing123",
      title: "missing",
    },
  ],
});

console.log(JSON.stringify({
  stopped: outcome.stopped,
  skipped: outcome.skipped,
  missingTarget: outcome.missingTarget,
  scopes: outcome.records.map((record) => record.scope),
  eventNames: events.map((event) => event.event),
  manualSnapshotExists: existsSync(join(assetsPath, "manual-action-waterfall_target_missing-snapshot.json")),
  manualScreenshotExists: existsSync(join(assetsPath, "manual-action-waterfall_target_missing.png")),
  calls,
}));
rmSync(assetsPath, { recursive: true, force: true });
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["stopped"])
        self.assertTrue(payload["skipped"])
        self.assertTrue(payload["missingTarget"])
        self.assertIn("detail_error_screenshot", payload["scopes"])
        self.assertNotIn("manual_action_snapshot", payload["scopes"])
        self.assertNotIn("manual_action_screenshot", payload["scopes"])
        self.assertNotIn("manual_action_required", payload["eventNames"])
        self.assertFalse(payload["manualSnapshotExists"])
        self.assertFalse(payload["manualScreenshotExists"])

    def test_xiaohongshu_missing_waterfall_targets_skip_and_recover_after_threshold(self):
        script = r"""
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { collectWaterfallRecords, normalizeCollectorRequest } from "./sidecar/collector/xiaohongshu.mjs";

const runRoot = mkdtempSync(join(tmpdir(), "falcon-waterfall-skip-"));
const assetsPath = join(runRoot, "assets");
mkdirSync(assetsPath, { recursive: true });
const calls = [];
const events = [];
const empty = {
  first() { return this; },
  nth() { return this; },
  locator() { return this; },
  async count() { return 0; },
  async all() { return []; },
  async boundingBox() { return null; },
  async innerText() { return ""; },
  async textContent() { return ""; },
  async getAttribute() { return ""; },
};
const searchPage = {
  viewportSize() { return { width: 1366, height: 1000 }; },
  locator(selector) { calls.push(["locator", selector]); return empty; },
  waitForEvent(event, options) { calls.push(["waitForEvent", event, options.timeout]); return Promise.resolve(null); },
  mouse: {
    async move() {},
    async click() {},
    async wheel(_x, y) { calls.push(["wheel", y]); },
  },
  keyboard: { async press(key) { calls.push(["press", key]); } },
  async waitForLoadState() {},
  async waitForTimeout() {},
  async screenshot(options) { writeFileSync(options.path, "screenshot"); },
  async title() { return "search"; },
  url() { return "https://www.xiaohongshu.com/search_result?keyword=avatar"; },
};
const request = normalizeCollectorRequest({
  run_id: "waterfall-skip-run",
  platform: "xiaohongshu",
  profile: "default",
  keyword: "avatar",
  max_posts: 6,
  max_comments_per_post: 0,
  checkpoint_enabled: true,
  pace: {
    max_relocate_scrolls: 1,
    waterfall_missing_recovery_threshold: 5,
    scroll_delay_range_seconds: [0, 0],
    scroll_distance_viewport_range: [0.5, 0.5],
    click_delay_range_ms: [0, 0],
    batch_rest_after_cards_range: [99, 99],
    batch_rest_seconds_range: [0, 0],
  },
});

const missingPosts = Array.from({ length: 5 }, (_, index) => ({
  postId: `xiaohongshu:missing12${index}`,
  url: `https://www.xiaohongshu.com/explore/missing12${index}`,
  title: "missing",
}));
const outcome = await collectWaterfallRecords({
  context: {},
  searchPage,
  request,
  assetsPath,
  events: {
    write(level, scope, event, message, payload) {
      events.push({ level, scope, event, message, payload });
    },
  },
  initialPosts: missingPosts,
});

const checkpoint = JSON.parse(readFileSync(join(runRoot, "checkpoint.json"), "utf8"));
console.log(JSON.stringify({ outcome, events, calls, checkpoint }));
rmSync(runRoot, { recursive: true, force: true });
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        event_names = [event["event"] for event in payload["events"]]
        self.assertFalse(payload["outcome"]["stopped"])
        self.assertNotIn("manual_action_required", event_names)
        self.assertEqual(event_names.count("waterfall_target_skipped"), 5)
        skipped_events = [event for event in payload["events"] if event["event"] == "waterfall_target_skipped"]
        self.assertTrue(skipped_events)
        self.assertNotIn("target_url", skipped_events[0]["payload"])
        self.assertIn("waterfall_missing_threshold_recovery", event_names)
        self.assertEqual(payload["checkpoint"]["waterfall_missing_skipped"], 5)
        self.assertEqual(payload["checkpoint"]["waterfall_missing_threshold_triggers"], 1)
        self.assertEqual(payload["outcome"]["waterfall_missing_skipped"], 5)
        self.assertEqual(payload["outcome"]["waterfall_missing_threshold_triggers"], 1)
        self.assertIn(["wheel", 500], payload["calls"])

    def test_xiaohongshu_open_detail_page_does_not_trigger_login_false_positive(self):
        script = r"""
import { detectManualAction } from "./sidecar/collector/xiaohongshu.mjs";

const empty = {
  first() { return this; },
  nth() { return this; },
  async count() { return 0; },
  async all() { return []; },
  async boundingBox() { return null; },
  async innerText() { return ""; },
  async textContent() { return ""; },
};
const detail = {
  first() { return this; },
  nth() { return this; },
  async count() { return 1; },
  async all() { return [this]; },
  async boundingBox() { return { x: 0, y: 0, width: 900, height: 700 }; },
  async innerText() { return "完整笔记正文 评论区 login 注册 手机号 验证码"; },
  async textContent() { return "完整笔记正文 评论区 login 注册 手机号 验证码"; },
};
const result = await detectManualAction({
  url() { return "https://www.xiaohongshu.com/explore/65abc123?xsec_token=token"; },
  async title() { return "sample - 小红书"; },
  locator(selector) {
    return selector === "#noteContainer" || selector === "body" ? detail : empty;
  },
});

console.log(JSON.stringify({ result }));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIsNone(payload["result"])

    def test_xiaohongshu_home_feed_login_link_does_not_trigger_manual_action(self):
        script = r"""
import { detectManualAction } from "./sidecar/collector/xiaohongshu.mjs";

const body = {
  first() { return this; },
  nth() { return this; },
  async count() { return 1; },
  async all() { return [this]; },
  async boundingBox() { return { x: 0, y: 0, width: 1200, height: 800 }; },
  async innerText() { return "发现 直播 发布 通知 我 登录 推荐 穿搭 美食"; },
  async textContent() { return "发现 直播 发布 通知 我 登录 推荐 穿搭 美食"; },
};
const empty = {
  first() { return this; },
  nth() { return this; },
  async count() { return 0; },
  async all() { return []; },
  async boundingBox() { return null; },
  async innerText() { return ""; },
  async textContent() { return ""; },
};

const result = await detectManualAction({
  url() { return "https://www.xiaohongshu.com/explore"; },
  async title() { return "小红书 - 你的生活兴趣社区"; },
  locator(selector) {
    return selector === "body" ? body : empty;
  },
});

console.log(JSON.stringify({ result }));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIsNone(payload["result"])

    def test_xiaohongshu_plain_script_word_does_not_trigger_account_risk(self):
        script = r"""
import { detectManualAction } from "./sidecar/collector/xiaohongshu.mjs";

const body = {
  first() { return this; },
  nth() { return this; },
  async count() { return 1; },
  async all() { return [this]; },
  async boundingBox() { return { x: 0, y: 0, width: 1200, height: 800 }; },
  async innerText() { return "AI \u811a\u672c\u7f16\u5199\u6559\u7a0b \u5185\u5bb9\u521b\u4f5c\u5de5\u5177 \u9996\u9875\u63a8\u8350"; },
  async textContent() { return "AI \u811a\u672c\u7f16\u5199\u6559\u7a0b \u5185\u5bb9\u521b\u4f5c\u5de5\u5177 \u9996\u9875\u63a8\u8350"; },
};
const empty = {
  first() { return this; },
  nth() { return this; },
  async count() { return 0; },
  async all() { return []; },
  async boundingBox() { return null; },
};

const result = await detectManualAction({
  url() { return "https://www.xiaohongshu.com/explore"; },
  async title() { return "\u5c0f\u7ea2\u4e66"; },
  locator(selector) {
    return selector === "body" ? body : empty;
  },
});

console.log(JSON.stringify({ result }));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIsNone(payload["result"])

    def test_xiaohongshu_account_risk_warning_triggers_manual_action(self):
        script = r"""
import { detectManualAction } from "./sidecar/collector/xiaohongshu.mjs";

const body = {
  first() { return this; },
  nth() { return this; },
  async count() { return 1; },
  async all() { return [this]; },
  async boundingBox() { return { x: 0, y: 0, width: 900, height: 500 }; },
  async innerText() { return "账号违规预警：检测到第三方工具或自动浏览脚本"; },
  async textContent() { return "账号违规预警：检测到第三方工具或自动浏览脚本"; },
};
const empty = {
  first() { return this; },
  nth() { return this; },
  async count() { return 0; },
  async all() { return []; },
  async boundingBox() { return null; },
};

const result = await detectManualAction({
  url() { return "https://www.xiaohongshu.com/"; },
  async title() { return "小红书"; },
  locator(selector) {
    return selector === "body" ? body : empty;
  },
});

console.log(JSON.stringify(result));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["reason"], "account_risk_warning")
        self.assertEqual(payload["matched_signals"][0]["reason"], "account_risk_warning")
        self.assertEqual(payload["matched_signals"][0]["source"], "body")

    def test_xiaohongshu_detail_snapshot_reads_visible_detail_container_without_image_urls(self):
        script = r"""
import { extractDetailSnapshot } from "./sidecar/collector/xiaohongshu.mjs";

function emptyCollection() {
  return {
    first() { return emptyLocator(); },
    nth() { return emptyLocator(); },
    async count() { return 0; },
    async all() { return []; },
  };
}

function collection(items) {
  return {
    first() { return items[0] || emptyLocator(); },
    nth(index) { return items[index] || emptyLocator(); },
    async count() { return items.length; },
    async all() { return items; },
  };
}

function emptyLocator() {
  return makeLocator({ box: null });
}

function makeLocator({ text = "", box = { x: 10, y: 10, width: 320, height: 40 }, attrs = {}, children = {}, lists = {} } = {}) {
  return {
    first() { return this; },
    nth() { return this; },
    async count() { return box ? 1 : 0; },
    async all() { return box ? [this] : []; },
    async boundingBox() { return box; },
    async innerText() { return text; },
    async textContent() { return text; },
    async getAttribute(name) { return attrs[name] || ""; },
    locator(selector) {
      if (children[selector]) return collection([children[selector]]);
      if (lists[selector]) return collection(lists[selector]);
      return emptyCollection();
    },
  };
}

const comment = makeLocator({
  text: "commenter\nuseful comment",
  box: { x: 20, y: 360, width: 420, height: 72 },
  children: {
    "[class*='author']": makeLocator({ text: "commenter" }),
    "[class*='content']": makeLocator({ text: "useful comment" }),
  },
});
const detailRoot = makeLocator({
  box: { x: 0, y: 0, width: 900, height: 700 },
  children: {
    "#detail-title": makeLocator({ text: "detail title" }),
    "#detail-desc": makeLocator({ text: "detail body" }),
    "a[href*='/user/profile']": makeLocator({ text: "detail author" }),
    "[class*='interact']": makeLocator({ text: "12 likes" }),
  },
  lists: {
    ".comment-item, [class*='comment-item'], [class*='reply-item']": [comment],
    "img": [],
  },
});

const page = {
  url() { return "https://www.xiaohongshu.com/explore/detail"; },
  locator(selector) {
    return selector === "#noteContainer" ? collection([detailRoot]) : emptyCollection();
  },
};

const snapshot = await extractDetailSnapshot(page, 2);
console.log(JSON.stringify(snapshot));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["images"], [])
        self.assertEqual(payload["title"], "detail title")
        self.assertEqual(payload["comments"][0]["content"], "useful comment")

    def test_xiaohongshu_visible_screenshot_media_asset_has_no_remote_url(self):
        script = r"""
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { captureVisibleMediaScreenshots, normalizeCollectorRequest } from "./sidecar/collector/xiaohongshu.mjs";

function emptyCollection() {
  return {
    first() { return emptyLocator(); },
    nth() { return emptyLocator(); },
    async count() { return 0; },
    async all() { return []; },
  };
}

function collection(items) {
  return {
    first() { return items[0] || emptyLocator(); },
    nth(index) { return items[index] || emptyLocator(); },
    async count() { return items.length; },
    async all() { return items; },
  };
}

function emptyLocator() {
  return makeLocator({ box: null });
}

function makeLocator({ box = { x: 0, y: 0, width: 320, height: 240 }, lists = {}, screenshotBody = "" } = {}) {
  return {
    first() { return this; },
    nth() { return this; },
    async count() { return box ? 1 : 0; },
    async all() { return box ? [this] : []; },
    async boundingBox() { return box; },
    locator(selector) {
      if (lists[selector]) return collection(lists[selector]);
      return emptyCollection();
    },
    async screenshot(options) {
      writeFileSync(options.path, screenshotBody || "visible-image");
    },
  };
}

const assetsPath = mkdtempSync(join(tmpdir(), "falcon-visible-media-"));
const image = makeLocator({ box: { x: 12, y: 20, width: 320, height: 240 }, screenshotBody: "fake-png" });
const root = makeLocator({
  box: { x: 0, y: 0, width: 900, height: 700 },
  lists: { "img": [image] },
});
const events = [];

const records = await captureVisibleMediaScreenshots({
  page: {
    locator(selector) {
      return selector === "#noteContainer" ? collection([root]) : emptyCollection();
    },
  },
  request: normalizeCollectorRequest({
    run_id: "visible-media-run",
    platform: "xiaohongshu",
    media_policy: "visible_screenshot",
  }),
  assetsPath,
  stem: "post-1",
  postId: "xiaohongshu:post-1",
  events: {
    write(level, scope, event, message, payload) {
      events.push({ level, scope, event, message, payload });
    },
  },
});

console.log(JSON.stringify({ records, events }));
rmSync(assetsPath, { recursive: true, force: true });
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload["records"]), 1)
        record = payload["records"][0]
        self.assertEqual(record["type"], "media_asset")
        self.assertEqual(record["source"], "visible_screenshot")
        self.assertEqual(record["url"], "")
        self.assertEqual(record["mime_type"], "image/png")
        self.assertTrue(record["sha256"])

    def test_xiaohongshu_browser_loaded_image_media_asset_uses_cached_response_body(self):
        script = r"""
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { captureVisibleMediaAssets, createLoadedImageStore, normalizeCollectorRequest } from "./sidecar/collector/xiaohongshu.mjs";

function emptyCollection() {
  return {
    first() { return emptyLocator(); },
    nth() { return emptyLocator(); },
    async count() { return 0; },
    async all() { return []; },
  };
}

function collection(items) {
  return {
    first() { return items[0] || emptyLocator(); },
    nth(index) { return items[index] || emptyLocator(); },
    async count() { return items.length; },
    async all() { return items; },
  };
}

function emptyLocator() {
  return makeLocator({ box: null });
}

function makeLocator({ box = { x: 0, y: 0, width: 320, height: 240 }, attrs = {}, lists = {}, screenshotBody = "" } = {}) {
  return {
    screenshotCalls: [],
    first() { return this; },
    nth() { return this; },
    async count() { return box ? 1 : 0; },
    async all() { return box ? [this] : []; },
    async boundingBox() { return box; },
    async getAttribute(name) { return attrs[name] ?? ""; },
    locator(selector) {
      if (lists[selector]) return collection(lists[selector]);
      return emptyCollection();
    },
    async screenshot(options) {
      this.screenshotCalls.push(options);
      writeFileSync(options.path, screenshotBody || "visible-image");
    },
  };
}

function fakePage(root, response) {
  const handlers = {};
  return {
    on(event, handler) {
      handlers[event] = handlers[event] || [];
      handlers[event].push(handler);
    },
    async emitResponse() {
      for (const handler of handlers.response || []) {
        handler(response);
      }
      await response.bodySettled;
    },
    locator(selector) {
      return selector === "#noteContainer" ? collection([root]) : emptyCollection();
    },
  };
}

function fakeResponse({ url, mimeType, body }) {
  let settle;
  const bodySettled = new Promise((resolve) => { settle = resolve; });
  return {
    bodySettled,
    url() { return url; },
    headers() { return { "content-type": mimeType }; },
    async body() {
      settle();
      return Buffer.from(body);
    },
  };
}

const assetsPath = mkdtempSync(join(tmpdir(), "falcon-loaded-media-"));
const imageUrl = "https://sns-webpic-qc.xhscdn.com/notes_pre_post/loaded-image-id!nd_dft_wlteh_webp_3";
const response = fakeResponse({ url: imageUrl, mimeType: "image/jpeg", body: "loaded-image-body" });
const image = makeLocator({
  box: { x: 12, y: 20, width: 320, height: 240 },
  attrs: { src: imageUrl },
  screenshotBody: "screenshot-fallback-body",
});
const duplicateImage = makeLocator({
  box: { x: 24, y: 40, width: 320, height: 240 },
  attrs: { src: imageUrl },
  screenshotBody: "duplicate-screenshot-fallback-body",
});
const root = makeLocator({
  box: { x: 0, y: 0, width: 900, height: 700 },
  lists: { "img": [image, duplicateImage] },
});
const page = fakePage(root, response);
const loadedImages = createLoadedImageStore();
loadedImages.attachPage(page);
await page.emitResponse();

const events = [];
const records = await captureVisibleMediaAssets({
  page,
  request: normalizeCollectorRequest({
    run_id: "loaded-media-run",
    platform: "xiaohongshu",
    media_policy: "browser_loaded_image",
  }),
  assetsPath,
  stem: "post-1",
  postId: "xiaohongshu:post-1",
  events: {
    write(level, scope, event, message, payload) {
      events.push({ level, scope, event, message, payload });
    },
  },
  loadedImages,
});

const fileBody = records[0] ? readFileSync(records[0].path, "utf8") : "";
console.log(JSON.stringify({ records, events, fileBody, screenshotCalls: image.screenshotCalls.length }));
rmSync(assetsPath, { recursive: true, force: true });
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload["records"]), 1)
        record = payload["records"][0]
        self.assertEqual(record["type"], "media_asset")
        self.assertEqual(record["source"], "browser_loaded_image")
        self.assertEqual(record["url"], "https://sns-webpic-qc.xhscdn.com/notes_pre_post/loaded-image-id!nd_dft_wlteh_webp_3")
        self.assertEqual(record["mime_type"], "image/jpeg")
        self.assertTrue(record["path"].endswith(".jpg"))
        self.assertEqual(payload["fileBody"], "loaded-image-body")
        self.assertEqual(payload["screenshotCalls"], 0)

    def test_xiaohongshu_browser_loaded_image_media_asset_falls_back_to_screenshot(self):
        script = r"""
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { captureVisibleMediaAssets, createLoadedImageStore, normalizeCollectorRequest } from "./sidecar/collector/xiaohongshu.mjs";

function emptyCollection() {
  return {
    first() { return emptyLocator(); },
    nth() { return emptyLocator(); },
    async count() { return 0; },
    async all() { return []; },
  };
}

function collection(items) {
  return {
    first() { return items[0] || emptyLocator(); },
    nth(index) { return items[index] || emptyLocator(); },
    async count() { return items.length; },
    async all() { return items; },
  };
}

function emptyLocator() {
  return makeLocator({ box: null });
}

function makeLocator({ box = { x: 0, y: 0, width: 320, height: 240 }, attrs = {}, lists = {}, screenshotBody = "" } = {}) {
  return {
    first() { return this; },
    nth() { return this; },
    async count() { return box ? 1 : 0; },
    async all() { return box ? [this] : []; },
    async boundingBox() { return box; },
    async getAttribute(name) { return attrs[name] ?? ""; },
    locator(selector) {
      if (lists[selector]) return collection(lists[selector]);
      return emptyCollection();
    },
    async screenshot(options) {
      writeFileSync(options.path, screenshotBody || "visible-image");
    },
  };
}

const assetsPath = mkdtempSync(join(tmpdir(), "falcon-loaded-media-fallback-"));
const image = makeLocator({
  box: { x: 12, y: 20, width: 320, height: 240 },
  attrs: { src: "https://sns-webpic-qc.xhscdn.com/notes_pre_post/not-loaded!nd_dft_wlteh_webp_3" },
  screenshotBody: "fallback-png",
});
const root = makeLocator({
  box: { x: 0, y: 0, width: 900, height: 700 },
  lists: { "img": [image] },
});
const records = await captureVisibleMediaAssets({
  page: {
    locator(selector) {
      return selector === "#noteContainer" ? collection([root]) : emptyCollection();
    },
  },
  request: normalizeCollectorRequest({
    run_id: "loaded-media-fallback-run",
    platform: "xiaohongshu",
    media_policy: "browser_loaded_image",
  }),
  assetsPath,
  stem: "post-1",
  postId: "xiaohongshu:post-1",
  events: { write() {} },
  loadedImages: createLoadedImageStore(),
});

console.log(JSON.stringify({ records }));
rmSync(assetsPath, { recursive: true, force: true });
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload["records"]), 1)
        self.assertEqual(payload["records"][0]["source"], "visible_screenshot")
        self.assertEqual(payload["records"][0]["url"], "")

    def test_xiaohongshu_media_url_dedupe_collapses_cdn_variants(self):
        script = r"""
import { uniqueMediaUrls } from "./sidecar/collector/xiaohongshu.mjs";

const detailUrl = "https://sns-webpic-qc.xhscdn.com/202605231943/da4f44570b3b857d293582c72529419e/notes_pre_post/1040g3k031ig9al7jns005nqfivhg9ckarv489h0!nd_dft_wlteh_webp_3";
const cardUrl = "https://sns-webpic-qc.xhscdn.com/202605231942/108d1b1f65ce49c82955b43c18a5a9fc/notes_pre_post/1040g3k031ig9al7jns005nqfivhg9ckarv489h0!nc_n_webp_mw_1";
const otherUrl = "https://sns-webpic-qc.xhscdn.com/202605231943/da4f44570b3b857d293582c72529419e/notes_pre_post/another-image-id!nd_dft_wlteh_webp_3";

console.log(JSON.stringify(uniqueMediaUrls([detailUrl, cardUrl, otherUrl])));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload, [
            "https://sns-webpic-qc.xhscdn.com/202605231943/da4f44570b3b857d293582c72529419e/notes_pre_post/1040g3k031ig9al7jns005nqfivhg9ckarv489h0!nd_dft_wlteh_webp_3",
            "https://sns-webpic-qc.xhscdn.com/202605231943/da4f44570b3b857d293582c72529419e/notes_pre_post/another-image-id!nd_dft_wlteh_webp_3",
        ])

    def test_xiaohongshu_detail_metrics_ignore_body_numbers_and_include_collects(self):
        script = r"""
import { normalizeDetailSnapshot } from "./sidecar/collector/xiaohongshu.mjs";

const normalized = normalizeDetailSnapshot({
  body: "Daily UV3000+ should stay in body and not become likes.",
  interactionText: "Daily UV3000+",
  interactionMetrics: [
    { role: "like", text: "24", label: "like button" },
    { role: "collect", text: "10", label: "collect button" },
    { role: "comment", text: "37", label: "comment button" },
  ],
});

console.log(JSON.stringify(normalized.metrics));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload, {"likes": 24, "collects": 10, "comments": 37})

    def test_xiaohongshu_detail_snapshot_marks_reply_relationship(self):
        script = r"""
import { extractDetailSnapshot, normalizeDetailSnapshot } from "./sidecar/collector/xiaohongshu.mjs";

const node = (values = {}) => ({
  first() { return this; },
  nth() { return this; },
  async count() { return values.box === null ? 0 : 1; },
  async all() { return values.box === null ? [] : [this]; },
  async boundingBox() { return values.box === null ? null : (values.box || { x: 20, y: 20, width: 360, height: 50 }); },
  async innerText() { return values.text || ""; },
  async textContent() { return values.text || ""; },
  async getAttribute(name) { return values.attrs?.[name] || (name === "class" ? values.className || "" : ""); },
  locator(selector) {
    const item = values.selectors?.[selector];
    if (item) return collection([item]);
    return collection(values.lists?.[selector] || []);
  },
});

const collection = (items) => ({
  first() { return items[0] || node({ box: null }); },
  nth(index) { return items[index] || node({ box: null }); },
  async count() { return items.length; },
  async all() { return items; },
});

const reply = node({
  text: "replyer\nReply target user: this is a nested reply\n1",
  className: "reply-item",
  selectors: {
    "[class*='author']": node({ text: "replyer" }),
    "[class*='content']": node({ text: "Reply target user: this is a nested reply" }),
    "[class*='like']": node({ text: "1" }),
  },
});
const detailRoot = node({
  box: { x: 0, y: 0, width: 900, height: 700 },
  selectors: {
    "#detail-title": node({ text: "detail title" }),
  },
  lists: {
    ".comment-item, [class*='comment-item']": [reply],
    ".comment-item, [class*='comment-item'], [class*='reply-item']": [reply],
    "img": [],
  },
});
const page = {
  url() { return "https://www.xiaohongshu.com/explore/detail"; },
  locator(selector) {
    return selector === "#noteContainer" ? collection([detailRoot]) : collection([]);
  },
};

const normalized = normalizeDetailSnapshot(await extractDetailSnapshot(page, 5));
console.log(JSON.stringify(normalized.comments[0]));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["comment_type"], "reply")
        self.assertEqual(payload["reply_to"], "target user")
        self.assertEqual(payload["content"], "this is a nested reply")

    def test_xiaohongshu_expands_reply_threads_with_mouse_click(self):
        script = r"""
import { expandVisibleCommentReplies } from "./sidecar/collector/xiaohongshu.mjs";

const calls = [];
let available = true;
const replyLocator = {
  first() { return this; },
  async count() { calls.push(["count"]); return available ? 1 : 0; },
  async all() { calls.push(["all"]); return available ? [this] : []; },
  async scrollIntoViewIfNeeded(options) { calls.push(["scroll", options.timeout]); },
  async boundingBox() { calls.push(["box"]); return { x: 120, y: 220, width: 160, height: 32 }; },
  async click() { calls.push(["locator-click"]); },
};
const page = {
  getByText(pattern) { calls.push(["getByText", String(pattern)]); return replyLocator; },
  mouse: {
    async move(x, y, options) { calls.push(["move", Math.round(x), Math.round(y), options.steps]); },
    async click(x, y, options) {
      calls.push(["mouse-click", Math.round(x), Math.round(y), options.delay]);
      available = false;
    },
  },
  async waitForTimeout(ms) { calls.push(["wait", ms]); },
};

const clicked = await expandVisibleCommentReplies(page, 3);
console.log(JSON.stringify({ clicked, calls }));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        call_names = [call[0] for call in payload["calls"]]
        self.assertEqual(payload["clicked"], 1)
        self.assertIn("mouse-click", call_names)
        self.assertNotIn("locator-click", call_names)

    def test_xiaohongshu_prepares_fifty_comments_without_fixed_scroll_or_reply_caps(self):
        script = r"""
import { normalizeCollectorRequest, prepareVisibleCommentsForExtraction } from "./sidecar/collector/xiaohongshu.mjs";

let commentCount = 3;
let replyClicks = 0;
const calls = [];

const empty = {
  first() { return this; },
  nth() { return this; },
  async count() { return 0; },
  async all() { return []; },
  async boundingBox() { return null; },
  async innerText() { return ""; },
  async textContent() { return ""; },
  async getAttribute() { return ""; },
};
const commentCollection = {
  first() { return this; },
  nth() { return this; },
  async count() { calls.push(["comment-count", commentCount]); return commentCount; },
  async all() { return []; },
};
const replyLocator = {
  first() { return this; },
  async count() { return replyClicks < 10 ? 1 : 0; },
  async all() { return replyClicks < 10 ? [this] : []; },
  async scrollIntoViewIfNeeded() { calls.push(["reply-scroll"]); },
  async boundingBox() { return { x: 120, y: 220, width: 180, height: 32 }; },
  async innerText() { return "expand replies"; },
  async textContent() { return "expand replies"; },
  async getAttribute() { return ""; },
};
const root = {
  locator(selector) {
    calls.push(["root-locator", selector]);
    if (selector === ".comment-item, [class*='comment-item'], [class*='reply-item']") {
      return commentCollection;
    }
    return empty;
  },
};
const page = {
  viewportSize() { return { width: 1366, height: 1000 }; },
  getByText(pattern) { calls.push(["getByText", String(pattern)]); return replyLocator; },
  mouse: {
    async move(x, y, options) { calls.push(["move", Math.round(x), Math.round(y), options.steps]); },
    async click(x, y, options) { replyClicks += 1; calls.push(["reply-click", Math.round(x), Math.round(y), options.delay]); },
    async wheel(x, y) { commentCount += 6; calls.push(["wheel", x, y, commentCount]); },
  },
  async waitForTimeout(ms) { calls.push(["wait", ms]); },
};
const request = normalizeCollectorRequest({
  run_id: "comment-pace-run",
  platform: "xiaohongshu",
  max_comments_per_post: 50,
});
const originalRandom = Math.random;
Math.random = () => 0;
const outcome = await prepareVisibleCommentsForExtraction(page, root, request, 50);
Math.random = originalRandom;
console.log(JSON.stringify({ outcome, calls, commentCount, replyClicks }));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        call_names = [call[0] for call in payload["calls"]]
        self.assertGreaterEqual(payload["outcome"]["scrolls"], 7)
        self.assertGreaterEqual(payload["replyClicks"], 7)
        self.assertIn("wheel", call_names)
        self.assertIn(["wait", 4000], payload["calls"])
        self.assertIn(["wait", 5000], payload["calls"])

    def test_xiaohongshu_post_progress_payload_counts_current_post(self):
        script = r"""
import { postProgressPayload } from "./sidecar/collector/xiaohongshu.mjs";

console.log(JSON.stringify({
  opening: postProgressPayload({
    request: { run_id: "progress-run" },
    platform: "xiaohongshu",
    postId: "xiaohongshu:post-5",
    postUrl: "https://www.xiaohongshu.com/explore/post-5",
    index: 4,
    total: 5,
    phase: "opening",
  }),
  collected: postProgressPayload({
    request: { run_id: "progress-run" },
    platform: "xiaohongshu",
    postId: "xiaohongshu:post-5",
    postUrl: "https://www.xiaohongshu.com/explore/post-5",
    index: 4,
    total: 5,
    phase: "collected",
  }),
}));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["opening"]["post_index"], 5)
        self.assertEqual(payload["opening"]["post_total"], 5)
        self.assertEqual(payload["opening"]["post_percent"], 100)
        self.assertEqual(payload["opening"]["phase"], "opening")
        self.assertEqual(payload["collected"]["post_percent"], 100)
        self.assertEqual(payload["collected"]["phase"], "collected")

    def run_sidecar(self, request, env=None):
        temp_root = Path(self.temp_dir.name)
        run_dir = temp_root / "runtime" / "collector" / request["run_id"]
        assets_dir = run_dir / "assets"
        profile_dir = (
            temp_root
            / "browser-profiles"
            / request["platform"]
            / request["profile"]
        )
        request_path = run_dir / "request.json"
        events_path = run_dir / "events.jsonl"
        records_path = run_dir / "records.jsonl"

        run_dir.mkdir(parents=True)
        request_path.write_text(
            json.dumps(request, ensure_ascii=False),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                "node",
                str(SIDECAR),
                "--request",
                str(request_path),
                "--events",
                str(events_path),
                "--output",
                str(records_path),
                "--assets",
                str(assets_dir),
                "--profile",
                str(profile_dir),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        return result, events_path, records_path, assets_dir

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_xiaohongshu_dry_run_writes_events_records_and_assets(self):
        result, events_path, records_path, assets_dir = self.run_sidecar(
            {
                "schema_version": 1,
                "run_id": "run-dry-xhs",
                "platform": "xiaohongshu",
                "profile": "default",
                "keyword": "运营助手",
                "max_posts": 2,
                "max_comments_per_post": 1,
                "headed": False,
                "dry_run": True,
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(assets_dir.is_dir())

        events = read_jsonl(events_path)
        self.assertGreaterEqual(len(events), 4)
        for index, event in enumerate(events, start=1):
            self.assertEqual(event["sequence"], index)
            self.assertIsInstance(event["time"], str)
            for field in [
                "level",
                "scope",
                "event",
                "message",
                "payload",
            ]:
                self.assertIn(field, event)

        event_types = {event["event"] for event in events}
        self.assertTrue(
            {
                "run_started",
                "profile_loaded",
                "record_collected",
                "run_completed",
            }.issubset(event_types)
        )

        records = read_jsonl(records_path)
        record_types = {record["type"] for record in records}
        self.assertTrue(
            {"post", "comment", "evidence", "media_asset"}.issubset(record_types)
        )
        for record in records:
            self.assertEqual(record.get("run_id"), "run-dry-xhs")
            if record["type"] != "evidence":
                self.assertEqual(record.get("platform"), "xiaohongshu")
            if record["type"] == "media_asset":
                self.assertTrue(Path(record["path"]).is_file())

    def test_unsupported_platform_writes_failure_event_and_exits_nonzero(self):
        result, events_path, records_path, assets_dir = self.run_sidecar(
            {
                "schema_version": 1,
                "run_id": "run-bad-platform",
                "platform": "unsupported",
                "profile": "default",
                "keyword": "运营助手",
                "max_posts": 1,
                "max_comments_per_post": 1,
                "headed": False,
                "dry_run": True,
            }
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(assets_dir.is_dir())
        self.assertFalse(records_path.exists())

        events = read_jsonl(events_path)
        self.assertEqual(events[-1]["event"], "run_failed")
        self.assertEqual(events[-1]["payload"]["platform"], "unsupported")

    def test_sidecar_event_writer_streams_each_event_before_final_flush(self):
        script = r"""
import { EventWriter } from "./sidecar/collector/index.mjs";
import { readFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const path = join(tmpdir(), `falcon-event-stream-${Date.now()}.jsonl`);
rmSync(path, { force: true });
const events = new EventWriter(path);
events.write("info", "collector", "run_started", "started", {});
const afterFirst = readFileSync(path, "utf8").trim().split("\n").length;
events.write("info", "collector", "profile_loaded", "profile", {});
const afterSecond = readFileSync(path, "utf8").trim().split("\n").length;
await events.flush();
const afterFlush = readFileSync(path, "utf8").trim().split("\n").length;
rmSync(path, { force: true });
console.log(JSON.stringify({ afterFirst, afterSecond, afterFlush }));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["afterFirst"], 1)
        self.assertEqual(payload["afterSecond"], 2)
        self.assertEqual(payload["afterFlush"], 2)

    def test_xiaohongshu_real_mode_missing_playwright_is_clear_failure(self):
        env = {
            **dict(os.environ),
            "FALCON_COLLECTOR_FORCE_PLAYWRIGHT_MISSING": "1",
        }
        result, events_path, records_path, assets_dir = self.run_sidecar(
            {
                "schema_version": 1,
                "run_id": "run-real-missing-playwright",
                "platform": "xiaohongshu",
                "profile": "default",
                "keyword": "content ops",
                "max_posts": 1,
                "max_comments_per_post": 0,
                "headed": True,
                "dry_run": False,
            },
            env=env,
        )

        self.assertEqual(result.returncode, 1)
        self.assertTrue(assets_dir.is_dir())
        self.assertTrue(records_path.exists())
        records = read_jsonl(records_path)
        self.assertEqual(records[-1]["type"], "evidence")
        self.assertEqual(records[-1]["scope"], "failure_snapshot")
        self.assertTrue(Path(records[-1]["path"]).is_file())
        self.assertEqual(records[-1]["payload"]["code"], "PLAYWRIGHT_MISSING")

        events = read_jsonl(events_path)
        self.assertEqual(events[-1]["event"], "run_failed")
        self.assertIn("Playwright is required", events[-1]["message"])
        self.assertIn("sidecar", events[-1]["message"])
        self.assertEqual(events[-1]["payload"]["code"], "PLAYWRIGHT_MISSING")
        self.assertEqual(events[-1]["payload"]["failure_evidence"], records[-1]["path"])

    def test_sidecar_run_failed_event_uses_existing_failure_snapshot_context(self):
        script = r"""
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { writeFailureRecordsOnError } from "./sidecar/collector/index.mjs";

const runtimePath = mkdtempSync(join(tmpdir(), "falcon-failure-records-"));
const outputPath = join(runtimePath, "records.jsonl");
const assetsPath = join(runtimePath, "assets");
const error = new Error("已输入关键词，但页面没有进入搜索结果。");
error.code = "SEARCH_NOT_CONFIRMED";
error.failurePayload = {
  reason: "search_not_confirmed",
  url: "https://www.xiaohongshu.com/explore",
  title: "小红书 首页",
  matched_signals: [
    { reason: "search_not_confirmed", signal: "expected_keyword_not_confirmed", source: "search_confirmation" },
  ],
};
error.partialRecords = [
  {
    type: "evidence",
    run_id: "search-confirmation-run",
    platform: "xiaohongshu",
    evidence_id: "search-confirmation-run-failure-snapshot",
    scope: "failure_snapshot",
    path: join(assetsPath, "failure-search_not_confirmed-snapshot.json"),
    payload: error.failurePayload,
  },
  {
    type: "evidence",
    run_id: "search-confirmation-run",
    platform: "xiaohongshu",
    evidence_id: "search-confirmation-run-failure-screenshot",
    scope: "failure_screenshot",
    path: join(assetsPath, "failure-search_not_confirmed.png"),
    payload: { reason: "search_not_confirmed" },
  },
];
const result = await writeFailureRecordsOnError(outputPath, error, {
  request: { run_id: "search-confirmation-run", platform: "xiaohongshu", profile: "default", keyword: "AI氛围感" },
  assetsPath,
});
const records = readFileSync(outputPath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
console.log(JSON.stringify({ result, records }));
rmSync(runtimePath, { recursive: true, force: true });
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["result"]["count"], 2)
        self.assertTrue(payload["result"]["failureEvidence"].endswith("failure-search_not_confirmed-snapshot.json"))
        self.assertEqual(payload["result"]["failurePayload"]["reason"], "search_not_confirmed")
        self.assertEqual([record["scope"] for record in payload["records"]], ["failure_snapshot", "failure_screenshot"])
        self.assertNotIn("run-failed-snapshot.json", payload["result"]["failureEvidence"])


if __name__ == "__main__":
    unittest.main()
