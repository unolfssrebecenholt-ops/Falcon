import { appendFile, writeFile } from "node:fs/promises";

export function createRunSummary({ platform, keywords, targetPerKeyword, startedAt = new Date() }) {
  return {
    platform,
    keywords,
    target_per_keyword: targetPerKeyword,
    started_at: startedAt.toISOString(),
    finished_at: null,
    elapsed_ms: null,
    status: "running",
    keyword_results: [],
    errors: [],
  };
}

export function finishRunSummary(summary, { status = "completed", finishedAt = new Date() } = {}) {
  summary.finished_at = finishedAt.toISOString();
  summary.elapsed_ms = Date.parse(summary.finished_at) - Date.parse(summary.started_at);
  summary.status = status;
  return summary;
}

export async function writeRunSummary(summaryPath, summary) {
  await writeFile(summaryPath, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
}

export async function initializeSteps(stepsPath, { platform, keyword, startedAt = new Date() }) {
  const text = [
    `# Collection Steps`,
    ``,
    `- platform: ${platform}`,
    `- keyword: ${keyword}`,
    `- started_at: ${startedAt.toISOString()}`,
    ``,
  ].join("\n");
  await writeFile(stepsPath, text, "utf8");
}

export async function appendStep(stepsPath, message, at = new Date()) {
  await appendFile(stepsPath, `- ${at.toISOString()} ${message}\n`, "utf8");
}
