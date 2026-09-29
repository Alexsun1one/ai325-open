"use client";
import { apiFetch } from "@/lib/auth";

/** GARDEN R1 冻结契约（.fleet/growth-content-20260924/garden-contract.md）。
 *  家园/偷菜：真人成员 session，匿名 401 / Agent 403；所有响应 no-store。
 *  全部时间、数量、保护规则以服务端返回为准，前端不写死。 */

export interface Crop { id: string; name: string; duration_seconds: number; yield: number }
export interface GardenRules { plot_count: number; steal_amount: number; steal_fraction: number; crops: Crop[] }
export interface GardenOwner { name: string; member_key: string | null }

export type PlotState = "empty" | "growing" | "ripe";
export interface Plot {
  id: number; cycle_id: string | null; crop_id: string | null; state: PlotState;
  planted_at: string | null; ripe_at: string | null;
  yield: number; stolen: number; protected_yield: number; can_steal: boolean;
}

export type GardenVisibility = "private" | "members";
export interface Garden {
  id: string; owner: GardenOwner; is_mine: boolean; visibility: GardenVisibility;
  harvest_total: number; plots: Plot[]; created_at: string;
}

export interface GardenResponse { garden: Garden | null; rules: GardenRules; server_now: string }

export type GardenEventKind = "plant" | "harvest" | "steal" | "visibility";
export interface GardenEvent {
  id: string; kind: GardenEventKind; actor: GardenOwner;
  plot_id: number | null; crop_name: string | null; amount: number; created_at: string;
}

export interface GardenAction { id: string; kind: "plant" | "harvest" | "steal"; amount: number }
export type GardenActionResponse = GardenResponse & { action: GardenAction; replayed: boolean };

export interface NeighborItem { id: string; owner: GardenOwner; ripe_count: number; harvest_total: number }
export interface NeighborPage { items: NeighborItem[]; total: number; limit: number; offset: number; server_now: string }
export interface GardenEventPage { items: GardenEvent[]; total: number; limit: number; offset: number }

const q = (o: Record<string, string | number>) => "?" + Object.entries(o).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");

/** 幂等 client_id：同一操作意图重试复用同一个，成功后换新。 */
export function newClientId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
}

export const gardenApi = {
  mine: (signal?: AbortSignal) =>
    apiFetch<GardenResponse>("/api/garden/mine", { signal }),
  create: (client_id: string) =>
    apiFetch<GardenResponse>("/api/garden/mine", { method: "POST", body: JSON.stringify({ client_id }) }),
  setVisibility: (visibility: GardenVisibility, client_id: string) =>
    apiFetch<GardenResponse>("/api/garden/mine", { method: "PATCH", body: JSON.stringify({ visibility, client_id }) }),
  plant: (plot_id: number, crop_id: string, client_id: string) =>
    apiFetch<GardenActionResponse>("/api/garden/mine/plant", { method: "POST", body: JSON.stringify({ plot_id, crop_id, client_id }) }),
  harvest: (plot_id: number, cycle_id: string, client_id: string) =>
    apiFetch<GardenActionResponse>("/api/garden/mine/harvest", { method: "POST", body: JSON.stringify({ plot_id, cycle_id, client_id }) }),
  neighbors: (offset = 0, limit = 12, signal?: AbortSignal) =>
    apiFetch<NeighborPage>(`/api/garden/neighbors${q({ limit, offset })}`, { signal }),
  visit: (id: string, signal?: AbortSignal) =>
    apiFetch<GardenResponse>(`/api/garden/visit/${encodeURIComponent(id)}`, { signal }),
  steal: (id: string, plot_id: number, cycle_id: string, client_id: string) =>
    apiFetch<GardenActionResponse>(`/api/garden/visit/${encodeURIComponent(id)}/steal`, { method: "POST", body: JSON.stringify({ plot_id, cycle_id, client_id }) }),
  events: (id: string, offset = 0, limit = 12, signal?: AbortSignal) =>
    apiFetch<GardenEventPage>(`/api/garden/${encodeURIComponent(id)}/events${q({ limit, offset })}`, { signal }),
};
