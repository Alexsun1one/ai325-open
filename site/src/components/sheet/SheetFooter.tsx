"use client";
import type { Ledger } from "@/lib/shared";
import { DoubleRule } from "./DoubleRule";

export function SheetFooter({ l, prev, next }: { l: Ledger; prev?: { date: string; issue: number; title: string } | null; next?: { date: string; issue: number; title: string } | null }) {
  return (
    <footer className="pt-2">
      <DoubleRule />
      <nav aria-label="相邻批次" className="no-print mb-8 grid gap-3 sm:grid-cols-2">
        <a href={prev ? `/ledger/${prev.date}/` : "/archive/"} className={`rounded-[10px] border px-4 py-3 no-underline transition-colors ${prev ? "border-rule hover:border-blue-2" : "border-rule-soft text-ink-3"}`}>
          <div className="label">上一批</div>
          <div className="mt-1 font-serif text-[15px] font-semibold text-ink">{prev ? `第 ${String(prev.issue).padStart(3, "0")} 批 · ${prev.title}` : "这是第一锅 · 去往期看线索图"}</div>
        </a>
        <a href={next ? `/ledger/${next.date}/` : "/archive/"} className={`rounded-[10px] border px-4 py-3 text-right no-underline transition-colors ${next ? "border-rule hover:border-blue-2" : "border-rule-soft text-ink-3"}`}>
          <div className="label">下一批</div>
          <div className="mt-1 font-serif text-[15px] font-semibold text-ink">{next ? `第 ${String(next.issue).padStart(3, "0")} 批 · ${next.title}` : "明早 7 点蒸昨天这一锅"}</div>
        </a>
      </nav>
      <div className="grid gap-8 lg:grid-cols-[168px_minmax(0,1fr)]">
        <div id="caliber" className="label scroll-mt-24">这期怎么记的</div>
        <div className="max-w-[44em] space-y-3 font-sans text-[13.5px] leading-[1.8] text-ink-3">
          <p>{l.coverage.note}</p>
          <p>三处数字数法不同：刊头「消息」算上了建群日档案；蒸馏曲线只算有准确时间的那部分；度数按评分当时的统计。所以它们之间不能直接相减。</p>
          {l.footer.map((p, i) => <p key={i} dangerouslySetInnerHTML={{ __html: p }} />)}
          <div className="no-print flex flex-wrap gap-3 pt-2">
            <button type="button" onClick={() => window.print()} className="rounded-md border border-rule bg-paper px-3 py-1.5 font-medium text-ink-2 transition-colors hover:border-blue-2 hover:text-ink">打印 / 存为 PDF</button>
            <a href="#top" className="rounded-md border border-rule bg-paper px-3 py-1.5 font-medium text-ink-2 no-underline transition-colors hover:border-blue-2 hover:text-ink">回到刊头</a>
          </div>
        </div>
      </div>
    </footer>
  );
}
