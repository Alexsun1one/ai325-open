import type { Clash, Docket as D } from "@/lib/shared";
import { maskRawIds, pad3 } from "@/lib/shared";

/** 悬案台账（跨期挂账）× 分歧对撞。 */
export function Docket({ docket, clashes, issue }: { docket: D[]; clashes: Clash[]; issue: number }) {
  return (
    <div className="space-y-12">
      <ul className="divide-y divide-rule-soft border-y border-rule">
        {docket.map((d, i) => (
          // items-baseline：分类标签、案由、挂账三格同落在标题那条基线上
          <li key={i} className="grid gap-x-6 gap-y-2 py-5 sm:grid-cols-[100px_minmax(0,1fr)_auto] sm:items-baseline">
            {/* 宽屏统一撑满 100px 格并居中，三字五字的分类不再宽窄不一 */}
            <span className="inline-flex h-fit w-fit items-center justify-center rounded-[3px] border border-blue-wash-2 bg-blue-wash px-2 py-[3px] text-center font-sans text-[11.5px] font-semibold whitespace-nowrap text-blue-text sm:h-auto sm:w-full">{d.kind}</span>
            <div className="min-w-0">
              <div className="font-serif text-[17px] font-semibold leading-[1.5] text-ink">{d.h}</div>
              <p className="prose-sheet mt-1.5 text-[15.5px] leading-[1.8] text-ink-2" dangerouslySetInnerHTML={{ __html: maskRawIds(d.d) }} />
            </div>
            <span className="num whitespace-nowrap font-sans text-[12px] text-ink-3 sm:text-right">挂账 · 自第 {pad3(issue)} 批</span>
          </li>
        ))}
      </ul>
      <div className="grid gap-x-10 gap-y-9 lg:grid-cols-3">
        {clashes.map((c, i) => (
          <article key={i} className="min-w-0 border-t border-rule-soft pt-5">
            <h3 className="font-serif text-[19px] font-bold leading-[1.4] text-ink">{c.h}</h3>
            {c.en && <div className="mt-1.5 font-sans text-[10.5px] font-medium tracking-[0.2em] text-ink-3">{c.en}</div>}
            <p className="prose-sheet mt-4 text-[15.5px] leading-[1.85]" dangerouslySetInnerHTML={{ __html: maskRawIds(c.sides) }} />
            {/* 裁决是整理者写上去的：手写体 + 段首缩进，读起来是另一个人开口 */}
            {c.verdict && <p className="hand mt-4 indent-[1em] text-[17px] leading-[1.85]" dangerouslySetInnerHTML={{ __html: maskRawIds(c.verdict) }} />}
          </article>
        ))}
      </div>
    </div>
  );
}
