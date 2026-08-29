import type { Newcomer } from "@/lib/shared";
import { isRawId, maskRawIds, pad3 } from "@/lib/shared";

/** 新面孔：入群当天就出卡，「首见于第 N 批」会跟着这个人走。 */
export function Newcomers({ items, issue }: { items: Newcomer[]; issue: number }) {
  if (!items.length) return null;
  return (
    <div className="mb-10">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="font-serif text-[19px] font-bold text-ink">新面孔</h3>
        <span className="font-sans text-[12.5px] text-ink-3">欢迎卡 · 从今天起你的名字会出现在台账里</span>
      </div>
      <ul className="mt-5 grid gap-x-10 gap-y-7 sm:grid-cols-2">
        {items.map((n, i) => (
          <li key={i} className="min-w-0 border-t border-amber-deep/50 pt-3.5">
            {/* 窄栏时「首见于第 001 批 · 时间」整条落到下一行靠左，不再被挤出栏外 */}
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <span className="min-w-0 font-serif text-[18px] font-bold leading-[1.4] text-ink">{n.name}</span>
              <span className="num shrink-0 font-sans text-[12px] text-amber-text sm:text-right">首见于第 {pad3(issue)} 批 · {n.t}</span>
            </div>
            <div className="mt-1.5 font-sans text-[13px] leading-[1.6] text-ink-2">{maskRawIds(n.note)}{n.by && !isRawId(n.by) ? ` · ${n.by}` : ""}</div>
            {n.first_words && <p className="hand mt-2.5 max-w-[34em] text-[16px] leading-[1.8]">{n.first_words}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}
