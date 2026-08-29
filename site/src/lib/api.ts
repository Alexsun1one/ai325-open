/** 与 FastAPI 后端的最小接线：同源 /api；静态站被挂在同一容器下。 */
export const API = process.env.NEXT_PUBLIC_API_BASE ?? "";
export function token(): string | null { try { return localStorage.getItem("xf-token"); } catch { return null; } }
export async function api<T>(path: string, init?: RequestInit & { auth?: boolean }): Promise<T> {
  const h: Record<string, string> = { "Content-Type": "application/json", ...(init?.headers as Record<string, string> | undefined) };
  const t = token(); if (init?.auth !== false && t) h.Authorization = `Bearer ${t}`;
  const r = await fetch(`${API}${path}`, { ...init, headers: h });
  if (!r.ok) { let d: unknown = null; try { d = await r.json(); } catch {} const msg = (d as { detail?: string } | null)?.detail || `HTTP ${r.status}`; const e = new Error(msg) as Error & { status: number }; e.status = r.status; throw e; }
  return r.json() as Promise<T>;
}
