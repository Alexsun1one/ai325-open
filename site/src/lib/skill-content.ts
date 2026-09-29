import fs from "node:fs";
import path from "node:path";
import type { LibrarySkill, SkillLibraryData } from "./skill-library";

/** Human page and Agent export share the same build-time catalog. */
export function readSkillLibrary(): SkillLibraryData {
  const sources = ["upstream.json", "catalog.json"].map((name) => {
    const file = path.join(process.cwd(), "public/skills", name);
    const data: SkillLibraryData = JSON.parse(fs.readFileSync(file, "utf8"));
    if (data.schemaVersion !== 1 || !Array.isArray(data.items) || !Number.isFinite(Date.parse(data.generatedAt))) {
      throw new Error(`Invalid skill catalog: ${name}`);
    }
    return data;
  });
  const items = new Map<string, LibrarySkill>();
  for (const source of sources) for (const item of source.items) {
    if (items.has(item.id)) throw new Error(`Duplicate skill ID: ${item.id}`);
    items.set(item.id, item);
  }
  const detailFile = path.join(process.cwd(), "public/skills/detail-index.json");
  if (fs.existsSync(detailFile)) {
    const details: { items: { id: string; detailUrl: string; hasEditorial?: boolean; repositoryUrl: string | null; repositoryStars?: number | null; starsCheckedAt?: string | null }[] } = JSON.parse(fs.readFileSync(detailFile, "utf8"));
    for (const detail of details.items) {
      const item = items.get(detail.id);
      if (!item) throw new Error(`Unknown skill detail: ${detail.id}`);
      if (!detail.detailUrl.startsWith("/skills/details/") || detail.detailUrl.includes("..")) throw new Error(`Invalid skill detail URL: ${detail.id}`);
      items.set(detail.id, { ...item, detailUrl: detail.detailUrl, hasEditorial: detail.hasEditorial, repositoryUrl: detail.repositoryUrl, repositoryStars: detail.repositoryStars, starsCheckedAt: detail.starsCheckedAt });
    }
  }
  return {
    schemaVersion: 1,
    generatedAt: sources.map((source) => source.generatedAt).sort((a, b) => Date.parse(b) - Date.parse(a))[0],
    items: [...items.values()],
  };
}
