import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { dirname, join } from "node:path";
import {
  canonicalPostId,
  canonicalPostUrl,
  normalizeSearchCards,
  normalizeWhitespace,
  parseMetricNumber,
  stableFingerprint,
} from "./xiaohongshu-normalize.mjs";

const DEFAULT_ACCESS_POLICY = {
  js_access: false,
  direct_url_access: false,
  network_api_access: false,
};

const DEFAULT_PACE = {
  detail_delay_range_seconds: [8, 18],
  scroll_delay_range_seconds: [5, 12],
  scroll_distance_viewport_range: [0.45, 0.85],
  batch_rest_after_cards_range: [5, 11],
  batch_rest_seconds_range: [6, 10],
  click_delay_range_ms: [250, 900],
  waterfall_missing_recovery_threshold: 5,
  detail_scroll_distance_viewport_range: [0.25, 0.55],
  comment_scroll_delay_range_seconds: [4, 9],
  comment_scroll_distance_viewport_range: [0.25, 0.5],
  reply_expand_delay_range_seconds: [5, 8],
  max_relocate_scrolls: 6,
  max_comment_scrolls_per_post: 0,
  max_reply_expansions_per_post: 0,
  max_screenshot_media_per_post: 4,
};

const COMMENT_ITEM_SELECTOR = ".comment-item, [class*='comment-item'], [class*='reply-item']";
const SEARCH_SCREENSHOT_FULL_PAGE_TIMEOUT_MS = 90_000;
const SEARCH_SCREENSHOT_VIEWPORT_TIMEOUT_MS = 15_000;

const DEFAULT_REQUEST_POLICY = {
  safety_profile: "respectful_human",
  automation_boundary: "browser_control",
  media_policy: "browser_loaded_image",
  checkpoint_enabled: true,
  access_policy: DEFAULT_ACCESS_POLICY,
  pace: DEFAULT_PACE,
};

export async function collectXiaohongshu({ request, assetsPath, profilePath, events }) {
  const collectorRequest = normalizeCollectorRequest(request);
  if (!collectorRequest.dry_run) {
    return collectXiaohongshuReal({ request: collectorRequest, assetsPath, profilePath, events });
  }

  const run_id = collectorRequest.run_id;
  const platform = collectorRequest.platform;
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
      keyword: collectorRequest.keyword,
      title: `Dry-run sample for ${collectorRequest.keyword}`,
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
          keyword: collectorRequest.keyword,
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

export function normalizeCollectorRequest(request = {}) {
  return {
    ...request,
    safety_profile: request.safety_profile || DEFAULT_REQUEST_POLICY.safety_profile,
    automation_boundary: request.automation_boundary || DEFAULT_REQUEST_POLICY.automation_boundary,
    media_policy: request.media_policy || DEFAULT_REQUEST_POLICY.media_policy,
    checkpoint_enabled: request.checkpoint_enabled !== false,
    access_policy: {
      ...DEFAULT_ACCESS_POLICY,
      ...(request.access_policy || {}),
    },
    pace: normalizePace(request.pace),
  };
}

export async function selectUsableBrowserPage(context, options = {}) {
  const pages = typeof context.pages === "function" ? context.pages() : [];
  const preferredHost = normalizeWhitespace(options.preferredHost || "").toLowerCase();
  const preferredPage = pages.find((page) => pageHostMatches(pageUrl(page), preferredHost));
  const nonBlankPage = pages.find((page) => isUsableBrowserPageUrl(pageUrl(page)));
  const page = preferredPage ?? nonBlankPage ?? pages[0] ?? (await context.newPage());
  if (page && typeof page.bringToFront === "function") {
    await page.bringToFront().catch(() => {});
  }
  return page;
}

function pageUrl(page) {
  try {
    return typeof page?.url === "function" ? String(page.url() || "") : "";
  } catch {
    return "";
  }
}

function isUsableBrowserPageUrl(value) {
  const url = normalizeWhitespace(value).toLowerCase();
  return Boolean(url) && url !== "about:blank" && !url.startsWith("chrome://") && !url.startsWith("devtools://");
}

function pageHostMatches(value, preferredHost) {
  if (!preferredHost || !isUsableBrowserPageUrl(value)) {
    return false;
  }
  try {
    const hostname = new URL(value).hostname.toLowerCase();
    return hostname === preferredHost || hostname.endsWith(`.${preferredHost}`) || hostname.endsWith(preferredHost);
  } catch {
    return false;
  }
}

async function collectXiaohongshuReal({ request, assetsPath, profilePath, events }) {
  const run_id = request.run_id;
  const platform = request.platform;
  const maxPosts = Math.max(1, Number(request.max_posts ?? 5));
  let context;
  const loadedImages = createLoadedImageStore();

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
      const { chromium } = await loadPlaywright();
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
    const page = await selectUsableBrowserPage(context, { preferredHost: "xiaohongshu.com" });
    loadedImages.attachPage(page);

    try {
      if (process.env.FALCON_COLLECTOR_FORCE_EARLY_BROWSER_CLOSE === "1") {
        await page.close().catch(() => {});
        throw new Error("page.waitForTimeout: Target page, context or browser has been closed");
      }
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
          matchedSignals: landingStop.matched_signals,
        });
      }

      await performSearchFromHome(page, request, events);
      await humanWait(page, secondsRangeToMs(request.pace.scroll_delay_range_seconds));

      const searchStop = await detectManualAction(page);
      if (searchStop) {
        return manualActionRecords({
          page,
          request,
          assetsPath,
          events,
          reason: searchStop.reason,
          detail: searchStop.detail,
          matchedSignals: searchStop.matched_signals,
        });
      }
    } catch (error) {
      if (isPlaywrightTargetClosedError(error)) {
        return manualActionRecords({
          page,
          request,
          assetsPath,
          events,
          reason: "browser_closed_early",
          detail: "浏览器窗口在采集准备阶段被关闭。请确认窗口状态后继续采集，或重新运行新任务。",
          matchedSignals: [
            {
              reason: "browser_closed_early",
              signal: error.message || String(error),
              source: "playwright",
            },
          ],
        });
      }
      throw error;
    }

    const searchReady = await verifySearchResultsReady(page, request);
    if (!searchReady.ok) {
      throw createSearchNotConfirmedError(
        searchReady,
        await searchNotConfirmedFailureRecords({
          page,
          request,
          assetsPath,
          searchReady,
        }),
      );
    }

    const screenshotPath = join(assetsPath, "xiaohongshu-search-results.png");
    const searchScreenshot = await captureSearchResultsScreenshot(page, screenshotPath, {
      request,
      events,
    });

    const rawSnapshot = await extractVisibleSnapshot(page, maxPosts * 4);
    const snapshot = {
      ...rawSnapshot,
      posts: normalizeSearchCards(rawSnapshot.posts, maxPosts),
    };
    const snapshotPath = join(assetsPath, "xiaohongshu-search-snapshot.json");
    await writeFile(snapshotPath, `${JSON.stringify(snapshot, null, 2)}\n`, "utf8");
    const searchScreenshotEvidence = searchScreenshot.path
      ? [
          evidenceRecord({
            request,
            evidenceId: `${run_id}-search-screenshot`,
            scope: "search_results_screenshot",
            path: searchScreenshot.path,
            payload: {
              keyword: request.keyword,
              mode: searchScreenshot.mode,
              full_page_error: searchScreenshot.fullPageError || "",
            },
          }),
        ]
      : [];

    if (snapshot.posts.length === 0) {
      return manualActionRecords({
        page,
        request,
        assetsPath,
        events,
        reason: "no_posts_detected",
        detail: "小红书已打开，但采集器没有识别到可见笔记卡片。",
        existingEvidence: [
          ...searchScreenshotEvidence,
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
      ...searchScreenshotEvidence,
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
      detailOutcome = await collectWaterfallRecords({
        context,
        searchPage: page,
        request,
        assetsPath,
        events,
        initialPosts: snapshot.posts,
        loadedImages,
      });
      records.push(...detailOutcome.records);
    } catch (error) {
      if (Array.isArray(error.partialRecords)) {
        records.push(...error.partialRecords);
      }
      error.partialRecords = records;
      throw error;
    }

    if (!detailOutcome.stopped) {
      events.write("info", "xiaohongshu", "records_collected", "已生成小红书采集记录", {
        run_id,
        platform,
        posts: detailOutcome.collected,
        discovered: detailOutcome.discovered,
        skipped: detailOutcome.skipped,
        requested: maxPosts,
      });
    }
    return records;
  } finally {
    if (context) {
      await context.close().catch(() => {});
    }
  }
}

export function isPlaywrightTargetClosedError(error) {
  const message = String(error?.message || error || "").toLowerCase();
  return (
    message.includes("target page, context or browser has been closed") ||
    message.includes("target page closed") ||
    message.includes("target closed") ||
    message.includes("page has been closed") ||
    message.includes("context has been closed") ||
    message.includes("browser has been closed")
  );
}

function searchCardNotFoundError(message) {
  const error = new Error(message);
  error.code = "XIAOHONGSHU_CARD_NOT_FOUND";
  return error;
}

function isSearchCardNotFoundError(error) {
  return error?.code === "XIAOHONGSHU_CARD_NOT_FOUND";
}

function detailOpenFailedError(message, reason = "detail_not_detected") {
  const error = new Error(message);
  error.code = "XIAOHONGSHU_DETAIL_OPEN_FAILED";
  error.reason = reason;
  return error;
}

function isDetailOpenFailedError(error) {
  return error?.code === "XIAOHONGSHU_DETAIL_OPEN_FAILED";
}

export function isPersistentProfileLaunchConflict(error) {
  const message = String(error?.message || error || "");
  return (
    message.includes("launchPersistentContext") &&
    message.includes("Target page, context or browser has been closed") &&
    (message.includes("process did exit: exitCode=0") || message.includes("--user-data-dir="))
  );
}

export async function collectWaterfallRecords({
  context,
  searchPage,
  request,
  assetsPath,
  events,
  initialPosts = [],
  loadedImages,
}) {
  const maxPosts = Math.max(1, Number(request.max_posts ?? 5));
  const checkpointPath = checkpointPathForAssets(assetsPath);
  const checkpoint = await readCheckpoint(checkpointPath, request);
  const records = [];
  const pending = [];
  const queuedIds = new Set();
  const collectedIds = new Set(checkpoint.collected_ids || []);
  const skippedIds = new Set(checkpoint.skipped_ids || []);
  const failedIds = new Set(checkpoint.failed_ids || []);
  let consecutiveMissingTargets = Number(checkpoint.waterfall_consecutive_missing_targets || 0);
  let waterfallMissingSkipped = Number(checkpoint.waterfall_missing_skipped || 0);
  let waterfallMissingThresholdTriggers = Number(checkpoint.waterfall_missing_threshold_triggers || 0);
  const paceState = {
    attemptedSinceBatchRest: Number(checkpoint.attempted_since_batch_rest || 0),
    nextBatchRestAfter:
      Number(checkpoint.next_batch_rest_after || 0) ||
      randomIntFromRange(request.pace.batch_rest_after_cards_range),
  };
  let stagnantScrolls = 0;

  const enqueuePosts = (posts, source) => {
    let added = 0;
    for (const post of posts) {
      const remainingNeeded = Math.max(0, maxPosts - collectedIds.size);
      if (pending.length >= remainingNeeded) {
        break;
      }
      const postId = postIdForSearchPost(post);
      if (
        !postId ||
        queuedIds.has(postId) ||
        collectedIds.has(postId) ||
        skippedIds.has(postId) ||
        failedIds.has(postId)
      ) {
        continue;
      }
      pending.push(post);
      queuedIds.add(postId);
      added += 1;
    }
    if (added > 0) {
      events.write("info", "xiaohongshu", "waterfall_cards_discovered", `瀑布流已发现 ${queuedIds.size}/${maxPosts} 条候选笔记`, {
        run_id: request.run_id,
        platform: request.platform,
        source,
        added,
        queued: pending.length,
        discovered: queuedIds.size,
        requested: maxPosts,
      });
    }
    return added;
  };

  enqueuePosts([...(checkpoint.pending_posts || []), ...initialPosts], "initial_view");

  while (collectedIds.size < maxPosts) {
    if (pending.length === 0) {
      const discovered = await discoverMoreWaterfallPosts({
        searchPage,
        request,
        maxPosts,
        enqueuePosts,
      });
      if (discovered === 0) {
        stagnantScrolls += 1;
        if (stagnantScrolls >= 8) {
          events.write(
            "warning",
            "xiaohongshu",
            "waterfall_exhausted",
            `瀑布流连续滚动未发现更多新笔记，已采集 ${collectedIds.size}/${maxPosts} 条。`,
            {
              run_id: request.run_id,
              platform: request.platform,
              collected: collectedIds.size,
              discovered: queuedIds.size,
              requested: maxPosts,
            },
          );
          break;
        }
      } else {
        stagnantScrolls = 0;
      }
      continue;
    }

    const searchPost = pending.shift();
    const postId = postIdForSearchPost(searchPost);
    if (!postId || collectedIds.has(postId)) {
      continue;
    }

    try {
      const detailOutcome = await collectDetailRecords({
        context,
        searchPage,
        request,
        assetsPath,
        events,
        posts: [searchPost],
        startIndex: collectedIds.size,
        total: maxPosts,
        loadedImages,
      });
      records.push(...detailOutcome.records);
      if (detailOutcome.stopped) {
        await writeCheckpoint(checkpointPath, request, {
          collectedIds,
          skippedIds,
          failedIds,
          pending,
          paceState,
          waterfallStats: {
            consecutiveMissingTargets,
            missingSkipped: waterfallMissingSkipped,
            thresholdTriggers: waterfallMissingThresholdTriggers,
          },
        });
        return {
          records,
          stopped: true,
          collected: collectedIds.size,
          discovered: queuedIds.size,
          waterfall_missing_skipped: waterfallMissingSkipped,
          waterfall_missing_threshold_triggers: waterfallMissingThresholdTriggers,
        };
      }
      if (detailOutcome.missingTarget) {
        skippedIds.add(postId);
        consecutiveMissingTargets += 1;
        waterfallMissingSkipped += 1;
        const threshold = request.pace.waterfall_missing_recovery_threshold;
        events.write(
          "warning",
          "xiaohongshu",
          "waterfall_target_skipped",
          `瀑布流未找到目标卡片，已跳过第 ${consecutiveMissingTargets}/${threshold} 个连续缺失目标。`,
          {
            run_id: request.run_id,
            platform: request.platform,
            reason: "waterfall_target_missing",
            post_id: postId,
            search_url: safePageUrl(searchPage),
            skipped_cards: waterfallMissingSkipped,
            consecutive_missing: consecutiveMissingTargets,
            recovery_threshold: threshold,
            error: detailOutcome.error || "",
          },
        );
        if (consecutiveMissingTargets >= threshold) {
          waterfallMissingThresholdTriggers += 1;
          const scrolled = await scrollSearchResultsHalfPage(searchPage, request);
          events.write(
            "warning",
            "xiaohongshu",
            "waterfall_missing_threshold_recovery",
            "连续未找到目标卡片达到阈值，已向下滚动半屏并重新收集瀑布流卡片。",
            {
              run_id: request.run_id,
              platform: request.platform,
              reason: "waterfall_target_missing_threshold",
              skipped_cards: waterfallMissingSkipped,
              consecutive_missing: consecutiveMissingTargets,
              recovery_threshold: threshold,
              threshold_triggers: waterfallMissingThresholdTriggers,
              scroll_delta_y: scrolled,
            },
          );
          consecutiveMissingTargets = 0;
          await discoverMoreWaterfallPosts({
            searchPage,
            request,
            maxPosts,
            enqueuePosts,
            alreadyScrolled: true,
          });
        }
      } else if (detailOutcome.skipped) {
        skippedIds.add(postId);
        failedIds.add(postId);
        consecutiveMissingTargets = 0;
      } else {
        collectedIds.add(postId);
        consecutiveMissingTargets = 0;
      }
      await writeCheckpoint(checkpointPath, request, {
        collectedIds,
        skippedIds,
        failedIds,
        pending,
        paceState,
        waterfallStats: {
          consecutiveMissingTargets,
          missingSkipped: waterfallMissingSkipped,
          thresholdTriggers: waterfallMissingThresholdTriggers,
        },
      });
      if (collectedIds.size < maxPosts) {
        await restBetweenCards(searchPage, request, events, paceState);
        await writeCheckpoint(checkpointPath, request, {
          collectedIds,
          skippedIds,
          failedIds,
          pending,
          paceState,
          waterfallStats: {
            consecutiveMissingTargets,
            missingSkipped: waterfallMissingSkipped,
            thresholdTriggers: waterfallMissingThresholdTriggers,
          },
        });
      }
    } catch (error) {
      if (Array.isArray(error.partialRecords)) {
        records.push(...error.partialRecords);
      }
      await writeCheckpoint(checkpointPath, request, {
        collectedIds,
        skippedIds,
        failedIds,
        pending,
        paceState,
        waterfallStats: {
          consecutiveMissingTargets,
          missingSkipped: waterfallMissingSkipped,
          thresholdTriggers: waterfallMissingThresholdTriggers,
        },
      });
      error.partialRecords = records;
      throw error;
    }
  }

  await writeCheckpoint(checkpointPath, request, {
    collectedIds,
    skippedIds,
    failedIds,
    pending,
    paceState,
    waterfallStats: {
      consecutiveMissingTargets,
      missingSkipped: waterfallMissingSkipped,
      thresholdTriggers: waterfallMissingThresholdTriggers,
    },
  });

  return {
    records,
    stopped: false,
    collected: collectedIds.size,
    discovered: queuedIds.size,
    skipped: skippedIds.size,
    waterfall_missing_skipped: waterfallMissingSkipped,
    waterfall_missing_threshold_triggers: waterfallMissingThresholdTriggers,
  };
}

async function discoverMoreWaterfallPosts({ searchPage, request, maxPosts, enqueuePosts, alreadyScrolled = false }) {
  if (!alreadyScrolled) {
    await scrollSearchResults(searchPage, request);
  }
  const rawSnapshot = await extractVisibleSnapshot(searchPage, maxPosts * 4);
  const snapshot = {
    ...rawSnapshot,
    posts: normalizeSearchCards(rawSnapshot.posts, maxPosts),
  };
  return enqueuePosts(snapshot.posts, "scroll");
}

export async function scrollSearchResultsHalfPage(page, request = {}) {
  const viewport = page.viewportSize?.() ?? { width: 1366, height: 900 };
  const deltaY = Math.max(180, Math.round((viewport.height || 900) * 0.5));
  await page.mouse.wheel(0, deltaY);
  await humanWait(page, secondsRangeToMs(request.pace?.scroll_delay_range_seconds || DEFAULT_PACE.scroll_delay_range_seconds));
  return deltaY;
}

export async function scrollSearchResults(page, request = {}) {
  const viewport = page.viewportSize?.() ?? { width: 1366, height: 900 };
  const ratio = randomFloatFromRange(request.pace?.scroll_distance_viewport_range || DEFAULT_PACE.scroll_distance_viewport_range);
  const deltaY = Math.max(180, Math.round(Math.min(viewport.height, viewport.height * ratio)));
  await page.mouse.wheel(0, deltaY);
  await humanWait(page, secondsRangeToMs(request.pace?.scroll_delay_range_seconds || DEFAULT_PACE.scroll_delay_range_seconds));
  return deltaY;
}

function postIdForSearchPost(searchPost) {
  const postUrl = canonicalPostUrl(searchPost?.url || searchPost?.href);
  return searchPost?.postId || canonicalPostId(postUrl || searchPost?.href || "");
}

export async function collectDetailRecords({
  context,
  searchPage,
  request,
  assetsPath,
  events,
  posts,
  startIndex = 0,
  total,
  loadedImages,
}) {
  const records = [];
  const platform = request.platform;
  const maxComments = Math.max(0, Number(request.max_comments_per_post ?? 10));
  const postTotal = Math.max(1, Number(total ?? posts.length));

  for (const [index, searchPost] of posts.entries()) {
    const progressIndex = startIndex + index;
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
        index: progressIndex,
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
        request,
      });
      const detailPage = detailHandle.page;
      loadedImages?.attachPage?.(detailPage);
      await humanWait(detailPage, [2200, 4200]);

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
            matchedSignals: detailStop.matched_signals,
          })),
        );
        return { records, stopped: true };
      }

      const detailScreenshotPath = join(assetsPath, `${stem}-detail.png`);
      await captureDetailScreenshot(detailPage, detailScreenshotPath);
      if (maxComments > 0) {
        const detailRoot = await detailRootLocator(detailPage);
        await prepareVisibleCommentsForExtraction(detailPage, detailRoot, request, maxComments);
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
      records.push(
        ...(await captureVisibleMediaAssets({
          page: detailPage,
          request,
          assetsPath,
          stem,
          postId,
          events,
          loadedImages,
        })),
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

      const collectedPayload = postProgressPayload({
        request,
        platform,
        postId,
        postUrl,
        index: progressIndex,
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
      if (isPlaywrightTargetClosedError(error)) {
        const collectedPosts = startIndex + records.filter((record) => record.type === "post").length;
        events.write(
          "warning",
          "xiaohongshu",
          "manual_action_required",
          `浏览器或详情页在第 ${index + 1}/${postTotal} 条采集时已关闭，已保留 ${collectedPosts} 条已采集笔记；请确认窗口状态后继续采集或重新运行。`,
          {
            run_id: request.run_id,
            platform,
            reason: "browser_closed_mid_run",
            post_id: postId,
            url: postUrl,
            post_index: index + 1,
            post_total: postTotal,
            collected_posts: collectedPosts,
            error: error.message,
          },
        );
        return { records, stopped: true };
      }
      if (isSearchCardNotFoundError(error)) {
        return { records, stopped: false, skipped: true, missingTarget: true, error: error.message };
      }
      if (isDetailOpenFailedError(error)) {
        events.write(
          "warning",
          "xiaohongshu",
          "detail_open_skipped",
          `第 ${progressIndex + 1}/${postTotal} 条笔记详情未能打开，已记录证据并继续采集后续笔记。`,
          {
            run_id: request.run_id,
            platform,
            reason: error.reason || "detail_not_detected",
            post_id: postId,
            url: postUrl,
            post_index: progressIndex + 1,
            post_total: postTotal,
            error: error.message,
          },
        );
        return { records, stopped: false, skipped: true };
      }
      const wrapped = new Error(`小红书详情页采集失败：第 ${progressIndex + 1} 条笔记，${error.message}`);
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

export async function openDetailFromSearchCard({ context, searchPage, searchPost, index, request = {} }) {
  const browserContext = context || searchPage.context?.();
  let lastReason = "detail_not_detected";

  for (let attempt = 0; attempt < 2; attempt += 1) {
    const locator = await findSearchCardLocator(searchPage, searchPost, index, request);
    if (!locator) {
      throw new Error("未找到可点击的小红书笔记卡片，已停止直接 URL 访问以避免触发风控。");
    }

    const beforeUrl = searchPage.url();
    const beforePages = browserContext?.pages ? new Set(browserContext.pages()) : new Set();
    const popupPromise = searchPage.waitForEvent
      ? searchPage.waitForEvent("popup", { timeout: 8000 }).catch(() => null)
      : Promise.resolve(null);
    const contextPagePromise = browserContext?.waitForEvent
      ? browserContext.waitForEvent("page", { timeout: 8000 }).catch(() => null)
      : Promise.resolve(null);

    await humanMouseClickLocator(searchPage, locator);
    const popup = await firstOpenedPage([popupPromise, contextPagePromise]);
    if (popup) {
      await popup.waitForLoadState("domcontentloaded", { timeout: 12_000 }).catch(() => {});
      return { page: popup, mode: "popup", searchPage };
    }

    await searchPage.waitForLoadState("domcontentloaded", { timeout: 8000 }).catch(() => {});
    await humanWait(searchPage, [1400, 2600]);
    const afterUrl = searchPage.url();
    if (afterUrl !== beforeUrl || (await hasDetailContainer(searchPage))) {
      return { page: searchPage, mode: "same_page", searchPage, beforeUrl };
    }

    const fallbackPage = browserContext?.pages
      ? browserContext
          .pages()
          .find((page) => page !== searchPage && !beforePages.has(page) && safePageUrl(page) !== beforeUrl)
      : null;
    if (fallbackPage) {
      await fallbackPage.waitForLoadState("domcontentloaded", { timeout: 8000 }).catch(() => {});
      return { page: fallbackPage, mode: "context_page", searchPage };
    }

    const noteOpenFailure = await detectNoteOpenFailure(searchPage);
    lastReason = noteOpenFailure || "detail_not_detected";
    if (attempt < 1) {
      if (searchPage.keyboard?.press) {
        await searchPage.keyboard.press("Escape").catch(() => {});
      }
      await humanWait(searchPage, [1200, 2600]);
      continue;
    }
  }

  if (lastReason === "note_load_failed") {
    throw detailOpenFailedError("点击笔记卡片后小红书提示笔记加载失败。", lastReason);
  }
  throw detailOpenFailedError("点击笔记卡片后未检测到详情页或弹窗。", lastReason);
}

async function firstOpenedPage(promises) {
  try {
    return await Promise.any(
      promises.map((promise) =>
        promise
          .then((page) => {
            if (page) {
              return page;
            }
            throw new Error("No opened page");
          })
          .catch((error) => {
            throw error;
          }),
      ),
    );
  } catch {
    return null;
  }
}

function safePageUrl(page) {
  try {
    return page.url();
  } catch {
    return "";
  }
}

async function detectNoteOpenFailure(page) {
  try {
    const text = await visibleTextForSelectors(page, [
      "[class*='toast']",
      "[class*='message']",
      "[class*='notify']",
      "[role='alert']",
      "body",
    ], 3000);
    if (/笔记加载失败|加载失败|内容不存在|已删除|无法查看|暂时无法浏览/.test(text)) {
      return "note_load_failed";
    }
  } catch {
    return "";
  }
  return "";
}

async function findSearchCardLocator(page, searchPost, index, request = {}) {
  const expectedIds = expectedSearchCardIds(searchPost);
  const expectedLocator = await findExpectedSearchCardLocator(page, expectedIds);
  if (expectedLocator) {
    return expectedLocator;
  }

  if (expectedIds.size) {
    const recoveredLocator = await scrollToSearchCardLocator(page, expectedIds, searchPost, request);
    if (recoveredLocator) {
      return recoveredLocator;
    }
    throw searchCardNotFoundError(
      `未找到与 ${Array.from(expectedIds).join(", ")} 匹配的可点击笔记卡片，搜索页可能已经离开原结果页或瀑布流未继续加载，已停止按序号兜底以避免采错帖子。`,
    );
  }

  const cardIndex = Number.isInteger(searchPost?.cardIndex) ? searchPost.cardIndex : index;
  return indexedClickableLocator(page, ".note-item, .feeds-page .note-card, section, article", cardIndex);
}

function expectedSearchCardIds(searchPost) {
  const ids = new Set();
  const rawId = String(searchPost?.postId || "").replace(/^xiaohongshu:/, "");
  if (rawId) {
    ids.add(rawId);
  }
  for (const value of [searchPost?.href, searchPost?.url]) {
    const hrefId = String(value || "").match(/(?:\/(?:explore|search_result)\/)([A-Za-z0-9_-]{6,})/)?.[1];
    if (hrefId) {
      ids.add(hrefId);
    }
  }
  return ids;
}

function searchCardSelectorsForIds(expectedIds) {
  const selectors = [];
  for (const id of expectedIds) {
    selectors.push(`a[href*="/search_result/${cssEscape(id)}"]`);
    selectors.push(`a[href*="/explore/${cssEscape(id)}"]`);
    selectors.push(`a[href*="${cssEscape(id)}"]`);
    selectors.push(`.note-item:has(a[href*="${cssEscape(id)}"])`);
    selectors.push(`.feeds-page .note-card:has(a[href*="${cssEscape(id)}"])`);
    selectors.push(`section:has(a[href*="${cssEscape(id)}"])`);
    selectors.push(`article:has(a[href*="${cssEscape(id)}"])`);
  }
  return selectors;
}

async function findExpectedSearchCardLocator(page, expectedIds) {
  for (const selector of searchCardSelectorsForIds(expectedIds)) {
    const locator = await firstClickableLocator(page, selector, {
      minimumSize: selector.startsWith("a[href") ? 10 : 80,
    });
    if (locator) {
      return locator;
    }
  }
  return null;
}

async function scrollToSearchCardLocator(page, expectedIds, searchPost, request = {}) {
  const maxScrolls = Math.max(1, Number(request.pace?.max_relocate_scrolls || DEFAULT_PACE.max_relocate_scrolls));
  for (let attempt = 0; attempt < maxScrolls; attempt += 1) {
    await scrollSearchResults(page, request);
    const locator = await findExpectedSearchCardLocator(page, expectedIds);
    if (locator) {
      return locator;
    }
  }
  return null;
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
  await humanWait(page, [250, 900]);
  const point = await findSafeClickPoint(page, locator, { allowReposition: true });
  if (!point) {
    throw new Error("小红书笔记卡片不可见，无法模拟点击。");
  }
  const { x, y } = point;
  await page.mouse.move(x - 18, y - 10, { steps: 8 });
  await humanWait(page, [120, 360]);
  await page.mouse.move(x, y, { steps: 10 });
  await humanWait(page, [120, 360]);
  await page.mouse.click(x, y, { delay: randomInt(80, 180) });
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
    await page.mouse.wheel(0, deltaY + randomInt(-40, 40));
    await humanWait(page, [450, 900]);
  }
  return null;
}

async function locatorHitTestPoint(locator) {
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
  await humanWait(handle.page, [900, 1800]).catch(() => {});
  if (beforeUrl && (await isBackOnExpectedSearchPage(handle.page, beforeUrl))) {
    return;
  }
  if (handle.page.goBack) {
    await handle.page.goBack({ waitUntil: "domcontentloaded", timeout: 8000 }).catch(() => {});
  }
  await humanWait(handle.page, [900, 1800]).catch(() => {});
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

export async function expandVisibleCommentReplies(page, maxExpansions = 4, pace = {}) {
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
      await humanWait(page, secondsRangeToMs(pace.reply_expand_delay_range_seconds || DEFAULT_PACE.reply_expand_delay_range_seconds));
      break;
    }
    if (!clickedThisPass) {
      break;
    }
  }
  return clicked;
}

export async function captureDetailScreenshot(page, path) {
  const viewport = page.viewportSize?.() ?? { width: 1366, height: 900 };
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

export async function captureSearchResultsScreenshot(page, path, options = {}) {
  const request = options.request || {};
  const events = options.events;
  const fullPageTimeoutMs = positiveTimeoutMs(
    request.search_screenshot_timeout_ms,
    SEARCH_SCREENSHOT_FULL_PAGE_TIMEOUT_MS,
  );
  const viewportTimeoutMs = positiveTimeoutMs(
    request.search_screenshot_viewport_timeout_ms,
    SEARCH_SCREENSHOT_VIEWPORT_TIMEOUT_MS,
  );

  try {
    await page.screenshot({ path, fullPage: true, timeout: fullPageTimeoutMs });
    return {
      path,
      mode: "full_page",
      timeoutMs: fullPageTimeoutMs,
      fullPageError: "",
      viewportError: "",
    };
  } catch (fullPageError) {
    const fullPageErrorMessage = errorMessage(fullPageError);
    try {
      await page.screenshot({ path, fullPage: false, timeout: viewportTimeoutMs });
      writeBestEffortEvent(
        events,
        "warning",
        "xiaohongshu",
        "search_screenshot_fallback",
        "搜索结果全页截图失败，已降级保存当前屏幕截图。",
        {
          run_id: request.run_id,
          platform: request.platform,
          path,
          mode: "viewport",
          full_page_timeout_ms: fullPageTimeoutMs,
          viewport_timeout_ms: viewportTimeoutMs,
          full_page_error: fullPageErrorMessage,
        },
      );
      return {
        path,
        mode: "viewport",
        timeoutMs: viewportTimeoutMs,
        fullPageError: fullPageErrorMessage,
        viewportError: "",
      };
    } catch (viewportError) {
      const viewportErrorMessage = errorMessage(viewportError);
      writeBestEffortEvent(
        events,
        "warning",
        "xiaohongshu",
        "search_screenshot_failed",
        "搜索结果页截图失败，已继续采集。",
        {
          run_id: request.run_id,
          platform: request.platform,
          requested_path: path,
          mode: "failed",
          full_page_timeout_ms: fullPageTimeoutMs,
          viewport_timeout_ms: viewportTimeoutMs,
          full_page_error: fullPageErrorMessage,
          viewport_error: viewportErrorMessage,
        },
      );
      return {
        path: "",
        requestedPath: path,
        mode: "failed",
        timeoutMs: viewportTimeoutMs,
        fullPageError: fullPageErrorMessage,
        viewportError: viewportErrorMessage,
      };
    }
  }
}

function positiveTimeoutMs(value, fallback) {
  const timeoutMs = Number(value);
  return Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : fallback;
}

function errorMessage(error) {
  return String(error?.message || error || "");
}

function writeBestEffortEvent(events, level, scope, event, message, payload) {
  try {
    if (events?.write) {
      events.write(level, scope, event, message, payload);
    }
  } catch {
    // Event logging should not break evidence capture fallback paths.
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

function normalizePace(pace = {}) {
  return {
    ...DEFAULT_PACE,
    ...pace,
    detail_delay_range_seconds: numericRange(pace.detail_delay_range_seconds, DEFAULT_PACE.detail_delay_range_seconds),
    scroll_delay_range_seconds: numericRange(pace.scroll_delay_range_seconds, DEFAULT_PACE.scroll_delay_range_seconds),
    scroll_distance_viewport_range: numericRange(pace.scroll_distance_viewport_range, DEFAULT_PACE.scroll_distance_viewport_range),
    batch_rest_after_cards_range: numericRange(pace.batch_rest_after_cards_range, DEFAULT_PACE.batch_rest_after_cards_range),
    batch_rest_seconds_range: numericRange(pace.batch_rest_seconds_range, DEFAULT_PACE.batch_rest_seconds_range),
    click_delay_range_ms: numericRange(pace.click_delay_range_ms, DEFAULT_PACE.click_delay_range_ms),
    detail_scroll_distance_viewport_range: numericRange(
      pace.detail_scroll_distance_viewport_range,
      DEFAULT_PACE.detail_scroll_distance_viewport_range,
    ),
    comment_scroll_delay_range_seconds: numericRange(
      pace.comment_scroll_delay_range_seconds,
      DEFAULT_PACE.comment_scroll_delay_range_seconds,
    ),
    comment_scroll_distance_viewport_range: numericRange(
      pace.comment_scroll_distance_viewport_range,
      DEFAULT_PACE.comment_scroll_distance_viewport_range,
    ),
    reply_expand_delay_range_seconds: numericRange(
      pace.reply_expand_delay_range_seconds,
      DEFAULT_PACE.reply_expand_delay_range_seconds,
    ),
    max_relocate_scrolls: Math.max(1, Number(pace.max_relocate_scrolls || DEFAULT_PACE.max_relocate_scrolls)),
    waterfall_missing_recovery_threshold: Math.max(
      1,
      Number(pace.waterfall_missing_recovery_threshold || DEFAULT_PACE.waterfall_missing_recovery_threshold),
    ),
    max_comment_scrolls_per_post: Math.max(
      0,
      Number(pace.max_comment_scrolls_per_post ?? DEFAULT_PACE.max_comment_scrolls_per_post),
    ),
    max_reply_expansions_per_post: Math.max(
      0,
      Number(pace.max_reply_expansions_per_post ?? DEFAULT_PACE.max_reply_expansions_per_post),
    ),
    max_screenshot_media_per_post: Math.max(
      0,
      Number(pace.max_screenshot_media_per_post ?? DEFAULT_PACE.max_screenshot_media_per_post),
    ),
  };
}

function numericRange(value, fallback) {
  if (!Array.isArray(value) || value.length < 2) {
    return [...fallback];
  }
  const left = Number(value[0]);
  const right = Number(value[1]);
  if (!Number.isFinite(left) || !Number.isFinite(right)) {
    return [...fallback];
  }
  return [Math.min(left, right), Math.max(left, right)];
}

function secondsRangeToMs(range) {
  const normalized = numericRange(range, [0, 0]);
  return [Math.round(normalized[0] * 1000), Math.round(normalized[1] * 1000)];
}

function randomInt(min, max) {
  const left = Math.ceil(Math.min(Number(min), Number(max)));
  const right = Math.floor(Math.max(Number(min), Number(max)));
  if (!Number.isFinite(left) || !Number.isFinite(right)) {
    return 0;
  }
  return left + Math.floor(Math.random() * (right - left + 1));
}

function randomIntFromRange(range) {
  const normalized = numericRange(range, [0, 0]);
  return randomInt(normalized[0], normalized[1]);
}

function randomFloatFromRange(range) {
  const normalized = numericRange(range, [0, 0]);
  return normalized[0] + Math.random() * (normalized[1] - normalized[0]);
}

async function humanWait(page, millisecondsRange) {
  const delay = randomIntFromRange(millisecondsRange);
  if (delay > 0) {
    await page.waitForTimeout(delay);
  }
  return delay;
}

async function performSearchFromHome(page, request, events) {
  const keyword = String(request.keyword || "").trim();
  if (!keyword) {
    return;
  }
  const input = await firstUsableLocator(page, [
    "input[placeholder*='搜索']",
    "input[type='search']",
    "input[aria-label*='搜索']",
    "input",
  ]);
  if (!input) {
    throw new Error("未找到小红书搜索输入框，已停止直接 URL 搜索访问。");
  }
  await humanMouseClickLocator(page, input);
  await input.fill("").catch(() => {});
  await humanWait(page, [250, 900]);
  if (input.pressSequentially) {
    await input.pressSequentially(keyword, { delay: randomInt(60, 180) });
  } else {
    await input.fill(keyword);
  }
  await humanWait(page, [300, 1200]);
  await input.press("Enter").catch(async () => {
    if (page.keyboard?.press) {
      await page.keyboard.press("Enter");
    }
  });
  events.write("info", "xiaohongshu", "search_submitted", "已通过页面搜索框提交关键词", {
    run_id: request.run_id,
    platform: request.platform,
    keyword,
    access_policy: request.access_policy,
  });
}

export async function verifySearchResultsReady(page, request) {
  const keyword = String(request.keyword || "").trim();
  if (!keyword) {
    return { ok: true, reason: "" };
  }

  const timeoutMs = Math.max(0, Number(request.search_confirmation_timeout_ms ?? 15_000));
  const deadline = Date.now() + timeoutMs;
  let lastState = {
    url: safePageUrl(page),
    title: await safePageTitle(page),
    searchLinkCount: 0,
    bodyText: "",
  };

  while (true) {
    lastState = {
      url: safePageUrl(page),
      title: await safePageTitle(page),
      searchLinkCount: await safeLocatorCount(page.locator("a[href*='/search_result/']")),
      bodyText: await visibleTextForSelectors(page, ["body"], 2000),
    };
    if (isConfirmedSearchResultsPage(lastState, keyword)) {
      return { ok: true, reason: "", ...lastState };
    }
    const remaining = deadline - Date.now();
    if (remaining <= 0 || !page.waitForTimeout) {
      break;
    }
    await page.waitForTimeout(Math.min(500, remaining));
  }

  return {
    ok: false,
    reason: "search_not_confirmed",
    detail: `已输入关键词“${keyword}”，但页面没有进入该关键词的搜索结果。请在浏览器中确认搜索完成后再继续采集。`,
    ...lastState,
  };
}

export async function searchNotConfirmedFailureRecords({ page, request, assetsPath, searchReady }) {
  const reason = "search_not_confirmed";
  const screenshotPath = join(assetsPath, `failure-${reason}.png`);
  const snapshotPath = join(assetsPath, `failure-${reason}-snapshot.json`);
  let savedScreenshotPath = "";
  let screenshotError = "";
  try {
    await page.screenshot({ path: screenshotPath, fullPage: true });
    savedScreenshotPath = screenshotPath;
  } catch (error) {
    screenshotError = error.message || String(error);
  }
  const keyword = request.keyword || "";
  const payload = {
    run_id: request.run_id,
    platform: request.platform,
    profile: request.profile || "",
    keyword,
    code: "SEARCH_NOT_CONFIRMED",
    reason,
    detail: searchReady?.detail || "",
    url: searchReady?.url || safePageUrl(page),
    title: searchReady?.title || (await safePageTitle(page)),
    search_link_count: Number(searchReady?.searchLinkCount || 0),
    body_text: searchReady?.bodyText || (await visibleTextForSelectors(page, ["body"], 8000).catch(() => "")),
    screenshot: savedScreenshotPath,
    screenshot_error: screenshotError,
    matched_signals: searchNotConfirmedSignals(searchReady, keyword),
    captured_at: new Date().toISOString(),
  };
  await writeFile(snapshotPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  const records = [
    evidenceRecord({
      request,
      evidenceId: `${request.run_id}-failure-${reason}-snapshot`,
      scope: "failure_snapshot",
      path: snapshotPath,
      payload,
    }),
  ];
  if (savedScreenshotPath) {
    records.push(
      evidenceRecord({
        request,
        evidenceId: `${request.run_id}-failure-${reason}-screenshot`,
        scope: "failure_screenshot",
        path: savedScreenshotPath,
        payload: {
          reason,
          code: "SEARCH_NOT_CONFIRMED",
          detail: payload.detail,
          url: payload.url,
          title: payload.title,
          screenshot_error: screenshotError,
        },
      }),
    );
  }
  return records;
}

function searchNotConfirmedSignals(searchReady, keyword) {
  return [
    {
      reason: "search_not_confirmed",
      signal: "expected_keyword_not_confirmed",
      source: "search_confirmation",
      expected_keyword: keyword || "",
      observed_url: searchReady?.url || "",
      observed_title: searchReady?.title || "",
      search_link_count: Number(searchReady?.searchLinkCount || 0),
    },
  ];
}

export function createSearchNotConfirmedError(searchReady, evidence) {
  const error = new Error(
    searchReady?.detail || "已输入关键词，但页面没有进入该关键词的搜索结果。",
  );
  error.code = "SEARCH_NOT_CONFIRMED";
  error.partialRecords = Array.isArray(evidence) ? evidence : evidence ? [evidence] : [];
  const failureSnapshot = error.partialRecords.find((record) => record?.scope === "failure_snapshot");
  error.failurePayload = {
    reason: "search_not_confirmed",
    url: searchReady?.url || "",
    title: searchReady?.title || "",
    search_link_count: Number(searchReady?.searchLinkCount || 0),
    matched_signals: failureSnapshot?.payload?.matched_signals || searchNotConfirmedSignals(searchReady, ""),
    screenshot_error: failureSnapshot?.payload?.screenshot_error || "",
  };
  return error;
}

function isConfirmedSearchResultsPage(state, keyword) {
  const url = String(state.url || "");
  const title = String(state.title || "");
  const bodyText = String(state.bodyText || "");
  const searchLinkCount = Number(state.searchLinkCount || 0);
  const urlHasSearchKeyword = url.includes("/search_result") && urlKeywordMatches(url, keyword);
  const visibleKeywordSearch = searchLinkCount > 0 && (title.includes(keyword) || bodyText.includes(keyword));
  return urlHasSearchKeyword || visibleKeywordSearch;
}

function urlKeywordMatches(rawUrl, keyword) {
  try {
    const parsed = new URL(rawUrl);
    return parsed.searchParams.get("keyword") === keyword;
  } catch {
    const encodedKeyword = encodeURIComponent(keyword);
    return rawUrl.includes(`keyword=${encodedKeyword}`) || rawUrl.includes(`keyword=${keyword}`);
  }
}

export async function firstUsableLocator(pageOrLocator, selectors, { minimumSize = 8 } = {}) {
  for (const selector of selectors) {
    try {
      const collection = pageOrLocator.locator(selector);
      const count = await safeLocatorCount(collection);
      for (let index = 0; index < Math.min(count, 20); index += 1) {
        const locator = collection.nth(index);
        if (await locatorIsAriaHidden(locator)) {
          continue;
        }
        const box = await locator.boundingBox().catch(() => null);
        if (box && box.width >= minimumSize && box.height >= minimumSize) {
          return locator;
        }
      }
    } catch {
      // Try the next selector.
    }
  }
  return null;
}

async function locatorIsAriaHidden(locator) {
  try {
    return String((await locator.getAttribute?.("aria-hidden")) || "").toLowerCase() === "true";
  } catch {
    return false;
  }
}

async function safeLocatorCount(locator) {
  try {
    return locator?.count ? await locator.count() : 0;
  } catch {
    return 0;
  }
}

async function safeLocatorText(locator, limit = 4000) {
  try {
    const text = locator?.innerText ? await locator.innerText({ timeout: 1000 }) : "";
    return normalizeWhitespace(text).slice(0, limit);
  } catch {
    try {
      const text = locator?.textContent ? await locator.textContent({ timeout: 1000 }) : "";
      return normalizeWhitespace(text).slice(0, limit);
    } catch {
      return "";
    }
  }
}

async function safeLocatorAttribute(locator, name) {
  try {
    return normalizeWhitespace((await locator.getAttribute(name, { timeout: 1000 })) || "");
  } catch {
    return "";
  }
}

async function firstVisibleText(root, selectors, limit = 1000) {
  for (const selector of selectors) {
    try {
      const collection = root.locator(selector);
      const count = await safeLocatorCount(collection);
      for (let index = 0; index < Math.min(count, 10); index += 1) {
        const locator = collection.nth(index);
        const box = await locator.boundingBox().catch(() => null);
        if (!box || box.width < 1 || box.height < 1) {
          continue;
        }
        const text = await safeLocatorText(locator, limit);
        if (text) {
          return text;
        }
      }
    } catch {
      // Try the next selector.
    }
  }
  return "";
}

async function visibleTextForSelectors(page, selectors, limit = 8000, { minimumSize = 1 } = {}) {
  const chunks = [];
  for (const selector of selectors) {
    try {
      const collection = page.locator(selector);
      const count = await safeLocatorCount(collection);
      for (let index = 0; index < Math.min(count, 12); index += 1) {
        const locator = collection.nth(index);
        const box = await locator.boundingBox().catch(() => null);
        if (!box || box.width < minimumSize || box.height < minimumSize) {
          continue;
        }
        const text = await safeLocatorText(locator, limit);
        if (text) {
          chunks.push(text);
        }
      }
    } catch {
      // Try the next selector.
    }
  }
  return chunks.join("\n").slice(0, limit);
}

async function safePageTitle(page) {
  try {
    return await page.title();
  } catch {
    return "";
  }
}

async function detailRootLocator(page) {
  return (
    (await firstUsableLocator(page, ["#noteContainer", ".note-detail-mask .note-container", ".note-container", ".note-detail", "main"], {
      minimumSize: 120,
    })) || page.locator("body")
  );
}

async function extractInteractionMetrics(root) {
  const selectors = [
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
  ];
  const collection = root.locator(selectors.join(","));
  const count = await safeLocatorCount(collection);
  const metrics = [];
  const seen = new Set();
  for (let index = 0; index < Math.min(count, 80); index += 1) {
    const locator = collection.nth(index);
    const box = await locator.boundingBox().catch(() => null);
    if (!box || box.width < 1 || box.height < 1) {
      continue;
    }
    const text = await safeLocatorText(locator, 500);
    const label = (await safeLocatorAttribute(locator, "aria-label")) || (await safeLocatorAttribute(locator, "title"));
    const className = await safeLocatorAttribute(locator, "class");
    const role = normalizeMetricRole(`${className} ${label} ${text}`).replace(/s$/, "");
    if (!role) {
      continue;
    }
    const key = `${role}\n${text}\n${label}\n${className}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    metrics.push({ role, text, label, className });
  }
  return metrics;
}

async function extractVisibleComments(root, maxComments) {
  const limit = Math.max(0, Number(maxComments || 0));
  if (limit <= 0) {
    return [];
  }
  const collection = root.locator(COMMENT_ITEM_SELECTOR);
  const count = await safeLocatorCount(collection);
  const comments = [];
  for (let index = 0; index < count && comments.length < limit; index += 1) {
    const locator = collection.nth(index);
    const box = await locator.boundingBox().catch(() => null);
    if (!box || box.width < 80 || box.height < 12) {
      continue;
    }
    const rawText = await safeLocatorText(locator, 2000);
    if (rawText.length < 2) {
      continue;
    }
    const author = await firstVisibleText(locator, ["[class*='author']", "[class*='name']", "a[href*='/user/profile']"], 160);
    const content =
      (await firstVisibleText(locator, ["[class*='content']", "[class*='text']", "p"], 1200)) ||
      rawText
        .split(/\r?\n/)
        .map((line) => line.trim())
        .find((line) => line && line !== author) ||
      "";
    const likeText = await firstVisibleText(locator, ["[class*='like']", "[class*='count']"], 160);
    const replyTo = await firstVisibleText(locator, ["[class*='reply-to']", "[class*='replyTarget']", "[class*='target']"], 160);
    const className = await safeLocatorAttribute(locator, "class");
    comments.push({
      author,
      content,
      likeText,
      rawText,
      commentType: replyTo || /reply/i.test(className) || /回复/.test(className) ? "reply" : "comment",
      replyTo,
    });
  }
  return comments;
}

export async function prepareVisibleCommentsForExtraction(page, root, request = {}, maxComments = 0) {
  const target = Math.max(0, Number(maxComments || 0));
  if (target <= 0) {
    return { scrolls: 0, replyExpansions: 0, visibleComments: 0 };
  }

  const pace = request.pace || DEFAULT_PACE;
  let visibleComments = await countVisibleCommentNodes(root);
  let replyExpansions = 0;
  const replyLimit = optionalPositiveLimit(pace.max_reply_expansions_per_post);
  const maxScrolls = optionalPositiveLimit(pace.max_comment_scrolls_per_post);
  let scrolls = 0;
  let stagnantPasses = 0;

  while (visibleComments < target && scrolls < maxScrolls) {
    const beforeCount = visibleComments;
    if (replyExpansions < replyLimit) {
      replyExpansions += await expandVisibleCommentReplies(page, 1, pace);
      visibleComments = await countVisibleCommentNodes(root);
      if (visibleComments >= target) {
        break;
      }
    }

    await scrollCommentArea(page, root, request);
    scrolls += 1;
    await humanWait(page, secondsRangeToMs(pace.comment_scroll_delay_range_seconds || DEFAULT_PACE.comment_scroll_delay_range_seconds));

    visibleComments = await countVisibleCommentNodes(root);
    stagnantPasses = visibleComments > beforeCount ? 0 : stagnantPasses + 1;
    if (stagnantPasses >= 3) {
      break;
    }
  }

  return { scrolls, replyExpansions, visibleComments };
}

function optionalPositiveLimit(value) {
  const numeric = Number(value ?? 0);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : Number.POSITIVE_INFINITY;
}

async function countVisibleCommentNodes(root) {
  try {
    return await safeLocatorCount(root.locator(COMMENT_ITEM_SELECTOR));
  } catch {
    return 0;
  }
}

async function scrollCommentArea(page, root, request = {}) {
  const pace = request.pace || DEFAULT_PACE;
  const viewport = page.viewportSize?.() ?? { width: 1366, height: 900 };
  const ratio = randomFloatFromRange(
    pace.comment_scroll_distance_viewport_range || DEFAULT_PACE.comment_scroll_distance_viewport_range,
  );
  const deltaY = Math.max(120, Math.round(viewport.height * ratio));
  const target = await firstUsableLocator(
    root,
    ["[class*='comments']", "[class*='comment-list']", "[class*='comment']", COMMENT_ITEM_SELECTOR],
    { minimumSize: 80 },
  );
  if (target) {
    const box = await target.boundingBox().catch(() => null);
    if (box) {
      const x = box.x + Math.min(Math.max(box.width * 0.55, 24), Math.max(24, box.width - 18));
      const y = box.y + Math.min(Math.max(box.height * 0.55, 24), Math.max(24, box.height - 18));
      if (x >= 0 && y >= 0) {
        await page.mouse.move(x, y, { steps: 6 }).catch(() => {});
      }
    }
  }
  await page.mouse.wheel(0, deltaY);
  return deltaY;
}

async function scrollDetailPage(page, request = {}) {
  const viewport = page.viewportSize?.() ?? { width: 1366, height: 900 };
  const ratio = randomFloatFromRange(
    request.pace?.detail_scroll_distance_viewport_range || DEFAULT_PACE.detail_scroll_distance_viewport_range,
  );
  const deltaY = Math.max(120, Math.round(viewport.height * ratio));
  await page.mouse.wheel(0, deltaY);
  await humanWait(page, [900, 1800]);
}

export function createLoadedImageStore({ maxBytes = 15 * 1024 * 1024 } = {}) {
  const attachedPages = new WeakSet();
  const byExactUrl = new Map();
  const byCanonicalUrl = new Map();

  const storeEntry = (url, response) => {
    const cleanUrl = normalizeWhitespace(url);
    if (!cleanUrl || byExactUrl.has(cleanUrl)) {
      return;
    }
    const headers = response.headers?.() || {};
    const mimeType = imageMimeTypeFromHeaders(headers);
    if (!mimeType) {
      return;
    }
    const entryPromise = Promise.resolve()
      .then(() => response.body())
      .then((body) => {
        const buffer = Buffer.from(body || []);
        if (!buffer.length || buffer.length > maxBytes) {
          return null;
        }
        return { url: cleanUrl, body: buffer, mimeType };
      })
      .catch(() => null);
    byExactUrl.set(cleanUrl, entryPromise);
    const canonicalKey = canonicalMediaUrlKey(cleanUrl);
    if (canonicalKey && !byCanonicalUrl.has(canonicalKey)) {
      byCanonicalUrl.set(canonicalKey, entryPromise);
    }
  };

  return {
    attachPage(page) {
      if (!page || attachedPages.has(page) || typeof page.on !== "function") {
        return;
      }
      attachedPages.add(page);
      page.on("response", (response) => {
        try {
          storeEntry(response.url?.() || "", response);
        } catch {
          // Passive capture must never interfere with browser collection.
        }
      });
    },
    async findForLocator(locator) {
      const candidates = await visibleImageUrlCandidates(locator);
      for (const candidate of candidates) {
        const entry =
          byExactUrl.get(candidate) ||
          byCanonicalUrl.get(canonicalMediaUrlKey(candidate));
        if (!entry) {
          continue;
        }
        const resolved = await entry;
        if (resolved) {
          return resolved;
        }
      }
      return null;
    },
  };
}

function imageMimeTypeFromHeaders(headers) {
  const contentType = String(headers["content-type"] || headers["Content-Type"] || "").split(";")[0].trim().toLowerCase();
  return contentType.startsWith("image/") ? contentType : "";
}

async function visibleImageUrlCandidates(locator) {
  const values = [];
  for (const name of ["src", "data-src", "data-original", "data-xhs-img"]) {
    const value = await safeLocatorAttribute(locator, name);
    if (value) {
      values.push(value);
    }
  }
  const srcset = await safeLocatorAttribute(locator, "srcset");
  values.push(...parseSrcsetUrls(srcset));
  return uniqueMediaUrls(values).filter((url) => !url.startsWith("data:"));
}

function parseSrcsetUrls(value) {
  return String(value || "")
    .split(",")
    .map((part) => normalizeWhitespace(part).split(/\s+/)[0])
    .filter(Boolean);
}

function extensionForMimeType(mimeType) {
  return {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/avif": "avif",
  }[String(mimeType || "").toLowerCase()] || "img";
}

export async function captureVisibleMediaAssets(options) {
  if (options.request?.media_policy === "browser_loaded_image") {
    const records = await captureBrowserLoadedImageAssets(options);
    if (records.length > 0) {
      return records;
    }
    return captureVisibleMediaScreenshots({
      ...options,
      request: { ...options.request, media_policy: "visible_screenshot" },
    });
  }
  return captureVisibleMediaScreenshots(options);
}

async function captureBrowserLoadedImageAssets({ page, request, assetsPath, stem, postId, loadedImages }) {
  if (!loadedImages) {
    return [];
  }
  const root = await detailRootLocator(page);
  const images = root.locator("img");
  const count = await safeLocatorCount(images);
  const limit = Math.min(count, Number(request.pace?.max_screenshot_media_per_post || DEFAULT_PACE.max_screenshot_media_per_post));
  const records = [];
  const seenAssetKeys = new Set();
  for (let index = 0; index < limit; index += 1) {
    const image = images.nth(index);
    const box = await image.boundingBox().catch(() => null);
    if (!box || box.width < 120 || box.height < 90) {
      continue;
    }
    const loaded = await loadedImages.findForLocator(image);
    if (!loaded) {
      continue;
    }
    const sha256 = createHash("sha256").update(loaded.body).digest("hex");
    const assetKey = canonicalMediaUrlKey(loaded.url) || sha256;
    if (seenAssetKeys.has(assetKey)) {
      continue;
    }
    seenAssetKeys.add(assetKey);
    const assetId = `${stem}-loaded-image-${records.length + 1}`;
    const extension = extensionForMimeType(loaded.mimeType);
    const path = join(assetsPath, `${assetId}.${extension}`);
    await writeFile(path, loaded.body);
    records.push({
      type: "media_asset",
      run_id: request.run_id,
      platform: request.platform,
      asset_id: assetId,
      post_id: postId,
      media_type: "image",
      path,
      mime_type: loaded.mimeType,
      sha256,
      url: loaded.url,
      source: "browser_loaded_image",
    });
  }
  return records;
}

export async function captureVisibleMediaScreenshots({ page, request, assetsPath, stem, postId, events }) {
  if (request.media_policy !== "visible_screenshot") {
    return [];
  }
  const root = await detailRootLocator(page);
  const images = root.locator("img");
  const count = await safeLocatorCount(images);
  const limit = Math.min(count, Number(request.pace?.max_screenshot_media_per_post || DEFAULT_PACE.max_screenshot_media_per_post));
  const records = [];
  for (let index = 0; index < limit; index += 1) {
    const image = images.nth(index);
    const box = await image.boundingBox().catch(() => null);
    if (!box || box.width < 120 || box.height < 90) {
      continue;
    }
    const assetId = `${stem}-visible-image-${records.length + 1}`;
    const path = join(assetsPath, `${assetId}.png`);
    try {
      await image.screenshot({ path, timeout: 5000 });
      const body = await readFile(path);
      records.push({
        type: "media_asset",
        run_id: request.run_id,
        platform: request.platform,
        asset_id: assetId,
        post_id: postId,
        media_type: "image",
        path,
        mime_type: "image/png",
        sha256: createHash("sha256").update(body).digest("hex"),
        url: "",
        source: "visible_screenshot",
      });
    } catch (error) {
      events.write("warning", "xiaohongshu", "media_screenshot_failed", "可见图片局部截图失败，已保留详情页截图", {
        run_id: request.run_id,
        platform: request.platform,
        post_id: postId,
        asset_id: assetId,
        error: error.message,
      });
    }
  }
  return records;
}

export async function restBetweenCards(page, request, events, paceState) {
  const detailDelay = await humanWait(page, secondsRangeToMs(request.pace.detail_delay_range_seconds));
  events.write("info", "xiaohongshu", "collector_pace_wait", "详情之间已按人类节奏等待", {
    run_id: request.run_id,
    platform: request.platform,
    wait_ms: detailDelay,
    reason: "detail_interval",
  });
  paceState.attemptedSinceBatchRest += 1;
  if (paceState.attemptedSinceBatchRest < paceState.nextBatchRestAfter) {
    return;
  }
  const restDelay = await humanWait(page, secondsRangeToMs(request.pace.batch_rest_seconds_range));
  events.write("info", "xiaohongshu", "collector_batch_rest", "小批量采集后已大停等待", {
    run_id: request.run_id,
    platform: request.platform,
    wait_ms: restDelay,
    after_cards: paceState.attemptedSinceBatchRest,
  });
  paceState.attemptedSinceBatchRest = 0;
  paceState.nextBatchRestAfter = randomIntFromRange(request.pace.batch_rest_after_cards_range);
}

function checkpointPathForAssets(assetsPath) {
  return join(dirname(assetsPath), "checkpoint.json");
}

async function readCheckpoint(path, request) {
  if (request.checkpoint_enabled === false) {
    return {};
  }
  try {
    const payload = JSON.parse(await readFile(path, "utf8"));
    if (payload?.run_id !== request.run_id || payload?.platform !== request.platform) {
      return {};
    }
    return payload;
  } catch {
    return {};
  }
}

async function writeCheckpoint(
  path,
  request,
  { collectedIds, skippedIds, failedIds, pending, paceState, waterfallStats = {} },
) {
  if (request.checkpoint_enabled === false) {
    return;
  }
  const payload = {
    run_id: request.run_id,
    platform: request.platform,
    profile: request.profile,
    keyword: request.keyword,
    updated_at: new Date().toISOString(),
    collected_ids: Array.from(collectedIds),
    skipped_ids: Array.from(skippedIds),
    failed_ids: Array.from(failedIds),
    pending_posts: pending.slice(0, Math.max(0, Number(request.max_posts || 0))),
    attempted_since_batch_rest: paceState.attemptedSinceBatchRest,
    next_batch_rest_after: paceState.nextBatchRestAfter,
    waterfall_consecutive_missing_targets: Number(waterfallStats.consecutiveMissingTargets || 0),
    waterfall_missing_skipped: Number(waterfallStats.missingSkipped || 0),
    waterfall_missing_threshold_triggers: Number(waterfallStats.thresholdTriggers || 0),
    waterfall_missing_recovery_threshold: Number(
      request.pace?.waterfall_missing_recovery_threshold || DEFAULT_PACE.waterfall_missing_recovery_threshold,
    ),
  };
  await writeFile(path, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
}

export async function detectManualAction(page) {
  const state = {
    url: safePageUrl(page),
    title: await safePageTitle(page),
    text: await visibleTextForSelectors(page, ["body"], 8000),
    blockingText: await visibleTextForSelectors(
      page,
      ["[role='dialog']", "[class*='login']", "[class*='captcha']", "[class*='verify']", "[class*='modal']"],
      4000,
      { minimumSize: 80 },
    ),
    hasDetailContainer: await hasDetailContainer(page),
  };
  if (state.hasDetailContainer && !state.blockingText) {
    return null;
  }
  const manualText = state.hasDetailContainer ? state.blockingText : state.text;
  const sources = [
    { source: "url", text: state.url },
    { source: "title", text: state.title },
    { source: state.hasDetailContainer ? "blocking_text" : "body", text: manualText },
  ];
  const haystack = sources.map((item) => item.text).join("\n").toLowerCase();
  const accountRiskSignals = matchedManualSignals(
    "account_risk_warning",
    ["账号违规预警", "技术手段模拟真人行为", "第三方工具或自动浏览脚本", "自动浏览脚本"],
    sources,
  );
  if (isAccountRiskWarningText(haystack)) {
    return {
      reason: "account_risk_warning",
      matched_signals: accountRiskSignals.length > 0
        ? accountRiskSignals
        : matchedManualSignals("account_risk_warning", ["第三方工具", "自动浏览", "使用脚本"], sources),
      detail: `检测到 ${manualReasonLabel("account_risk_warning")}，需要人工处理后再继续。`,
    };
  }
  const checks = [
    ["app_scan_required", ["当前笔记暂时无法浏览", "打开小红书app扫码", "扫码查看", "请打开小红书app"]],
    ["login_required", ["请登录", "登录后", "登录/注册", "login required", "signin required", "验证码", "手机号"]],
    ["platform_risk_circuit_breaker", ["risk", "安全验证", "环境异常", "访问异常", "操作频繁", "滑块", "验证", "疑似异常", "请稍后再试"]],
    ["verification_required", ["captcha", "verify", "verification", "人机验证", "身份验证"]],
  ];

  for (const [reason, needles] of checks) {
    const matchedSignals = matchedManualSignals(reason, needles, sources);
    if (matchedSignals.length > 0) {
      return {
        reason,
        matched_signals: matchedSignals,
        detail: `检测到 ${manualReasonLabel(reason)}，需要人工处理后再继续。`,
      };
    }
  }
  return null;
}

function matchedManualSignals(reason, needles, sources) {
  const matches = [];
  for (const needle of needles) {
    const normalizedNeedle = String(needle || "").toLowerCase();
    if (!normalizedNeedle) {
      continue;
    }
    const source = sources.find((item) => String(item.text || "").toLowerCase().includes(normalizedNeedle));
    if (source) {
      matches.push({
        reason,
        signal: needle,
        source: source.source,
      });
    }
  }
  return matches;
}

function isAccountRiskWarningText(haystack) {
  const directSignals = ["账号违规预警", "技术手段模拟真人行为", "第三方工具或自动浏览脚本", "自动浏览脚本"];
  if (directSignals.some((signal) => haystack.includes(signal.toLowerCase()))) {
    return true;
  }
  return haystack.includes("第三方工具") && (haystack.includes("自动浏览") || haystack.includes("使用脚本"));
}

export async function manualActionRecords({
  page,
  request,
  assetsPath,
  events,
  reason,
  detail,
  matchedSignals = [],
  existingEvidence = [],
}) {
  const screenshotPath = join(assetsPath, `manual-action-${reason}.png`);
  const snapshotPath = join(assetsPath, `manual-action-${reason}-snapshot.json`);
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
  const snapshot = await buildManualActionSnapshot({
    page,
    request,
    reason,
    detail,
    url: targetUrl,
    screenshot: savedScreenshotPath,
    screenshotError,
    matchedSignals,
  });
  await writeFile(snapshotPath, `${JSON.stringify(snapshot, null, 2)}\n`, "utf8");
  events.write("warning", "xiaohongshu", "manual_action_required", detail, {
    run_id: request.run_id,
    platform: request.platform,
    reason,
    screenshot: savedScreenshotPath,
    snapshot: snapshotPath,
    evidence_chain_path: snapshotPath,
    url: targetUrl,
    screenshot_error: screenshotError,
    matched_signals: snapshot.matched_signals,
  });
  const snapshotEvidence = [
    evidenceRecord({
      request,
      evidenceId: `${request.run_id}-manual-action-${reason}-snapshot`,
      scope: "manual_action_snapshot",
      path: snapshotPath,
      payload: {
        reason,
        detail,
        url: targetUrl,
        screenshot: savedScreenshotPath,
        screenshot_error: screenshotError,
        matched_signals: snapshot.matched_signals,
      },
    }),
  ];
  const screenshotEvidence = savedScreenshotPath
    ? [
        evidenceRecord({
          request,
          evidenceId: `${request.run_id}-manual-action-${reason}`,
          scope: "manual_action_screenshot",
          path: savedScreenshotPath,
          payload: { reason, detail, url: targetUrl },
        }),
      ]
    : [];
  return [...screenshotEvidence, ...snapshotEvidence, ...existingEvidence];
}

async function buildManualActionSnapshot({ page, request, reason, detail, url, screenshot, screenshotError, matchedSignals }) {
  return {
    run_id: request.run_id,
    platform: request.platform,
    profile: request.profile || "",
    keyword: request.keyword || "",
    reason,
    detail,
    url,
    title: await safePageTitle(page),
    body_text: await visibleTextForSelectors(page, ["body"], 8000).catch(() => ""),
    blocking_text: await visibleTextForSelectors(
      page,
      ["[role='dialog']", "[class*='login']", "[class*='captcha']", "[class*='verify']", "[class*='modal']"],
      4000,
      { minimumSize: 80 },
    ).catch(() => ""),
    screenshot,
    screenshot_error: screenshotError,
    matched_signals: Array.isArray(matchedSignals) ? matchedSignals : [],
    captured_at: new Date().toISOString(),
  };
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
    await scrollSearchResults(page);
  }
}

async function extractVisibleSnapshot(page, maxCandidates) {
  const selectors = [
    ".note-item",
    ".feeds-page .note-card",
    "section",
    "article",
    "a[href*='/explore/']",
    "a[href*='/search_result/']",
  ];
  const candidates = page.locator(selectors.join(","));
  const count = await safeLocatorCount(candidates);
  const posts = [];
  const limit = Math.min(count, Math.max(1, Number(maxCandidates || 20)) * 2);

  for (let cardIndex = 0; cardIndex < limit && posts.length < maxCandidates; cardIndex += 1) {
    const element = candidates.nth(cardIndex);
    const box = await element.boundingBox().catch(() => null);
    if (!box || box.width < 80 || box.height < 80) {
      continue;
    }
    const text = await safeLocatorText(element);
    const anchor = element.locator("a[href*='/explore/'], a[href*='/search_result/'], a[href]").first();
    const href = await safeLocatorAttribute(anchor, "href");
    if (!href && text.length < 8) {
      continue;
    }
    const title = await firstVisibleText(element, ["[class*='title']", "[class*='desc']", "h1", "h2", "h3"]);
    const author = await firstVisibleText(element, ["[class*='author']", "[class*='user']", "[class*='name']"]);
    const likesText = await firstVisibleText(element, ["[class*='like']", "[class*='count']"]);

    posts.push({
      href,
      title,
      text,
      author,
      image: "",
      likesText,
      cardIndex,
    });
  }

  return {
    url: safePageUrl(page),
    title: await safePageTitle(page),
    collected_at: new Date().toISOString(),
    posts,
  };
}

function cssEscape(value) {
  return String(value).replace(/["\\]/g, "\\$&");
}

export async function extractDetailSnapshot(page, maxComments) {
  const detailRoot = await detailRootLocator(page);
  const title = await firstVisibleText(detailRoot, ["#detail-title", "[class*='title']", "h1"]);
  const body = await firstVisibleText(detailRoot, ["#detail-desc", "[class*='desc']", ".note-content", "[class*='content']"]);
  const author = await firstVisibleText(detailRoot, [
    "a[href*='/user/profile']",
    "[class*='author'] [class*='name']",
    "[class*='user'] [class*='name']",
    "[class*='nickname']",
  ]);
  const interactionText = await firstVisibleText(detailRoot, [
    "[class*='interact']",
    "[class*='engage']",
    "[class*='like']",
    "[class*='bottom-bar']",
  ]);
  const interactionMetrics = await extractInteractionMetrics(detailRoot);
  const comments = await extractVisibleComments(detailRoot, maxComments);

  return {
    url: safePageUrl(page),
    title,
    body,
    author,
    interactionText,
    interactionMetrics,
    images: [],
    comments,
  };
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
    account_risk_warning: "账号违规预警",
    platform_risk_circuit_breaker: "平台风险熔断",
    login_required: "登录或账号确认",
    risk_control: "平台风控或安全验证",
    verification_required: "验证码或人机验证",
    app_scan_required: "手机扫码查看",
    no_posts_detected: "搜索结果识别异常",
  }[reason] || "人工处理点";
}
