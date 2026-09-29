"use client";
import { apiFetch } from "@/lib/auth";

/** GROWTH-CONTENT R1 冻结契约（.fleet/growth-content-20260924/practice-contract.md）。
 *  私人实践与共练：均需真人成员 session，匿名 401 / Agent 403。所有字段按契约原样透传。 */

export type PracticeStatus = "active" | "completed" | "archived";

export interface Practice {
  id: string; title: string; outcome: string; next_step: string; notes: string;
  result_url: string; source_url: string; source_title: string;
  status: PracticeStatus; revision: number; challenge_id: string | null;
  created_at: string; updated_at: string;
}
export interface Challenge {
  id: string; title: string; summary: string; instructions: string[]; outcome: string;
  status: "open" | "closed"; my_practice_id: string | null; submission_count: number;
}
export interface Author { name: string; kind: "human"; member_key?: string }
export interface Submission {
  id: string; practice_id: string | null; challenge_id: string;
  title: string; body: string; result_url: string; author: Author;
  created_at: string; revision: number; reply_count: number; is_mine: boolean;
}
export interface Reply { id: string; text: string; author: Author; created_at: string }
export interface Page<T> { items: T[]; total: number; limit: number; offset: number }

export interface PracticeInput {
  title: string; outcome: string; next_step?: string; source_url?: string; source_title?: string;
  /** 同一次创建意图复用的幂等键（garden-marks 契约）：0/5xx 重试沿用，4xx 确定拒绝后换新 */
  client_id?: string;
}
export type PracticePatch = Partial<Pick<Practice, "title" | "outcome" | "next_step" | "notes" | "result_url" | "status">>;

const q = (o: Record<string, string | number>) => "?" + Object.entries(o).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");

export const practiceApi = {
  listMine: (status: PracticeStatus | "all" = "all", offset = 0, limit = 20, signal?: AbortSignal) =>
    apiFetch<Page<Practice>>(`/api/practice/mine${q({ status, limit, offset })}`, { signal }),
  create: (input: PracticeInput) =>
    apiFetch<Practice>("/api/practice/mine", { method: "POST", body: JSON.stringify(input) }),
  get: (id: string, signal?: AbortSignal) =>
    apiFetch<Practice>(`/api/practice/mine/${encodeURIComponent(id)}`, { signal }),
  patch: (id: string, revision: number, fields: PracticePatch) =>
    apiFetch<Practice>(`/api/practice/mine/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ revision, ...fields }) }),
  challenges: (signal?: AbortSignal) =>
    apiFetch<{ items: Challenge[]; total: number }>("/api/practice/challenges", { signal }),
  join: (id: string) =>
    apiFetch<Practice>(`/api/practice/challenges/${encodeURIComponent(id)}/join`, { method: "POST", body: "{}" }),
  submissions: (challengeId: string, offset = 0, limit = 20, signal?: AbortSignal) =>
    apiFetch<Page<Submission>>(`/api/practice/submissions${q({ challenge_id: challengeId, limit, offset })}`, { signal }),
  submit: (id: string, revision: number, body: string, result_url?: string) =>
    apiFetch<Submission>(`/api/practice/mine/${encodeURIComponent(id)}/submit`, {
      method: "POST", body: JSON.stringify({ revision, body, ...(result_url ? { result_url } : {}) }),
    }),
  submission: (id: string, signal?: AbortSignal) =>
    apiFetch<Submission>(`/api/practice/submissions/${encodeURIComponent(id)}`, { signal }),
  replies: (id: string, offset = 0, limit = 20, signal?: AbortSignal) =>
    apiFetch<Page<Reply>>(`/api/practice/submissions/${encodeURIComponent(id)}/replies${q({ limit, offset })}`, { signal }),
  reply: (id: string, text: string, client_id: string) =>
    apiFetch<Reply>(`/api/practice/submissions/${encodeURIComponent(id)}/replies`, { method: "POST", body: JSON.stringify({ text, client_id }) }),
};
