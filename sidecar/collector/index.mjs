import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
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

class EventWriter {
  constructor(path) {
    this.path = path;
    this.sequence = 0;
    this.lines = [];
  }

  write(level, scope, event, message, payload = {}) {
    this.sequence += 1;
    this.lines.push(
      jsonLine({
        sequence: this.sequence,
        time: new Date().toISOString(),
        level,
        scope,
        event,
        message,
        payload,
      }),
    );
  }

  hasEvent(eventName) {
    return this.lines.some((line) => JSON.parse(line).event === eventName);
  }

  async flush() {
    await mkdir(dirname(this.path), { recursive: true });
    await writeFile(this.path, this.lines.join(""), "utf8");
  }
}

async function writeRecords(path, records) {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, records.map(jsonLine).join(""), "utf8");
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
    events.write("error", "collector", "run_failed", error.message, {
      run_id: request.run_id,
      platform: request.platform,
      code: error.code ?? "RUN_FAILED",
    });
    await events.flush();
    return error.code === "UNSUPPORTED_PLATFORM" ? 2 : 1;
  }
}

main()
  .then((code) => {
    process.exitCode = code;
  })
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
