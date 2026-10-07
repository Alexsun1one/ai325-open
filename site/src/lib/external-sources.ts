import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import type { DiscoveryItem } from "./discovery";

/** External RSS/Atom knowledge, collected by scripts/ops/collect_external_sources.py. Independent from group-chat sources. */
export interface ExternalSource { id: string; name: string; feedUrl: string; homepage: string; tags: string[]; status: "ok" | "failed"; lastAttemptAt: string; lastSuccessAt: string | null; lastError: string | null; itemCount: number }
export interface ExternalItem { id: string; sourceId: string; sourceName: string; url: string; canonicalUrl: string; title: string; summary: string; tags: string[]; publishedAt: string | null; fetchedAt: string }
export interface ExternalSourcesData { schemaVersion: 1; updatedAt: string | null; sources: ExternalSource[]; items: ExternalItem[] }

const FILE = "public/data/external-knowledge.json";
const ISO_Z = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;
const SOURCE_ID = /^[a-z0-9][a-z0-9-]{0,39}$/;
const MARKUP = /<[^>]*>/;
const CTRL = /[\x00-\x1f\x7f]/;
const MAX_TITLE = 240;
const MAX_SUMMARY = 300;
const MAX_NAME = 120;
const MAX_ERROR = 200;
const MAX_TAG = 40;
const MAX_TAGS = 8;

const isString = (v: unknown): v is string => typeof v === "string" && v.length > 0;
const httpUrl = (v: unknown) => { if (!isString(v)) return false; try { const u = new URL(v); return (u.protocol === "https:" || u.protocol === "http:") && !u.username && !u.password && !v.includes("\\") && !v.includes(" "); } catch { return false; } };
const isoZ = (v: unknown) => isString(v) && ISO_Z.test(v) && Number.isFinite(Date.parse(v));
const isoOrNull = (v: unknown) => v === null || isoZ(v);
const plain = (v: unknown, max: number, allowEmpty = false) => typeof v === "string" && v.length <= max && (allowEmpty || v.length > 0) && !MARKUP.test(v) && !CTRL.test(v);
const tagList = (v: unknown) => Array.isArray(v) && v.length <= MAX_TAGS && v.every((t) => plain(t, MAX_TAG));

export function readExternalSources(): ExternalSourcesData {
  const file = path.join(process.cwd(), FILE);
  if (!fs.existsSync(file)) return { schemaVersion: 1, updatedAt: null, sources: [], items: [] };
  const data: ExternalSourcesData = JSON.parse(fs.readFileSync(file, "utf8"));
  if (data.schemaVersion !== 1 || !Array.isArray(data.sources) || !Array.isArray(data.items) || !isoOrNull(data.updatedAt)) throw new Error("Invalid external knowledge document");
  const sourceIds = new Set<string>();
  const counts = new Map<string, number>();
  for (const s of data.sources) {
    if (!SOURCE_ID.test(s.id) || sourceIds.has(s.id) || !plain(s.name, MAX_NAME) || !httpUrl(s.feedUrl) || !httpUrl(s.homepage) || !tagList(s.tags) || !["ok", "failed"].includes(s.status) || !isoZ(s.lastAttemptAt) || !isoOrNull(s.lastSuccessAt) || !Number.isInteger(s.itemCount) || s.itemCount < 0) throw new Error(`Invalid external source: ${s.id}`);
    if (s.status === "ok" && !isoZ(s.lastSuccessAt)) throw new Error(`Invalid external source: ${s.id}`);
    if (s.status === "failed" ? !plain(s.lastError, MAX_ERROR) : s.lastError !== null) throw new Error(`Invalid external source: ${s.id}`);
    sourceIds.add(s.id);
    counts.set(s.id, 0);
  }
  const ids = new Set<string>();
  for (const e of data.items) {
    if (!isString(e.id) || ids.has(e.id) || !sourceIds.has(e.sourceId) || !plain(e.sourceName, MAX_NAME) || !plain(e.title, MAX_TITLE) || !plain(e.summary, MAX_SUMMARY, true) || !tagList(e.tags) || !httpUrl(e.url) || !httpUrl(e.canonicalUrl) || !isoOrNull(e.publishedAt) || !isoZ(e.fetchedAt)) throw new Error(`Invalid external item: ${e.id}`);
    ids.add(e.id);
    counts.set(e.sourceId, (counts.get(e.sourceId) ?? 0) + 1);
  }
  for (const s of data.sources) if (s.itemCount !== counts.get(s.id)) throw new Error(`Invalid external source: ${s.id}`);
  return data;
}

/** Dated items only: discovery requires a real date, and undated items never get a fabricated one. url is a site path (/sources/#id); sourceUrl is the original https link. */
export function readExternalDiscovery(): DiscoveryItem[] {
  return readExternalSources().items.filter((e) => e.publishedAt).map((e) => ({
    id: `resource:${createHash("sha256").update(`external:${e.id}`).digest("hex").slice(0, 24)}`,
    kind: "resource" as const,
    title: e.title,
    summary: `外部公开来源 · ${e.sourceName}：${e.summary || "摘要请见原文"}`,
    url: `/sources/#${e.id}`,
    date: (e.publishedAt as string).slice(0, 10),
    tags: ["外部来源", e.sourceName, ...e.tags],
    ...(e.url.startsWith("https://") ? { sourceUrl: e.url } : {}),
  }));
}
