import fs from "node:fs";
import path from "node:path";
import type { ReadingEntry } from "./readings";

// Deliberate editorial promotion: catalogue and capability annotations are not articles.
export const READING_COLLECTIONS = [
  "seed.json",
  "research.json",
  "local-books-20260924.json",
  "local-repositories-20260924.json",
  "web-readings-20260924.json",
] as const;

export function readReadings(): ReadingEntry[] {
  const directory = path.join(process.cwd(), "content/readings");
  const entries: ReadingEntry[] = [];
  for (const name of READING_COLLECTIONS) {
    const file = path.join(directory, name);
    // A promoted collection disappearing is a failed build, never a silently empty shelf.
    const collection = JSON.parse(fs.readFileSync(file, "utf8")) as { entries: ReadingEntry[] };
    if (!Array.isArray(collection.entries)) throw new Error(`Invalid reading collection: ${name}`);
    entries.push(...collection.entries);
  }
  const ids = new Set<string>();
  for (const entry of entries) {
    let source: URL;
    try { source = new URL(entry.source?.url); }
    catch { throw new Error(`Invalid reading source: ${entry.id}`); }
    if (!/^[a-z0-9-]+$/.test(entry.id) || ids.has(entry.id)
      || !["book", "repository"].includes(entry.kind)
      || !entry.title?.trim() || !entry.subtitle?.trim() || !entry.summary?.trim()
      || !entry.caveat?.trim() || !entry.source?.title?.trim()
      || !entry.sections?.length || !entry.exercise?.steps?.length
      || !Array.isArray(entry.tags) || !Array.isArray(entry.takeaways)
      || source.protocol !== "https:" || !source.hostname || source.username || source.password
      || !Number.isFinite(Date.parse(entry.reviewedAt))) {
      throw new Error(`Incomplete or duplicate reading: ${entry.id}`);
    }
    ids.add(entry.id);
  }
  return entries;
}
