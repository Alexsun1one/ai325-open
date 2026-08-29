import fs from "node:fs";
import path from "node:path";
import type { Ledger } from "./shared";
export * from "./shared";

const LEDGER_DIR = path.join(process.cwd(), "content", "ledgers");

export function listLedgerDates(): string[] {
  if (!fs.existsSync(LEDGER_DIR)) return [];
  return fs
    .readdirSync(LEDGER_DIR)
    .filter((f) => f.endsWith(".json"))
    .map((f) => f.replace(/\.json$/, ""))
    .sort()
    .reverse();
}

export function getLedger(date: string): Ledger {
  const p = path.join(LEDGER_DIR, `${date}.json`);
  return JSON.parse(fs.readFileSync(p, "utf-8")) as Ledger;
}

export function getAllLedgers(): Ledger[] {
  return listLedgerDates().map(getLedger);
}

export function getLatestLedger(): Ledger {
  const dates = listLedgerDates();
  return getLedger(dates[0]);
}


export function getNeighbors(date: string): { prev: { date: string; issue: number; title: string } | null; next: { date: string; issue: number; title: string } | null; prevOpen: number } {
  const dates = listLedgerDates().slice().sort();
  const i = dates.indexOf(date);
  const pick = (d?: string) => { if (!d) return null; const l = getLedger(d); return { date: l.date, issue: l.issue, title: l.title }; };
  const prevL = i > 0 ? getLedger(dates[i - 1]) : null;
  return { prev: pick(dates[i - 1]), next: pick(dates[i + 1]), prevOpen: prevL ? prevL.docket.filter((d) => d.status === "open").length : 0 };
}

/** 六幕插画：构建时探测 public/art/illus/theme-0N.webp，存在才渲染。 */
export function getThemeIllustrations(count: number): (string | null)[] {
  return Array.from({ length: count }, (_, i) => {
    const rel = `/art/illus/theme-${String(i + 1).padStart(2, "0")}.webp`;
    return fs.existsSync(path.join(process.cwd(), "public", rel)) ? rel : null;
  });
}
export function getSpotIllustrations(): Record<string, string> {
  const ids = ["intake", "run", "timeline", "tone", "quotes", "score", "growth", "docket", "members"];
  const out: Record<string, string> = {};
  for (const id of ids) { const cut = `/art/illus/cut/spot-${id}.webp`; const rel = `/art/illus/spot-${id}.webp`; if (fs.existsSync(path.join(process.cwd(), "public", cut))) out[id] = cut; else if (fs.existsSync(path.join(process.cwd(), "public", rel))) out[id] = rel; }
  return out;
}
