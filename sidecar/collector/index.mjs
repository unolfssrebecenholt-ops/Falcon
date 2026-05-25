import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { pathToFileURL } from "node:url";
import { collectXiaohongshu } from "./xiaohongshu.mjs";

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error(`Invalid argument near ${key ?? "<end>"}`);
    }
    args[key.slice(2)] = value;
  }
  return args;
}

function requireArg(args, name) {
  const value = args[name];
  if (!value) {
    throw new Error(`Missing required --${name}`);
  }
  return value;
}

function jsonLine(value) {
  return `${JSON.stringify(value)}\n`;
}

export class EventWriter {
  constructor(path) {
    this.path = path;
    this.sequence = 0;
    this.lines = [];
    mkdirSync(dirname(this.path), { recursive: true });
    writeFileSync(this.path, "", "utf8");
  }

  write(level, scope, event, message, payload = {}) {
    this.sequence += 1;
    const line = jsonLine({
      sequence: this.sequence,
      time: new Date().toISOString(),
      level,
      scope,
      event,
      message,
      payload,
    });
    this.lines.push(line);
    appendFileSync(this.path, line, "utf8");
  }

  hasEvent(eventName) {
    return this.lines.some((line) => JSON.parse(line).event === eventName);
  }

  async flush() {
    await mkdir(dirname(this.path), { recursive: true });
    await writeFile(this.path, this.lines.join(""), "utf8");
  }
}

export async function writeRecords(path, records) {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, records.map(jsonLine).join(""), "utf8");
}

export async function writePartialRecordsOnError(path, error) {
  const records = Array.isArray(error?.partialRecords) ? error.partialRecords : [];
  if (!records.length) {
    return 0;
  }
  await writeRecords(path, records);
  return records.length;
}

export async function writeFailureRecordsOnError(path, error, context) {
  const records = Array.isArray(error?.partialRecords) ? [...error.partialRecords] : [];
  const existingFailureEvidence = records.find((record) => record?.type === "evidence" && record?.scope === "failure_snapshot");
  const failureEvidence = existingFailureEvidence ? null : await failureEvidenceRecordForError(error, context);
  if (failureEvidence) {
    records.push(failureEvidence);
  }
  if (!records.length) {
    return { count: 0, failureEvidence: "", failurePayload: error?.failurePayload || {} };
  }
  await writeRecords(path, records);
  return {
    count: records.length,
    failureEvidence: failureEvidence?.path || existingFailureEvidence?.path || "",
    failurePayload: error?.failurePayload || failureEvidence?.payload || existingFailureEvidence?.payload || {},
  };
}

async function failureEvidenceRecordForError(error, context) {
  const request = context?.request || {};
  if (request.platform !== "xiaohongshu") {
    return null;
  }
  const code = error?.code ?? "RUN_FAILED";
  const path = join(context.assetsPath, "run-failed-snapshot.json");
  const snapshot = {
    run_id: request.run_id,
    platform: request.platform,
    profile: request.profile || "",
    keyword: request.keyword || "",
    code,
    message: String(error?.message || error || ""),
    ...(error?.failurePayload || {}),
    captured_at: new Date().toISOString(),
  };
  await mkdir(context.assetsPath, { recursive: true });
  await writeFile(path, `${JSON.stringify(snapshot, null, 2)}\n`, "utf8");
  return {
    type: "evidence",
    run_id: request.run_id,
    platform: request.platform,
    evidence_id: `${request.run_id}-failure-snapshot`,
    scope: "failure_snapshot",
    path,
    payload: {
      code,
      reason: code,
      message: snapshot.message,
      ...(error?.failurePayload || {}),
    },
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const requestPath = requireArg(args, "request");
  const eventsPath = requireArg(args, "events");
  const outputPath = requireArg(args, "output");
  const assetsPath = requireArg(args, "assets");
  const profilePath = requireArg(args, "profile");

  await mkdir(assetsPath, { recursive: true });
  const events = new EventWriter(eventsPath);
  const request = JSON.parse(await readFile(requestPath, "utf8"));
  const context = {
    request,
    assetsPath,
    profilePath,
    events,
  };

  events.write("info", "collector", "run_started", "采集任务已启动", {
    run_id: request.run_id,
    platform: request.platform,
    dry_run: Boolean(request.dry_run),
  });

  try {
    if (request.schema_version !== 1) {
      throw new Error(`Unsupported request schema version: ${request.schema_version}`);
    }

    if (request.platform !== "xiaohongshu") {
      const error = new Error(`Unsupported platform: ${request.platform}`);
      error.code = "UNSUPPORTED_PLATFORM";
      throw error;
    }

    events.write("info", "collector", "profile_loaded", "账号环境已加载", {
      profile: request.profile,
      profile_path: profilePath,
    });

    const records = await collectXiaohongshu(context);
    await writeRecords(outputPath, records);

    if (!events.hasEvent("manual_action_required")) {
      events.write("info", "collector", "run_completed", "采集任务已完成", {
        run_id: request.run_id,
        records: records.length,
      });
    }
    await events.flush();
    return 0;
  } catch (error) {
    const failureRecords = await writeFailureRecordsOnError(outputPath, error, context);
    const failurePayload = {
      run_id: request.run_id,
      platform: request.platform,
      code: error.code ?? "RUN_FAILED",
      partial_records: failureRecords.count,
      failure_evidence: failureRecords.failureEvidence,
      ...failureRecords.failurePayload,
    };
    events.write("error", "collector", "run_failed", error.message, failurePayload);
    await events.flush();
    return error.code === "UNSUPPORTED_PLATFORM" ? 2 : 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main()
    .then((code) => {
      process.exitCode = code;
    })
    .catch((error) => {
      console.error(error);
      process.exitCode = 1;
    });
}
