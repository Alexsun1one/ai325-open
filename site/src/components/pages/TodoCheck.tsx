"use client";
import { useEffect, useMemo, useState } from "react";
import type { TodoPhase } from "@/lib/shared";

const KEY = (date: string) => `xf-todo-${date}`;

/** 本期行动打卡：与本期页共用 localStorage `xf-todo-<date>` 和同一套 id，勾选互通。只在这台设备。 */
export function TodoCheck({ todo, date }: { todo: TodoPhase[]; date: string }) {
  const ids = useMemo(() => todo.flatMap((p, pi) => p.items.map((_, ii) => `${pi}-${ii}`)), [todo]);
  const [done, setDone] = useState<Record<string, boolean>>({});
  const [ready, setReady] = useState(false);
  useEffect(() => {
    try { const raw = localStorage.getItem(KEY(date)); if (raw) setDone(JSON.parse(raw)); } catch {}
    setReady(true);
  }, [date]);
  const toggle = (id: string) => setDone((d) => { const n = { ...d, [id]: !d[id] }; try { localStorage.setItem(KEY(date), JSON.stringify(n)); } catch {} return n; });
  const count = ids.filter((i) => done[i]).length;
  const pct = ids.length ? (count / ids.length) * 100 : 0;

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-1">
        <div className="flex items-baseline gap-2">
          <span className="num text-[42px] font-semibold leading-none text-amber-text">{ready ? count : 0}</span>
          <span className="num text-[16px] font-medium text-ink-3">/ {ids.length} 项</span>
        </div>
        <span className="font-sans text-[12.5px] text-ink-3">{ready ? "只留在你这台设备上 · 不上传、不汇总、换台设备就没了" : "读取中……"}</span>
      </div>
      <div className="mt-2.5 h-[4px] w-full overflow-hidden rounded-full bg-paper-3">
        <div className="h-full bg-amber transition-[width] duration-700 ease-[var(--ease-out-expo)]" style={{ width: `${ready ? pct : 0}%` }} />
      </div>
      <div className="mt-6 grid gap-x-10 gap-y-7 sm:grid-cols-3">
        {todo.map((p, pi) => (
          <div key={p.phase}>
            <div className="label mb-2.5">{p.phase}</div>
            <ul className="space-y-2.5">
              {p.items.map((it, ii) => {
                const id = `${pi}-${ii}`;
                const on = !!done[id];
                return (
                  <li key={id}>
                    <button type="button" onClick={() => toggle(id)} aria-pressed={on} className="grid min-h-11 w-full grid-cols-[18px_1fr] items-start gap-2.5 py-1 text-left sm:min-h-0 sm:py-0">
                      <span aria-hidden className={`mt-[5px] inline-flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[4px] border transition-colors ${on ? "border-amber-deep bg-amber" : "border-blue-2 bg-paper"}`}>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" className={`text-paper transition-transform duration-300 ease-[var(--ease-out-expo)] ${on ? "scale-100" : "scale-0"}`}><path d="M5 12.5l4.5 4.5L19 7" /></svg>
                      </span>
                      <span className={`font-serif text-[15.5px] leading-[1.75] ${on ? "text-ink-3 line-through decoration-amber-deep/50" : "text-ink"}`}>{it}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
