"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/auth";
import { Note } from "./FormBits";

/** 契约（backend 追加节待定稿，按 §B 提案起骨架，见报告契约缺口节）：
 *  GET /api/context-units?date=YYYY-MM-DD → { items: [{
 *    id, date, topic, start_at, end_at, participants: [{name}], message_count
 *  }] }   // 公开：未登录也只见块摘要
 */
export interface UnitSummary {
  id: number; date: string; topic: string;
  start_at?: string; end_at?: string;
  participants?: { name: string }[];
  message_count?: number;
}

function whenT(s?: string) {
  if (!s) return "";
  return s.replace("T", " ").slice(11, 16);
}

/** 窖藏目录：一天的原浆坛子，一坛一块。坛子是「一坛」，不是卡片墙。 */
export function CellarList({ date }: { date: string }) {
  const [items, setItems] = useState<UnitSummary[] | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    apiFetch<{ items: UnitSummary[] }>(`/api/context-units?date=${encodeURIComponent(date)}`)
      .then((d) => { if (alive) { setItems(d.items ?? []); setErr(""); } })
      .catch((e) => { if (alive) { setItems(null); setErr(e instanceof ApiError ? e.message : "这一天的原浆还没装坛"); } });
    return () => { alive = false; };
  }, [date]);

  if (err && !items) {
    return (
      <Note tone="ink">{err}——窖藏刚起步，先从 2026-08-23 一天装起。想看原浆长什么样，往下翻日报，金句旁会有「凭证」小链。</Note>
    );
  }
  if (!items) return <p className="py-8 font-sans text-[14px] text-ink-3">正在开窖……</p>;
  if (!items.length) {
    return <p className="rounded-[10px] border border-dashed border-rule px-6 py-10 text-center font-serif text-[17px] text-ink">这一天的原浆还没装坛。</p>;
  }

  return (
    <div className="divide-y divide-rule-soft border-y border-rule">
      {items.map((u) => (
        <Link key={u.id} href={`/cellar/?unit=${u.id}`} className="group block px-1 py-5 transition-colors hover:bg-paper-2/40">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="num font-serif text-[15px] font-bold text-amber-text">坛 #{u.id}</span>
            <h3 className="font-serif text-[19px] font-bold leading-snug text-ink group-hover:text-blue-text">{u.topic || "无题的一坛"}</h3>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 font-sans text-[12.5px] text-ink-3">
            {u.start_at && u.end_at && (
              <span className="num">{whenT(u.start_at)} – {whenT(u.end_at)}</span>
            )}
            {typeof u.message_count === "number" && <span className="num">{u.message_count} 句原话</span>}
            {(u.participants ?? []).length > 0 && (
              <span className="flex flex-wrap gap-x-1.5 gap-y-1">
                {u.participants!.slice(0, 8).map((p) => (
                  <span key={p.name} data-person={p.name} className="rounded-[3px] bg-blue-wash px-1.5 py-[2px] font-sans text-[11.5px] text-blue-text">{p.name}</span>
                ))}
                {u.participants!.length > 8 && <span className="num">等 {u.participants!.length} 人</span>}
              </span>
            )}
          </div>
        </Link>
      ))}
    </div>
  );
}
