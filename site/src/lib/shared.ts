export type Tone = "s" | "j" | "h";

export interface Voice { a: string; v: string }
export interface Theme { h: string; when: string; body: string; deep: string; voices: Voice[] }
export interface Event { t: string; h: string; d: string; src?: "digest" | "db" }
export interface ToneNote { h: string; cls: Tone; body: string }
export interface Insight { h: string; en: string; body: string }
export interface Quote { t: string; a: string; g: Tone; evidence?: { unit: number; ordinal?: number } }
export interface Glossary { term: string; def: string }
export interface Arsenal { h: string; body: string }
export interface Docket { kind: string; h: string; d: string; status: "open" | "closed"; carried_from?: number }
export interface Clash { h: string; en: string; sides: string; verdict: string }
export interface TodoPhase { phase: string; items: string[] }
export interface MemberFocus { name: string; role: string; msgs: number; tone: Tone; quote: string; tags: string[] }
export interface Newcomer { name: string; note: string; t: string; by?: string; first_words?: string }
export interface Dimension { name: string; score: number; grade: string; detail: string }
export interface Thread { id: string; title: string; theme: string; status: "ongoing" | "closed"; first_issue?: number; prev_issue?: number | null }

export interface Ledger {
  date: string;
  issue: number;
  title: string;
  coverage: { from: string; to: string; cutoff: string; note: string };
  complete: boolean;
  lead: string;
  stats: { msgs: number; speakers: number; members: number; essays: number; essays_open: number; quotes: number; themes: number; decoded: number };
  hours: Record<string, number>;
  pulse: { caption: string; note: string };
  events: Event[];
  themes: Theme[];
  tone_notes: ToneNote[];
  insights: Insight[];
  quotes: Quote[];
  glossary: Glossary[];
  arsenal: Arsenal[];
  docket: Docket[];
  clashes: Clash[];
  growth: { takeaways: string[]; todo: TodoPhase[]; carried?: TodoPhase[] };
  members_focus: MemberFocus[];
  newcomers?: Newcomer[];
  thanks?: { name: string; why: string }[];
  quality: { overall: number; grade: string; dimensions: Dimension[]; basis: string };
  threads: Thread[];
  credits: { distilled_by: string; reviewed_by: string; generated_at: string };
  footer: string[];
}

export const TONE_META: Record<Tone, { label: string; emoji: string; color: string; wash: string }> = {
  s: { label: "认真", emoji: "💡", color: "var(--blue-text)", wash: "var(--blue-wash)" },
  j: { label: "玩笑", emoji: "😄", color: "var(--teal-text)", wash: "var(--teal-wash)" },
  h: { label: "半真", emoji: "🔥", color: "var(--cinnabar-text)", wash: "var(--cinnabar-wash)" },
};

/** 没解析出昵称的微信/QQ 原始账号，读者眼里就是乱码——渲染前统一打码成「群友」。 */
const RAW_ID_RE = /(?:wxid_[A-Za-z0-9_-]{4,}|\bQQ\d{5,}\b|\bq\d{6,}\b)/g;
export function isRawId(s: string | undefined | null) {
  if (!s) return false;
  RAW_ID_RE.lastIndex = 0;
  const m = RAW_ID_RE.exec(s.trim());
  return m !== null && m[0].length === s.trim().length;
}
export function maskRawIds(s: string) {
  return s.replace(RAW_ID_RE, "群友");
}

export function pad3(n: number) {
  return String(n).padStart(3, "0");
}

export function fmtInt(n: number) {
  return new Intl.NumberFormat("en-US").format(n);
}
