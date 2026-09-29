import fs from "node:fs";
import path from "node:path";

export interface ArsenalItem {
  id: string; title: string; kind: string;
  source: { name: string; url?: string; author?: string; published_at?: string };
  collected_at: string; by: string;
  one_line: string; why: string; for_whom: string;
  takeaways: string[]; quote?: string;
  tags: string[]; threads?: string[];
  body_md?: string; status: "shelved" | "featured" | "retired" | string;
  /** 后端合并进来的那批（形状照 backend 2026-08-23 10:56 报告）：
   *  origin=market 表示群友上架；via 是贡献者；files 是受控附件；skill_md 只在详情里给。 */
  origin?: "static" | "market" | string;
  via?: string;
  files?: { path: string; url: string; size?: number }[];
  downloads?: number;
  skill_md?: string;
}

const DIR = path.join(process.cwd(), "content", "arsenal");

/** seed.json 是打底，YYYY-MM-DD.json 是每天新到的；同 id 以晚的为准。 */
export function readArsenal(): ArsenalItem[] {
  if (!fs.existsSync(DIR)) return [];
  const files = fs.readdirSync(DIR).filter((f) => f.endsWith(".json") && !f.endsWith(".gap.json")).sort();
  const byId = new Map<string, ArsenalItem>();
  for (const f of files) {
    try {
      const arr = JSON.parse(fs.readFileSync(path.join(DIR, f), "utf-8")) as ArsenalItem[];
      if (!Array.isArray(arr)) continue;
      for (const it of arr) if (it?.id) byId.set(it.id, it);
    } catch { /* 单个文件坏了不拖垮整架 */ }
  }
  return [...byId.values()].filter((x) => x.status !== "retired");
}

/** 后端契约：那批军火没过审时写 <date>.gap.json，不写 <date>.json。 */
export interface ArsenalGap {
  date: string;
  reason: string;
}

function parseGap(f: string): ArsenalGap | null {
  try {
    const raw = JSON.parse(fs.readFileSync(path.join(DIR, f), "utf-8"));
    const date = typeof raw?.date === "string" ? raw.date : f.slice(0, 10);
    const reason = typeof raw?.reason === "string" && raw.reason ? raw.reason : "这一批没过审";
    return { date, reason };
  } catch {
    return { date: f.slice(0, 10), reason: "这一批没过审" };
  }
}

export function readArsenalGaps(): ArsenalGap[] {
  if (!fs.existsSync(DIR)) return [];
  return fs
    .readdirSync(DIR)
    .filter((f) => f.endsWith(".gap.json"))
    .sort()
    .map(parseGap)
    .filter((g): g is ArsenalGap => g !== null);
}

export function arsenalGapFor(date: string): ArsenalGap | null {
  const p = path.join(DIR, `${date}.gap.json`);
  if (!fs.existsSync(p)) return null;
  return parseGap(`${date}.gap.json`);
}

export function artFile(name: string) {
  const p = path.join(process.cwd(), "public", "art", name);
  return fs.existsSync(p) ? `/art/${name}` : null;
}

/** 六个架位，固定顺序；数据里出现的其他 kind 排在后面。 */
export const SHELVES = ["技能", "提示词", "方法", "文章", "案例", "工具", "产品", "论文", "拆书"];
