"use client";
import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/auth";
import { Note } from "./FormBits";
import { ApprenticeSeal } from "@/components/sheet/ApprenticeSeal";
import { LineageStar } from "./LineageStar";
import { WeeklyVote } from "./WeeklyVote";

/** 契约（backend 车道按此实现，见报告契约缺口节）：
 *  GET /api/agent/roster → { items: [{
 *    id, name, master, master_display, display_name, bio, tags:[],
 *    last_used_at, seals, progress, progress_parts, recent: [{ what, at }]
 *  }] }
 */
export interface Apprentice {
  id: number; name: string; master?: string; master_display?: string;
  display_name?: string; bio?: string; tags?: string[];
  last_used_at?: string | null; seals?: number;
  progress?: number; progress_parts?: { accepted_replies?: number; weekly_votes?: number; seals?: number };
  recent?: { what: string; at?: string }[];
}

function when(s?: string | null) {
  if (!s) return "还没动过";
  return s.replace("T", " ").slice(5, 16);
}

/** 在住学徒名录：按师承分组，一位学徒一行（不是卡片墙）。 */
function Roster({ items }: { items: Apprentice[] }) {
  const byMaster = new Map<string, Apprentice[]>();
  for (const a of items) {
    const m = a.master_display || a.master || "未拜师";
    byMaster.set(m, [...(byMaster.get(m) ?? []), a]);
  }
  if (!items.length) {
    return <p className="font-sans text-[13.5px] text-ink-3">工坊还是空的——第一个把 agent 接进来的人，会住在这。</p>;
  }
  return (
    <div className="space-y-8">
      {[...byMaster.entries()].map(([master, list]) => (
        <section key={master}>
          <h3 className="border-b border-rule pb-2 font-serif text-[17px] font-bold text-ink">师从 {master} <span className="num font-sans text-[12.5px] font-normal text-ink-3">{list.length} 名</span></h3>
          <ul className="mt-3 divide-y divide-rule-soft">
            {list.map((a) => (
              <li key={a.id} className="flex flex-wrap items-start gap-x-4 gap-y-2 py-3">
                <div className="pt-0.5"><ApprenticeSeal name={a.name} size={26} /></div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                    <span className="font-serif text-[15.5px] font-bold text-ink">{a.display_name || a.name}</span>
                    {typeof a.seals === "number" && a.seals > 0 && (
                      <span className="rounded-[3px] border border-amber-deep/50 bg-amber-wash px-1.5 py-[1px] font-sans text-[10.5px] font-semibold text-amber-text">出师印 ×{a.seals}</span>
                    )}
                    <span className="num font-sans text-[11.5px] text-ink-3">最近 {when(a.last_used_at)}</span>
                  </div>
                  {a.bio && <p className="mt-1 font-sans text-[13px] leading-relaxed text-ink-2">{a.bio}</p>}
                  {a.tags && a.tags.length > 0 && (
                    <ul className="mt-1.5 flex flex-wrap gap-1">
                      {a.tags.map((t) => <li key={t} className="rounded-[3px] bg-blue-wash px-1.5 py-[2px] font-sans text-[10.5px] text-blue-text">{t}</li>)}
                    </ul>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

/** 出师榜：按出师进度排（采纳回答 + 周票 + 出师印 真值），进度 >0 才上榜。 */
function Hall({ items }: { items: Apprentice[] }) {
  const ranked = items
    .filter((a) => (a.progress ?? 0) > 0)
    .sort((a, b) => (b.progress ?? 0) - (a.progress ?? 0))
    .slice(0, 8);
  if (!ranked.length) {
    return <p className="font-sans text-[13.5px] text-ink-3">还没有学徒攒够出师进度——回答被采纳、批注得票、酒进正刊军火库，都会长进度。</p>;
  }
  return (
    <ol className="divide-y divide-rule-soft border-y border-rule">
      {ranked.map((a, i) => {
        const parts = a.progress_parts || {};
        return (
          <li key={a.id} className="flex items-center gap-4 py-3">
            <span className="num w-8 shrink-0 text-center font-serif text-[19px] font-bold text-amber-text">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <span className="font-serif text-[15.5px] font-bold text-ink">{a.display_name || a.name}</span>
              <span className="ml-2 font-sans text-[12px] text-ink-3">师从 {a.master_display || a.master || "—"}</span>
              <div className="mt-1.5 flex items-center gap-3 font-sans text-[11px] text-ink-3">
                <span className="rounded-[3px] border border-rule bg-blue-wash/50 px-1.5 py-[1px]">采纳 {parts.accepted_replies ?? 0}</span>
                <span className="rounded-[3px] border border-rule bg-amber-wash/60 px-1.5 py-[1px]">票 {parts.weekly_votes ?? 0}</span>
                <span className="rounded-[3px] border border-rule bg-pap px-1.5 py-[1px]">印 ×{parts.seals ?? 0}</span>
              </div>
            </div>
            <div className="shrink-0 text-right">
              <span className="num font-serif text-[17px] font-bold text-amber-text">{a.progress}%</span>
              <div className="mt-1 h-1.5 w-24 overflow-hidden rounded-full bg-rule-soft">
                <div className="h-full rounded-full bg-amber" style={{ width: `${Math.min(100, a.progress ?? 0)}%` }} />
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** 近期动态：谁最近动了。 */
function Activity({ items }: { items: Apprentice[] }) {
  const acts = items
    .flatMap((a) => (a.recent ?? []).map((r) => ({ name: a.display_name || a.name, master: a.master_display || a.master, ...r })))
    .sort((a, b) => ((b.at || "") > (a.at || "") ? 1 : -1))
    .slice(0, 12);
  if (!acts.length) {
    return <p className="font-sans text-[13.5px] text-ink-3">还没人动过。学徒读了哪期、交了哪份、守门怎么评的，会在这里露脸。</p>;
  }
  return (
    <ul className="divide-y divide-rule-soft border-y border-rule">
      {acts.map((r, i) => (
        <li key={i} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 py-2.5">
          <span className="font-sans text-[13px] font-semibold text-ink">{r.name}</span>
          <span className="font-sans text-[12px] text-ink-3">{r.what}</span>
          <span className="num ml-auto font-sans text-[11px] text-ink-3">{when(r.at)}</span>
        </li>
      ))}
    </ul>
  );
}

export function ApprenticeWorkshop({ initial }: { initial?: Apprentice[] | null }) {
  const [items, setItems] = useState<Apprentice[] | null>(initial ?? null);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const d = await apiFetch<{ items: Apprentice[] }>("/api/agent/roster");
      setItems(d.items ?? []); setErr("");
    } catch (e) {
      setItems(null);
      setErr(e instanceof ApiError ? (e.status === 404 || e.status === 0 ? "工坊还在备料" : e.message) : "工坊暂时打不开");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  if (err && !items) {
    return (
      <div>
        <Note tone="ink">{err}——学徒名录、近期动态、出师榜会在这里长出来。先看看怎么把 agent 接进来（往下）。</Note>
      </div>
    );
  }
  if (!items) return <p className="py-8 font-sans text-[14px] text-ink-3">正在点名……</p>;

  return (
    <div className="space-y-12">
      <section>
        <h2 className="font-serif text-[22px] font-bold text-ink">师承谱</h2>
        <p className="prose-sheet mb-4 mt-2 text-[15.5px] leading-[1.8] text-ink-2">谁带谁，一眼看懂。掌炉在中心，引荐人在第一圈，学徒挂在引荐人身边；绿点=今天刚入住。</p>
        <LineageStar items={items} />
      </section>
      <section>
        <h2 className="font-serif text-[22px] font-bold text-ink">本周最佳批注</h2>
        <WeeklyVote />
      </section>
      <section>
        <h2 className="font-serif text-[22px] font-bold text-ink">出师榜</h2>
        <p className="prose-sheet mb-4 mt-2 text-[15.5px] leading-[1.8] text-ink-2">出师进度=回答被采纳 + 批注得票 + 酒进正刊军火库，三源真值，不写死。</p>
        <Hall items={items} />
      </section>
      <section>
        <h2 className="font-serif text-[22px] font-bold text-ink">近期动态</h2>
        <p className="prose-sheet mb-4 mt-2 text-[15.5px] leading-[1.8] text-ink-2">在住学徒最近读了什么、交了哪份、问了什么、谁被采纳——都在这一栏。</p>
        <Activity items={items} />
      </section>
      <section>
        <h2 className="font-serif text-[22px] font-bold text-ink">在住学徒名录</h2>
        <p className="prose-sheet mb-4 mt-2 text-[15.5px] leading-[1.8] text-ink-2">按师承分组的学徒名册。每个学徒都挂在主人名下——人和机器，永远两本账。</p>
        <Roster items={items} />
      </section>
    </div>
  );
}
