"use client";
import { apiFetch } from "@/lib/auth";

/** READING-GROWTH R1 冻结契约（.fleet/reading-growth-20260924/contract.md）。
 *  个人阅读足迹与参与：全部端点仅真人 session；kind/resource_id 走服务端白名单，
 *  客户端不传标题/用户ID/任意 URL。 */

export type ReadingKind = "book_note" | "reading";

export interface ReadingRecord {
  kind: ReadingKind; resource_id: string; title: string;
  url: string | null; category: string; available: boolean;
  last_opened_at: string | null; saved: boolean; saved_at: string | null;
  finished: boolean; finished_at: string | null; updated_at: string | null;
}
export interface ProgressPage {
  items: ReadingRecord[]; total: number; has_more: boolean;
  summary: { opened: number; saved: number; finished: number };
}
export type ActivityType = "comment" | "question" | "reply" | "practice" | "practice_reply" | "paragraph_saved";
export interface ActivityItem {
  id: string; type: ActivityType; title: string; excerpt: string;
  url: string | null; at: string;
}
export interface ActivityPage {
  items: ActivityItem[]; total: number; has_more: boolean;
  summary: { contributions: number; practices_completed: number; paragraphs_saved: number };
}

const q = (o: Record<string, string | number>) => "?" + Object.entries(o).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
const rid = (kind: ReadingKind, id: string) => `/api/me/reading-progress/${kind}/${encodeURIComponent(id)}`;

export const readingGrowthApi = {
  get: (kind: ReadingKind, id: string, signal?: AbortSignal) =>
    apiFetch<{ item: ReadingRecord }>(rid(kind, id), { signal }),
  open: (kind: ReadingKind, id: string) =>
    apiFetch<{ item: ReadingRecord }>(`${rid(kind, id)}/open`, { method: "POST" }),
  patch: (kind: ReadingKind, id: string, fields: { saved?: boolean; finished?: boolean }) =>
    apiFetch<{ item: ReadingRecord }>(rid(kind, id), { method: "PATCH", body: JSON.stringify(fields) }),
  remove: (kind: ReadingKind, id: string) =>
    apiFetch<{ ok: true }>(rid(kind, id), { method: "DELETE" }),
  list: (filter: "all" | "saved" | "finished", offset = 0, limit = 20, signal?: AbortSignal) =>
    apiFetch<ProgressPage>(`/api/me/reading-progress${q({ filter, offset, limit })}`, { signal }),
  activity: (offset = 0, limit = 20, signal?: AbortSignal) =>
    apiFetch<ActivityPage>(`/api/me/growth-activity${q({ offset, limit })}`, { signal }),
};
