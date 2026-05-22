import { cleanText, normalizeCount } from "../core/text_cleaner.mjs";

export const xiaohongshuProfile = Object.freeze({
  platform: "小红书",
  slug: "xiaohongshu",
  mode: "full",
  startUrl: "https://www.xiaohongshu.com/",
  searchUrl(keyword) {
    return `https://www.xiaohongshu.com/search_result?keyword=${encodeURIComponent(keyword)}&source=web_explore_feed`;
  },
  csvHeader: "platform,title,content,published_at,like_count,collect_count,comment_count,cover_asset_name,asset_names",
  rules: [
    "content cards must be opened by real mouse/touch click",
    "do not use JavaScript click for opening content cards",
    "do not navigate directly to transient detail links",
    "do not save URLs",
    "scroll like a human to load waterfall results",
  ],
  knownPitfalls: [
    "login wall",
    "verification code",
    "waterfall virtual DOM",
    "detail modal",
    "image zoom layer",
    "misaligned interaction counts",
  ],
});

export async function readVisibleCards(tab) {
  return tab.evaluate(() => {
    const candidates = [
      ...document.querySelectorAll("section.note-item, div.note-item, a.cover, a[href*='/search_result/']"),
    ];
    return candidates.map((node, index) => {
      const rect = node.getBoundingClientRect();
      return {
        index,
        text: node.innerText || node.textContent || "",
        visible: rect.width > 0 && rect.height > 0,
        x: Math.round(rect.left + rect.width / 2),
        y: Math.round(rect.top + rect.height / 2),
      };
    }).filter((item) => item.visible);
  });
}

export async function hasDetailModal(tab) {
  return tab.evaluate(() => {
    const selectors = [
      ".note-detail-mask",
      ".note-detail",
      "[class*='note-detail']",
      "[class*='interaction-container']",
      "[role='dialog']",
    ];
    return selectors.some((selector) => document.querySelector(selector));
  });
}

export async function readDetail(tab) {
  return tab.evaluate(() => {
    const textOf = (selectors) => {
      for (const selector of selectors) {
        const node = document.querySelector(selector);
        const text = node?.innerText || node?.textContent;
        if (text && text.trim()) {
          return text.trim();
        }
      }
      return "";
    };

    const title = textOf(["#detail-title", ".title", "[class*='title']"]);
    const content = textOf(["#detail-desc", ".desc", "[class*='desc']", "[class*='content']"]);
    const publishedAt = textOf([".date", "[class*='date']", "[class*='time']"]);
    const interactionText = textOf(["[class*='interact']", "[class*='engage']", "[class*='toolbar']"]);
    const imageUrls = [...document.querySelectorAll("img")]
      .map((img) => img.currentSrc || img.src)
      .filter((src) => src && !src.startsWith("data:"));

    return {
      title,
      content,
      publishedAt,
      interactionText,
      imageUrls: [...new Set(imageUrls)],
    };
  });
}

export function normalizeDetail(detail) {
  const counts = cleanText(detail.interactionText).match(/[\d.,]+(?:万|w|k|千)?/gi) ?? [];
  return {
    platform: "xiaohongshu",
    title: cleanText(detail.title),
    content: cleanText(detail.content),
    published_at: cleanText(detail.publishedAt),
    like_count: normalizeCount(counts[0] ?? ""),
    collect_count: normalizeCount(counts[1] ?? ""),
    comment_count: normalizeCount(counts[2] ?? ""),
    imageUrls: detail.imageUrls ?? [],
  };
}
