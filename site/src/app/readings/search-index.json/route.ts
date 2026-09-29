import fs from "node:fs";
import path from "node:path";
import { readReadings } from "@/lib/reading-content";
import { buildIndexDocs, type CapabilityEntry } from "@/lib/repository-retrieval";

/** /readings/search-index.json —— 只导出已晋升 readReadings 内 repository 的公开精读元数据
 *  （标题/简介/tags/takeaways/节标题/每节≤500字摘录）+ p9 的 repository-capabilities（仅晋升条目）。
 *  未晋升/内部数据不进索引；capabilities 文件未到时诚实降级（codeRefs 空、capabilitiesLoaded=false）。 */
export const dynamic = "force-static";

interface CapabilityFile { version: number; entries: CapabilityEntry[] }

export function GET() {
  const repos = readReadings().filter((e) => e.kind === "repository");
  const promoted = new Set(repos.map((e) => e.id));

  let caps: CapabilityEntry[] = [];
  let capabilitiesLoaded = false;
  const capPath = path.join(process.cwd(), "content/readings/repository-capabilities.json");
  if (fs.existsSync(capPath)) {
    try {
      const parsed = JSON.parse(fs.readFileSync(capPath, "utf8")) as CapabilityFile;
      if (parsed?.version === 1 && Array.isArray(parsed.entries)) {
        caps = parsed.entries.filter((c) => promoted.has(c.entryId));
        capabilitiesLoaded = true;
      }
    } catch { /* 解析失败按缺失降级，不阻断索引 */ }
  }

  const docs = buildIndexDocs(repos, caps);
  return new Response(JSON.stringify({
    version: 1,
    total: docs.length,
    withCodeRefs: docs.filter((d) => d.codeRefs.length > 0).length,
    capabilitiesLoaded,
    docs,
  }), { headers: { "content-type": "application/json; charset=utf-8" } });
}
