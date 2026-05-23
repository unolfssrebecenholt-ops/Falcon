import { mkdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { extname, join } from "node:path";
import {
  canonicalPostUrl,
  normalizeSearchCards,
  normalizeWhitespace,
  parseMetricNumber,
  stableFingerprint,
} from "./xiaohongshu-normalize.mjs";

export async function collectXiaohongshu({ request, assetsPath, profilePath, events }) {
  if (!request.dry_run) {
    return collectXiaohongshuReal({ request, assetsPath, profilePath, events });
  }

  const run_id = request.run_id;
  const platform = request.platform;
  const postId = `${run_id}-post-1`;
  const commentId = `${postId}-comment-1`;
  const assetId = `${postId}-asset-1`;
  const evidenceId = `${postId}-evidence-1`;
  const assetPath = join(assetsPath, "dry-run-xiaohongshu-placeholder.txt");

  await writeFile(
    assetPath,
    "Falcon Xiaohongshu dry-run media asset placeholder.\n",
    "utf8",
  );

  const records = [
    {
      type: "post",
      run_id,
      platform,
      post_id: postId,
      keyword: request.keyword,
      title: `Dry-run sample for ${request.keyword}`,
      body: "A deterministic Xiaohongshu dry-run post fixture for the Falcon collector contract.",
      author: {
        display_name: "Falcon dry-run author",
      },
      metrics: {
        likes: 128,
        comments: 1,
        collects: 24,
      },
    },
    {
      type: "comment",
      run_id,
      platform,
      comment_id: commentId,
      post_id: postId,
      body: "Dry-run comment asking for a repeatable AI image workflow.",
      author: {
        display_name: "Falcon dry-run commenter",
      },
    },
    {
      type: "evidence",
      run_id,
      evidence_id: evidenceId,
      platform,
      post_id: postId,
      scope: "dry_run_fixture",
      payload: {
        source: "sidecar/collector/xiaohongshu.mjs",
        keyword: request.keyword,
      },
    },
    {
      type: "media_asset",
      run_id,
      platform,
      asset_id: assetId,
      post_id: postId,
      media_type: "image",
      path: assetPath,
      mime_type: "text/plain",
    },
  ];

  for (const record of records) {
    events.write("info", "xiaohongshu", "record_collected", `已生成 ${record.type} dry-run 记录`, {
      run_id,
      platform,
      type: record.type,
    });
  }

  return records;
}

async function collectXiaohongshuReal({ request, assetsPath, profilePath, events }) {
  const { chromium } = await loadPlaywright();
  const run_id = request.run_id;
  const platform = request.platform;
  const maxPosts = Math.max(1, Number(request.max_posts ?? 5));
  let context;

  await mkdir(assetsPath, { recursive: true });
  events.write("info", "xiaohongshu", "browser_launching", "小红书浏览器采集已启动", {
    run_id,
    platform,
    headed: request.headed !== false,
  });

  try {
    context = await chromium.launchPersistentContext(profilePath, {
      headless: request.headed === false,
      viewport: { width: 1366, height: 900 },
      locale: "zh-CN",
    });
    const page = context.pages()[0] ?? (await context.newPage());

    await page.goto("https://www.xiaohongshu.com/", {
      waitUntil: "domcontentloaded",
      timeout: 30_000,
    });
    await quietWait(page, 2500);

    const landingStop = await detectManualAction(page);
    if (landingStop) {
      return manualActionRecords({
        page,
        request,
        assetsPath,
        events,
        reason: landingStop.reason,
        detail: landingStop.detail,
      });
    }

    const searchUrl = new URL("https://www.xiaohongshu.com/search_result");
    searchUrl.searchParams.set("keyword", request.keyword ?? "");
    searchUrl.searchParams.set("source", "web_search_result_notes");
    await page.goto(searchUrl.toString(), {
      waitUntil: "domcontentloaded",
      timeout: 30_000,
    });
    await quietWait(page, 5000);

    const searchStop = await detectManualAction(page);
    if (searchStop) {
      return manualActionRecords({
        page,
        request,
        assetsPath,
        events,
        reason: searchStop.reason,
        detail: searchStop.detail,
      });
    }

    await bestEffortScroll(page);

    const screenshotPath = join(assetsPath, "xiaohongshu-search-results.png");
    await page.screenshot({ path: screenshotPath, fullPage: true });

    const rawSnapshot = await extractVisibleSnapshot(page, maxPosts * 4);
    const snapshot = {
      ...rawSnapshot,
      posts: normalizeSearchCards(rawSnapshot.posts, maxPosts),
    };
    const snapshotPath = join(assetsPath, "xiaohongshu-search-snapshot.json");
    await writeFile(snapshotPath, `${JSON.stringify(snapshot, null, 2)}\n`, "utf8");

    if (snapshot.posts.length === 0) {
      return manualActionRecords({
        page,
        request,
        assetsPath,
        events,
        reason: "no_posts_detected",
        detail: "小红书已打开，但采集器没有识别到可见笔记卡片。",
        existingEvidence: [
          evidenceRecord({
            request,
            evidenceId: `${run_id}-search-screenshot`,
            scope: "search_results_screenshot",
            path: screenshotPath,
            payload: { keyword: request.keyword },
          }),
          evidenceRecord({
            request,
            evidenceId: `${run_id}-search-snapshot`,
            scope: "field_snapshot",
            path: snapshotPath,
            payload: { keyword: request.keyword, cards: snapshot.posts.length },
          }),
        ],
      });
    }

    const records = [
      evidenceRecord({
        request,
        evidenceId: `${run_id}-search-screenshot`,
        scope: "search_results_screenshot",
        path: screenshotPath,
        payload: { keyword: request.keyword },
      }),
      evidenceRecord({
        request,
        evidenceId: `${run_id}-search-snapshot`,
        scope: "field_snapshot",
        path: snapshotPath,
        payload: { keyword: request.keyword, cards: snapshot.posts.length },
      }),
    ];

    const detailOutcome = await collectDetailRecords({
      context,
      request,
      assetsPath,
      events,
      posts: snapshot.posts,
    });
    records.push(...detailOutcome.records);

    events.write("info", "xiaohongshu", "records_collected", "已生成小红书采集记录", {
      run_id,
      platform,
      posts: snapshot.posts.length,
      stopped: detailOutcome.stopped,
    });
    return records;
  } finally {
    if (context) {
      await context.close();
    }
  }
}

async function collectDetailRecords({ context, request, assetsPath, events, posts }) {
  const records = [];
  const platform = request.platform;
  const maxComments = Math.max(0, Number(request.max_comments_per_post ?? 10));

  for (const [index, searchPost] of posts.entries()) {
    const postUrl = canonicalPostUrl(searchPost.url || searchPost.href);
    const postId = searchPost.postId || `xiaohongshu:${stableFingerprint(postUrl || searchPost.text).slice(0, 16)}`;
    const stem = safeAssetStem(postId);
    const detailPage = await context.newPage();

    try {
      events.write("info", "xiaohongshu", "detail_opening", "正在打开小红书笔记详情", {
        run_id: request.run_id,
        platform,
        post_id: postId,
        url: postUrl,
      });
      await detailPage.goto(postUrl, { waitUntil: "domcontentloaded", timeout: 30_000 });
      await quietWait(detailPage, 3500);
      await detailPage.mouse.wheel(0, 650);
      await quietWait(detailPage, 1200);

      const detailStop = await detectManualAction(detailPage);
      if (detailStop) {
        records.push(
          ...(await manualActionRecords({
            page: detailPage,
            request,
            assetsPath,
            events,
            reason: detailStop.reason,
            detail: detailStop.detail,
          })),
        );
        return { records, stopped: true };
      }

      const detailScreenshotPath = join(assetsPath, `${stem}-detail.png`);
      await detailPage.screenshot({ path: detailScreenshotPath, fullPage: true });
      const detail = normalizeDetailSnapshot(await extractDetailSnapshot(detailPage, maxComments));
      const detailSnapshotPath = join(assetsPath, `${stem}-detail-snapshot.json`);
      await writeFile(detailSnapshotPath, `${JSON.stringify(detail, null, 2)}\n`, "utf8");

      const merged = mergePost(searchPost, detail);
      records.push({
        type: "post",
        run_id: request.run_id,
        platform,
        post_id: postId,
        keyword: request.keyword,
        title: merged.title,
        body: merged.body,
        author: merged.author ? { display_name: merged.author } : {},
        published_at: merged.published_at,
        metrics: merged.metrics,
        url: postUrl,
        detail_fingerprint: postId,
      });
      records.push(
        evidenceRecord({
          request,
          evidenceId: `${request.run_id}-${stem}-detail-screenshot`,
          scope: "detail_screenshot",
          path: detailScreenshotPath,
          payload: { post_id: postId, url: postUrl },
        }),
      );
      records.push(
        evidenceRecord({
          request,
          evidenceId: `${request.run_id}-${stem}-detail-snapshot`,
          scope: "field_snapshot",
          path: detailSnapshotPath,
          payload: { post_id: postId, url: postUrl, comments: detail.comments.length },
        }),
      );

      for (const [commentIndex, comment] of detail.comments.entries()) {
        if (!comment.content) {
          continue;
        }
        records.push({
          type: "comment",
          run_id: request.run_id,
          platform,
          comment_id: `${postId}-comment-${stableFingerprint(`${comment.author}\n${comment.content}`).slice(0, 10)}`,
          post_id: postId,
          body: comment.content,
          author: comment.author ? { display_name: comment.author } : {},
          like_count: comment.like_count,
          comment_rank: String(commentIndex + 1),
        });
      }

      const imageUrls = uniqueStrings([...detail.images, searchPost.image]).filter((url) => /^https?:|^data:image\//.test(url));
      for (const [imageIndex, imageUrl] of imageUrls.entries()) {
        const assetId = `${stem}-image-${imageIndex + 1}`;
        try {
          const asset = await downloadImage(detailPage, imageUrl, assetsPath, assetId);
          records.push({
            type: "media_asset",
            run_id: request.run_id,
            platform,
            asset_id: assetId,
            post_id: postId,
            media_type: "image",
            path: asset.path,
            mime_type: asset.mime_type,
            sha256: asset.sha256,
            url: imageUrl,
          });
        } catch (error) {
          events.write("warning", "xiaohongshu", "media_download_failed", "图片下载失败，已跳过该素材", {
            run_id: request.run_id,
            platform,
            post_id: postId,
            url: imageUrl,
            error: error.message,
          });
        }
      }
    } catch (error) {
      const errorPath = join(assetsPath, `${stem}-detail-error.png`);
      try {
        await detailPage.screenshot({ path: errorPath, fullPage: true });
      } catch {
        // Ignore screenshot errors while preserving the original failure.
      }
      const wrapped = new Error(`小红书详情页采集失败：第 ${index + 1} 条笔记，${error.message}`);
      wrapped.code = error.code ?? "XIAOHONGSHU_DETAIL_FAILED";
      throw wrapped;
    } finally {
      await detailPage.close();
    }
  }

  return { records, stopped: false };
}

async function loadPlaywright() {
  try {
    if (process.env.FALCON_COLLECTOR_FORCE_PLAYWRIGHT_MISSING === "1") {
      const forced = new Error("Forced missing Playwright for sidecar contract testing.");
      forced.code = "ERR_MODULE_NOT_FOUND";
      throw forced;
    }
    return await import("playwright");
  } catch (error) {
    if (
      error?.code === "ERR_MODULE_NOT_FOUND" &&
      (String(error.message).toLowerCase().includes("playwright") ||
        process.env.FALCON_COLLECTOR_FORCE_PLAYWRIGHT_MISSING === "1")
    ) {
      const missing = new Error(
        "Playwright is required for Xiaohongshu real-mode collection. Install sidecar deps with `npm install` in the sidecar package/workspace before running non-dry-run collection.",
      );
      missing.code = "PLAYWRIGHT_MISSING";
      throw missing;
    }
    throw error;
  }
}

async function quietWait(page, milliseconds) {
  await page.waitForTimeout(milliseconds);
}

async function detectManualAction(page) {
  const state = await page.evaluate(() => {
    const bodyText = document.body?.innerText ?? "";
    return {
      url: location.href,
      title: document.title,
      text: bodyText.slice(0, 8000),
    };
  });
  const haystack = `${state.url}\n${state.title}\n${state.text}`.toLowerCase();
  const checks = [
    ["app_scan_required", ["当前笔记暂时无法浏览", "打开小红书app扫码", "扫码查看", "请打开小红书app"]],
    ["login_required", ["login", "signin", "登录", "注册", "验证码", "手机号"]],
    ["risk_control", ["risk", "安全验证", "环境异常", "访问异常", "操作频繁", "滑块", "验证"]],
    ["verification_required", ["captcha", "verify", "verification", "人机验证", "身份验证"]],
  ];

  for (const [reason, needles] of checks) {
    if (needles.some((needle) => haystack.includes(needle.toLowerCase()))) {
      return {
        reason,
        detail: `检测到 ${manualReasonLabel(reason)}，需要人工处理后再继续。`,
      };
    }
  }
  return null;
}

async function manualActionRecords({
  page,
  request,
  assetsPath,
  events,
  reason,
  detail,
  existingEvidence = [],
}) {
  const screenshotPath = join(assetsPath, `manual-action-${reason}.png`);
  await page.screenshot({ path: screenshotPath, fullPage: true });
  events.write("warning", "xiaohongshu", "manual_action_required", detail, {
    run_id: request.run_id,
    platform: request.platform,
    reason,
    screenshot: screenshotPath,
  });
  return [
    evidenceRecord({
      request,
      evidenceId: `${request.run_id}-manual-action-${reason}`,
      scope: "manual_action_required",
      path: screenshotPath,
      payload: { reason, detail },
    }),
    ...existingEvidence,
  ];
}

function evidenceRecord({ request, evidenceId, scope, path, payload }) {
  return {
    type: "evidence",
    run_id: request.run_id,
    platform: request.platform,
    evidence_id: evidenceId,
    scope,
    path,
    payload,
  };
}

async function bestEffortScroll(page) {
  for (let index = 0; index < 3; index += 1) {
    await page.mouse.wheel(0, 700);
    await quietWait(page, 1200);
  }
}

async function extractVisibleSnapshot(page, maxCandidates) {
  return page.evaluate((limit) => {
    const selectors = [
      "section",
      "article",
      ".note-item",
      ".feeds-page .note-card",
      "a[href*='/explore/']",
      "a[href*='/search_result/']",
    ];
    const candidates = Array.from(document.querySelectorAll(selectors.join(",")));
    const posts = [];

    for (const element of candidates) {
      if (posts.length >= limit) {
        break;
      }
      const anchor = element.matches("a[href]") ? element : element.querySelector("a[href*='/explore/'], a[href*='/search_result/'], a[href]");
      const href = anchor?.href || "";
      const text = (element.innerText || element.textContent || "").trim();
      if (!href && text.length < 8) {
        continue;
      }
      const image = element.querySelector("img")?.currentSrc || element.querySelector("img")?.src || "";
      const title =
        element.querySelector("[class*='title'], [class*='desc'], h1, h2, h3")?.textContent?.trim() ||
        "";
      const author =
        element.querySelector("[class*='author'], [class*='user'], [class*='name']")?.textContent?.trim() ||
        "";
      const likesText =
        element.querySelector("[class*='like'], [class*='count']")?.textContent?.trim() ||
        "";

      posts.push({
        href,
        title,
        text,
        author,
        image,
        likesText,
      });
    }

    return {
      url: location.href,
      title: document.title,
      collected_at: new Date().toISOString(),
      posts,
    };
  }, maxCandidates);
}

async function extractDetailSnapshot(page, maxComments) {
  return page.evaluate((commentLimit) => {
    const textOf = (root, selectors) => {
      for (const selector of selectors) {
        const value = root.querySelector(selector)?.innerText || root.querySelector(selector)?.textContent || "";
        const cleaned = value.trim();
        if (cleaned) {
          return cleaned;
        }
      }
      return "";
    };
    const title = textOf(document, ["#detail-title", "[class*='title']", "h1"]);
    const body = textOf(document, ["#detail-desc", "[class*='desc']", ".note-content", "[class*='content']"]);
    const author = textOf(document, [
      "a[href*='/user/profile']",
      "[class*='author'] [class*='name']",
      "[class*='user'] [class*='name']",
      "[class*='nickname']",
    ]);
    const interactionText = textOf(document, [
      "[class*='interact']",
      "[class*='engage']",
      "[class*='like']",
      "[class*='bottom-bar']",
    ]);
    const imageUrls = Array.from(document.images)
      .filter((image) => (image.naturalWidth || image.width || 0) >= 160 && (image.naturalHeight || image.height || 0) >= 120)
      .map((image) => image.currentSrc || image.src)
      .filter(Boolean);
    const commentElements = Array.from(document.querySelectorAll(".comment-item, [class*='comment-item']"));
    const comments = [];
    for (const element of commentElements) {
      if (comments.length >= commentLimit) {
        break;
      }
      const rawText = (element.innerText || element.textContent || "").trim();
      if (rawText.length < 2) {
        continue;
      }
      const commentAuthor = textOf(element, ["[class*='author']", "[class*='name']", "a[href*='/user/profile']"]);
      const commentContent =
        textOf(element, ["[class*='content']", "[class*='text']", "p"]) ||
        rawText
          .split(/\r?\n/)
          .map((line) => line.trim())
          .find((line) => line && line !== commentAuthor) ||
        "";
      const likeText = textOf(element, ["[class*='like']", "[class*='count']"]);
      comments.push({ author: commentAuthor, content: commentContent, likeText, rawText });
    }
    return {
      url: location.href,
      title,
      body,
      author,
      interactionText,
      images: Array.from(new Set(imageUrls)).slice(0, 8),
      comments,
    };
  }, maxComments);
}

function normalizeDetailSnapshot(raw) {
  return {
    url: normalizeWhitespace(raw?.url),
    title: normalizeWhitespace(raw?.title).slice(0, 180),
    body: normalizeWhitespace(raw?.body),
    author: normalizeWhitespace(raw?.author),
    metrics: metricsFromText(raw?.interactionText),
    images: uniqueStrings(raw?.images ?? []),
    comments: (raw?.comments ?? []).map((comment) => ({
      author: normalizeWhitespace(comment.author),
      content: normalizeWhitespace(comment.content),
      like_count: metricString(comment.likeText),
      raw_text: normalizeWhitespace(comment.rawText),
    })),
  };
}

function mergePost(searchPost, detail) {
  return {
    title: detail.title || searchPost.title || firstLine(searchPost.text),
    body: detail.body || searchPost.text || searchPost.title,
    author: detail.author || searchPost.author,
    published_at: searchPost.published_at,
    metrics: {
      ...(searchPost.metrics ?? {}),
      ...detail.metrics,
    },
  };
}

function metricsFromText(value) {
  const text = normalizeWhitespace(value);
  const metrics = {};
  const first = parseMetricNumber(text);
  if (first !== undefined) {
    metrics.likes = first;
  }
  return metrics;
}

function metricString(value) {
  const parsed = parseMetricNumber(value);
  return parsed === undefined ? "" : String(parsed);
}

async function downloadImage(page, imageUrl, assetsPath, assetId) {
  let body;
  let mimeType = "";
  if (imageUrl.startsWith("data:image/")) {
    const match = imageUrl.match(/^data:([^;,]+)(;base64)?,(.*)$/);
    if (!match) {
      throw new Error("Invalid data image URL");
    }
    mimeType = match[1];
    body = match[2] ? Buffer.from(match[3], "base64") : Buffer.from(decodeURIComponent(match[3]), "utf8");
  } else {
    const response = await page.context().request.get(imageUrl, { timeout: 20_000 });
    if (!response.ok()) {
      throw new Error(`HTTP ${response.status()}`);
    }
    mimeType = (response.headers()["content-type"] || "").split(";")[0].trim() || "application/octet-stream";
    body = await response.body();
  }
  if (!body?.length) {
    throw new Error("empty image response");
  }
  const sha256 = createHash("sha256").update(body).digest("hex");
  const extension = extensionForMime(mimeType) || extensionFromUrl(imageUrl) || ".bin";
  const path = join(assetsPath, `${assetId}-${sha256.slice(0, 12)}${extension}`);
  await writeFile(path, body);
  return { path, mime_type: mimeType, sha256 };
}

function extensionForMime(mimeType) {
  const normalized = mimeType.toLowerCase();
  if (normalized === "image/jpeg") return ".jpg";
  if (normalized === "image/png") return ".png";
  if (normalized === "image/webp") return ".webp";
  if (normalized === "image/gif") return ".gif";
  return "";
}

function extensionFromUrl(value) {
  try {
    const extension = extname(new URL(value).pathname).toLowerCase();
    return extension && extension.length <= 6 ? extension : "";
  } catch {
    return "";
  }
}

function uniqueStrings(values) {
  return Array.from(new Set((values ?? []).map((value) => normalizeWhitespace(value)).filter(Boolean)));
}

function firstLine(value) {
  return String(value ?? "").split(/\r?\n|。|，|!|\?/)[0].trim().slice(0, 120);
}

function safeAssetStem(value) {
  return String(value ?? "")
    .replace(/^xiaohongshu:/, "xhs-")
    .replace(/[^A-Za-z0-9_.-]+/g, "-")
    .replace(/-+/g, "-")
    .slice(0, 80) || "xhs-post";
}

function manualReasonLabel(reason) {
  return {
    login_required: "登录或账号确认",
    risk_control: "平台风控或安全验证",
    verification_required: "验证码或人机验证",
    app_scan_required: "手机扫码查看",
    no_posts_detected: "搜索结果识别异常",
  }[reason] || "人工处理点";
}
