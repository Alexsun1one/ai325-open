"use client";
/** Admin 兑换后台：审核/发放/库存设置/录码。
 *  激活码明文只在「发放」请求体出现一次，服务端只存 hash+掩码——页面不留明文、不打印。 */
import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/auth";
import { Btn, Field, Note } from "./FormBits";

interface Redemption { id: number; user_id: number; item_id: string; cost: number; status: string; created_at: string; reviewed_by?: number | null; reviewed_at?: string | null }
interface RewardItem { id: string; name: string; description?: string; kind?: string; price_original?: number; cost_vitality?: number | null; stock?: number | null; require_review?: number; dispatch_note?: string; icon?: string; active?: number }
interface Redemption { id: number; user_id: number; item_id: string; cost: number; status: string; created_at: string; reviewed_by?: number | null; reviewed_at?: string | null; fulfillment_status?: string; shipping_mask?: { province?: string; city?: string; receiver?: string; phone?: string } | null }
interface CodeRow { id: number; item_id: string; code_mask: string; status: string; issued_to?: number | null; issued_at?: string | null }
interface Payload {
  items: RewardItem[]; redemptions: Redemption[];
  spent: { user_id: number; spent: number }[]; codes: CodeRow[];
}

const STATUS_LABEL: Record<string, string> = { pending: "待审", approved: "已通过", rejected: "已驳回", issued: "已发放" };

export function RewardsAdmin() {
  const [data, setData] = useState<Payload | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [codeDraft, setCodeDraft] = useState<Record<number, string>>({});
  const [issuedOnce, setIssuedOnce] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    try { setData(await apiFetch<Payload>("/api/admin/rewards")); setErr(""); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "后台打不开"); }
  }, []);
  useEffect(() => { const t = setTimeout(() => void load(), 0); return () => clearTimeout(t); }, [load]);

  const act = async (path: string, body?: object) => {
    setBusy(true); setErr("");
    try {
      await apiFetch(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
      await load();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "操作失败"); }
    finally { setBusy(false); }
  };

  const saveItem = async (item: RewardItem, patch: Partial<RewardItem>) => {
    setBusy(true);
    try {
      await apiFetch(`/api/admin/rewards/items/${item.id}`, { method: "POST", body: JSON.stringify(patch) });
      await load();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "保存失败"); }
    finally { setBusy(false); }
  };

  const ship = async (r: Redemption) => {
    setBusy(true); setErr("");
    try { await apiFetch(`/api/admin/rewards/redemptions/${r.id}/ship`, { method: "POST" }); await load(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "发货失败"); }
    finally { setBusy(false); }
  };

  const issue = async (r: Redemption) => {
    const code = (codeDraft[r.id] ?? "").trim();
    if (code.length < 8) { setErr("激活码至少 8 位"); return; }
    setBusy(true); setErr("");
    try {
      const res = await apiFetch<{ code: string; code_mask: string }>(`/api/admin/rewards/redemptions/${r.id}/issue`, { method: "POST", body: JSON.stringify({ code }) });
      setIssuedOnce((m) => ({ ...m, [r.id]: res.code }));
      setCodeDraft((m) => ({ ...m, [r.id]: "" }));
      await load();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "发放失败"); }
    finally { setBusy(false); }
  };

  if (!data) return <div>{err ? <Note tone="bad">{err}<Btn type="button" tone="ghost" onClick={() => void load()} className="ml-2 min-h-[44px] px-3 py-1 text-[12px]">重试</Btn></Note> : <p className="py-6 font-sans text-[13.5px] text-ink-3">加载中……</p>}</div>;

  const pending = data.redemptions.filter((r) => r.status === "pending");
  const active = data.redemptions.filter((r) => r.status !== "pending");
  return (
    <div className="space-y-10">
      {err && <Note tone="bad">{err}</Note>}

      <section>
        <h2 className="font-serif text-[20px] font-bold text-ink">奖品与门槛</h2>
        <p className="mt-1 font-sans text-[12.5px] text-ink-3">门槛/库存留空=未定（Sun 后填）；保存写 DB 覆盖层，不写死。</p>
        <div className="mt-3 space-y-3">
          {data.items.map((it) => (
            <div key={it.id} className="flex flex-wrap items-end gap-3 rounded-[8px] border border-rule bg-paper-2/50 p-3">
              <div>
                <div className="label">奖品</div>
                <div className="font-serif text-[15px] font-bold text-ink">{it.name}</div>
                {it.price_original ? <div className="num font-sans text-[11.5px] text-ink-3">原价 ¥{it.price_original}</div> : null}
              </div>
              <Field label="兑换酒力" value={it.cost_vitality === null ? "" : String(it.cost_vitality)}
                onChange={(e) => { const n = e.target.value === "" ? null : Number(e.target.value); void saveItem(it, { cost_vitality: Number.isFinite(n as number) ? n : null }); }}
                className="w-28" />
              <Field label="库存" value={it.stock === null ? "" : String(it.stock)}
                onChange={(e) => { const n = e.target.value === "" ? null : Number(e.target.value); void saveItem(it, { stock: Number.isFinite(n as number) ? n : null }); }}
                className="w-28" />
              <Btn type="button" tone={it.active ? "ghost" : "primary"} busy={busy} disabled={busy}
                onClick={() => void saveItem(it, { active: it.active ? 0 : 1 })}
                className="min-h-0 px-3 py-1.5 text-[12px]">{it.active ? "下架" : "上架"}</Btn>
              {it.kind ? <span className="rounded-[3px] border border-rule px-1.5 py-[1px] font-sans text-[10.5px] text-ink-3">{it.kind === "virtual_code" ? "虚拟码" : it.kind === "physical" ? "实物" : "额度"}</span> : null}
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="font-serif text-[20px] font-bold text-ink">待审核 <span className="num text-ink-3">({pending.length})</span></h2>
        {pending.length === 0 ? (
          <p className="mt-2 font-sans text-[13px] text-ink-3">没有待审核的兑换申请。</p>
        ) : (
          <ul className="mt-3 divide-y divide-rule-soft border-y border-rule">
            {pending.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
                <div className="min-w-0 flex-1">
                  <div className="font-sans text-[13.5px] font-semibold text-ink">用户 #{r.user_id} · {r.item_id === "mycel-lifetime" ? "Mycel 永久激活码" : r.item_id}</div>
                  <div className="num font-sans text-[12px] text-ink-3">{r.created_at.slice(0, 16).replace("T", " ")} · 扣 {r.cost} 酒力</div>
                </div>
                <Btn type="button" tone="primary" busy={busy} disabled={busy} onClick={() => void act(`/api/admin/rewards/redemptions/${r.id}/approve`)} className="min-h-0 px-4 py-1.5 text-[12.5px]">通过</Btn>
                <Btn type="button" tone="ghost" busy={busy} disabled={busy} onClick={() => void act(`/api/admin/rewards/redemptions/${r.id}/reject`)} className="min-h-0 px-4 py-1.5 text-[12.5px]">驳回</Btn>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="font-serif text-[20px] font-bold text-ink">发放记录</h2>
        {active.length === 0 ? (
          <p className="mt-2 font-sans text-[13px] text-ink-3">还没有审核过的申请。</p>
        ) : (
          <ul className="mt-3 divide-y divide-rule-soft border-y border-rule">
            {active.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
                <div className="min-w-0 flex-1">
                  <div className="font-sans text-[13.5px] font-semibold text-ink">用户 #{r.user_id} · {STATUS_LABEL[r.status] ?? r.status}</div>
                  <div className="num font-sans text-[12px] text-ink-3">{r.created_at.slice(0, 16).replace("T", " ")} · 扣 {r.cost} 酒力</div>
                </div>
                {r.shipping_mask && (
                  <span className="font-sans text-[11.5px] text-ink-3">收货 {r.shipping_mask.province}{r.shipping_mask.city} · {r.shipping_mask.receiver} · {r.shipping_mask.phone}</span>
                )}
                {r.fulfillment_status === "shipped" && <span className="font-sans text-[12px] text-teal">已发货</span>}
                {r.status === "approved" && r.item_id === "pioneer-tee" && (
                  <Btn type="button" tone="ghost" busy={busy} disabled={busy} onClick={() => void ship(r)} className="min-h-0 px-3 py-1.5 text-[12px]">发货</Btn>
                )}
                {r.status === "approved" && (
                  <div className="flex items-center gap-2">
                    {issuedOnce[r.id] ? (
                      <span className="rounded-[4px] border border-teal/50 bg-teal-wash px-2 py-1 font-mono text-[12px] text-teal-text">{issuedOnce[r.id]}</span>
                    ) : (
                      <>
                        <input value={codeDraft[r.id] ?? ""} onChange={(e) => setCodeDraft((m) => ({ ...m, [r.id]: e.target.value }))}
                          placeholder="粘贴激活码（只显示这一次）" className="w-56 rounded-[5px] border border-rule bg-paper px-2 py-1.5 font-mono text-[12px] text-ink outline-none focus:border-blue-2" />
                        <Btn type="button" tone="primary" busy={busy} disabled={busy} onClick={() => void issue(r)} className="min-h-0 px-3 py-1.5 text-[12px]">发放</Btn>
                      </>
                    )}
                  </div>
                )}
                {r.status === "issued" && <span className="num font-sans text-[12px] text-ink-3">已发码（库只存 hash+掩码）</span>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="font-serif text-[20px] font-bold text-ink">酒力已花 <span className="num text-ink-3">({data.spent.length})</span></h2>
        {data.spent.length === 0 ? (
          <p className="mt-2 font-sans text-[13px] text-ink-3">还没有扣过酒力。</p>
        ) : (
          <ul className="mt-2 space-y-1">
            {data.spent.map((s) => (
              <li key={s.user_id} className="flex justify-between font-sans text-[12.5px] text-ink-2">
                <span>用户 #{s.user_id}</span><span className="num">-{s.spent}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
