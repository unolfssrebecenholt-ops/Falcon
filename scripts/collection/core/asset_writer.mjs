import { writeFile } from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";

const EXTENSIONS = new Map([
  ["image/jpeg", ".jpg"],
  ["image/jpg", ".jpg"],
  ["image/png", ".png"],
  ["image/webp", ".webp"],
  ["image/gif", ".gif"],
  ["image/avif", ".avif"],
]);

export function uuidAssetName(contentType = "image/jpeg") {
  const cleanType = String(contentType).split(";")[0].trim().toLowerCase();
  const extension = EXTENSIONS.get(cleanType) ?? ".jpg";
  return `${randomUUID().replace(/-/g, "")}${extension}`;
}

export async function downloadAsset(url, assetsDir, fetchImpl = globalThis.fetch) {
  if (!url) {
    return null;
  }
  if (typeof fetchImpl !== "function") {
    throw new Error("No fetch implementation is available for asset download.");
  }

  const response = await fetchImpl(url);
  if (!response.ok) {
    throw new Error(`Asset download failed: HTTP ${response.status}`);
  }

  const contentType = response.headers.get("content-type") ?? "image/jpeg";
  const assetName = uuidAssetName(contentType);
  const bytes = Buffer.from(await response.arrayBuffer());
  await writeFile(path.join(assetsDir, assetName), bytes);
  return assetName;
}

export async function downloadAssets(urls, assetsDir, fetchImpl = globalThis.fetch) {
  const names = [];
  for (const url of urls ?? []) {
    const name = await downloadAsset(url, assetsDir, fetchImpl);
    if (name) {
      names.push(name);
    }
  }
  return names;
}
