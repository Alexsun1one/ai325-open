"use client";
/** 私窖「我的酒力」：总额/明细来源/兑换入口/兑换记录。
 *  数字全接后端真值；库存与门槛未定（null）时如实显示「等 Sun 定价」。 */
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, apiFetch } from "@/lib/auth";
import { Btn, Note } from "./FormBits";

interface Vitality {
  total: number; net?: number; spent?: number; streak_days?: number; band?: string;
  parts?: Record<string, number>; stream?: { date: string; points: number; msgs: number }[];
  today_gain?: number;
}
interface RewardItem { id: string; name: string; description?: string; kind?: string; price_original?: number; cost_vitality?: number | null; stock?: number | null; require_review?: number; dispatch_note?: string; icon?: string }
interface Redemption { id: number; item_id: string; cost: number; status: string; created_at: string; code_mask?: string | null }

const PART_LABELS: Record<string, string> = {
  message: "发言（日封顶）", streak: "连续在场", essay: "入窖小作文",
  quote: "入选金句", annotation: "站内批注", accepted_reply: "回答被采纳", seal: "学徒出师印",
  highlight: "划线", note: "笔记", comment: "段评", favorite: "收藏",
  multi_highlight: "多人同段",
};

export function VitalityCard() {
  const [v, setV] = useState<Vitality | null>(null);
  const [vErr, setVErr] = useState("");
  const [items, setItems] = useState<RewardItem[] | null>(null);
  const [itemsErr, setItemsErr] = useState("");
  const [reds, setReds] = useState<Redemption[] | null>(null);
  const [redsErr, setRedsErr] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [okMsg, setOkMsg] = useState("");
  const gen = useRef(0);

  const msg = (e: unknown, fb: string) => (e instanceof ApiError ? e.message : fb);
  const load = useCallback(() => {
    const seq = ++gen.current;
    const alive = () => seq === gen.current;
    setLoading(true);
    let remain = 3;
    const fin = () => { if (--remain === 0 && alive()) setLoading(false); };
    void apiFetch<Vitality>("/api/vitality/me")
      .then((x) => { if (alive()) { setV(x); setVErr(""); } })
      .catch((e) => { if (alive()) setVErr(msg(e, "酒力数据打不开")); })
      .finally(fin);
    void apiFetch<{ items: RewardItem[] }>("/api/rewards/items")
      .then((x) => { if (alive()) { setItems(x.items ?? []); setItemsErr(""); } })
      .catch((e) => { if (alive()) setItemsErr(msg(e, "奖品目录打不开")); })
      .finally(fin);
    void apiFetch<{ items: Redemption[] }>("/api/rewards/me")
      .then((x) => { if (alive()) { setReds(x.items ?? []); setRedsErr(""); } })
      .catch((e) => { if (alive()) setRedsErr(msg(e, "兑换记录打不开")); })
      .finally(fin);
  }, []);
  useEffect(() => { const t = setTimeout(load, 0); return () => clearTimeout(t); }, [load]);
  useEffect(() => () => { gen.current++; }, []);
  const retry = <Btn type="button" tone="ghost" busy={loading} disabled={loading} onClick={load} className="ml-2 min-h-[44px] px-3 py-1 text-[12px]">重试</Btn>;

  const redeem = async (id: string) => {
    setBusy(true); setErr(""); setOkMsg("");
    try {
      await apiFetch("/api/rewards/redemptions", { method: "POST", body: JSON.stringify({ item_id: id }) });
      setOkMsg("申请已提交，等 Sun 审核发放。");
      load();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "兑换没成功"); }
    finally { setBusy(false); }
  };

  const parts = v?.parts ? Object.entries(v.parts).filter(([, n]) => n > 0) : [];
  return (
    <div className="grid gap-x-10 gap-y-7 lg:grid-cols-[minmax(0,1fr)_minmax(0,300px)]">
      <div>
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span className="font-serif text-[30px] font-bold text-amber-text">{v ? v.net ?? v.total : "…"}</span>
          <span className="font-sans text-[12.5px] text-ink-3">酒力（已花 {v ? v.spent ?? 0 : "…"}）</span>
          {v?.band && <span className="rounded-[4px] border border-amber-deep/50 bg-amber-wash px-2 py-[1px] font-serif text-[13px] font-bold text-amber-text">{v.band}</span>}
          {typeof v?.today_gain === "number" && v.today_gain > 0 && (
            <span className="rounded-[3px] border border-teal/50 bg-teal-wash px-2 py-[1px] font-sans text-[12px] text-teal-text">今天 +{v.today_gain}</span>
          )}
          {typeof v?.streak_days === "number" && v.streak_days > 0 && (
            <span className="rounded-[3px] border border-rule bg-amber-wash/50 px-1.5 py-[1px] font-sans text-[11px] text-amber-text">连续 {v.streak_days} 天在场</span>
          )}
        </div>
        {vErr ? <Note tone="bad">{vErr}{retry}</Note> : null}
        {parts.length > 0 ? (
          <ul className="mt-3 space-y-1.5">
            {parts.map(([k, n]) => (
              <li key={k} className="flex items-baseline justify-between gap-4 font-sans text-[13px] text-ink-2">
                <span>{PART_LABELS[k] ?? k}</span>
                <span className="num text-ink">{n}</span>
              </li>
            ))}
          </ul>
        ) : v && !vErr ? (
          <p className="mt-3 font-sans text-[13.5px] text-ink-3">还没有酒力。发言、入窖、金句、批注都会酿出酒力。</p>
        ) : null}
        {v?.stream && v.stream.length > 1 && (
          <div className="mt-4 border-t border-dashed border-rule pt-3">
            <div className="label text-[11px]">近 7 天</div>
            <ul className="mt-1.5 space-y-1">
              {v.stream.slice(-7).map((s) => (
                <li key={s.date} className="flex items-baseline justify-between gap-3 font-sans text-[12.5px] text-ink-2">
                  <span className="num text-ink-3">{s.date.slice(5)}</span>
                  <span className="text-ink-2">{s.msgs} 条</span>
                  <span className="num text-teal-text">+{s.points}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      <div>
        <div className="label mb-2">奖励兑换</div>
        {itemsErr ? <Note tone="bad">{itemsErr}{retry}</Note> : null}
        {items === null && !itemsErr ? <p className="font-sans text-[12.5px] text-ink-3">载入中…</p> : null}
        {(items ?? []).map((it) => {
          const cost = it.cost_vitality ?? null;
          const stock = it.stock;
          const kindTag = it.kind === "virtual_code" ? "虚拟码" : it.kind === "physical" ? "实物" : "额度";
          const vReady = v !== null && !vErr;
          const afford = vReady && cost !== null && (v?.net ?? 0) >= cost;
          const soldOut = stock !== null && stock !== undefined && stock <= 0;
          const canRedeem = vReady && !loading && cost !== null && afford && !soldOut;
          return (
            <div key={it.id} className="mb-3 rounded-[8px] border border-rule bg-paper-2/60 p-3">
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-serif text-[15px] font-bold text-ink">{it.icon ? `${it.icon} ` : ""}{it.name}</span>
                <span className="rounded-[3px] border border-rule px-1.5 py-[1px] font-sans text-[10px] text-ink-3">{kindTag}</span>
              </div>
              {it.description ? <p className="mt-1 font-sans text-[12px] leading-relaxed text-ink-3">{it.description}</p> : null}
              <p className="mt-1 font-sans text-[12.5px] text-ink-2">
                兑换：{cost === null ? "等 Sun 定价" : `${cost} 酒力`}
                {stock !== null && stock !== undefined ? ` · 库存 ${stock}` : cost !== null ? " · 不限量" : ""}
                {it.require_review ? " · 需 Sun 审核" : " · 即时发放"}
              </p>
              <Btn type="button" tone={canRedeem ? "primary" : "ghost"} busy={busy}
                disabled={!canRedeem}
                onClick={() => void redeem(it.id)} className="mt-2 min-h-[44px] px-4 py-1.5 text-[12.5px]">
                {cost === null ? "门槛未定" : soldOut ? "已兑完" : !vReady ? "积分待确认" : afford ? "兑换" : `还差 ${cost - (v?.net ?? 0)}`}
              </Btn>
            </div>
          );
        })}
        {items !== null && items.length === 0 && !itemsErr && <p className="font-sans text-[12.5px] text-ink-3">还没有上架奖品。</p>}
        {redsErr ? <Note tone="bad">{redsErr}{retry}</Note> : null}
        {reds === null && !redsErr ? <p className="mt-2 font-sans text-[12px] text-ink-3">兑换记录载入中…</p> : null}
        {reds !== null && reds.length > 0 && (
          <div className="mt-3 border-t border-rule pt-3">
            <div className="label mb-1.5 text-[11px]">我的兑换记录</div>
            <ul className="space-y-1.5">
              {reds.map((r) => (
                <li key={r.id} className="flex flex-wrap items-baseline gap-x-2 font-sans text-[12px] text-ink-2">
                  <span className="text-ink">{r.item_id === "mycel-lifetime" ? "Mycel 激活码" : r.item_id}</span>
                  <span className="rounded-[3px] border border-rule px-1 py-[1px] text-[10.5px]">{r.status}</span>
                  <span className="num text-ink-3">-{r.cost} 酒力</span>
                  {r.code_mask && <span className="num text-ink-3">码 {r.code_mask}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
        {okMsg ? <Note tone="good">{okMsg}</Note> : null}
        {err ? <Note tone="bad">{err}</Note> : null}
      </div>
    </div>
  );
}
