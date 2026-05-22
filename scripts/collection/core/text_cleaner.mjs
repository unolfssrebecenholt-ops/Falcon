export const DEFAULT_PHONE = "17630962337";
export const MASKED_DEFAULT_PHONE = maskPhone(DEFAULT_PHONE);

export function cleanText(value) {
  if (value == null) {
    return "";
  }
  return String(value)
    .replace(/\u00a0/g, " ")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .join("\n")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

export function normalizeCount(value) {
  const text = cleanText(value).toLowerCase();
  if (!text || text === "-" || text === "赞" || text === "收藏" || text === "评论") {
    return "";
  }

  const compact = text.replace(/,/g, "").replace(/\s+/g, "");
  const match = compact.match(/([\d.]+)(万|w|k|千)?/i);
  if (!match) {
    return compact;
  }

  const number = Number.parseFloat(match[1]);
  if (!Number.isFinite(number)) {
    return compact;
  }

  const unit = match[2];
  if (unit === "万" || unit === "w") {
    return String(Math.round(number * 10000));
  }
  if (unit === "k" || unit === "千") {
    return String(Math.round(number * 1000));
  }
  return String(Math.round(number));
}

export function maskPhone(phone) {
  const text = String(phone ?? "");
  if (text.length < 8) {
    return "***";
  }
  return `${text.slice(0, 3)}****${text.slice(-4)}`;
}

export function safeFilePart(value) {
  const cleaned = cleanText(value)
    .replace(/[<>:"/\\|?*\x00-\x1f]/g, "_")
    .replace(/\s+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
  return cleaned || "untitled";
}
