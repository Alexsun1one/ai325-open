"use client";
import { apiFetch } from "@/lib/auth";

/** GARDEN-MARKS R1 冻结契约（.fleet/refinement-library-20260924/garden-marks-contract.md）。
 *  家园木牌：只挂标题与阅读来源，正文仍私密；默认仅本人，显式确认才展示给群友。
 *  真人 session（匿名 401 / Agent 403），no-store。无奖励、无积分。 */

export interface OwnerMark {
  id: string; practice_id: string; title: string; source_title: string; source_url: string | null;
  shown: boolean; revision: number; created_at: string; updated_at: string;
}
export interface OwnerMarks { garden_id: string | null; max_marks: number; items: OwnerMark[] }
export type OwnerMarksResponse = OwnerMarks & { replayed: boolean };

export interface VisitorMark { id: string; title: string; source_title: string; source_url: string | null; created_at: string }
export interface VisitorMarks { garden_id: string; items: VisitorMark[] }

const enc = encodeURIComponent;

export const gardenMarksApi = {
  mine: (signal?: AbortSignal) =>
    apiFetch<OwnerMarks>("/api/garden/mine/marks", { signal }),
  visit: (gardenId: string, signal?: AbortSignal) =>
    apiFetch<VisitorMarks>(`/api/garden/visit/${enc(gardenId)}/marks`, { signal }),
  create: (practice_id: string, client_id: string) =>
    apiFetch<OwnerMarksResponse>("/api/garden/mine/marks", { method: "POST", body: JSON.stringify({ practice_id, client_id }) }),
  setShown: (id: string, shown: boolean, revision: number, client_id: string) =>
    apiFetch<OwnerMarksResponse>(`/api/garden/mine/marks/${enc(id)}`, { method: "PATCH", body: JSON.stringify({ shown, revision, client_id }) }),
  remove: (id: string, client_id: string) =>
    apiFetch<OwnerMarksResponse>(`/api/garden/mine/marks/${enc(id)}`, { method: "DELETE", body: JSON.stringify({ client_id }) }),
};
