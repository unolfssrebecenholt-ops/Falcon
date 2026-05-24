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
    try {
      if (process.env.FALCON_COLLECTOR_FORCE_PROFILE_LAUNCH_CONFLICT === "1") {
        throw new Error(
          "browserType.launchPersistentContext: Target page, context or browser has been closed\nBrowser logs:\n<launching> chrome.exe --user-data-dir=browser-profiles/xiaohongshu/default --remote-debugging-pipe about:blank\n<launched> pid=49380\n[pid=49380] <process did exit: exitCode=0, signal=null>",
        );
      }
      context = await chromium.launchPersistentContext(profilePath, {
        headless: request.headed === false,
        viewport: { width: 1366, height: 900 },
        locale: "zh-CN",
      });
    } catch (error) {
      if (isPersistentProfileLaunchConflict(error)) {
        events.write(
          "warning",
          "xiaohongshu",
          "manual_action_required",
          `浏览器 Profile 正在被其他窗口占用。请关闭 ${request.platform}/${request.profile} 的登录或人工处理窗口后，再点击继续采集。`,
          {
            run_id,
            platform,
            reason: "profile_window_busy",
            profile: request.profile,
            profile_path: profilePath,
          },
        );
        return [];
      }
      throw error;
    }
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

    let detailOutcome;
    try {
      detailOutcome = await collectDetailRecords({
        context,
        searchPage: page,
        request,
        assetsPath,
        events,
        posts: snapshot.posts,
      });
      records.push(...detailOutcome.records);
    } catch (error) {
      if (Array.isArray(error.partialRecords)) {
        records.push(...error.partialRecords);
      }
      error.partialRecords = records;
      throw error;
    }

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

export function isPersistentProfileLaunchConflict(error) {
  const message = String(error?.message || error || "");
  return (
    message.includes("launchPersistentContext") &&
    message.includes("Target page, context or browser has been closed") &&
    (message.includes("process did exit: exitCode=0") || message.includes("--user-data-dir="))
  );
}

async function collectDetailRecords({ context, searchPage, request, assetsPath, events, posts }) {
  const records = [];
  const platform = request.platform;
  const maxComments = Math.max(0, Number(request.max_comments_per_post ?? 10));
  const postTotal = Math.max(1, posts.length);

  for (const [index, searchPost] of posts.entries()) {
    const postUrl = canonicalPostUrl(searchPost.url || searchPost.href);
    const postId = searchPost.postId || `xiaohongshu:${stableFingerprint(postUrl || searchPost.text).slice(0, 16)}`;
    const stem = safeAssetStem(postId);
    let detailHandle;

    try {
      const openingPayload = postProgressPayload({
        request,
        platform,
        postId,
        postUrl,
        index,
        total: postTotal,
        phase: "opening",
      });
      events.write("info", "xiaohongshu", "detail_opening", `正在采集第 ${openingPayload.post_index}/${openingPayload.post_total} 条小红书笔记`, {
        ...openingPayload,
        run_id: request.run_id,
        platform,
        post_id: postId,
        url: postUrl,
        open_mode: "mouse_click",
      });
      detailHandle = await openDetailFromSearchCard({
        context,
        searchPage,
        searchPost,
        index,
      });
      const detailPage = detailHandle.page;
      await quietWait(detailPage, 2500);

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
      await captureDetailScreenshot(detailPage, detailScreenshotPath);
      if (maxComments > 0) {
        await detailPage.mouse.wheel(0, 650);
        await quietWait(detailPage, 1200);
        await expandVisibleCommentReplies(detailPage, Math.min(maxComments, 6));
      }
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
          payload: { post_id: postId, url: postUrl, comments: detail.comments.length, media_scope: "detail_container" },
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
          comment_type: comment.comment_type,
          reply_to: comment.reply_to,
        });
      }

      const imageUrls = uniqueMediaUrls([...detail.images, searchPost.image]).filter((url) => /^https?:|^data:image\//.test(url));
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
      const collectedPayload = postProgressPayload({
        request,
        platform,
        postId,
        postUrl,
        index,
        total: postTotal,
        phase: "collected",
      });
      events.write("info", "xiaohongshu", "detail_collected", `第 ${collectedPayload.post_index}/${collectedPayload.post_total} 条小红书笔记已采集`, collectedPayload);
    } catch (error) {
      const errorPath = join(assetsPath, `${stem}-detail-error.png`);
      let errorScreenshotSaved = false;
      try {
        const detailPage = detailHandle?.page || searchPage;
        await detailPage.screenshot({ path: errorPath, fullPage: false });
        errorScreenshotSaved = true;
      } catch {
        // Ignore screenshot errors while preserving the original failure.
      }
      if (errorScreenshotSaved) {
        records.push(
          evidenceRecord({
            request,
            evidenceId: `${request.run_id}-${stem}-detail-error`,
            scope: "detail_error_screenshot",
            path: errorPath,
            payload: { post_id: postId, url: postUrl, error: error.message },
          }),
        );
      }
      const wrapped = new Error(`小红书详情页采集失败：第 ${index + 1} 条笔记，${error.message}`);
      wrapped.code = error.code ?? "XIAOHONGSHU_DETAIL_FAILED";
      wrapped.partialRecords = records;
      throw wrapped;
    } finally {
      if (detailHandle) {
        await closeDetailAfterCollection(detailHandle);
      }
    }
  }

  return { records, stopped: false };
}

export function postProgressPayload({ request, platform, postId, postUrl, index, total, phase }) {
  const postTotal = Math.max(1, Number(total || 1));
  const postIndex = Math.min(postTotal, Math.max(1, Number(index || 0) + 1));
  return {
    run_id: request.run_id,
    platform,
    post_id: postId,
    url: postUrl,
    post_index: postIndex,
    post_total: postTotal,
    post_percent: Math.round((postIndex / postTotal) * 100),
    phase,
  };
}

export async function openDetailFromSearchCard({ context, searchPage, searchPost, index }) {
  const locator = await findSearchCardLocator(searchPage, searchPost, index);
  if (!locator) {
    throw new Error("未找到可点击的小红书笔记卡片，已停止直接 URL 访问以避免触发风控。");
  }

  const browserContext = context || searchPage.context?.();
  const popupPromise = searchPage.waitForEvent
    ? searchPage.waitForEvent("popup", { timeout: 8000 }).catch(() => null)
    : browserContext?.waitForEvent
      ? browserContext.waitForEvent("page", { timeout: 8000 }).catch(() => null)
      : Promise.resolve(null);
  const beforeUrl = searchPage.url();
  await humanMouseClickLocator(searchPage, locator);
  const popup = await popupPromise;
  if (popup) {
    await popup.waitForLoadState("domcontentloaded", { timeout: 12_000 }).catch(() => {});
    return { page: popup, mode: "popup", searchPage };
  }

  await searchPage.waitForLoadState("domcontentloaded", { timeout: 8000 }).catch(() => {});
  await searchPage.waitForTimeout(1500);
  const afterUrl = searchPage.url();
  if (afterUrl !== beforeUrl || (await hasDetailContainer(searchPage))) {
    return { page: searchPage, mode: "same_page", searchPage, beforeUrl };
  }

  const fallbackPage = browserContext?.pages
    ? browserContext.pages().find((page) => page !== searchPage && page.url() !== beforeUrl)
    : null;
  if (fallbackPage) {
    await fallbackPage.waitForLoadState("domcontentloaded", { timeout: 8000 }).catch(() => {});
    return { page: fallbackPage, mode: "context_page", searchPage };
  }

  throw new Error("点击笔记卡片后未检测到详情页或弹窗。");
}

async function findSearchCardLocator(page, searchPost, index) {
  const rawId = String(searchPost?.postId || "").replace(/^xiaohongshu:/, "");
  const selectors = [];
  const expectedIds = new Set();
  if (rawId) {
    expectedIds.add(rawId);
    selectors.push(`a[href*="/search_result/${cssEscape(rawId)}"]`);
    selectors.push(`a[href*="/explore/${cssEscape(rawId)}"]`);
    selectors.push(`a[href*="${cssEscape(rawId)}"]`);
    selectors.push(`.note-item:has(a[href*="${cssEscape(rawId)}"])`);
    selectors.push(`.feeds-page .note-card:has(a[href*="${cssEscape(rawId)}"])`);
    selectors.push(`section:has(a[href*="${cssEscape(rawId)}"])`);
    selectors.push(`article:has(a[href*="${cssEscape(rawId)}"])`);
  }
  if (searchPost?.href) {
    const hrefId = String(searchPost.href).match(/(?:\/(?:explore|search_result)\/)([A-Za-z0-9_-]{6,})/)?.[1];
    if (hrefId && hrefId !== rawId) {
      expectedIds.add(hrefId);
      selectors.push(`a[href*="/search_result/${cssEscape(hrefId)}"]`);
      selectors.push(`a[href*="/explore/${cssEscape(hrefId)}"]`);
      selectors.push(`a[href*="${cssEscape(hrefId)}"]`);
      selectors.push(`.note-item:has(a[href*="${cssEscape(hrefId)}"])`);
      selectors.push(`.feeds-page .note-card:has(a[href*="${cssEscape(hrefId)}"])`);
    }
  }

  for (const selector of selectors) {
    const locator = await firstClickableLocator(page, selector, {
      minimumSize: selector.startsWith("a[href") ? 10 : 80,
    });
    if (locator) {
      return locator;
    }
  }

  if (expectedIds.size) {
    throw new Error(
      `未找到与 ${Array.from(expectedIds).join(", ")} 匹配的可点击笔记卡片，搜索页可能已经离开原结果页，已停止按序号兜底以避免采错帖子。`,
    );
  }

  const cardIndex = Number.isInteger(searchPost?.cardIndex) ? searchPost.cardIndex : index;
  return indexedClickableLocator(page, ".note-item, .feeds-page .note-card, section, article", cardIndex);
}

async function firstClickableLocator(page, selector, { minimumSize = 10 } = {}) {
  let collection;
  try {
    collection = page.locator(selector);
  } catch {
    return null;
  }

  const candidates = await locatorCandidates(collection);
  for (const locator of candidates) {
    if (await isClickableLocator(page, locator, { minimumSize })) {
      return locator;
    }
  }
  return null;
}

async function indexedClickableLocator(page, selector, index) {
  let locator;
  try {
    const collection = page.locator(selector);
    locator = collection.nth ? collection.nth(index) : collection.first?.();
  } catch {
    return null;
  }

  if (locator && (await isClickableLocator(page, locator, { minimumSize: 80 }))) {
    return locator;
  }
  return null;
}

async function locatorCandidates(collection) {
  try {
    const count = collection.count ? await collection.count() : 0;
    if (count <= 0) {
      return [];
    }
    if (collection.all) {
      return collection.all();
    }
    if (collection.nth) {
      return Array.from({ length: count }, (_, index) => collection.nth(index));
    }
    return [collection.first ? collection.first() : collection];
  } catch {
    return [];
  }
}

async function isClickableLocator(page, locator, { minimumSize }) {
  try {
    const box = await locator.boundingBox().catch(() => null);
    if (!box || box.width < minimumSize || box.height < minimumSize) {
      return false;
    }
    return Boolean(await findSafeClickPoint(page, locator, { allowReposition: true }));
  } catch {
    return false;
  }
}

async function humanMouseClickLocator(page, locator) {
  await locator.scrollIntoViewIfNeeded({ timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(350);
  const point = await findSafeClickPoint(page, locator, { allowReposition: true });
  if (!point) {
    throw new Error("小红书笔记卡片不可见，无法模拟点击。");
  }
  const { x, y } = point;
  await page.mouse.move(x - 18, y - 10, { steps: 8 });
  await page.waitForTimeout(180);
  await page.mouse.move(x, y, { steps: 10 });
  await page.waitForTimeout(160);
  await page.mouse.click(x, y, { delay: 95 });
}

async function findSafeClickPoint(page, locator, { allowReposition = false } = {}) {
  const attempts = allowReposition ? 4 : 1;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const point = await locatorHitTestPoint(locator);
    if (point) {
      return point;
    }

    const box = await locator.boundingBox().catch(() => null);
    if (!allowReposition || !box) {
      return null;
    }
    const viewport = page.viewportSize?.() ?? { width: 1366, height: 900 };
    const centerY = box.y + box.height / 2;
    let deltaY = 0;
    if (centerY < 140 || box.y < 120) {
      deltaY = -320;
    } else if (centerY > viewport.height - 80 || box.y + box.height > viewport.height - 20) {
      deltaY = 320;
    } else {
      return null;
    }
    await page.mouse.wheel(0, deltaY);
    await page.waitForTimeout(550);
  }
  return null;
}

async function locatorHitTestPoint(locator) {
  if (locator.evaluate) {
    const point = await locator.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      if (!rect || rect.width <= 0 || rect.height <= 0) {
        return null;
      }

      const topGuard = 120;
      const margin = 8;
      const ownAnchor = element.matches?.("a[href]") ? element : element.closest?.("a[href]");
      const descendantAnchor = element.querySelector?.("a[href]");
      const targetHref = ownAnchor?.href || descendantAnchor?.href || "";
      const candidates = [
        [rect.x + rect.width * 0.5, rect.y + rect.height * 0.5, "center"],
        [rect.x + rect.width * 0.5, rect.y + Math.min(rect.height - margin, 32), "upper"],
        [rect.x + rect.width * 0.5, rect.y + Math.max(margin, rect.height - 32), "lower"],
        [rect.x + Math.min(rect.width - margin, 32), rect.y + rect.height * 0.5, "left_center"],
      ];

      for (const [x, y, label] of candidates) {
        if (x < margin || x > window.innerWidth - margin || y < topGuard || y > window.innerHeight - margin) {
          continue;
        }
        const hit = document.elementFromPoint(x, y);
        if (!hit) {
          continue;
        }
        const hitAnchor = hit.closest?.("a[href]");
        const hrefMatches = Boolean(targetHref && hitAnchor?.href === targetHref);
        const elementOwnsHit = element === hit || element.contains(hit);
        if (hrefMatches || elementOwnsHit) {
          return {
            x,
            y,
            label,
            href: hitAnchor?.href || targetHref,
            hitClass: String(hit.className || ""),
          };
        }
      }
      return null;
    }).catch(() => null);
    if (point) {
      return point;
    }
  }

  const box = await locator.boundingBox().catch(() => null);
  if (!box) {
    return null;
  }
  const x = box.x + Math.min(Math.max(box.width * 0.48, 24), Math.max(24, box.width - 18));
  const y = box.y + Math.min(Math.max(box.height * 0.46, 24), Math.max(24, box.height - 18));
  if (x < 0 || y < 0) {
    return null;
  }
  return { x, y, label: "box_fallback" };
}

async function hasDetailContainer(page) {
  const selectors = ["#noteContainer", ".note-detail-mask", ".note-container", ".note-detail"];
  for (const selector of selectors) {
    try {
      if ((await page.locator(selector).first().count()) > 0) {
        return true;
      }
    } catch {
      // Try the next selector.
    }
  }
  return false;
}

export async function closeDetailAfterCollection(handle) {
  if (handle.mode === "popup" || handle.mode === "context_page") {
    await handle.page.close().catch(() => {});
    return;
  }
  const beforeUrl = handle.beforeUrl || "";
  if (handle.page.keyboard?.press) {
    await handle.page.keyboard.press("Escape").catch(() => {});
  }
  if (handle.page.waitForTimeout) {
    await handle.page.waitForTimeout(1000).catch(() => {});
  }
  if (beforeUrl && (await isBackOnExpectedSearchPage(handle.page, beforeUrl))) {
    return;
  }
  if (handle.page.goBack) {
    await handle.page.goBack({ waitUntil: "domcontentloaded", timeout: 8000 }).catch(() => {});
  }
  if (handle.page.waitForTimeout) {
    await handle.page.waitForTimeout(1000).catch(() => {});
  }
  if (beforeUrl && !(await isBackOnExpectedSearchPage(handle.page, beforeUrl)) && handle.page.goto) {
    await handle.page.goto(beforeUrl, { waitUntil: "domcontentloaded", timeout: 12_000 }).catch(() => {});
    if (handle.page.waitForTimeout) {
      await handle.page.waitForTimeout(1200).catch(() => {});
    }
  }
}

async function isBackOnExpectedSearchPage(page, beforeUrl) {
  let currentUrl = "";
  try {
    currentUrl = page.url();
  } catch {
    return false;
  }
  if (!sameUrlWithoutHash(currentUrl, beforeUrl)) {
    return false;
  }
  return !(await hasDetailContainer(page));
}

function sameUrlWithoutHash(left, right) {
  try {
    const leftUrl = new URL(left);
    const rightUrl = new URL(right);
    leftUrl.hash = "";
    rightUrl.hash = "";
    return leftUrl.toString() === rightUrl.toString();
  } catch {
    return String(left || "").split("#")[0] === String(right || "").split("#")[0];
  }
}

export async function expandVisibleCommentReplies(page, maxExpansions = 4) {
  const limit = Math.max(0, Number(maxExpansions || 0));
  let clicked = 0;
  for (let attempt = 0; attempt < limit; attempt += 1) {
    const locator = page.getByText
      ? page.getByText(/展开\s*\d*\s*条?回复|展开.*回复|查看更多回复|共\s*\d+\s*条回复/)
      : page.locator("text=/展开\\s*\\d*\\s*条?回复|展开.*回复|查看更多回复|共\\s*\\d+\\s*条回复/");
    const candidates = await locatorCandidates(locator);
    let clickedThisPass = false;
    for (const candidate of candidates) {
      if (!(await isClickableLocator(page, candidate, { minimumSize: 12 }))) {
        continue;
      }
      await humanMouseClickLocator(page, candidate);
      clicked += 1;
      clickedThisPass = true;
      await page.waitForTimeout(900);
      break;
    }
    if (!clickedThisPass) {
      break;
    }
  }
  return clicked;
}

export async function captureDetailScreenshot(page, path) {
  const viewport = page.viewportSize() ?? { width: 1366, height: 900 };
  const selectors = [
    "#noteContainer",
    ".note-detail-mask .note-container",
    ".note-container",
    ".note-content",
    "main",
  ];

  for (const selector of selectors) {
    const element = page.locator(selector).first();
    try {
      if (!(await element.isVisible({ timeout: 1000 }))) {
        continue;
      }
      const box = await element.boundingBox();
      if (!box || box.width < 240 || box.height < 180) {
        continue;
      }
      const clipX = Math.max(0, box.x);
      const clipY = Math.max(0, box.y);
      const clipWidth = Math.min(box.width, viewport.width - clipX);
      const clipHeight = Math.min(box.height, viewport.height - clipY);
      if (clipWidth < 120 || clipHeight < 120) {
        continue;
      }
      await page.screenshot({
        path,
        fullPage: false,
        clip: {
          x: clipX,
          y: clipY,
          width: clipWidth,
          height: clipHeight,
        },
      });
      return { mode: "container", selector };
    } catch {
      // Try the next selector, then fall back to the visible viewport.
    }
  }

  await page.screenshot({ path, fullPage: false });
  return { mode: "viewport" };
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

export async function detectManualAction(page) {
  const state = await page.evaluate(() => {
    const bodyText = document.body?.innerText ?? "";
    const isVisible = (element) => {
      const rect = element.getBoundingClientRect();
      const style = window.getComputedStyle(element);
      return rect.width >= 120 && rect.height >= 80 && style.visibility !== "hidden" && style.display !== "none";
    };
    const blockingText = Array.from(
      document.querySelectorAll("[role='dialog'], [class*='login'], [class*='captcha'], [class*='verify'], [class*='modal']"),
    )
      .filter(isVisible)
      .map((element) => element.innerText || element.textContent || "")
      .filter(Boolean)
      .join("\n")
      .slice(0, 4000);
    return {
      url: location.href,
      title: document.title,
      text: bodyText.slice(0, 8000),
      blockingText,
      hasDetailContainer: Boolean(document.querySelector("#noteContainer, .note-detail-mask, .note-container, .note-detail")),
    };
  });
  if (state.hasDetailContainer && !state.blockingText) {
    return null;
  }
  const manualText = state.hasDetailContainer ? state.blockingText : state.text;
  const haystack = `${state.url}\n${state.title}\n${manualText}`.toLowerCase();
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

export async function manualActionRecords({
  page,
  request,
  assetsPath,
  events,
  reason,
  detail,
  existingEvidence = [],
}) {
  const screenshotPath = join(assetsPath, `manual-action-${reason}.png`);
  let savedScreenshotPath = "";
  let screenshotError = "";
  try {
    await page.screenshot({ path: screenshotPath, fullPage: false });
    savedScreenshotPath = screenshotPath;
  } catch (error) {
    screenshotError = error.message || String(error);
  }
  let targetUrl = "";
  try {
    targetUrl = page.url();
  } catch {
    targetUrl = "";
  }
  events.write("warning", "xiaohongshu", "manual_action_required", detail, {
    run_id: request.run_id,
    platform: request.platform,
    reason,
    screenshot: savedScreenshotPath,
    url: targetUrl,
    screenshot_error: screenshotError,
  });
  const screenshotEvidence = savedScreenshotPath
    ? [
        evidenceRecord({
          request,
          evidenceId: `${request.run_id}-manual-action-${reason}`,
          scope: "manual_action_required",
          path: savedScreenshotPath,
          payload: { reason, detail, url: targetUrl },
        }),
      ]
    : [];
  return [...screenshotEvidence, ...existingEvidence];
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

    for (const [cardIndex, element] of candidates.entries()) {
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
        cardIndex,
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

function cssEscape(value) {
  return String(value).replace(/["\\]/g, "\\$&");
}

export async function extractDetailSnapshot(page, maxComments) {
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
    const detailRoot = document.querySelector("#noteContainer, .note-detail-mask .note-container, .note-container, .note-detail") || document;
    const classOf = (element) => {
      if (!element) return "";
      if (typeof element.className === "string") return element.className;
      return element.className?.baseVal || "";
    };
    const attrOf = (element, name) => element?.getAttribute?.(name) || "";
    const metricRole = (element) => {
      const parent = element?.parentElement;
      const grand = parent?.parentElement;
      const haystack = [
        classOf(element),
        classOf(parent),
        classOf(grand),
        attrOf(element, "aria-label"),
        attrOf(parent, "aria-label"),
        attrOf(element, "title"),
        attrOf(parent, "title"),
        element?.innerText || element?.textContent || "",
      ].join(" ").toLowerCase();
      if (/collect|favorite|fav|star|save|收藏/.test(haystack)) return "collect";
      if (/comment|chat|reply|评论|回复/.test(haystack)) return "comment";
      if (/like|heart|赞|点赞|喜欢/.test(haystack)) return "like";
      return "";
    };
    const metricText = (element) => {
      const scoped =
        element?.closest?.("[class*='like'], [class*='collect'], [class*='favorite'], [class*='comment'], [class*='chat'], [class*='interact']") ||
        element;
      return (scoped?.innerText || scoped?.textContent || element?.innerText || element?.textContent || "").trim();
    };
    const metricElements = Array.from(
      detailRoot.querySelectorAll(
        [
          "button",
          "[role='button']",
          "[class*='like']",
          "[class*='collect']",
          "[class*='favorite']",
          "[class*='comment']",
          "[class*='chat']",
          "[class*='interact'] span",
          "[class*='engage'] span",
          "[class*='bottom'] span",
        ].join(","),
      ),
    );
    const interactionMetrics = [];
    const seenMetricElements = new Set();
    for (const element of metricElements) {
      if (element?.closest?.(".comment-item, [class*='comment-item'], [class*='reply-item']")) {
        continue;
      }
      const role = metricRole(element);
      if (!role) continue;
      const text = metricText(element);
      const key = `${role}\n${text}\n${classOf(element)}`;
      if (seenMetricElements.has(key)) continue;
      seenMetricElements.add(key);
      interactionMetrics.push({
        role,
        text,
        label: attrOf(element, "aria-label") || attrOf(element, "title"),
        className: classOf(element),
      });
    }
    const parseReplyPrefix = (value) => {
      const text = (value || "").trim();
      const match = text.match(/^(?:回复|Reply)\s+(.+?)[：:]\s*(.+)$/i);
      if (!match) {
        return { replyTo: "", content: text };
      }
      return { replyTo: match[1].trim(), content: match[2].trim() };
    };
    const title = textOf(detailRoot, ["#detail-title", "[class*='title']", "h1"]);
    const body = textOf(detailRoot, ["#detail-desc", "[class*='desc']", ".note-content", "[class*='content']"]);
    const author = textOf(detailRoot, [
      "a[href*='/user/profile']",
      "[class*='author'] [class*='name']",
      "[class*='user'] [class*='name']",
      "[class*='nickname']",
    ]);
    const interactionText = textOf(detailRoot, [
      "[class*='interact']",
      "[class*='engage']",
      "[class*='like']",
      "[class*='bottom-bar']",
    ]);
    const imageUrls = Array.from(detailRoot.querySelectorAll("img"))
      .filter((image) => (image.width || image.naturalWidth || 0) >= 160 && (image.height || image.naturalHeight || 0) >= 120)
      .map((image) => image.currentSrc || image.src)
      .filter((url) => !/avatar/i.test(url))
      .filter(Boolean);
    const commentElements = Array.from(
      new Set([
        ...detailRoot.querySelectorAll(".comment-item, [class*='comment-item']"),
        ...detailRoot.querySelectorAll("[class*='reply-item']"),
      ]),
    );
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
      const parsedReply = parseReplyPrefix(commentContent) || parseReplyPrefix(rawText);
      const replyTo = textOf(element, ["[class*='reply-to']", "[class*='replyTarget']", "[class*='target']"]) || parsedReply.replyTo;
      const className = classOf(element);
      const commentType = replyTo || /reply/i.test(className) || /回复/.test(className) ? "reply" : "comment";
      comments.push({
        author: commentAuthor,
        content: parsedReply.content || commentContent,
        likeText,
        rawText,
        commentType,
        replyTo,
      });
    }
    return {
      url: location.href,
      title,
      body,
      author,
      interactionText,
      interactionMetrics,
      images: Array.from(new Set(imageUrls)).slice(0, 8),
      comments,
    };
  }, maxComments);
}

export function normalizeDetailSnapshot(raw) {
  return {
    url: normalizeWhitespace(raw?.url),
    title: normalizeWhitespace(raw?.title).slice(0, 180),
    body: normalizeWhitespace(raw?.body),
    author: normalizeWhitespace(raw?.author),
    metrics: metricsFromDetailControls(raw?.interactionMetrics, raw?.interactionText),
    images: uniqueMediaUrls(raw?.images ?? []),
    comments: (raw?.comments ?? []).map((comment) => ({
      author: normalizeWhitespace(comment.author),
      ...normalizeCommentReply(comment.content, comment.commentType || comment.comment_type, comment.replyTo || comment.reply_to),
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

function metricsFromDetailControls(controls, fallbackText) {
  const metrics = {};
  for (const control of controls ?? []) {
    const role = normalizeMetricRole(control?.role || control?.label || control?.className || control?.text);
    if (!role || metrics[role] !== undefined) {
      continue;
    }
    const parsed = parseMetricNumber(control?.text || control?.label || "");
    if (parsed !== undefined) {
      metrics[role] = parsed;
    }
  }
  return {
    ...metricsFromText(fallbackText),
    ...metrics,
  };
}

function normalizeMetricRole(value) {
  const text = normalizeWhitespace(value).toLowerCase();
  if (!text) return "";
  if (/^collect$|^favorite$|collect|favorite|fav|star|save|收藏/.test(text)) return "collects";
  if (/^comment$|comment|chat|reply|评论|回复/.test(text)) return "comments";
  if (/^like$|like|heart|赞|点赞|喜欢/.test(text)) return "likes";
  return "";
}

function metricsFromText(value) {
  const text = normalizeWhitespace(value);
  const metrics = {};
  const patterns = [
    ["likes", /(?:赞|点赞|喜欢|like|likes)\D{0,16}(\d+(?:\.\d+)?\s*[万wW千kK]?)/i],
    ["likes", /(\d+(?:\.\d+)?\s*[万wW千kK]?)\D{0,8}(?:赞|点赞|喜欢|like|likes)/i],
    ["collects", /(?:收藏|collect|favorite|favorites|star|save)\D{0,16}(\d+(?:\.\d+)?\s*[万wW千kK]?)/i],
    ["collects", /(\d+(?:\.\d+)?\s*[万wW千kK]?)\D{0,8}(?:收藏|collect|favorite|favorites|star|save)/i],
    ["comments", /(?:评论|回复|comment|comments|chat)\D{0,16}(\d+(?:\.\d+)?\s*[万wW千kK]?)/i],
    ["comments", /(\d+(?:\.\d+)?\s*[万wW千kK]?)\D{0,8}(?:评论|回复|comment|comments|chat)/i],
  ];
  for (const [name, pattern] of patterns) {
    if (metrics[name] !== undefined) {
      continue;
    }
    const match = text.match(pattern);
    const parsed = match ? parseMetricNumber(match[1]) : undefined;
    if (parsed !== undefined) {
      metrics[name] = parsed;
    }
  }
  return metrics;
}

function normalizeCommentReply(content, commentType, replyTo) {
  const parsed = parseReplyContent(content);
  const target = normalizeWhitespace(replyTo) || parsed.reply_to;
  const type = normalizeWhitespace(commentType) === "reply" || target ? "reply" : "comment";
  return {
    content: parsed.content,
    comment_type: type,
    reply_to: type === "reply" ? target : "",
  };
}

function parseReplyContent(value) {
  const text = normalizeWhitespace(value);
  const match = text.match(/^(?:回复|Reply)\s+(.+?)[：:]\s*(.+)$/i);
  if (!match) {
    return { content: text, reply_to: "" };
  }
  return {
    reply_to: normalizeWhitespace(match[1]),
    content: normalizeWhitespace(match[2]),
  };
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

export function uniqueMediaUrls(values) {
  const seen = new Set();
  const urls = [];
  for (const value of values ?? []) {
    const url = normalizeWhitespace(value);
    if (!url) {
      continue;
    }
    const key = canonicalMediaUrlKey(url);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    urls.push(url);
  }
  return urls;
}

function canonicalMediaUrlKey(value) {
  const text = normalizeWhitespace(value);
  if (!text) {
    return "";
  }
  if (text.startsWith("data:image/")) {
    return `data:${stableFingerprint(text)}`;
  }
  try {
    const url = new URL(text);
    const path = decodeURIComponent(url.pathname || "");
    const filename = path.split("/").filter(Boolean).pop() || path;
    const imageId = filename.split("!")[0];
    if (imageId && imageId.length >= 10) {
      return `image:${imageId}`;
    }
    return `${url.hostname}${path.split("!")[0]}`;
  } catch {
    return text;
  }
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
