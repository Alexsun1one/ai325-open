import fs from "node:fs";
import path from "node:path";

export interface CuratedReport {
  id: string; title: string; summary: string; reason: string; url: string;
  sourceName: string; publishedAt: string; originalTitle: string; originalSummary: string;
  scores: number[]; evidenceQuotes: string[]; relation: "new" | "same" | "development";
}
export interface CuratedEvent {
  id: string; title: string; summary: string; reason: string; tags: string[];
  publishedAt: string; updatedAt: string; heat: number; independentSources: number;
  trend: "new" | "rising" | "steady"; reports: CuratedReport[];
}
export interface CuratedEdition {
  date: string; status: "in_progress" | "complete" | "partial"; revision: number; total: number;
  items: { eventId: string; reportId: string; title: string; summary: string; reason: string;
    url: string; sourceName: string; scores: number[]; development: boolean }[];
}
export interface ExternalCuration {
  schemaVersion: 1; generatedAt: string; lastSuccessAt: string | null;
  run: { status: "ok" | "partial" | "budget_limited" | "failed"; attemptedAt: string; counts: Record<string, number>; failedSources: number };
  rules: { hotWindowHours: number; hotHalfLifeHours: number; digestLimit: number; maxItemsPerRun: number };
  events: CuratedEvent[]; editions: CuratedEdition[];
}
const plain = (s: unknown, max: number) => typeof s === "string" && s.length > 0 && s.length <= max && !/[\x00-\x1f\x7f<>]/.test(s);
const stamp = (s: unknown) => typeof s === "string" && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/.test(s) && Number.isFinite(Date.parse(s));
const url = (s: unknown) => { try { const u = new URL(String(s)); return ["http:", "https:"].includes(u.protocol) && !u.username && !u.password; } catch { return false; } };
const integer = (n: unknown) => typeof n === "number" && Number.isSafeInteger(n) && n >= 0;
const scores = (a: unknown) => Array.isArray(a) && a.length === 2 && a.every(n => integer(n) && n <= 100);
const eventId = (s: unknown) => typeof s === "string" && /^event-[a-f0-9]{20}$/.test(s);

export function readExternalCuration(): ExternalCuration | null {
  const file = path.join(process.cwd(), "public/data/external-curated.json");
  if (!fs.existsSync(file)) return null;
  const d: ExternalCuration = JSON.parse(fs.readFileSync(file, "utf8"));
  const fail = () => { throw new Error("Invalid external curation document"); };
  if (d.schemaVersion !== 1 || !stamp(d.generatedAt) || !(d.lastSuccessAt === null || stamp(d.lastSuccessAt)) ||
      !d.run || !["ok", "partial", "budget_limited", "failed"].includes(d.run.status) || !stamp(d.run.attemptedAt) ||
      !d.run.counts || !Object.values(d.run.counts).every(integer) || !integer(d.run.failedSources) ||
      !d.rules || !Object.values(d.rules).every(n => integer(n) && n > 0) || !Array.isArray(d.events) || !Array.isArray(d.editions)) fail();
  const seen = new Set<string>();
  for (const e of d.events) {
    if (!eventId(e.id) || seen.has(e.id) || !plain(e.title, 80) || !plain(e.summary, 300) || !plain(e.reason, 120) ||
        !stamp(e.publishedAt) || !stamp(e.updatedAt) || !Number.isFinite(e.heat) || e.heat < 0 || !integer(e.independentSources) ||
        !["new", "rising", "steady"].includes(e.trend) || !Array.isArray(e.tags) || !e.tags.every(t => plain(t, 30)) ||
        !Array.isArray(e.reports) || !e.reports.length) fail();
    seen.add(e.id);
    for (const r of e.reports) {
      if (!plain(r.id, 120) || !plain(r.title, 80) || !plain(r.summary, 300) || !plain(r.reason, 120) ||
          !url(r.url) || !plain(r.sourceName, 120) || !stamp(r.publishedAt) || !scores(r.scores) ||
          !plain(r.originalTitle, 240) || typeof r.originalSummary !== "string" ||
          !["same", "new", "development"].includes(r.relation) || !Array.isArray(r.evidenceQuotes) ||
          !r.evidenceQuotes.every(q => plain(q, 120))) fail();
    }
  }
  for (const edition of d.editions) {
    if (!/^\d{4}-\d\d-\d\d$/.test(edition.date) || !["in_progress", "complete", "partial"].includes(edition.status) ||
        !integer(edition.revision) || !integer(edition.total) || !Array.isArray(edition.items) || edition.items.length > edition.total) fail();
    for (const i of edition.items) {
      if (!eventId(i.eventId) || !plain(i.reportId, 120) || !plain(i.title, 80) || !plain(i.summary, 300) || !plain(i.reason, 120) ||
          !url(i.url) || !plain(i.sourceName, 120) || !scores(i.scores) || typeof i.development !== "boolean") fail();
    }
  }
  return d;
}
