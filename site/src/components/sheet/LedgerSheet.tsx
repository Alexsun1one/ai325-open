"use client";
import { useRef } from "react";
import { fmtInt, type Ledger } from "@/lib/shared";
import { Section } from "./Section";
import { SheetHeader } from "./SheetHeader";
import { Intake } from "./Intake";
import { RunChart } from "./RunChart";
import { Timeline } from "./Timeline";
import { Themes } from "./Themes";
import { ToneStamps } from "./ToneStamps";
import { Insights } from "./Insights";
import { QuoteWall } from "./QuoteWall";
import { ScoreGrid } from "./ScoreGrid";
import { Growth } from "./Growth";
import { Docket } from "./Docket";
import { Glossary } from "./Glossary";
import { MembersFocus } from "./MembersFocus";
import { SheetFooter } from "./SheetFooter";
import { ProofRuler } from "./ProofRuler";
import { TermHover } from "./TermHover";
import { Newcomers } from "./Newcomers";
import { Notebook } from "./Notebook";
import { Ambient } from "./Ambient";
import { DoubleRule } from "./DoubleRule";
import { ParagraphTools } from "./ParagraphTools";
import { Highlights } from "./Highlights";
import { PersonHover } from "./PersonHover";

const SECTIONS = [
  { id: "intake", label: "进料" },
  { id: "run", label: "蒸馏曲线" },
  { id: "timeline", label: "大事记" },
  { id: "themes", label: "品评项" },
  { id: "tone", label: "真伪鉴定" },
  { id: "insights", label: "深潜" },
  { id: "quotes", label: "逐字摘录" },
  { id: "score", label: "五维 · 度数" },
  { id: "growth", label: "出品" },
  { id: "docket", label: "悬案台账" },
  { id: "glossary", label: "黑话 · 弹药" },
  { id: "members", label: "成员高光" },
];

type Neighbor = { date: string; issue: number; title: string } | null;
export function LedgerSheet({ l, prevOpen = 0, totalIssues = 1, prev = null, next = null, illus = [], spots = {} }: { l: Ledger; prevOpen?: number; totalIssues?: number; prev?: Neighbor; next?: Neighbor; illus?: (string | null)[]; spots?: Record<string, string> }) {
  const ref = useRef<HTMLDivElement>(null);
  const intake = [
    { k: "消息", v: l.stats.msgs, note: "含建群日档案" },
    { k: "发声者", v: l.stats.speakers, note: `群成员 ${l.stats.members}` },
    { k: "小作文", v: l.stats.essays, suffix: l.stats.essays_open ? `+${l.stats.essays_open} 悬` : undefined, note: "入群仪式已交" },
    { k: "新面孔", v: (l.newcomers ?? []).length, note: "本批入群" },
    { k: "主题幕", v: l.stats.themes, note: "本批蒸出的主题" },
    { k: "金句", v: l.stats.quotes, note: "逐字摘录" },
  ];
  return (
    <main id="top" className="relative z-[1] mx-auto max-w-[1180px] px-5 sm:px-8">
      <Ambient />
      <TermHover glossary={l.glossary} />
      <PersonHover />
      <Notebook date={l.date} issue={l.issue} title={l.title} />
      <ParagraphTools date={l.date} issue={l.issue} degree={l.quality.overall} />
      <Highlights date={l.date} />
      <SheetHeader l={l} prevOpen={prevOpen} totalIssues={totalIssues} />
      <DoubleRule />

      <div ref={ref} className="relative">
      <ProofRuler target={ref} marks={SECTIONS} degree={l.quality.overall} grade={l.quality.grade} />
      <Section id="intake" spot={spots["intake"]} label="进料" sub="这一锅投进了什么">
        <Intake fields={intake} />
        <p className="mt-2.5 font-sans text-[12px] text-ink-3">这里的「消息」和下面曲线、度数用的数法不同，不能直接相减 · <a href="#caliber" className="text-blue-text">怎么数的</a></p>
      </Section>

      <Section id="run" spot={spots["run"]} label="蒸馏曲线" sub="这一天什么时候最热">
        <RunChart hours={l.hours} events={l.events} caption={l.pulse.caption} />
        {l.pulse.note && <p className="prose-sheet mt-5 border-t border-dotted border-blue-wash-2 pt-3 text-[15.5px] leading-[1.8] text-ink-2" dangerouslySetInnerHTML={{ __html: l.pulse.note }} />}
      </Section>

      <Section id="timeline" spot={spots["timeline"]} label="大事记" sub="按北京时间">
        <Timeline events={l.events} />
      </Section>

      <Section id="themes" spot={spots["themes"]} label="品评项" sub="每幕 = 重织 + 手写深潜 + 逐字原声">
        <Themes themes={l.themes} threads={l.threads} issue={l.issue} illus={illus} />
      </Section>

      <Section id="tone" spot={spots["tone"]} label="真伪鉴定" sub="把段子当宣言 = 事故">
        <ToneStamps notes={l.tone_notes} />
      </Section>

      <Section id="insights" spot={spots["insights"]} label="深潜" sub="碎片之下的洋流 · 手写部分是整理者延伸">
        <Insights items={l.insights} />
      </Section>

      <Section id="quotes" spot={spots["quotes"]} label="逐字摘录" sub="全部原文 · 语气已鉴定">
        <QuoteWall quotes={l.quotes} issue={l.issue} date={l.date} degree={l.quality.overall} />
      </Section>

      <Section id="score" spot={spots["score"]} label="五维 · 度数" sub="给内容打分，不给人">
        <ScoreGrid dims={l.quality.dimensions} overall={l.quality.overall} grade={l.quality.grade} basis={l.quality.basis} />
      </Section>

      <Section id="growth" spot={spots["growth"]} label="出品" sub="带得走的成长">
        <Growth takeaways={l.growth.takeaways} todo={l.growth.todo} date={l.date} carried={l.growth.carried ?? []} prevDate={prev?.date} />
      </Section>

      <Section id="docket" spot={spots["docket"]} label="悬案台账" sub="没兑现的承诺、没吵完的架">
        <Docket docket={l.docket} clashes={l.clashes} issue={l.issue} />
      </Section>

      <Section id="glossary" spot={spots["glossary"]} label="黑话 · 弹药" sub="想听懂这个群先学这些词">
        <Glossary items={l.glossary} arsenal={l.arsenal} />
      </Section>

      <Section id="members" spot={spots["members"]} label="成员高光" sub="新面孔先出卡，再看本期最值得看见的人">
        <Newcomers items={l.newcomers ?? []} issue={l.issue} />
        <MembersFocus items={l.members_focus} thanks={l.thanks ?? []} />
      </Section>

      </div>
      <SheetFooter l={l} prev={prev} next={next} />
    </main>
  );
}
