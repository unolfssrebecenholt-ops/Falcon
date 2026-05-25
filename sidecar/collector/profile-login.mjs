import { mkdir } from "node:fs/promises";
import { selectUsableBrowserPage } from "./xiaohongshu.mjs";

const LOGIN_URLS = {
  xiaohongshu: "https://www.xiaohongshu.com/",
};

function parseArgs(argv) {
  const values = {};
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (!item.startsWith("--")) continue;
    values[item.slice(2)] = argv[index + 1];
    index += 1;
  }
  return values;
}

function requireArg(args, name) {
  const value = args[name];
  if (!value) {
    throw new Error(`Missing required --${name}`);
  }
  return value;
}

const args = parseArgs(process.argv.slice(2));
const platform = requireArg(args, "platform");
const profile = requireArg(args, "profile");
const profilePath = requireArg(args, "profile-path");
const loginUrl = args.url || LOGIN_URLS[platform];

if (!loginUrl) {
  throw new Error(`Profile login is not supported for platform: ${platform}`);
}

await mkdir(profilePath, { recursive: true });
const { chromium } = await import("playwright");
const context = await chromium.launchPersistentContext(profilePath, {
  headless: false,
  viewport: { width: 1366, height: 900 },
  locale: "zh-CN",
});
const page = await selectUsableBrowserPage(context, { preferredHost: "xiaohongshu.com" });

console.log(`Falcon profile login window opened for ${platform}/${profile}`);
console.log(`Profile path: ${profilePath}`);
await page.goto(loginUrl, { waitUntil: "domcontentloaded", timeout: 30_000 });

await new Promise((resolve) => {
  context.on("close", resolve);
  page.on("close", resolve);
});
await context.close().catch(() => {});
