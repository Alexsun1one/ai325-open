"use client";
import { useEffect, useMemo, useState } from "react";
import type { TodoPhase } from "@/lib/shared";

const KEY = (date: string) => `xf-todo-${date}`;

/**
 * 打勾框：未勾 = 待填的蓝格，勾上 = 注满的琥珀格。
 * 对勾用 stroke-dashoffset 从起笔画到收笔（21 ≈ 该路径长度），像笔划下去，不是弹出来。
 */
function Check({ checked }: { checked: boolean }) {
  return (
    <span
      aria-hidden
      className={`mt-[5px] inline-flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[4px] border transition-colors duration-200 ease-[var(--ease-out-expo)] ${checked ? "border-amber-deep bg-amber" : "border-blue-2 bg-paper group-hover/todo:border-blue group-hover/todo:bg-paper-2"}`}
    >
      <svg
        width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round"
        className={`text-paper transition-opacity duration-200 ease-[var(--ease-out-expo)] ${checked ? "opacity-100" : "opacity-0"}`}
      >
        <path
          d="M5 12.5l4.5 4.5L19 7"
          strokeDasharray="21"
          strokeDashoffset={checked ? 0 : 21}
          className="transition-[stroke-dashoffset] duration-[320ms] ease-[var(--ease-out-expo)] motion-reduce:transition-none"
        />
      </svg>
    </span>
  );
}

/**
 * 计数旁的琥珀液滴：一滴未落时只有轮廓，勾上第一项就注满——
 * 和量杯/进度条同一套「液面」语法，9x12 的小墨点，不抢读数。
 */
function Drop({ filled }: { filled: boolean }) {
  return (
    <svg
      aria-hidden width="9" height="12" viewBox="0 0 12 16" fill="none"
      className={`mr-1.5 inline-block align-[-1.5px] transition-colors duration-200 ease-[var(--ease-out-expo)] ${filled ? "text-amber" : "text-amber-2"}`}
    >
      <path d="M6 .9c0 0 5 5.7 5 9.2A5 5 0 0 1 1 10.1C1 6.6 6 .9 6 .9Z" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
    </svg>
  );
}

/** 带得走的成长：装备清单 + 可打勾的行动清单（本机保存）。 */
export function Growth({ takeaways, todo, date, carried = [], prevDate }: { takeaways: string[]; todo: TodoPhase[]; date: string; carried?: TodoPhase[]; prevDate?: string }) {
  const ids = useMemo(() => todo.flatMap((p, pi) => p.items.map((_, ii) => `${pi}-${ii}`)), [todo]);
  const [done, setDone] = useState<Record<string, boolean>>({});
  useEffect(() => { try { const raw = localStorage.getItem(KEY(date)); if (raw) setDone(JSON.parse(raw)); } catch {} }, [date]);
  const toggle = (id: string) => setDone((d) => { const n = { ...d, [id]: !d[id] }; try { localStorage.setItem(KEY(date), JSON.stringify(n)); } catch {} return n; });
  const count = ids.filter((i) => done[i]).length;
  return (
    <div className="grid gap-x-10 gap-y-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div>
        <h3 className="font-serif text-[20px] font-bold text-ink">六件随身装备</h3>
        <ol className="mt-5 list-none space-y-4">
          {takeaways.map((t, i) => (
            // 7px 的点正好占一列，mt 12px 让它落在首行汉字的视觉中线上
            <li key={i} className="grid grid-cols-[7px_minmax(0,1fr)] gap-x-2.5">
              <span aria-hidden className="mt-[12px] h-[7px] w-[7px] rounded-full bg-amber" />
              <p className="prose-sheet text-[16px] leading-[1.85]" dangerouslySetInnerHTML={{ __html: t }} />
            </li>
          ))}
        </ol>
      </div>
      <div>
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h3 className="font-serif text-[20px] font-bold text-ink">行动清单</h3>
          <span className="num font-sans text-[13px] text-ink-3">
            <Drop filled={count > 0} />已完成 <span className="font-semibold text-amber-text">{count}</span> / {ids.length} · 只存在你这台设备
          </span>
        </div>
        <div aria-hidden className="mt-3 h-[3px] w-full overflow-hidden rounded-full bg-paper-3">
          <div className="h-full rounded-full bg-amber transition-[width] duration-500 ease-[var(--ease-out-expo)] motion-reduce:transition-none" style={{ width: `${ids.length ? (count / ids.length) * 100 : 0}%` }} />
        </div>
        <div className="mt-6 space-y-6">
          {carried.length > 0 && (
            <div className="rounded-[10px] border border-amber-wash-2 bg-amber-wash/50 px-4 py-2.5 font-sans text-[12.5px] leading-[1.6] text-amber-text">
              顺延 · 上一批未勾完的 {carried.reduce((n, p) => n + p.items.length, 0)} 项仍在台账里{prevDate ? `（自 ${prevDate}）` : ""}；新出品在下面。
            </div>
          )}
          {todo.map((p, pi) => (
            <div key={pi}>
              <div className="label">{p.phase}</div>
              <ul className="mt-2.5 divide-y divide-rule-soft border-y border-rule-soft">
                {p.items.map((it, ii) => {
                  const id = `${pi}-${ii}`; const c = !!done[id];
                  return (
                    <li key={ii}>
                      <button
                        type="button"
                        onClick={() => toggle(id)}
                        aria-pressed={c}
                        className="group/todo flex w-full items-start gap-3 rounded-[4px] px-1.5 py-3 text-left transition-colors duration-200 ease-[var(--ease-out-expo)] hover:bg-paper-2/60 active:bg-paper-3/60"
                      >
                        <Check checked={c} />
                        <span className={`prose-sheet text-[15.5px] leading-[1.75] transition-colors duration-200 ease-[var(--ease-out-expo)] ${c ? "text-ink-3" : "text-ink"}`}>{it}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
