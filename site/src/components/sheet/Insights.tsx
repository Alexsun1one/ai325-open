import type { Insight } from "@/lib/shared";
import { Prose } from "@/components/pages/Prose";

/**
 * 深潜六层：打字的部分宋体，「没说破的」手写体（<u>）。
 * 两栏高度天然不齐，靠每条自己的上格线把参差的留白读成台账的行带，
 * 而不是「两块浮着的文字」。
 */
export function Insights({ items }: { items: Insight[] }) {
  return (
    <div className="grid gap-x-10 gap-y-9 lg:grid-cols-2">
      {items.map((it, i) => (
        <article key={i} className="min-w-0 border-t border-rule-soft pt-5">
          <h3 className="font-serif text-[20px] font-bold leading-[1.4] text-ink">{it.h}</h3>
          {it.en && <div className="mt-1.5 font-sans text-[10.5px] font-medium tracking-[0.2em] text-ink-3">{it.en}</div>}
          <Prose html={it.body} className="mt-4 text-[16px] leading-[1.9]" />
        </article>
      ))}
    </div>
  );
}
