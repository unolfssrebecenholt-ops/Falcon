import { mkdir } from "node:fs/promises";
import path from "node:path";
import { safeFilePart } from "./text_cleaner.mjs";

export const PLATFORM_SLUGS = new Map([
  ["小红书", "xiaohongshu"],
  ["xiaohongshu", "xiaohongshu"],
  ["xhs", "xiaohongshu"],
  ["抖音", "douyin"],
  ["douyin", "douyin"],
  ["闲鱼", "xianyu"],
  ["xianyu", "xianyu"],
  ["微博", "weibo"],
  ["weibo", "weibo"],
]);

export function platformSlug(platform) {
  const slug = PLATFORM_SLUGS.get(String(platform ?? "").trim());
  if (!slug) {
    throw new Error(`Unsupported collection platform: ${platform}`);
  }
  return slug;
}

export function timestampForFolder(date = new Date()) {
  const pad = (value) => String(value).padStart(2, "0");
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
    pad(date.getHours()),
    pad(date.getMinutes()),
  ].join("");
}

export async function createKeywordPaths({
  outputRoot = "datas",
  platform,
  keyword,
  runTimestamp = timestampForFolder(),
} = {}) {
  const slug = platformSlug(platform);
  const keywordPart = safeFilePart(keyword);
  const folderName = `${keywordPart}_${runTimestamp}`;
  const keywordDir = path.join(outputRoot, slug, folderName);
  const assetsDir = path.join(keywordDir, "assets");
  await mkdir(assetsDir, { recursive: true });

  return {
    platformSlug: slug,
    keyword,
    runTimestamp,
    keywordDir,
    assetsDir,
    csvPath: path.join(keywordDir, `${folderName}.csv`),
    extraPath: path.join(keywordDir, "extra.jsonl"),
    stepsPath: path.join(keywordDir, "collection_steps.md"),
    summaryPath: path.join(outputRoot, slug, `run_summary_${runTimestamp}.json`),
  };
}
