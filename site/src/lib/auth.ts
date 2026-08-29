"use client";
import { useCallback, useEffect, useState } from "react";

/** 同源部署：静态导出由后端 FastAPI 一并伺服，所以默认空前缀。本地联调可用 NEXT_PUBLIC_API_BASE 指到后端。 */
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";
export const TOKEN_KEY = "xf-token";
// 邀请码由群主在后台逐个发放（可撤销），前端不持有、不展示任何码。

export interface User { id?: number; username: string; role?: string; display_name?: string }

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

export function getToken(): string {
  if (typeof window === "undefined") return "";
  try { return localStorage.getItem(TOKEN_KEY) ?? ""; } catch { return ""; }
}
function setToken(t: string) { try { localStorage.setItem(TOKEN_KEY, t); } catch {} }
function clearToken() { try { localStorage.removeItem(TOKEN_KEY); } catch {} }

/** 带 Bearer 的 fetch。非 2xx 一律抛 ApiError，调用方自己决定怎么展示——不静默吞错。 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (!headers.has("content-type") && init.body) headers.set("content-type", "application/json");
  if (token) headers.set("authorization", `Bearer ${token}`);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "连不上服务器，等会儿再试试。");
  }
  if (!res.ok) {
    let detail = res.status === 404 ? "这个还没准备好。" : res.status >= 500 ? "服务器那边出问题了，等会儿再试。" : `没成功（${res.status}）`;
    try { const j = await res.json(); if (j?.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch {}
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function login(username: string, password: string): Promise<User> {
  const r = await apiFetch<{ token: string } & User>("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
  setToken(r.token);
  return { username: r.username, role: r.role, display_name: r.display_name };
}

export async function register(username: string, password: string, invite_code: string, display_name = ""): Promise<void> {
  await apiFetch<{ ok: boolean }>("/api/auth/register", { method: "POST", body: JSON.stringify({ username, password, invite_code, display_name }) });
}

export async function logout(): Promise<void> {
  try { await apiFetch("/api/auth/logout", { method: "POST" }); } catch {}
  clearToken();
}

export type AuthStatus = "loading" | "out" | "in";

/** 登录态。静态导出没有服务端会话，只能上来先问一次 /api/auth/me 验票。 */
export function useAuth() {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<User | null>(null);

  const check = useCallback(async () => {
    if (!getToken()) { setUser(null); setStatus("out"); return; }
    try {
      const u = await apiFetch<User>("/api/auth/me");
      setUser(u); setStatus("in");
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) clearToken();
      setUser(null); setStatus("out");
    }
  }, []);

  useEffect(() => { void check(); }, [check]);

  const signIn = useCallback(async (u: string, p: string) => { const me = await login(u, p); setUser(me); setStatus("in"); }, []);
  const signUp = useCallback(async (u: string, p: string, code: string, name?: string) => { await register(u, p, code, name); await login(u, p); await check(); }, [check]);
  const signOut = useCallback(async () => { await logout(); setUser(null); setStatus("out"); }, []);

  return { status, user, signIn, signUp, signOut, refresh: check };
}
