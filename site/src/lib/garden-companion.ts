"use client";
import { apiFetch } from "@/lib/auth";

/** GARDEN-COMPANION R1 契约（.fleet/growth-content-20260924/garden-companion-contract.md）。
 *  仅本人：匿名 401 / Agent 403；no-store。护法/图鉴/成就/足迹全部来自服务端聚合，前端不写死。 */

export interface GuardianOption { id: string; name: string; species: string; tagline: string; sprite: string }
export type WatchKind = "no_garden" | "ripe" | "empty" | "waiting";
export interface GuardianWatch {
  guardian_id: string; kind: WatchKind; message: string;
  situation: { plot_count: number; ripe: number; growing: number; empty: number; next_ripe_at: string | null };
}
export interface CompanionGuardian {
  note: string; options: GuardianOption[]; selected_id: string | null; watch: GuardianWatch | null;
}

export type CodexStatus = "locked" | "planted" | "harvested";
export interface CodexCrop {
  id: string; name: string; duration_seconds: number; yield: number; status: CodexStatus;
  planted: number; harvested: number; harvested_amount: number; first_planted_at: string | null;
}
export interface Milestone {
  id: string; title: string; description: string; kind: string;
  value: number; target: number; unlocked: boolean; unlocked_at: string | null;
}
export interface FootprintDay { date: string; planted: number; harvested: number; harvested_amount: number }

export interface CompanionResponse {
  server_now: string;
  garden_open: boolean;
  guardian: CompanionGuardian;
  protection: { steal_fraction: number; steal_amount: number };
  codex: { unlocked: number; total: number; crops: CodexCrop[] };
  milestones: { unlocked: number; total: number; items: Milestone[] };
  footprint: {
    timezone: string; days: FootprintDay[];
    totals: { planted: number; harvested: number; harvested_amount: number };
  };
}

export const gardenCompanionApi = {
  get: (signal?: AbortSignal) =>
    apiFetch<CompanionResponse>("/api/garden/companion", { signal }),
  setGuardian: (guardian_id: string | null) =>
    apiFetch<CompanionResponse>("/api/garden/companion", { method: "PATCH", body: JSON.stringify({ guardian_id }) }),
};
