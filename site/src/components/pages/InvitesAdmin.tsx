"use client";
import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch, useAuth } from "@/lib/auth";
import { Btn, Field, Note } from "./FormBits";
import { GapNote } from "./PageHead";

/** 形状对齐 app/main.py 的真实实现：
 *  GET  /api/admin/invites            → { items: [{code(已掩码), note, used, max, status, created_by, created_at, expires_at}] }
 *  POST /api/admin/invites            → { count, codes: ["XF-XXXX-XXXX", …] }  // 完整码只在这一次返回
 *  POST /api/admin/invites/{code}/revoke → { ok, code, status }                // 掩码码也认，后四位不唯一时 409
 */
export interface Invite {
  code: string; note?: string; member_name?: string | null; used?: number; max?: number;
  status?: "active" | "revoked" | "expired" | "exhausted" | string;
  created_by?: string; created_at?: string; expires_at?: string;
}

const STATUS: Record<string, { label: string; cls: string }> = {
  active: { label: "可用", cls: "border-blue-wash-2 bg-blue-wash text-blue-text" },
  exhausted: { label: "已用尽", cls: "border-teal/50 bg-teal-wash text-teal-text" },
  revoked: { label: "已撤销", cls: "border-rule bg-paper-2 text-ink-3" },
  expired: { label: "已过期", cls: "border-amber-deep/50 bg-amber-wash text-amber-text" },
};

export function InvitesAdmin() {
  const { status, user } = useAuth();
  const [items, setItems] = useState<Invite[] | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [fresh, setFresh] = useState<string[]>([]);
  const [count, setCount] = useState("3");
  const [note, setNote] = useState("");
  const [days, setDays] = useState("30");
  const [member, setMember] = useState("");
  const [people, setPeople] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch("/people.json").then((r) => r.json())
      .then((d: { name: string }[]) => setPeople(Array.isArray(d) ? d.map((x) => x.name).filter(Boolean) : []))
      .catch(() => setPeople([]));
  }, []);

  const load = useCallback(async () => {
    setErr("");
    try {
      const d = await apiFetch<{ items: Invite[] }>("/api/admin/invites");
      setItems(d.items ?? []);
    } catch (e) {
      setItems(null);
      setErr(e instanceof ApiError ? `${e.message}（HTTP ${e.status || "无响应"}）` : "读取失败");
    }
  }, []);

  useEffect(() => { if (status === "in" && user?.role === "admin") void load(); }, [status, user?.role, load]);

  if (status === "loading") return <p className="py-10 font-sans text-[14px] text-ink-3">正在验票……</p>;
  if (status === "out") return <Note tone="bad">请先登录。这一页只对群主（admin）开放。</Note>;
  if (user?.role !== "admin") {
    return (
      <Note tone="bad">
        当前账号 <b>{user?.display_name || user?.username}</b> 的角色是 <span className="num">{user?.role || "member"}</span>，看不到邀请码后台。这一页只对群主（admin）开放。
      </Note>
    );
  }

  const gen = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr(""); setMsg("");
    try {
      const d = await apiFetch<{ count: number; codes: string[] }>("/api/admin/invites", {
        method: "POST",
        body: JSON.stringify({
          count: member.trim() ? 1 : Math.max(1, Math.min(50, parseInt(count, 10) || 1)),
          note: note.trim(),
          expires_days: Math.max(1, parseInt(days, 10) || 30),
          ...(member.trim() ? { member_name: member.trim() } : {}),
        }),
      });
      setFresh(d.codes ?? []);
      setMsg(member.trim()
        ? `已生成绑定「${member.trim()}」的码。此码注册时自动使用这个成员名，对方自己填的昵称不生效。完整码只在这一次返回。`
        : `已生成 ${d.count} 个码。完整码只在这一次返回——现在不抄下来，之后只剩后四位。`);
      setNote(""); setMember("");
      await load();
    } catch (e2) {
      setErr(e2 instanceof ApiError ? `${e2.message}（HTTP ${e2.status || "无响应"}）` : "生成失败");
    } finally { setBusy(false); }
  };

  const revoke = async (v: Invite) => {
    setErr(""); setMsg("");
    try {
      await apiFetch(`/api/admin/invites/${encodeURIComponent(v.code)}/revoke`, { method: "POST" });
      setMsg(`已撤销 ${v.code}。`);
      await load();
    } catch (e) {
      setErr(e instanceof ApiError ? `撤销 ${v.code} 失败：${e.message}（HTTP ${e.status}）` : "撤销失败");
    }
  };

  return (
    <div className="grid gap-x-12 gap-y-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,320px)]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
          <h2 className="font-serif text-[22px] font-bold text-ink">已发放的码{items && <span className="num ml-3 text-[14px] font-normal text-ink-3">{items.length}</span>}</h2>
          <button type="button" onClick={() => void load()} className="font-sans text-[13px] text-blue-text hover:underline">重新读取</button>
        </div>

        {err && <div className="mt-4"><Note tone="bad">{err}</Note></div>}
        {msg && <div className="mt-4"><Note tone="good">{msg}</Note></div>}

        {fresh.length > 0 && (
          <div className="mt-6 rounded-[10px] border border-amber-deep/45 bg-amber-wash px-5 py-5">
            <div className="label" style={{ color: "var(--amber-text)" }}>刚生成 · 只显示这一次</div>
            <ul className="mt-3 flex flex-wrap gap-2">
              {fresh.map((c) => (
                <li key={c}>
                  <code className="num select-all rounded-[4px] border border-amber-deep/40 bg-paper px-2.5 py-1.5 font-sans text-[15px] font-semibold tracking-[0.08em] text-ink">{c}</code>
                </li>
              ))}
            </ul>
            <p className="mt-3 font-sans text-[12px] leading-relaxed text-amber-text">
              一码发一个人。刷新之后列表里只剩 <span className="num">XF-****-后四位</span>——这是故意的，只剩后四位的码贴出去也没用。
            </p>
          </div>
        )}

        {items === null ? (
          <div className="mt-5">
            <GapNote>
              <b>读不到已发的码</b>（上面是服务器原话）。这一页本身是好的，等服务器恢复了点「重新读取」就行——现在显示的不是「没有码」，是「问不到」。
            </GapNote>
          </div>
        ) : items.length === 0 ? (
          <p className="mt-5 font-sans text-[14px] text-ink-3">还没有生成过邀请码。用右边的表单生成第一批。</p>
        ) : (
          <div className="mt-5 overflow-x-auto">
            <table className="w-full min-w-[700px] border-collapse">
              <thead>
                <tr className="border-y border-rule">
                  {["码（后四位）", "绑定", "备注", "状态", "已用", "到期", ""].map((h, i) => (
                    <th key={h || i} className={`label whitespace-nowrap py-2.5 ${i >= 4 ? "text-right" : "text-left"}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-rule-soft">
                {items.map((v) => {
                  const st = STATUS[v.status ?? "active"] ?? { label: v.status ?? "—", cls: "border-rule bg-paper-2 text-ink-3" };
                  const dead = v.status === "revoked";
                  return (
                    <tr key={v.code} className="transition-colors hover:bg-paper-2/50">
                      <td className="num py-3 pr-4 font-sans text-[14px] font-semibold tracking-[0.06em] text-ink">{v.code}</td>
                      <td className="py-3 pr-4 font-sans text-[13.5px]">{v.member_name ? <span data-person="">{v.member_name}</span> : <span className="text-ink-3">—</span>}</td>
                      <td className="py-3 pr-4 font-sans text-[13.5px] text-ink-2">{v.note || <span className="text-ink-3">（无备注）</span>}</td>
                      <td className="py-3 pr-4 text-right"><span className={`inline-flex whitespace-nowrap rounded-[4px] border px-2 py-[3px] font-sans text-[11.5px] font-semibold ${st.cls}`}>{st.label}</span></td>
                      <td className="num py-3 pr-4 text-right font-sans text-[13.5px] text-ink-2">{v.used ?? 0} / {v.max ?? 1}</td>
                      <td className="num py-3 pr-4 text-right font-sans text-[13px] text-ink-3">{v.expires_at ? v.expires_at.slice(0, 10) : "—"}</td>
                      <td className="py-3 text-right">
                        <button type="button" disabled={dead} onClick={() => void revoke(v)}
                          className="font-sans text-[13px] font-semibold text-cinnabar-text disabled:cursor-not-allowed disabled:text-ink-3/50 hover:enabled:underline">
                          撤销
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="mt-4 font-sans text-[12px] leading-relaxed text-ink-3">
              撤销是按后四位找的。<b>万一两个码后四位撞了</b>，服务器会拒绝并要你用生成时那串完整码——真遇上了，这里会把服务器的原话显示出来。
            </p>
          </div>
        )}
      </div>

      <form onSubmit={gen} className="h-max rounded-[10px] border border-rule bg-paper-2/50 px-5 py-6">
        <div className="label mb-4">生成新码</div>
        <div className="space-y-4">
          <Field label="绑定成员" name="member" list="xf-invite-people" value={member} onChange={(e) => setMember(e.target.value)}
            placeholder="留空 = 不绑定" hint="绑定后此码注册时自动用这个成员名，一人一码一号；重复绑定会被服务器拦下来。" />
          <datalist id="xf-invite-people">{people.map((n) => <option key={n} value={n} />)}</datalist>
          <Field label="数量" name="count" type="number" min={1} max={50} required disabled={!!member.trim()}
            value={member.trim() ? "1" : count} onChange={(e) => setCount(e.target.value)}
            hint={member.trim() ? "绑定成员的码一次只发一张。" : undefined} />
          <Field label="有效天数" name="days" type="number" min={1} required value={days} onChange={(e) => setDays(e.target.value)} hint="到期后自动失效，不用手动撤。" />
          <Field label="备注" name="note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="发给谁 / 什么场合" hint="只给你自己看，用来日后对上人。" />
        </div>
        <div className="mt-5"><Btn type="submit" busy={busy}>生成</Btn></div>
        <p className="mt-4 font-sans text-[11.5px] leading-relaxed text-ink-3">
          默认一码一人。已用尽、已撤销、已过期的码都不能再注册。撤销不影响已经注册成功的账号——那要单独处理。
        </p>
      </form>
    </div>
  );
}
