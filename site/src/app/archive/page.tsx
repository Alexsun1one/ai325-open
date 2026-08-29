import type { Metadata } from "next";
import Link from "next/link";
import { getAllLedgers, pad3, fmtInt } from "@/lib/content";
import { Section } from "@/components/sheet/Section";
import { PageHead, PageShell, GapNote, ScrollHint } from "@/components/pages/PageHead";
import { ThreadMap, type ThreadRow } from "@/components/pages/ThreadMap";
import { CompoundRun, type Series } from "@/components/pages/CompoundRun";
import { Vessel } from "@/components/sheet/Vessel";

export const metadata: Metadata = {
  title: "往期 · 线索图",
  description: "所有批次的台账索引，以及主题线索跨期承接的线索图：每条线索首蒸于哪一批、最近复蒸于哪一批、成熟到了什么程度。",
};

export default function ArchivePage() {
  const ledgers = getAllLedgers();                      // 新 → 旧
  const asc = [...ledgers].sort((a, b) => a.issue - b.issue);
  const issues = asc.map((l) => l.issue);
  const latest = asc[asc.length - 1];

  // 线索索引：同一 id 在多批出现即连成一条线
  const map = new Map<string, ThreadRow>();
  for (const l of asc) {
    for (const t of l.threads) {
      const row = map.get(t.id) ?? { id: t.id, title: t.title, theme: t.theme, status: t.status, issues: [], dates: [] };
      row.title = t.title;
      row.theme = t.theme;
      row.status = t.status;
      row.issues.push(l.issue);
      row.dates.push(l.date);
      map.set(t.id, row);
    }
  }
  const rows = [...map.values()].sort((a, b) => b.issues.length - a.issues.length || a.issues[0] - b.issues[0]);
  const single = asc.length === 1;
  const totalMsgs = asc.reduce((s, l) => s + l.stats.msgs, 0);
  const openDocket = asc.reduce((s, l) => s + l.docket.filter((d) => d.status === "open").length, 0);

  // 复利：每一锅不是独立的，是往同一个缸里添——逐批累积，只增不减
  const cumOf = (f: (l: (typeof asc)[number]) => number) => { let n = 0; return asc.map((l) => (n += f(l))); };
  const seenThreads = new Set<string>();
  const cumThreads = asc.map((l) => { for (const t of l.threads) seenThreads.add(t.id); return seenThreads.size; });
  const series: Series[] = [
    { k: "累计批次", unit: "批", note: "每批 = 一锅，一天一锅", cum: asc.map((_, i) => i + 1) },
    { k: "累计金句", unit: "条", note: "逐字摘录，只进不出", cum: cumOf((l) => l.stats.quotes) },
    { k: "累计线索", unit: "条", note: "去重后的主题线索", cum: cumThreads },
    { k: "累计行动项", unit: "项", note: "已发出的可打勾行动", cum: cumOf((l) => l.growth.todo.reduce((s, p) => s + p.items.length, 0)) },
  ];
  const vesselLevel = Math.min(0.92, 0.12 + Math.log1p(Math.max(0, asc.length - 1)) * 0.16);
  const closedDocket = asc.reduce((s, l) => s + l.docket.filter((d) => d.status === "closed").length, 0);

  return (
    <PageShell>
      <PageHead
        title="往期 · 线索图"
        lead="每一批都是一锅。这一页把所有锅摆在一起：上半是每一批的账，下半是主题线索的图——一个话题最早在哪一批被蒸出来、后来又在哪一批被重新端上桌，一眼看得到。"
        fields={[
          { k: "已出批次", v: `${fmtInt(asc.length)} 批` },
          { k: "覆盖", v: `${asc[0].coverage.from} → ${latest.coverage.to.slice(5)}` },
          { k: "累计进料", v: `${fmtInt(totalMsgs)} 条` },
          { k: "在办悬案", v: `${openDocket} 件` },
        ]}
        note={
          single ? (
            <>
              目前只有<span className="num font-semibold text-blue-text"> 第 001 批</span>。跨期承接、复蒸标记、线索成熟度都已按多批次布好版，第 002 批一进来就会自动连线——现在图上留的虚线空槽就是它们的位置。
            </>
          ) : undefined
        }
      />

      <Section id="compound" label="复利" sub="每一锅不是独立的，是往同一个缸里添">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_232px]">
          <div className="min-w-0">
            <CompoundRun series={series} issues={issues} ghost={5} />
            <div className="mt-5">
              {single ? (
                <GapNote>
                  <b>曲线从第 002 批开始画。</b>现在四条线各只有一个点——累积量是真的，走势还不存在。右边虚线圈是接下来几批的落点，第 002 批一入库，线会从这个点长过去。
                </GapNote>
              ) : (
                <p className="font-sans text-[13px] text-ink-3">四条线都是累积量，只增不减；斜率越陡，说明那几批往缸里添得越多。</p>
              )}
            </div>
            <p className="prose-sheet mt-6 text-[16px] leading-[1.85] text-ink-2">
              悬案是另一种复利，方向相反：在办 <span className="num font-semibold text-cinnabar-text">{openDocket}</span> 件、已结案 <span className="num font-semibold text-teal-text">{closedDocket}</span> 件。
              {closedDocket === 0 && <> 第 001 批的三件悬案还全挂着——<span className="hand">挂账不销账，就不算复利。</span></>}
            </p>
            <p className="mt-3 font-sans text-[12.5px] leading-relaxed text-ink-3">
              「累计行动项」只统计<b>发出</b>了多少项。谁打没打勾<b>只留在你这台设备上</b>，不上传、不汇总，所以这里不会有「兑现率」这种数。你自己勾到哪了，去<Link href="/events/#todo" className="text-blue-text no-underline hover:underline">活动专区</Link>看。
            </p>
          </div>
          <div className="flex justify-center lg:justify-end lg:pt-1">
            <Vessel issue={latest.issue} level={vesselLevel} label={`累计 ${asc.length} 批入缸 · 每一锅都往里添`} />
          </div>
        </div>
      </Section>

      <Section id="batches" label="批次台账" sub="按批次号倒序 · 点标题读整锅">
        <ScrollHint />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[620px] border-collapse">
            <thead>
              <tr className="border-y border-rule">
                {["批次", "日期", "标题", "进料消息", "度数", "完整性"].map((h, i) => (
                  <th key={h} className={`label whitespace-nowrap py-2.5 ${i >= 3 ? "text-right" : "text-left"}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-rule-soft">
              {ledgers.map((l) => (
                <tr key={l.date} className="group transition-colors hover:bg-paper-2/60">
                  <td className="num whitespace-nowrap py-3.5 pr-4 font-sans text-[14px] font-semibold text-blue-text">第 {pad3(l.issue)} 批</td>
                  <td className="num whitespace-nowrap py-3.5 pr-4 font-sans text-[13.5px] text-ink-2">{l.date}</td>
                  <td className="py-3.5 pr-4">
                    <Link href={`/ledger/${l.date}/`} className="inline-flex min-h-11 items-center font-serif text-[16.5px] font-bold text-ink no-underline group-hover:text-blue-text sm:min-h-0">{l.title}</Link>
                    <div className="mt-0.5 font-sans text-[12.5px] text-ink-3">{l.stats.themes} 幕 · {l.stats.quotes} 金句 · {l.stats.speakers} 人发声</div>
                  </td>
                  <td className="num py-3.5 pr-4 text-right font-sans text-[15px] font-semibold text-ink">{fmtInt(l.stats.msgs)}</td>
                  <td className="num py-3.5 pr-4 text-right font-sans text-[15px] font-semibold text-amber-text">{l.quality.overall}°<span className="ml-1.5 text-[12px] font-medium text-ink-3">{l.quality.grade}</span></td>
                  <td className="py-3.5 text-right">
                    <span className={`inline-flex whitespace-nowrap rounded-[4px] border px-2 py-[3px] font-sans text-[11.5px] font-semibold ${l.complete ? "border-teal/50 bg-teal-wash text-teal-text" : "border-amber-deep/50 bg-amber-wash text-amber-text"}`}>
                      {l.complete ? "记全了" : "有漏的"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {ledgers.some((l) => !l.complete) && (
          <div className="mt-5">
            <GapNote>
              标「有漏的」是说那一天我们没记全，具体漏在哪写在那一期的最后。第 001 批漏的是：微信隔三个小时会掉一次线，掉线那阵子的消息补不回来；另外建群那天（08-21）的内容是从《群聊精华整理》里回溯的，不如后面几天记得细。
            </GapNote>
          </div>
        )}
      </Section>

      <Section id="threads" label="线索图" sub="行 = 线索 · 列 = 批次 · 点开看承接">
        <ScrollHint>线索图较宽，可左右滑动</ScrollHint>
        <ThreadMap rows={rows} issues={issues} ghost={5} />
        <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 font-sans text-[12.5px] text-ink-3">
          <span className="inline-flex items-center gap-2"><i className="inline-block h-[11px] w-[11px] rounded-full border-2 border-amber-deep bg-amber" />该批出现</span>
          <span className="inline-flex items-center gap-2"><i className="inline-block h-[5px] w-[5px] rounded-full bg-rule" />该批未出现</span>
          <span className="inline-flex items-center gap-2"><i className="inline-block h-[9px] w-[9px] rounded-full border border-dashed border-rule" />尚未出刊的批次</span>
        </div>
        <p className="prose-sheet mt-6 text-[16px] leading-[1.85] text-ink-2">
          成熟度是按<span className="hand">「出现过几次」</span>算的，不是按写得好不好：只蒸过一次叫<b>幼苗</b>，复蒸过叫<b>生长</b>，四批以上反复出现叫<b>成熟</b>，结案的叫<b>封存</b>。
          {single && <> 本批六条线索全部<b>首蒸于第 001 批 · 待续</b>——这是创刊号的事实，不是数据缺失。</>}
        </p>
      </Section>
    </PageShell>
  );
}
