"use client";
import { apiFetch } from "@/lib/auth";

/** CONTENT-ENGAGEMENT R1 冻结契约（.fleet/interactions-stickers-20260924/contract.md）。
 *  公开互动计数：kind 白名单，公共 stats 不含身份/名单；view 每浏览器每日一次；
 *  liked 仅真人 session。 */

export type EngagementKind = "book_note" | "reading" | "journey" | "knowledge";

export interface PublicStats {
  kind: EngagementKind; resource_id: string;
  views: number; likes: number; comments: number;
  view_policy: { visible_ms: number; dedupe: string; timezone: string };
  since?: string;
}

const rid = (kind: EngagementKind, id: string) =>
  `/api/content-engagement/${kind}/${encodeURIComponent(id)}`;

export const engagementApi = {
  /** 公共计数，匿名可读 */
  stats: (kind: EngagementKind, id: string, signal?: AbortSignal) =>
    apiFetch<PublicStats>(rid(kind, id), { signal, auth: false }),
  /** 可见停留记一次「阅读」；visitor_id 每浏览器随机 UUID，服务端按北京日去重 */
  view: (kind: EngagementKind, id: string, visitorId: string) =>
    apiFetch<PublicStats>(`${rid(kind, id)}/view`, { method: "POST", body: JSON.stringify({ visitor_id: visitorId }), auth: false }),
  /** 本人点赞态，仅登录 */
  myLike: (kind: EngagementKind, id: string, signal?: AbortSignal) =>
    apiFetch<{ liked: boolean }>(`/api/me/content-engagement/${kind}/${encodeURIComponent(id)}`, { signal }),
  setLike: (kind: EngagementKind, id: string, liked: boolean) =>
    apiFetch<{ liked: boolean; stats: PublicStats }>(`/api/me/content-engagement/${kind}/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ liked }) }),
};

/** 北京时间当日（服务端按此时区去重，本地同口径防重发） */
export function shanghaiDay(now = new Date()): string {
  return now.toLocaleDateString("en-CA", { timeZone: "Asia/Shanghai" }); // YYYY-MM-DD
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/** 每浏览器一个随机 visitor；localStorage 不可写时不发——避免重刷变新 ID 虚增 */
export function visitorId(): string | null {
  try {
    const k = "xce-visitor";
    const cur = window.localStorage.getItem(k);
    if (cur && UUID_RE.test(cur)) return cur;
    const id = crypto.randomUUID();
    window.localStorage.setItem(k, id);
    return window.localStorage.getItem(k) === id ? id : null; // 没写进去就当不可用
  } catch { return null; }
}
