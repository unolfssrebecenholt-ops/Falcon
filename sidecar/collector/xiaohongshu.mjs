import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

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
    events.write("info", "xiaohongshu", "record_collected", `Collected ${record.type} fixture`, {
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
  events.write("info", "xiaohongshu", "browser_launching", "Launching Xiaohongshu browser flow", {
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

    const snapshot = await extractVisibleSnapshot(page, maxPosts);
    const snapshotPath = join(assetsPath, "xiaohongshu-search-snapshot.json");
    await writeFile(snapshotPath, `${JSON.stringify(snapshot, null, 2)}\n`, "utf8");

    if (snapshot.posts.length === 0) {
      return manualActionRecords({
        page,
        request,
        assetsPath,
        events,
        reason: "no_posts_detected",
        detail: "Xiaohongshu loaded, but the sidecar could not identify visible post cards in the DOM.",
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

    for (const [index, post] of snapshot.posts.entries()) {
      const postId = post.href || `${run_id}-post-${index + 1}`;
      records.push({
        type: "post",
        run_id,
        platform,
        post_id: postId,
        keyword: request.keyword,
        title: post.title || firstLine(post.text),
        body: post.text,
        author: post.author ? { display_name: post.author } : {},
        metrics: post.metrics,
        url: post.href,
      });

      if (post.image) {
        const assetId = `${run_id}-post-${index + 1}-asset-1`;
        const placeholderPath = join(assetsPath, `${assetId}.json`);
        await writeFile(
          placeholderPath,
          `${JSON.stringify({ source_url: post.image, note: "Remote media was not downloaded by the MVP sidecar." }, null, 2)}\n`,
          "utf8",
        );
        records.push({
          type: "media_asset",
          run_id,
          platform,
          asset_id: assetId,
          post_id: postId,
          media_type: "image",
          path: placeholderPath,
          mime_type: "application/json",
          payload: { source_url: post.image },
        });
      }
    }

    events.write("info", "xiaohongshu", "records_collected", "Collected Xiaohongshu visible search records", {
      run_id,
      platform,
      posts: snapshot.posts.length,
    });
    return records;
  } finally {
    if (context) {
      await context.close();
    }
  }
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
    ["login_required", ["login", "signin", "登录", "注册", "验证码", "手机号"]],
    ["risk_control", ["risk", "安全验证", "环境异常", "访问异常", "操作频繁", "滑块", "验证"]],
    ["verification_required", ["captcha", "verify", "verification", "人机验证", "身份验证"]],
  ];

  for (const [reason, needles] of checks) {
    if (needles.some((needle) => haystack.includes(needle.toLowerCase()))) {
      return {
        reason,
        detail: `Detected ${reason} while loading Xiaohongshu.`,
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

async function extractVisibleSnapshot(page, maxPosts) {
  return page.evaluate((limit) => {
    const seen = new Set();
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
      const text = (element.innerText || element.textContent || "").trim().replace(/\s+/g, " ");
      const anchor = element.matches("a") ? element : element.querySelector("a[href]");
      const href = anchor?.href || "";
      const key = href || text.slice(0, 120);
      if (!key || seen.has(key) || text.length < 8) {
        continue;
      }
      seen.add(key);

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
        metrics: {
          likes_text: likesText,
        },
      });
    }

    return {
      url: location.href,
      title: document.title,
      collected_at: new Date().toISOString(),
      posts,
    };
  }, maxPosts);
}

function firstLine(value) {
  return String(value ?? "").split(/\r?\n|。|！|!|\?/)[0].trim().slice(0, 120);
}
