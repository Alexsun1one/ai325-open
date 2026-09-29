import { API_BASE, apiFetch, getToken } from "./auth";

/** 兼容旧组件入口，复用请求超时、认证和错误处理。 */
export const API = API_BASE;
export function token(): string | null { return getToken() || null; }
export async function api<T>(path: string, init?: RequestInit & { auth?: boolean }): Promise<T> {
  return apiFetch<T>(path, init);
}
