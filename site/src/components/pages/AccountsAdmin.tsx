"use client";
import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch, useAuth } from "@/lib/auth";
import { Btn, Note } from "./FormBits";

/** 形状对齐 app/main.py 的真实实现：
 *  GET  /api/admin/member-accounts → { items: [{member_key, display, msgs, last_active, account|null}], unbound: [{id, username, ...}] }
 *  POST /api/admin/member-accounts {member_key, username} → { username, display_name, password }  // 密码只回这一次
 *  POST /api/admin/member-accounts/{id}/reset-password → { username, password }
 *  POST /api/admin/member-accounts/{id}/revoke | /activate → { ok }
 *  POST /api/admin/member-accounts/{id}/bind {member_key} → { ok, display_name }
 */
export interface Account { id: number; username: string; display_name: string; role: string; created_at?: string; last_login?: string | null; active: number; member_key?: string | null }
interface Item { member_key: string; display: string; nickname?: string; msgs?: number; last_active?: string | null; account: Account | null }
interface Payload { items: Item[]; unbound: Account[] }
interface PwBox { title: string; username: string; password: string; display_name?: string }
/** 认领链接弹窗：一次性，只显示一次。契约：POST /api/admin/member-accounts/{member_key}/claim-link → { token, expires_at } */
interface LinkBox { title: string; name: string; url: string; expires?: string }
/** 契约（backend 车道实现，见报告契约缺口节）：GET /api/admin/agents → { items: [{id, user_id, username, name, token_prefix, created_at, last_used_at, revoked}] } */
interface AdminAgent { id: number; user_id: number; username: string; name: string; token_prefix?: string; created_at?: string; last_used_at?: string | null; revoked?: boolean }

const rawId = (s: string) => s.startsWith("wxid_") || s.startsWith("gh_");

function AgentRow({ a, onRevoke, busy }: { a: AdminAgent; onRevoke: (id: number) => void; busy: boolean }) {
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1.5 py-2">
      <span aria-hidden className="relative inline-flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full border border-amber-deep/70 bg-amber-wash/30">
        <span aria-hidden className="absolute inset-[2px] rounded-full border border-amber-deep/35" />
        <span className="font-serif text-[9px] font-bold text-amber-text">徒</span>
      </span>
      <span className="font-sans text-[13px] font-semibold text-ink">{a.name}</span>
      {a.revoked && <span className="rounded-[3px] border border-rule bg-paper-2 px-1.5 py-[1px] font-sans text-[10px] text-ink-3">已吊销</span>}
      <span className="num font-sans text-[11.5px] text-ink-3">活跃 {a.last_used_at ? a.last_used_at.replace("T", " ").slice(5, 16) : "从未"}</span>
      {!a.revoked && (
        <button type="button" disabled={busy} onClick={() => onRevoke(a.id)}
          className="ml-auto rounded-[4px] border border-cinnabar/45 bg-paper px-2 py-1 font-sans text-[11.5px] font-semibold text-cinnabar-text transition-colors hover:bg-cinnabar-wash disabled:opacity-50">吊销</button>
      )}
    </li>
  );
}

function Apprentices({ userId, agents, onRevoke, busy }: { userId: number; agents: AdminAgent[]; onRevoke: (id: number) => void; busy: boolean }) {
  const mine = agents.filter((a) => a.user_id === userId);
  if (!mine.length) return null;
  return (
    <details className="mt-2 rounded-[6px] border border-amber-deep/30 bg-amber-wash/15 px-3 py-2">
      <summary className="cursor-pointer list-none font-sans text-[12px] font-semibold text-amber-text">
        学徒 {mine.length} 名 · {mine.filter((a) => !a.revoked).length} 名在住
      </summary>
      <ul className="mt-1 divide-y divide-rule-soft">
        {mine.map((a) => <AgentRow key={a.id} a={a} onRevoke={onRevoke} busy={busy} />)}
      </ul>
    </details>
  );
}

export function AccountsAdmin() {
  const { status, user } = useAuth();
  const [data, setData] = useState<Payload | null>(null);
  const [agents, setAgents] = useState<AdminAgent[] | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState<{ tone: "good" | "bad"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [pw, setPw] = useState<PwBox | null>(null);
  const [link, setLink] = useState<LinkBox | null>(null);
  const [un, setUn] = useState<Record<string, string>>({});
  const [bindSel, setBindSel] = useState<Record<number, string>>({});
  const [bindErr, setBindErr] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    try { setData(await apiFetch<Payload>("/api/admin/member-accounts")); setErr(""); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "读取失败"); }
    try { setAgents(await apiFetch<{ items: AdminAgent[] }>("/api/admin/agents").then((d) => d.items ?? [])); }
    catch { setAgents([]); }
  }, []);

  useEffect(() => { if (status === "in" && user?.role === "admin") void load(); }, [status, user?.role, load]);

  if (status === "loading") return <p className="py-10 font-sans text-[14px] text-ink-3">正在验票……</p>;
  if (status === "out") return <Note tone="bad">请先登录。这一页只对群主（admin）开放。</Note>;
  if (user?.role !== "admin") return <Note tone="bad">这页只对群主开放，你的账号没有这个权限。</Note>;
  if (err) return <Note tone="bad">{err}</Note>;
  if (!data) return <p className="py-10 font-sans text-[14px] text-ink-3">正在读取成员与账号……</p>;

  const doGen = async (mk: string) => {
    setBusy(true); setMsg(null);
    try {
      const it = data?.items.find((x) => x.member_key === mk);
      const fallback = (it?.display || mk).replace(/\s+/g, "");
      const username = (un[mk] ?? fallback).trim();
      const d = await apiFetch<{ username: string; password: string; display_name: string }>("/api/admin/member-accounts", {
        method: "POST", body: JSON.stringify({ member_key: mk, username }),
      });
      setPw({ title: "账号已生成", username: d.username, password: d.password, display_name: d.display_name });
      void load();
    } catch (e) { setMsg({ tone: "bad", text: e instanceof ApiError ? e.message : "生成失败" }); }
    finally { setBusy(false); }
  };
  const doReset = async (a: Account) => {
    setBusy(true); setMsg(null);
    try {
      const d = await apiFetch<{ username: string; password: string }>(`/api/admin/member-accounts/${a.id}/reset-password`, { method: "POST" });
      setPw({ title: "密码已重置", username: d.username, password: d.password, display_name: a.display_name });
    } catch (e) { setMsg({ tone: "bad", text: e instanceof ApiError ? e.message : "重置失败" }); }
    finally { setBusy(false); }
  };
  const doToggle = async (a: Account, act: "revoke" | "activate") => {
    setBusy(true); setMsg(null);
    try { await apiFetch(`/api/admin/member-accounts/${a.id}/${act}`, { method: "POST" }); setMsg({ tone: "good", text: act === "revoke" ? `已禁用 ${a.username}` : `已启用 ${a.username}` }); void load(); }
    catch (e) { setMsg({ tone: "bad", text: e instanceof ApiError ? e.message : "操作失败" }); }
    finally { setBusy(false); }
  };
  const doBind = async (a: Account) => {
    const mk = bindSel[a.id]; if (!mk) return;
    setBusy(true); setMsg(null); setBindErr((v) => ({ ...v, [a.id]: "" }));
    try {
      const d = await apiFetch<{ display_name: string }>(`/api/admin/member-accounts/${a.id}/bind`, { method: "POST", body: JSON.stringify({ member_key: mk }) });
      setMsg({ tone: "good", text: `已把 ${a.username} 绑到 ${d.display_name}` });
      void load();
    } catch (e) { setBindErr((v) => ({ ...v, [a.id]: e instanceof ApiError ? e.message : "绑定失败" })); }
    finally { setBusy(false); }
  };
  const doRevokeAgent = async (tokenId: number) => {
    setBusy(true); setMsg(null);
    try { await apiFetch(`/api/agent/tokens/${tokenId}`, { method: "DELETE" }); setMsg({ tone: "good", text: "学徒钥匙已吊销，它立刻进不来了。" }); void load(); }
    catch (e) { setMsg({ tone: "bad", text: e instanceof ApiError ? e.message : "吊销失败（该接口当前只允许本人操作，等 backend 放开 admin）" }); }
    finally { setBusy(false); }
  };
  /** 单个认领链接（契约：POST /api/admin/member-accounts/{member_key}/claim-link，body {username?}；
   *  已有账号直接出链，未生成账号先建号（无密码态）再出链——一步完成）。 */
  const doClaimLink = async (mk: string) => {
    setBusy(true); setMsg(null);
    try {
      const it = data?.items.find((x) => x.member_key === mk);
      const fallback = (it?.display || mk).replace(/\s+/g, "");
      const body = it?.account ? {} : { username: (un[mk] ?? fallback).trim() };
      const d = await apiFetch<{ claim_token?: string; claim_url?: string; token?: string; expires_at?: string }>(`/api/admin/member-accounts/${encodeURIComponent(mk)}/claim-link`, { method: "POST", body: JSON.stringify(body) });
      const base = typeof window !== "undefined" ? window.location.origin : "https://www.ai325.com";
      const tok = d.claim_token ?? d.token;
      const url = d.claim_url ? `${base}${d.claim_url}` : tok ? `${base}/claim/?t=${encodeURIComponent(tok)}` : null;
      if (!url) throw new ApiError(0, "后端没返回链接");
      setLink({ title: it?.account ? "认领链接" : "账号已建，认领链接", name: it?.display || mk, url, expires: d.expires_at });
      void load();
    } catch (e) { setMsg({ tone: "bad", text: e instanceof ApiError ? e.message : "链接没发出来" }); }
    finally { setBusy(false); }
  };

  const candidates = data.items.filter((it) => !it.account);
  const unbound = data.unbound ?? [];

  return (
    <div>
      {msg && <div className="mb-5"><Note tone={msg.tone}>{msg.text}</Note></div>}

      {unbound.length > 0 && (
        <section className="mb-12">
          <h3 className="font-serif text-[19px] font-bold text-ink">已注册但没对上微信的账号</h3>
          <p className="mt-1 max-w-[46em] font-sans text-[13.5px] leading-relaxed text-ink-2">注册时没选群昵称、或名单里还没有他。在这里把账号绑到对应群成员，登录头像和发言归属就能对上。</p>
          <div className="mt-4 divide-y divide-rule-soft border-y border-rule">
            {unbound.map((a) => (
              <div key={a.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3.5">
                <div className="min-w-0 flex-1">
                  <div className="font-sans text-[14px] font-semibold text-ink">{a.username}</div>
                  <div className="mt-0.5 font-sans text-[12px] text-ink-3">注册于 {a.created_at?.slice(0, 10) ?? "—"}{a.last_login ? ` · 最近登录 ${a.last_login.slice(0, 10)}` : " · 还没登录过"}</div>
                </div>
                <select value={bindSel[a.id] ?? ""} onChange={(e) => setBindSel((v) => ({ ...v, [a.id]: e.target.value }))}
                  className="min-h-10 w-52 rounded-[4px] border border-rule bg-paper px-2 py-1.5 font-sans text-[13px] text-ink outline-none focus:border-blue-2">
                  <option value="">选择群成员…</option>
                  {candidates.map((it) => <option key={it.member_key} value={it.member_key}>{rawId(it.display) ? `${it.display}（昵称未解析）` : it.display}</option>)}
                </select>
                <Btn type="button" tone="ghost" busy={busy} onClick={() => void doBind(a)}>绑定</Btn>
                {bindErr[a.id] && <span className="font-sans text-[12px] text-cinnabar-text">{bindErr[a.id]}</span>}
                <div className="w-full">
                  <Apprentices userId={a.id} agents={agents ?? []} onRevoke={doRevokeAgent} busy={busy} />
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <h3 className="font-serif text-[19px] font-bold text-ink">群成员 → 账号</h3>
        <p className="mt-1 max-w-[46em] font-sans text-[13.5px] leading-relaxed text-ink-2">给群成员发账号：生成时填个用户名（默认用群昵称），密码只显示这一次。禁用的账号登录会被挡下，重置密码会踢掉旧登录。</p>
        <div className="mt-4 divide-y divide-rule-soft border-y border-rule">
          {data.items.map((it) => {
            const a = it.account; const dis = it.display || it.member_key;
            return (
              <div key={it.member_key} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3.5">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                    <span className="font-serif text-[15px] font-bold text-ink">{dis}</span>
                    {rawId(it.display) && <span className="rounded-[3px] border border-rule bg-paper-2 px-1.5 py-[1px] font-sans text-[10.5px] text-ink-3">昵称未解析</span>}
                    {a && !a.active && <span className="rounded-[3px] border border-cinnabar/40 bg-cinnabar-wash px-1.5 py-[1px] font-sans text-[10.5px] font-semibold text-cinnabar-text">已禁用</span>}
                  </div>
                  <div className="mt-0.5 font-sans text-[12px] text-ink-3">
                    {it.msgs ?? 0} 条 · {it.last_active ?? "—"}{a ? ` · ${a.username}` : ""}{a?.last_login ? ` · 最近登录 ${a.last_login.slice(0, 10)}` : a ? " · 还没登录过" : ""}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {!a ? (
                    <>
                      <input value={un[it.member_key] ?? dis.replace(/\s+/g, "")} onChange={(e) => setUn((v) => ({ ...v, [it.member_key]: e.target.value }))}
                        placeholder="用户名" aria-label={`${dis} 的用户名`}
                        className="min-h-10 w-40 rounded-[4px] border border-rule bg-paper px-2.5 py-1.5 font-sans text-[13px] text-ink outline-none placeholder:text-ink-3/70 focus:border-blue-2" />
                      <Btn type="button" busy={busy} onClick={() => void doClaimLink(it.member_key)}>建号 · 出认领链接</Btn>
                      <Btn type="button" tone="ghost" busy={busy} onClick={() => void doGen(it.member_key)}>生成密码账号</Btn>
                    </>
                  ) : a.role === "admin" ? (
                    <span className="rounded-[3px] border border-blue-wash-2 bg-blue-wash px-2 py-1 font-sans text-[11.5px] text-blue-text">管理员</span>
                  ) : (
                    <>
                      <Btn type="button" tone="ghost" busy={busy} onClick={() => void doClaimLink(it.member_key)}>认领链接</Btn>
                      <Btn type="button" tone="ghost" busy={busy} onClick={() => void doReset(a)}>重置密码</Btn>
                      <Btn type="button" tone={a.active ? "danger" : "ghost"} busy={busy} onClick={() => void doToggle(a, a.active ? "revoke" : "activate")}>{a.active ? "禁用" : "启用"}</Btn>
                    </>
                  )}
                </div>
                {a && a.role !== "admin" && (
                  <div className="w-full">
                    <Apprentices userId={a.id} agents={agents ?? []} onRevoke={doRevokeAgent} busy={busy} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {pw && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/45 px-4" onClick={() => setPw(null)}>
          <div className="w-full max-w-[400px] rounded-[12px] border border-rule bg-paper p-6 shadow-[var(--shadow-pop)]" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-serif text-[20px] font-bold text-ink">{pw.title}</h3>
            {pw.display_name && <div className="mt-4 flex items-baseline gap-2"><span className="label">成员</span><span className="font-sans text-[14px] text-ink">{pw.display_name}</span></div>}
            <div className="mt-3 flex items-baseline gap-2"><span className="label">用户名</span><span className="num font-sans text-[15px] font-semibold text-ink">{pw.username}</span></div>
            <div className="mt-3 flex items-baseline gap-2"><span className="label">密码</span><span className="num font-sans text-[15px] font-semibold text-blue-text">{pw.password}</span></div>
            <p className="mt-4 font-sans text-[12.5px] leading-relaxed text-ink-3">密码只显示这一次。复制后交给本人，提醒他登录后改密码。</p>
            <div className="mt-5 flex gap-2">
              <Btn type="button" onClick={() => { void navigator.clipboard?.writeText(pw.password); }}>复制密码</Btn>
              <Btn type="button" tone="ghost" onClick={() => setPw(null)}>关 闭</Btn>
            </div>
          </div>
        </div>
      )}

      {link && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/45 px-4" onClick={() => setLink(null)}>
          <div className="w-full max-w-[460px] rounded-[12px] border border-rule bg-paper p-6 shadow-[var(--shadow-pop)]" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-serif text-[20px] font-bold text-ink">{link.title}</h3>
            <div className="mt-4 flex items-baseline gap-2"><span className="label">给</span><span className="font-sans text-[14px] text-ink">{link.name}</span></div>
            <div className="mt-3 rounded-[6px] border border-amber-deep/40 bg-amber-wash/40 px-3 py-2.5">
              <div className="label mb-1">把这条发给他（一次性，只显示这一次）</div>
              <div className="break-all font-sans text-[13.5px] leading-relaxed text-ink">{link.url}</div>
            </div>
            {link.expires && <p className="mt-3 font-sans text-[12px] text-ink-3">{`${new Date(link.expires).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })} 前有效，点开即用，用过就失效。`}</p>}
            <p className="mt-2 font-sans text-[12px] leading-relaxed text-ink-3">对方点开就能登录；第一次进来会让他顺手设个密码。设完之前，他只能用这条链接进。</p>
            <div className="mt-5 flex gap-2">
              <Btn type="button" onClick={() => { void navigator.clipboard?.writeText(link.url); }}>复制链接</Btn>
              <Btn type="button" tone="ghost" onClick={() => setLink(null)}>关 闭</Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
