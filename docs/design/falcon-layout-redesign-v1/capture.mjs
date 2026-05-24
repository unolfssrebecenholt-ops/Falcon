import fs from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { pathToFileURL } from "node:url";

const requireFromCwd = createRequire(path.join(process.cwd(), "package.json"));
const { chromium } = requireFromCwd("playwright");

const root = path.resolve(process.cwd(), "../../docs/design/falcon-layout-redesign-v1");
const screenshotDir = path.join(root, "screenshots");

const pages = [
  ["01 仪表盘", "01-dashboard.html", "desktop-01-dashboard.png", "mobile-01-dashboard.png"],
  ["02 采集首页", "02-collector-home.html", "desktop-02-collector-home.png", "mobile-02-collector-home.png"],
  ["03 任务队列", "03-collector-runs.html", "desktop-03-collector-runs.png", "mobile-03-collector-runs.png"],
  ["04 任务创建", "04-collector-create.html", "desktop-04-collector-create.png", "mobile-04-collector-create.png"],
  ["05 账号管理", "05-collector-accounts.html", "desktop-05-collector-accounts.png", "mobile-05-collector-accounts.png"],
  ["06 环境自检", "06-collector-environment.html", "desktop-06-collector-environment.png", "mobile-06-collector-environment.png"],
  ["07 任务详情", "07-collector-run-detail.html", "desktop-07-collector-run-detail.png", "mobile-07-collector-run-detail.png"],
  ["08 样本预览", "08-collector-sample-preview.html", "desktop-08-collector-sample-preview.png", "mobile-08-collector-sample-preview.png"],
  ["09 关键词池", "09-keywords.html", "desktop-09-keywords.png", "mobile-09-keywords.png"],
  ["10 日报", "10-report.html", "desktop-10-report.png", "mobile-10-report.png"],
  ["11 分析首页", "11-analysis-home.html", "desktop-11-analysis-home.png", "mobile-11-analysis-home.png"],
  ["12 分析样本", "12-analysis-samples.html", "desktop-12-analysis-samples.png", "mobile-12-analysis-samples.png"],
  ["13 人工复核", "13-review.html", "desktop-13-review.png", "mobile-13-review.png"],
  ["14 执行首页", "14-execution-home.html", "desktop-14-execution-home.png", "mobile-14-execution-home.png"],
  ["15 触达任务", "15-tasks.html", "desktop-15-tasks.png", "mobile-15-tasks.png"],
];

async function inspect(page) {
  return page.evaluate(() => {
    const doc = document.documentElement;
    const body = document.body;
    const buttons = Array.from(document.querySelectorAll(".button, button"));
    const clippedButtons = buttons.filter((button) => button.scrollWidth > button.clientWidth + 1);
    const ledgers = Array.from(document.querySelectorAll(".ledger-body")).map((node) => ({
      rows: node.querySelectorAll(".ledger-row").length,
      scrollable: node.scrollHeight > node.clientHeight + 1,
      clientHeight: node.clientHeight,
      scrollHeight: node.scrollHeight,
    }));
    return {
      title: document.title,
      horizontalOverflow: doc.scrollWidth > doc.clientWidth + 1 || body.scrollWidth > body.clientWidth + 1,
      documentWidth: doc.scrollWidth,
      viewportWidth: doc.clientWidth,
      clippedButtons: clippedButtons.map((button) => button.textContent.trim()),
      panels: document.querySelectorAll(".panel").length,
      tables: document.querySelectorAll("table").length,
      ledgers,
    };
  });
}

async function capturePage(browser, label, file, desktopName, mobileName) {
  const url = pathToFileURL(path.join(root, file)).href;
  const result = { label, file, desktop: {}, mobile: {} };

  const desktop = await browser.newPage({ viewport: { width: 1440, height: 1024 }, deviceScaleFactor: 1 });
  await desktop.goto(url, { waitUntil: "networkidle" });
  await desktop.waitForSelector(".prototype-shell");
  result.desktop = await inspect(desktop);
  result.desktop.screenshot = path.join(screenshotDir, desktopName);
  await desktop.screenshot({ path: result.desktop.screenshot, fullPage: true });
  await desktop.close();

  const mobile = await browser.newPage({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 1,
    isMobile: true,
  });
  await mobile.goto(url, { waitUntil: "networkidle" });
  await mobile.waitForSelector(".prototype-shell");
  result.mobile = await inspect(mobile);
  result.mobile.screenshot = path.join(screenshotDir, mobileName);
  await mobile.screenshot({ path: result.mobile.screenshot, fullPage: true });
  await mobile.close();

  return result;
}

await fs.mkdir(screenshotDir, { recursive: true });
const browser = await chromium.launch();
const results = [];
try {
  for (const entry of pages) {
    results.push(await capturePage(browser, ...entry));
  }

  const contact = await browser.newPage({ viewport: { width: 1440, height: 1024 }, deviceScaleFactor: 1 });
  await contact.goto(pathToFileURL(path.join(root, "contact-sheet.html")).href, { waitUntil: "networkidle" });
  await contact.waitForFunction(() => Array.from(document.images).every((image) => image.complete));
  const contactPath = path.join(root, "contact-sheet.png");
  await contact.screenshot({ path: contactPath, fullPage: true });
  await contact.close();

  const index = await browser.newPage({ viewport: { width: 1440, height: 1024 }, deviceScaleFactor: 1 });
  await index.goto(pathToFileURL(path.join(root, "index.html")).href, { waitUntil: "networkidle" });
  await index.waitForFunction(() => Array.from(document.images).every((image) => image.complete));
  const indexPath = path.join(root, "index-preview.png");
  await index.screenshot({ path: indexPath, fullPage: true });
  await index.close();

  const summary = {
    generatedAt: new Date().toISOString(),
    root,
    contactSheet: contactPath,
    indexPreview: indexPath,
    pageCount: results.length,
    pages: results,
  };
  await fs.writeFile(path.join(root, "screenshots.json"), `${JSON.stringify(summary, null, 2)}\n`, "utf8");
  console.log(JSON.stringify({
    pageCount: results.length,
    desktopOverflow: results.filter((item) => item.desktop.horizontalOverflow).map((item) => item.label),
    mobileOverflow: results.filter((item) => item.mobile.horizontalOverflow).map((item) => item.label),
    clippedButtons: results.flatMap((item) => [
      ...item.desktop.clippedButtons.map((text) => `${item.label} desktop ${text}`),
      ...item.mobile.clippedButtons.map((text) => `${item.label} mobile ${text}`),
    ]),
    contactSheet: contactPath,
  }, null, 2));
} finally {
  await browser.close();
}
