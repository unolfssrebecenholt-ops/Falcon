import { appendFile, writeFile } from "node:fs/promises";
import { cleanText } from "./text_cleaner.mjs";

export const CSV_HEADER = [
  "platform",
  "title",
  "content",
  "published_at",
  "like_count",
  "collect_count",
  "comment_count",
  "cover_asset_name",
  "asset_names",
];

export function csvEscape(value) {
  const text = cleanText(value);
  if (/[",\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

export function toCsvLine(record) {
  return CSV_HEADER.map((field) => csvEscape(record[field] ?? "")).join(",");
}

export async function writeCsvHeader(csvPath) {
  await writeFile(csvPath, `${CSV_HEADER.join(",")}\n`, "utf8");
}

export async function appendCsvRow(csvPath, record) {
  await appendFile(csvPath, `${toCsvLine(record)}\n`, "utf8");
}
