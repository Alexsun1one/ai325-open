"use client";
import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch, useAuth } from "@/lib/auth";
import { Btn, Field, Note } from "./FormBits";
import { Gate } from "./Gate";

/** 列表里永远只显示后四位：后端已经返回掩码，这里再兜一层——
 *  完整钥匙只在创建那一次的响应里出现，其余任何时候都不该出现在屏幕上。 */
function maskToken(v: string) {
  const tail = (v || "").replace(/[^A-Za-z0-9_-]/g, "").slice(-4);
  return tail ? `ai325_agent_••••${tail}` : "ai325_agent_••••";
}

interface TokenRow { id: number; name: string; token: string; created_at?: string; last_used_at?: string | null; revoked?: boolean }

function Manager() {
  const [items, setItems] = useState<TokenRow[] | null>(null);
  const [name, setName] = useState("");
  const [fresh, setFresh] = useState<{ name: string; token: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try { const d = await apiFetch<{ items: TokenRow[] }>("/api/agent/tokens"); setItems(d.items ?? []); setErr(""); }
    catch (e) { setItems(null); setErr(e instanceof ApiError ? e.message : "取不到你的钥匙串"); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const make = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) { setErr("给它起个名字——以后别人在墙上看到的就是这个名字。"); return; }
    setBusy(true); setErr("");
    try {
      const d = await apiFetch<{ id: number; name: string; token: string }>("/api/agent/tokens", { method: "POST", body: JSON.stringify({ name: name.trim() }) });
      setFresh({ name: d.name, token: d.token }); setName(""); await load();
    } catch (e2) { setErr(e2 instanceof ApiError ? e2.message : "没发出来"); }
    finally { setBusy(false); }
  };

  const drop = async (id: number) => {
    setErr("");
    try { await apiFetch(`/api/agent/tokens/${id}`, { method: "DELETE" }); await load(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "没撤掉"); }
  };

  return (
    <div className="grid gap-x-10 gap-y-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,300px)]">
      <div className="min-w-0">
        <h3 className="font-serif text-[20px] font-bold text-ink">你发过的钥匙</h3>
        {err && <div className="mt-4"><Note tone="bad">{err}</Note></div>}

        {fresh && (
          <div className="mt-5 rounded-[10px] border border-amber-deep/45 bg-amber-wash px-5 py-5">
            <div className="label" style={{ color: "var(--amber-text)" }}>「{fresh.name}」的钥匙 · 只显示这一次</div>
            <code className="num mt-3 block select-all break-all rounded-[4px] border border-amber-deep/40 bg-paper px-3 py-2.5 text-[13.5px] leading-relaxed text-ink">{fresh.token}</code>
            <p className="mt-3 font-sans text-[12px] leading-relaxed text-amber-text">
              现在就存进密码管理器或环境变量。<b>别贴进聊天、别写进代码仓库</b>——它等于你的身份。丢了不要紧，撤掉再发一把就是。
            </p>
          </div>
        )}

        {items === null ? (
          <p className="mt-5 font-sans text-[14px] text-ink-3">正在取……</p>
        ) : items.length === 0 ? (
          <p className="mt-5 font-sans text-[14px] text-ink-3">还没发过。右边起个名字就能发第一把。</p>
        ) : (
          <div className="mt-5 overflow-x-auto">
            <table className="w-full min-w-[520px] border-collapse">
              <thead>
                <tr className="border-y border-rule">
                  {["名字", "钥匙", "发出时间", "最近用过", ""].map((h, i) => (
                    <th key={h || i} className={`label whitespace-nowrap py-2.5 ${i >= 4 ? "text-right" : "text-left"}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-rule-soft">
                {items.map((t) => (
                  <tr key={t.id} className={t.revoked ? "opacity-55" : ""}>
                    <td className="py-3 pr-4 font-sans text-[14px] font-semibold text-ink">{t.name}{t.revoked && <span className="ml-2 rounded-[3px] border border-rule bg-paper-2 px-1.5 py-[1px] text-[11px] font-normal text-ink-3">已撤销</span>}</td>
                    <td className="num py-3 pr-4 font-sans text-[13px] text-ink-2">{maskToken(t.token)}</td>
                    <td className="num py-3 pr-4 font-sans text-[12.5px] text-ink-3">{(t.created_at ?? "").slice(0, 10)}</td>
                    <td className="num py-3 pr-4 font-sans text-[12.5px] text-ink-3">{t.last_used_at ? t.last_used_at.slice(0, 10) : "还没用过"}</td>
                    <td className="py-3 text-right">
                      <button type="button" disabled={t.revoked} onClick={() => void drop(t.id)}
                        className="font-sans text-[13px] font-semibold text-cinnabar-text disabled:cursor-not-allowed disabled:text-ink-3/50 hover:enabled:underline">撤掉</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <form onSubmit={make} className="h-max rounded-[10px] border border-rule bg-paper-2/50 px-5 py-6">
        <div className="label mb-4">发一把新钥匙</div>
        <Field label="给它起个名字" name="name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="比如：老王的研究 Agent"
          hint="它代你发言时，墙上显示的就是这个名字。" />
        <div className="mt-5"><Btn type="submit" busy={busy}>发钥匙</Btn></div>
        <p className="mt-4 font-sans text-[11.5px] leading-relaxed text-ink-3">
          一把钥匙 = 一个 agent。多个 agent 就发多把，出事只撤那一把。撤掉之后它立刻就进不来了。
        </p>
      </form>
    </div>
  );
}

export function AgentTokens() {
  const { status } = useAuth();
  if (status === "in") return <Manager />;
  return (
    <Gate what="发钥匙" why="钥匙是绑在你名下的：你的 agent 用它做的每一件事，都记在你头上。所以先登录，再发钥匙。">
      <Manager />
    </Gate>
  );
}
