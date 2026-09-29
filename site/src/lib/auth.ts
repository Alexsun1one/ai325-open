"use client";
import { useCallback, useEffect, useSyncExternalStore } from "react";

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
export async function apiFetch<T>(path: string, init: RequestInit & { timeoutMs?: number; auth?: boolean } = {}): Promise<T> {
  const { timeoutMs = 15000, signal, auth = true, ...requestInit } = init;
  const token = getToken();
  const headers = new Headers(init.headers);
  if (!headers.has("content-type") && init.body) headers.set("content-type", "application/json");
  if (auth && token) headers.set("authorization", `Bearer ${token}`);
  const controller = new AbortController();
  const cancel = () => controller.abort();
  if (signal?.aborted) cancel();
  else signal?.addEventListener("abort", cancel, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, { ...requestInit, headers, signal: controller.signal });
    if (!res.ok) {
      let detail = res.status === 404 ? "这个还没准备好。" : res.status >= 500 ? "服务器那边出问题了，等会儿再试。" : `没成功（${res.status}）`;
      try { const j = await res.json(); if (j?.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch {}
      if (timedOut) throw new ApiError(0, "请求超时，请稍后重试。");
      throw new ApiError(res.status, detail);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError(0, timedOut ? "请求超时，请稍后重试。" : signal?.aborted ? "请求已取消。" : "连不上服务器，等会儿再试试。");
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", cancel);
  }
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
export interface AuthState { status: AuthStatus; user: User | null; netErr: string }

/** 全站共享一份会话：任何组件 signIn/signOut/验票结果，所有 useAuth 消费者同步更新。 */
let authState: AuthState = { status: "loading", user: null, netErr: "" };
const authSubs = new Set<() => void>();
function setAuthState(next: AuthState) { authState = next; authSubs.forEach((f) => f()); }

let authGen = 0;                          // 世代号：每次换票/登录/退出递增，旧时代的响应不得落状态
let authInflight: Promise<void> | null = null;
let authInflightToken = "";               // inflight 捕获的票；换票后不共享旧票 inflight
let authInflightGen = -1;                 // inflight 捕获的世代；换代后同票也不得共享旧任务

// 另一标签页登录/退出时同步本页：store 级单一监听（多消费者共享），一次事件只换代一次
let storageListener: ((e: StorageEvent) => void) | null = null;
function onAuthStorage(e: StorageEvent) {
  if (e.key !== TOKEN_KEY && e.key !== null) return;
  authGen += 1;
  setAuthState({ status: "loading", user: null, netErr: "" });
  void checkAuth(true);
}

function subscribeAuth(cb: () => void) {
  authSubs.add(cb);
  if (authSubs.size === 1 && typeof window !== "undefined" && !storageListener) {
    storageListener = onAuthStorage;
    window.addEventListener("storage", storageListener);
  }
  return () => {
    authSubs.delete(cb);
    if (authSubs.size === 0 && storageListener) {
      window.removeEventListener("storage", storageListener);
      storageListener = null;
    }
  };
}

/** 验票。同票并发共享一次请求；401/403 才清票，超时/断网保留 token 只报 netErr。
 *  世代+捕获票双护栏：响应落状态前要求 gen 未变且当前票===捕获票——
 *  signOut/新 signIn/跨标签换票期间的旧 /me 响应一律丢弃，旧 401 也清不到新票。 */
export function checkAuth(force = false): Promise<void> {
  const token = getToken();
  if (authInflight && authInflightToken === token && authInflightGen === authGen) return authInflight;
  if (!force && authState.status !== "loading") return Promise.resolve();
  const gen = authGen;
  authInflightToken = token;
  authInflightGen = gen;
  const task = (async () => {
    if (!token) { if (gen === authGen) setAuthState({ status: "out", user: null, netErr: "" }); return; }
    try {
      const u = await apiFetch<User>("/api/auth/me");
      if (gen !== authGen || getToken() !== token) return;
      setAuthState({ status: "in", user: u, netErr: "" });
    } catch (e) {
      if (gen !== authGen || getToken() !== token) return;
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
        clearToken();
        setAuthState({ status: "out", user: null, netErr: "" });
      } else {
        setAuthState({ status: "out", user: null, netErr: e instanceof ApiError ? e.message : "暂时连不上服务器。" });
      }
    }
  })();
  authInflight = task;
  void task.finally(() => { if (authInflight === task) authInflight = null; });
  return task;
}

/** 登录态。静态导出没有服务端会话，只能上来先问一次 /api/auth/me 验票；之后所有实例共享同一份状态。 */
export function useAuth() {
  const snap = useSyncExternalStore(
    subscribeAuth,
    () => authState,
    () => authState,
  );
  useEffect(() => { void checkAuth(); }, []);

  const signIn = useCallback(async (u: string, p: string) => { const me = await login(u, p); authGen += 1; setAuthState({ status: "in", user: me, netErr: "" }); }, []);
  const signUp = useCallback(async (u: string, p: string, code: string, name?: string) => { await register(u, p, code, name); const me = await login(u, p); authGen += 1; setAuthState({ status: "in", user: me, netErr: "" }); }, []);
  const signOut = useCallback(async () => { authGen += 1; try { await logout(); } finally { setAuthState({ status: "out", user: null, netErr: "" }); } }, []);
  const refresh = useCallback(() => checkAuth(true), []);

  return { status: snap.status, user: snap.user, netErr: snap.netErr, signIn, signUp, signOut, refresh };
}
