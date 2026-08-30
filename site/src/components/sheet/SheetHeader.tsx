import type { Ledger } from "@/lib/shared";

type LedgerCore = Omit<Ledger, "members_focus" | "thanks">;
import { pad3 } from "@/lib/shared";
import { byName } from "@/components/pages/PageHead";
import { Stamp } from "./Stamp";
import { Vessel } from "./Vessel";
import { TypeReveal } from "./TypeReveal";

function readMinutes(l: LedgerCore) {
  const text = [l.lead, ...l.themes.flatMap((t) => [t.body, t.deep]), ...l.insights.map((i) => i.body), ...l.events.map((e) => e.d), ...l.quotes.map((q) => q.t), ...l.growth.takeaways].join("");
  const chars = text.replace(/<[^>]+>/g, "").length;
  return Math.max(3, Math.round(chars / 420));
}

/** 刊头：样品信息行 + 刊名 + 导语；右上批次章。这一屏是论点，不是 banner。 */
export function SheetHeader({ l, prevOpen, totalIssues = 1 }: { l: LedgerCore; prevOpen: number; totalIssues?: number }) {
  const mins = readMinutes(l);
  // 液位 = 累计批次的成长：第 1 批 12%，之后每批 +4%，封顶 92%（对数缓和）
  const vesselLevel = Math.min(0.92, 0.12 + Math.log1p(Math.max(0, totalIssues - 1)) * 0.16);
  return (
    <header className="relative grid gap-6 pb-0 pt-8 sm:pt-10 lg:grid-cols-[minmax(0,1fr)_468px] lg:gap-10">
      <div className="min-w-0">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 border-y border-rule py-3 font-sans text-[13px] sm:grid-cols-4">
          <div><dt className="label">批次</dt><dd className="num mt-0.5 font-semibold text-ink">第 {pad3(l.issue)} 批</dd></div>
          <div><dt className="label">样品日期</dt><dd className="num mt-0.5 text-ink">{l.coverage.from} → {l.coverage.to.slice(5)}</dd></div>
          <div><dt className="label">截止</dt><dd className="num mt-0.5 text-ink">{l.coverage.cutoff}</dd></div>
          <div><dt className="label">阅读</dt><dd className="num mt-0.5 text-ink">约 {mins} 分钟</dd></div>
        </dl>
        <h1 className="mt-6 max-w-[14em] font-serif text-[40px] font-black leading-[1.18] tracking-[0.01em] text-ink sm:text-[52px] lg:text-[58px]">{l.title}</h1>
        <TypeReveal text={l.lead} className="prose-sheet mt-4 max-w-[36em] text-[17px] leading-[1.9] text-ink-2" delay={0.25} step={0.08} />
        {l.threads.some((t) => t.prev_issue) && (
          <div className="mt-6 rounded-[10px] border border-blue-wash-2 bg-blue-wash/70 px-4 py-3 font-sans text-[13.5px] text-ink-2">
            <span className="label mr-3">前情提要</span>
            {l.threads.filter((t) => t.prev_issue).map((t, i) => (
              <a key={t.id} href={`/archive/#thread-${t.id}`} className="mr-3 inline-flex items-center gap-1 text-blue-text no-underline hover:underline">
                {t.title}<span className="num text-ink-3">· 承自第 {pad3(t.prev_issue!)} 批</span>{i < l.threads.filter((x) => x.prev_issue).length - 1 ? "" : ""}
              </a>
            ))}
          </div>
        )}
        <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 font-sans text-[13px] text-ink-3">
          <span>鉴定：<span className="text-ink-2">{byName(l.credits.distilled_by)}</span></span>
          <span>复核：<span className="text-ink-2">{byName(l.credits.reviewed_by)}</span></span>
          {!l.complete && <a href="#caliber" className="inline-flex items-center gap-1.5 rounded-[3px] border border-amber-deep/50 bg-amber-wash px-2 py-[3px] font-medium text-amber-text no-underline transition-colors hover:border-amber-deep">这一期记录有空档 · 看说明 ↓</a>}
          {prevOpen > 0 && <span className="num">上一批遗留悬案 {prevOpen} 件</span>}
        </div>
      </div>
      <div className="flex flex-row flex-wrap items-start justify-start gap-6 lg:justify-end lg:gap-8 lg:pt-1">
        <div className="w-[156px] sm:w-[196px]"><Stamp issue={l.issue} degree={l.quality.overall} grade={l.quality.grade} date={l.date} size={196} /></div>
        <Vessel issue={l.issue} level={vesselLevel} label={`第 ${pad3(l.issue)} 批入缸 · 每一锅都往里添`} />
      </div>
    </header>
  );
}
