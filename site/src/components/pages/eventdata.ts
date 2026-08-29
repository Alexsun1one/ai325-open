import fs from "node:fs";
import path from "node:path";

export interface EventItem {
  slug: string; title: string; kind: string; status: string;
  starts_at: string; ends_at?: string; reward?: string; cover?: string;
  one_line?: string; rules_md?: string;
  participants?: { name: string; note?: string }[];
  timeline?: { t: string; h: string; d: string }[];
  links?: { label: string; href: string }[];
}

const FILE = path.join(process.cwd(), "content", "events.json");

/** 静态种子。上线后页面会再问一次后端，拿到就用后端的覆盖同名活动。 */
export function readEvents(): EventItem[] {
  if (!fs.existsSync(FILE)) return [];
  try { return JSON.parse(fs.readFileSync(FILE, "utf-8")) as EventItem[]; } catch { return []; }
}

export function artExists(file?: string) {
  if (!file) return false;
  return fs.existsSync(path.join(process.cwd(), "public", "art", file));
}

export const STATUS_STYLE: Record<string, string> = {
  进行中: "border-amber-deep/50 bg-amber-wash text-amber-text",
  常设: "border-teal/50 bg-teal-wash text-teal-text",
  筹备中: "border-blue-wash-2 bg-blue-wash text-blue-text",
  已结束: "border-rule bg-paper-2 text-ink-3",
};
