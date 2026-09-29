"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, apiFetch } from "@/lib/auth";
import { Btn, Note } from "./FormBits";

interface Account {
  id: number;
  username: string;
  active: boolean;
  last_login?: string | null;
  role?: string;
}
interface MemberRow {
  member_key: string;
  display: string;
  msgs: number;
  last_active: string | null;
  has_account: boolean;
  account: Account | null;
  unresolved: boolean;
  agent_count: number;
  activity: string;
  flags: string[];
}
interface MembersPayload {
  as_of: string;
  total: number;
  shown: number;
  truncated: boolean;
  filters: { has_account: number; no_account: number; unresolved: number; has_agents: number; active_7d: number; quiet: number };
  items: MemberRow[];
}
interface LinkBox { title: string; name: string; url: string; expires?: string }
interface PwBox { title: string; username: string; password: string; display_name?: string }

type FilterKey = "all" | "no_account" | "has_account" | "unresolved" | "has_agents" | "active_7d" | "quiet";

const rawId = (s: string) => s.startsWith("wxid_") || s.startsWith("gh_");

export function AdminOpsMembers() {
  const [data, setData] = useState<MembersPayload | null>(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "good" | "bad"; text: string } | null>(null);
  const [marked, setMarked] = useState<Record<string, boolean>>({});
  const [link, setLink] = useState<LinkBox | null>(null);
  const [pw, setPw] = useState<PwBox | null>(null);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    if (filter === "no_account") params.set("has_account", "false");
    if (filter === "has_account") params.set("has_account", "true");
    if (filter === "unresolved") params.set("unresolved", "true");
    if (filter === "has_agents") params.set("has_agents", "true");
    if (filter === "active_7d" || filter === "quiet") params.set("activity", filter);
    params.set("limit", "200");
    return `/api/admin/members?${params.toString()}`;
  }, [q, filter]);

  const load = useCallback(async () => {
    try { setData(await apiFetch<MembersPayload>(query)); setErr(""); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "成员表读不到"); }
  }, [query]);
  useEffect(() => { void load(); }, [load]);

  const doClaimLink = async (row: MemberRow) => {
    setBusy(true); setMsg(null);
    try {
      const d = await apiFetch<{ claim_token?: string; claim_url?: string; token?: string; expires_at?: string }>(
        `/api/admin/member-accounts/${encodeURIComponent(row.member_key)}/claim-link`,
        { method: "POST", body: JSON.stringify({}) },
      );
      const base = typeof window !== "undefined" ? window.location.origin : "https://www.ai325.com";
      const tok = d.claim_token ?? d.token;
      const url = d.claim_url ? `${base}${d.claim_url}` : tok ? `${base}/claim/?t=${encodeURIComponent(tok)}` : null;
      if (!url) throw new ApiError(0, "后端没返回链接");
      setLink({ title: "认领链接", name: row.display, url, expires: d.expires_at });
      void load();
    } catch (e) { setMsg({ tone: "bad", text: e instanceof ApiError ? e.message : "链接没发出来" }); }
    finally { setBusy(false); }
  };
  const doGen = async (row: MemberRow) => {
    setBusy(true); setMsg(null);
    try {
      const d = await apiFetch<{ username: string; password: string; display_name: string }>("/api/admin/member-accounts", {
        method: "POST", body: JSON.stringify({ member_key: row.member_key, username: row.display.replace(/\s+/g, "") }),
      });
      setPw({ title: "账号已生成", username: d.username, password: d.password, display_name: d.display_name });
      void load();
    } catch (e) { setMsg({ tone: "bad", text: e instanceof ApiError ? e.message : "生成失败" }); }
    finally { setBusy(false); }
  };
  const doToggle = async (row: MemberRow, act: "revoke" | "activate") => {
    const id = row.account?.id; if (!id) return;
    setBusy(true); setMsg(null);
    try {
      await apiFetch(`/api/admin/member-accounts/${id}/${act}`, { method: "POST" });
      setMsg({ tone: "good", text: act === "revoke" ? `已禁用 ${row.display}` : `已启用 ${row.display}` });
      void load();
    } catch (e) { setMsg({ tone: "bad", text: e instanceof ApiError ? e.message : "操作失败" }); }
    finally { setBusy(false); }
  };

  const exportMarked = () => {
    const rows = (data?.items ?? []).filter((row) => marked[row.member_key]);
    const lines = rows.map((row) => `${row.display}\t${row.has_account ? "有账号" : "无账号"}\t${row.last_active ?? "—"}`);
    const blob = new Blob([`显示名\t账号\t最近活跃\n${lines.join("\n")}`], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "ops-member-mark.txt";
    a.click();
  };

  if (err && !data) return <Note tone="bad">{err}</Note>;
  if (!data) return <p className="py-6 font-sans text-[13.5px] text-ink-3">正在取成员表格……</p>;

  const f = data.filters;
  const chips: { key: FilterKey; label: string }[] = [
    { key: "all", label: "全部" },
    { key: "no_account", label: `无账号 ${f.no_account}` },
    { key: "has_account", label: `有账号 ${f.has_account}` },
    { key: "unresolved", label: `身份未解析 ${f.unresolved}` },
    { key: "has_agents", label: `有学徒 ${f.has_agents}` },
    { key: "active_7d", label: `近 7 日活跃 ${f.active_7d}` },
    { key: "quiet", label: `不活跃 ${f.quiet}` },
  ];
  const markedN = Object.values(marked).filter(Boolean).length;

  return (
    <section>
      <h3 className="font-serif text-[19px] font-bold text-ink">成员表格</h3>
      <p className="mt-1 max-w-[46em] font-sans text-[13.5px] leading-relaxed text-ink-2">
        搜索、筛选后做单人操作。{data.truncated ? `前 ${data.shown} 条，筛选后共 ${data.total} 人。` : `共 ${data.total} 人。`}
        批量只许标记/导出清单，不出认领链接。
      </p>
      {msg && <div className="mt-3"><Note tone={msg.tone}>{msg.text}</Note></div>}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜显示名…" aria-label="搜索成员"
          className="min-h-11 w-52 rounded-[4px] border border-rule bg-paper px-3 py-2 font-sans text-[14px] text-ink outline-none focus:border-blue-2" />
        {chips.map((chip) => (
          <button key={chip.key} type="button" aria-pressed={filter === chip.key} onClick={() => setFilter(chip.key)}
            className={`min-h-9 rounded-[4px] border px-2.5 py-1 font-sans text-[12px] ${filter === chip.key ? "border-blue bg-blue-wash text-blue-text" : "border-rule bg-paper text-ink-2"}`}>
            {chip.label}
          </button>
        ))}
        <Btn type="button" tone="ghost" disabled={markedN === 0} onClick={exportMarked}>导出已标记清单{markedN ? `（${markedN}）` : ""}</Btn>
      </div>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full border-collapse text-left font-sans text-[13px]">
          <thead>
            <tr className="border-b border-rule font-serif text-[14px]">
              <th className="py-2 pr-2 font-medium"></th>
              <th className="py-2 pr-2 font-medium">成员</th>
              <th className="py-2 pr-2 font-medium">发言</th>
              <th className="py-2 pr-2 font-medium">最近活跃</th>
              <th className="py-2 pr-2 font-medium">账号</th>
              <th className="py-2 pr-2 font-medium">学徒</th>
              <th className="py-2 font-medium">单人操作</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((row) => {
              const a = row.account;
              return (
                <tr key={row.member_key} className="border-b border-rule-soft align-top">
                  <td className="py-2.5 pr-2">
                    <input type="checkbox" checked={!!marked[row.member_key]} aria-label={`标记 ${row.display}`}
                      onChange={(e) => setMarked((m) => ({ ...m, [row.member_key]: e.target.checked }))} />
                  </td>
                  <td className="py-2.5 pr-2">
                    <div className="font-serif text-[14.5px] font-bold text-ink">{row.display}</div>
                    {row.unresolved || rawId(row.display) ? <span className="mt-0.5 inline-block rounded-[3px] border border-rule bg-paper-2 px-1.5 py-[1px] text-[10.5px] text-ink-3">未解析</span> : null}
                  </td>
                  <td className="num py-2.5 pr-2">{row.msgs}</td>
                  <td className="num py-2.5 pr-2">{row.last_active ?? "—"}</td>
                  <td className="py-2.5 pr-2">{a ? (a.active ? a.username : "已禁用") : "无账号"}</td>
                  <td className="num py-2.5 pr-2">{row.agent_count}</td>
                  <td className="py-2.5">
                    <div className="flex flex-wrap gap-1.5">
                      {!a ? (
                        <>
                          <Btn type="button" busy={busy} onClick={() => void doClaimLink(row)} className="min-h-9 px-3 py-1.5 text-[12px]">认领链接</Btn>
                          <Btn type="button" tone="ghost" busy={busy} onClick={() => void doGen(row)} className="min-h-9 px-3 py-1.5 text-[12px]">开号</Btn>
                        </>
                      ) : a.role === "admin" ? (
                        <span className="text-[12px] text-ink-3">管理员</span>
                      ) : (
                        <>
                          <Btn type="button" tone="ghost" busy={busy} onClick={() => void doClaimLink(row)} className="min-h-9 px-3 py-1.5 text-[12px]">认领链接</Btn>
                          <Btn type="button" tone={a.active ? "danger" : "ghost"} busy={busy} onClick={() => void doToggle(row, a.active ? "revoke" : "activate")} className="min-h-9 px-3 py-1.5 text-[12px]">{a.active ? "禁用" : "启用"}</Btn>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {pw && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/45 px-4" onClick={() => setPw(null)}>
          <div className="w-full max-w-[400px] rounded-[12px] border border-rule bg-paper p-6 shadow-[var(--shadow-pop)]" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-serif text-[20px] font-bold text-ink">{pw.title}</h3>
            {pw.display_name && <div className="mt-4 flex items-baseline gap-2"><span className="label">成员</span><span className="font-sans text-[14px] text-ink">{pw.display_name}</span></div>}
            <div className="mt-3 flex items-baseline gap-2"><span className="label">用户名</span><span className="num font-sans text-[15px] font-semibold text-ink">{pw.username}</span></div>
            <div className="mt-3 flex items-baseline gap-2"><span className="label">密码</span><span className="num font-sans text-[15px] font-semibold text-blue-text">{pw.password}</span></div>
            <p className="mt-4 font-sans text-[12.5px] leading-relaxed text-ink-3">密码只显示这一次。复制后交给本人。</p>
            <div className="mt-5 flex gap-2">
              <Btn type="button" onClick={() => { void navigator.clipboard?.writeText(pw.password); }}>复制密码</Btn>
              <Btn type="button" tone="ghost" onClick={() => setPw(null)}>关闭</Btn>
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
            <p className="mt-3 font-sans text-[12px] leading-relaxed text-ink-3">只给这一人。不要群发、不要批量出链。</p>
            <div className="mt-5 flex gap-2">
              <Btn type="button" onClick={() => { void navigator.clipboard?.writeText(link.url); }}>复制链接</Btn>
              <Btn type="button" tone="ghost" onClick={() => setLink(null)}>关闭</Btn>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
