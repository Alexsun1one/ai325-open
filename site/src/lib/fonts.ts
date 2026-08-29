import fs from "node:fs";
import path from "node:path";

/** 从分片字体 CSS 反查文字→分片，用于整页 preload（消灭字体换入抖动）。 */
type Face = { family: string; weight: number; url: string; ranges: [number, number][] };
let cache: Face[] | null = null;
function load(): Face[] {
  if (cache) return cache;
  const faces: Face[] = [];
  for (const file of ["src/styles/noto-serif-sc.css", "src/styles/lxgw-wenkai.css"]) {
    let css = ""; try { css = fs.readFileSync(path.join(process.cwd(), file), "utf-8"); } catch { continue; }
    for (const m of css.matchAll(/@font-face\{([\s\S]*?)\}/g)) {
      const body = m[1];
      const family = /font-family:\s*["']?([^;"']+)/.exec(body)?.[1]?.trim() ?? "";
      const w = Number(/font-weight:\s*(\d+)/.exec(body)?.[1] ?? 400);
      const url = /url\(["']?([^"')]+)["']?\)/.exec(body)?.[1]; if (!url) continue;
      const ur = /unicode-range:([^;]+);?/.exec(body)?.[1] ?? "";
      const ranges: [number, number][] = [];
      for (const tok of ur.split(",")) {
        const t = tok.trim().replace(/^U\+/i, ""); if (!t) continue;
        const [a, b] = t.split("-"); const lo = parseInt(a, 16); const hi = b ? parseInt(b, 16) : lo;
        if (!Number.isNaN(lo)) ranges.push([lo, hi]);
      }
      faces.push({ family, weight: w, url, ranges });
    }
  }
  cache = faces; return faces;
}
/** 按命中字数排序的分片列表。family: "Noto Serif SC" | "LXGW WenKai" */
export function fontChunksRanked(text: string, family: string, weight: number): string[] {
  const faces = load().filter((f) => f.family === family && f.weight === weight);
  const hits = new Map<string, number>();
  const seen = new Set<number>();
  for (const ch of Array.from(text)) {
    const cp = ch.codePointAt(0)!; if (seen.has(cp)) continue; seen.add(cp);
    for (const f of faces) { if (f.ranges.some(([lo, hi]) => cp >= lo && cp <= hi)) { hits.set(f.url, (hits.get(f.url) ?? 0) + 1); break; } }
  }
  return Array.from(hits.entries()).sort((a, b) => b[1] - a[1]).map(([u]) => u);
}
export function fontChunksFor(text: string, weight: number): string[] { return fontChunksRanked(text, "Noto Serif SC", weight); }
