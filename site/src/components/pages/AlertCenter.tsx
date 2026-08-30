"use client";
import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/auth";
import { Note } from "./FormBits";

/** 契约：GET /api/admin/alerts?limit=N → { items: [{ts,status,level,source,summary,incident,count}], unread, total }（admin 专属） */
interface AlertRec { ts: string; status: string; level: string; source: string; summary: string; incident: string; count: number }
interface AlertPayload { items: AlertRec[]; unread: number; total: number }

const LEVEL_CLS: Record<string, string> = {
  CRITICAL: "border-cinnabar/45 bg-cinnabar-wash text-cinnabar-text",
  ERROR: "border-cinnabar/40 bg-cinnabar-wash/60 text-cinnabar-text",
  WARN: "border-amber-deep/45 bg-amber-wash text-amber-text",
  INFO: "border-rule bg-paper-2 text-ink-3",
};

const whenT = (s: string) => (s || "").replace("T", " ").slice(5, 16);

/** 值守台：未处理告警红点 + 最近 N 条。只在 admin 私窖出现。 */
export function AlertCenter() {
  const [data, setData] = useState<AlertPayload | null>(null);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try { setData(await apiFetch<AlertPayload>("/api/admin/alerts?limit=10")); setErr(""); }
    catch (e) { setData(null); setErr(e instanceof ApiError ? e.message : "值守台没取到"); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  if (err && !data) return <Note tone="bad">{err}</Note>;
  if (!data) return <p className="font-sans text-[13px] text-ink-3">值守台读取中……</p>;

  return (
    <div>
      <div className="flex items-center gap-2">
        <span className="font-serif text-[17px] font-bold text-ink">值守台</span>
        {data.unread > 0 ? (
          <span className="inline-flex items-center gap-1.5 rounded-[4px] border border-cinnabar/50 bg-cinnabar-wash px-2 py-[2px] font-sans text-[11.5px] font-bold text-cinnabar-text">
            <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-cinnabar" />
            近 24h {data.unread} 起待处理
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-[4px] border border-teal/45 bg-teal-wash px-2 py-[2px] font-sans text-[11.5px] font-semibold text-teal-text">
            <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-teal" />
            近 24h 无告警
          </span>
        )}
      </div>
      {data.items.length === 0 ? (
        <p className="mt-3 font-sans text-[13px] text-ink-3">还没有告警记录——自动化都在好好干活。</p>
      ) : (
        <ul className="mt-3 divide-y divide-rule-soft border-y border-rule">
          {data.items.map((a, i) => (
            <li key={`${a.ts}-${i}`} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 py-2.5">
              <span className={`rounded-[3px] border px-1.5 py-[1px] font-sans text-[10px] font-semibold ${LEVEL_CLS[a.level] || LEVEL_CLS.INFO}`}>{a.level}</span>
              <span className="font-sans text-[12px] font-semibold text-ink">{a.source}</span>
              <span className="min-w-0 flex-1 truncate font-sans text-[12.5px] text-ink-2" title={a.summary}>{a.summary}</span>
              <span className="num font-sans text-[10.5px] text-ink-3">{whenT(a.ts)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
