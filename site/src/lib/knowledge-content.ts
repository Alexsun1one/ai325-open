import fs from "node:fs";
import path from "node:path";
import type { KnowledgeData } from "./knowledge";
export function readKnowledge(): KnowledgeData {
  const data: KnowledgeData = JSON.parse(fs.readFileSync(path.join(process.cwd(), "content/knowledge/seed.json"), "utf8"));
  if (data.schemaVersion !== 1 || !Array.isArray(data.entries) || !Array.isArray(data.topics)) throw new Error("Invalid knowledge catalog");
  const ids = new Set(data.entries.map(entry => entry.id));
  const topics = new Set(data.topics.map(topic => topic.id));
  if (ids.size !== data.entries.length) throw new Error("Duplicate knowledge IDs");
  for (const entry of data.entries) {
    if (!topics.has(entry.topicId) || !entry.sources.length || !entry.counterpoint || !entry.question ||
      entry.relatedIds.some(id => !ids.has(id) || id === entry.id)) throw new Error(`Incomplete knowledge: ${entry.id}`);
    for (const source of entry.sources) {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(source.date)) throw new Error("Invalid source date");
      const ledger = JSON.parse(fs.readFileSync(path.join(process.cwd(), "content/ledgers", `${source.date}.json`), "utf8"));
      if (!ledger.themes.some((theme: { h: string }) => theme.h === source.themeTitle)) throw new Error(`Missing source for ${entry.id}`);
    }
  }
  return data;
}
