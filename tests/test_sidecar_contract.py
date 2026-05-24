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
  text: "小红书封面设计技巧\n何花说升学\n04-04\n1.2万",
  title: "",
  author: "何花说升学04-04",
  likesText: "1.2万",
});
const duplicate = normalizeSearchCards(
  [
    first,
    {
      href: "https://www.xiaohongshu.com/explore/65abc123?xsec_token=two",
      text: "小红书封面设计技巧\n何花说升学\n04-04\n1.2万",
      title: "小红书封面设计技巧",
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
        self.assertEqual(payload["title"], "小红书封面设计技巧")
        self.assertEqual(payload["author"], "何花说升学")
        self.assertEqual(payload["publishedAt"], "04-04")
        self.assertEqual(payload["likes"], 12000)
        self.assertEqual(payload["duplicateCount"], 1)

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

function makeLocator(name, box, safePoint = null) {
  return {
    name,
    first() { return this; },
    async count() { calls.push(["count", name]); return box ? 1 : 0; },
    async scrollIntoViewIfNeeded(options) { calls.push(["scroll", name, options.timeout]); },
    async boundingBox() { calls.push(["box", name]); return box; },
    async evaluate() { calls.push(["evaluate", name]); return safePoint; },
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
  {
    x: 210,
    y: 200,
    label: "center",
    href: "https://www.xiaohongshu.com/search_result/65abc123?xsec_token=token",
    rect: { x: 100, y: 180, width: 220, height: 40 },
    hitClass: "title",
  },
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
        self.assertIn(["evaluate", "visible-title"], payload["calls"])
        self.assertNotIn(["evaluate", "offscreen-note"], payload["calls"])

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
  async evaluate() { calls.push(["generic-evaluate"]); return { x: 200, y: 260, label: "center" }; },
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

const events = [];
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
  assetsPath: ".",
  events: {
    write(level, scope, event, message, payload) {
      events.push({ level, scope, event, message, payload });
    },
  },
  reason: "app_scan_required",
  detail: "需要人工处理",
});

console.log(JSON.stringify({ records, event: events[0] }));
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
        self.assertEqual(payload["records"], [])

    def test_xiaohongshu_open_detail_page_does_not_trigger_login_false_positive(self):
        script = r"""
import { detectManualAction } from "./sidecar/collector/xiaohongshu.mjs";

const result = await detectManualAction({
  async evaluate() {
    return {
      url: "https://www.xiaohongshu.com/explore/65abc123?xsec_token=token",
      title: "sample - 小红书",
      text: "完整笔记正文 评论区 login 注册 手机号 验证码",
      hasDetailContainer: true,
    };
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

    def test_xiaohongshu_detail_snapshot_uses_only_detail_container_images(self):
        script = r"""
import { extractDetailSnapshot } from "./sidecar/collector/xiaohongshu.mjs";

const node = (values = {}) => ({
  innerText: values.text || "",
  textContent: values.text || "",
  currentSrc: values.currentSrc || "",
  src: values.src || "",
  naturalWidth: values.width || 0,
  naturalHeight: values.height || 0,
  width: values.width || 0,
  height: values.height || 0,
  querySelector(selector) {
    return values.selectors?.[selector] || null;
  },
  querySelectorAll(selector) {
    return values.lists?.[selector] || [];
  },
});

const detailImage = node({
  currentSrc: "https://img.example/detail.webp",
  width: 640,
  height: 480,
});
const backgroundImage = node({
  currentSrc: "https://img.example/search-card.webp",
  width: 640,
  height: 480,
});
const comment = node({
  text: "commenter\nuseful comment",
  selectors: {
    "[class*='author']": node({ text: "commenter" }),
    "[class*='content']": node({ text: "useful comment" }),
  },
});
const detailRoot = node({
  selectors: {
    "#detail-title": node({ text: "detail title" }),
    "#detail-desc": node({ text: "detail body" }),
    "a[href*='/user/profile']": node({ text: "detail author" }),
    "[class*='interact']": node({ text: "12 likes" }),
  },
  lists: {
    "img": [detailImage],
    ".comment-item, [class*='comment-item']": [comment],
  },
});
const fakeDocument = {
  images: [detailImage, backgroundImage],
  querySelector(selector) {
    if (selector === "#noteContainer, .note-detail-mask .note-container, .note-container, .note-detail") {
      return detailRoot;
    }
    return null;
  },
  querySelectorAll(selector) {
    return selector === ".comment-item, [class*='comment-item']" ? [comment] : [];
  },
};

const page = {
  async evaluate(callback, commentLimit) {
    const oldDocument = globalThis.document;
    const oldLocation = globalThis.location;
    globalThis.document = fakeDocument;
    globalThis.location = { href: "https://www.xiaohongshu.com/explore/detail" };
    try {
      return callback(commentLimit);
    } finally {
      globalThis.document = oldDocument;
      globalThis.location = oldLocation;
    }
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
        self.assertEqual(payload["images"], ["https://img.example/detail.webp"])
        self.assertEqual(payload["title"], "detail title")
        self.assertEqual(payload["comments"][0]["content"], "useful comment")

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
  innerText: values.text || "",
  textContent: values.text || "",
  className: values.className || "",
  currentSrc: values.currentSrc || "",
  src: values.src || "",
  naturalWidth: values.width || 0,
  naturalHeight: values.height || 0,
  width: values.width || 0,
  height: values.height || 0,
  getAttribute(name) {
    return values.attrs?.[name] || "";
  },
  querySelector(selector) {
    return values.selectors?.[selector] || null;
  },
  querySelectorAll(selector) {
    return values.lists?.[selector] || [];
  },
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
  async evaluate(callback, commentLimit) {
    const oldDocument = globalThis.document;
    const oldLocation = globalThis.location;
    globalThis.document = {
      querySelector(selector) {
        if (selector === "#noteContainer, .note-detail-mask .note-container, .note-container, .note-detail") return detailRoot;
        return null;
      },
      querySelectorAll() { return []; },
    };
    globalThis.location = { href: "https://www.xiaohongshu.com/explore/detail" };
    try {
      return callback(commentLimit);
    } finally {
      globalThis.document = oldDocument;
      globalThis.location = oldLocation;
    }
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
  async evaluate() { calls.push(["evaluate"]); return { x: 200, y: 236, label: "center" }; },
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
                "keyword": "AI出图助手",
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
                "keyword": "AI出图助手",
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
                "keyword": "AI鍑哄浘鍔╂墜",
                "max_posts": 1,
                "max_comments_per_post": 0,
                "headed": True,
                "dry_run": False,
            },
            env=env,
        )

        self.assertEqual(result.returncode, 1)
        self.assertTrue(assets_dir.is_dir())
        self.assertFalse(records_path.exists())

        events = read_jsonl(events_path)
        self.assertEqual(events[-1]["event"], "run_failed")
        self.assertIn("Playwright is required", events[-1]["message"])
        self.assertIn("sidecar", events[-1]["message"])
        self.assertEqual(events[-1]["payload"]["code"], "PLAYWRIGHT_MISSING")


if __name__ == "__main__":
    unittest.main()
