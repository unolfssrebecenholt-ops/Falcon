import { createHash } from "node:crypto";

const DATE_PATTERN = /(?:^|\s)(今天|昨天|前天|\d{1,2}[-/.]\d{1,2}|\d+\s*(?:秒|分钟|小时|天|周|个月|年)前)(?:\s|$)/;
const METRIC_HINT_PATTERN = /(赞|点赞|喜欢|收藏|评论|like|likes|comment|comments)/i;

export function normalizeWhitespace(value) {
  return String(value ?? "")
    .replace(/\u00a0/g, " ")
    .replace(/[ \t\r\f\v]+/g, " ")
    .replace(/\n{2,}/g, "\n")
    .trim();
}

export function stableFingerprint(value) {
  return createHash("sha256").update(String(value ?? ""), "utf8").digest("hex");
}

export function canonicalPostId(value) {
  const raw = normalizeWhitespace(value);
  if (!raw) {
    return "";
  }
  if (raw.startsWith("xiaohongshu:")) {
    return raw;
  }
  const match = raw.match(/(?:\/(?:explore|search_result)\/)([A-Za-z0-9_-]{6,})/);
  if (match) {
    return `xiaohongshu:${match[1]}`;
  }
  return "";
}

export function canonicalPostUrl(value) {
  const raw = normalizeWhitespace(value);
  const id = canonicalPostId(raw).replace(/^xiaohongshu:/, "");
  if (id) {
    return `https://www.xiaohongshu.com/explore/${id}`;
  }
  return raw;
}

export function parseMetricNumber(value) {
  const text = normalizeWhitespace(value).replace(/,/g, "");
  if (!text) {
    return undefined;
  }
  const match = text.match(/(\d+(?:\.\d+)?)\s*([万萬wW千kK]?)/);
  if (!match) {
    return undefined;
  }
  const base = Number.parseFloat(match[1]);
  if (!Number.isFinite(base)) {
    return undefined;
  }
  const suffix = match[2];
  const multiplier = suffix === "万" || suffix === "萬" || suffix.toLowerCase() === "w"
    ? 10_000
    : suffix === "千" || suffix.toLowerCase() === "k"
      ? 1_000
      : 1;
  return Math.round(base * multiplier);
}

export function cleanAuthor(value) {
  return normalizeWhitespace(value)
    .replace(DATE_PATTERN, " ")
    .replace(/\d+(?:\.\d+)?\s*([万萬wW千kK])?\s*(赞|点赞|喜欢|收藏|评论)?/g, " ")
    .replace(/[·•|｜_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function cleanTitle(value) {
  return normalizeWhitespace(value)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => !looksLikeMetadataLine(line))
    .join(" ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 180);
}

export function normalizeSearchCard(rawCard) {
  const text = normalizeWhitespace(rawCard?.text ?? "");
  const lines = text
    .split(/\r?\n| {2,}/)
    .map((line) => normalizeWhitespace(line))
    .filter(Boolean);
  const metadata = parseCardMetadata(lines);
  const href = normalizeWhitespace(rawCard?.href ?? "");
  const postId = canonicalPostId(href) || `xiaohongshu:${stableFingerprint(href || text).slice(0, 16)}`;
  const rawMetrics = rawCard?.metrics && typeof rawCard.metrics === "object" ? rawCard.metrics : {};
  const likes = firstMetricValue(
    rawMetrics.likes,
    rawMetrics.like_count,
    rawMetrics.likes_text,
    rawCard?.likesText,
    metadata.likesText,
  );
  const comments = firstMetricValue(rawMetrics.comments, rawMetrics.comment_count, rawMetrics.comments_text);
  const collects = firstMetricValue(rawMetrics.collects, rawMetrics.collect_count, rawMetrics.collects_text);
  const metrics = {};
  if (likes !== undefined) metrics.likes = likes;
  if (comments !== undefined) metrics.comments = comments;
  if (collects !== undefined) metrics.collects = collects;

  return {
    postId,
    href,
    url: canonicalPostUrl(href),
    title: cleanTitle(rawCard?.title) || metadata.title,
    text,
    author: cleanAuthor(rawCard?.author) || metadata.author,
    published_at: normalizeWhitespace(rawCard?.published_at) || metadata.publishedAt,
    image: normalizeWhitespace(rawCard?.image),
    metrics,
  };
}

export function normalizeSearchCards(rawCards, limit) {
  const seen = new Set();
  const normalized = [];
  for (const rawCard of rawCards ?? []) {
    const card = rawCard?.postId ? rawCard : normalizeSearchCard(rawCard);
    const key = card.postId || card.url || stableFingerprint(`${card.title}\n${card.author}\n${card.text}`);
    if (seen.has(key)) {
      continue;
    }
    if (!card.url || (!card.title && !card.text)) {
      continue;
    }
    seen.add(key);
    normalized.push(card);
    if (normalized.length >= limit) {
      break;
    }
  }
  return normalized;
}

function parseCardMetadata(lines) {
  let title = "";
  let author = "";
  let publishedAt = "";
  let likesText = "";
  for (const line of lines) {
    if (!title && !looksLikeMetadataLine(line)) {
      title = cleanTitle(line);
      continue;
    }
    if (!publishedAt && DATE_PATTERN.test(` ${line} `)) {
      const dateMatch = line.match(DATE_PATTERN);
      publishedAt = normalizeWhitespace(dateMatch?.[1] ?? line);
    }
    if (!likesText && looksLikeMetricLine(line)) {
      likesText = line;
    }
    if (!author && line !== title && !looksLikeMetricLine(line)) {
      const cleaned = cleanAuthor(line);
      if (cleaned && cleaned !== title) {
        author = cleaned;
      }
    }
  }
  return { title, author, publishedAt, likesText };
}

function looksLikeMetricLine(value) {
  const text = normalizeWhitespace(value);
  if (!text) {
    return false;
  }
  return METRIC_HINT_PATTERN.test(text) || /^\d+(?:\.\d+)?\s*([万萬wW千kK])?$/.test(text);
}

function looksLikeMetadataLine(value) {
  const text = normalizeWhitespace(value);
  if (!text) {
    return true;
  }
  return DATE_PATTERN.test(` ${text} `) || looksLikeMetricLine(text);
}

function firstMetricValue(...values) {
  for (const value of values) {
    if (value === undefined || value === null || value === "") {
      continue;
    }
    if (typeof value === "number" && Number.isFinite(value)) {
      return Math.round(value);
    }
    const parsed = parseMetricNumber(value);
    if (parsed !== undefined) {
      return parsed;
    }
  }
  return undefined;
}
