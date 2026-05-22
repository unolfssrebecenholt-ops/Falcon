import { createHash } from "node:crypto";
import { cleanText } from "./text_cleaner.mjs";

export function fingerprint(parts) {
  const normalized = (parts ?? []).map((part) => cleanText(part)).join("\n---\n");
  return createHash("sha256").update(normalized).digest("hex");
}

export class DedupeSet {
  constructor(initial = []) {
    this.items = new Set(initial);
  }

  has(parts) {
    return this.items.has(fingerprint(parts));
  }

  add(parts) {
    const key = fingerprint(parts);
    const existed = this.items.has(key);
    this.items.add(key);
    return { key, existed };
  }
}
