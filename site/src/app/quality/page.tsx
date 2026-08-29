import type { Metadata } from "next";
import Link from "next/link";
import { getAllLedgers, pad3 } from "@/lib/content";
import { Section } from "@/components/sheet/Section";
import { ScoreGrid } from "@/components/sheet/ScoreGrid";
import { PageHead, PageShell, GapNote, ScrollHint } from "@/components/pages/PageHead";
import { DegreeRun } from "@/components/pages/DegreeRun";

export const metadata: Metadata = {
  title: "度数",
  description: "每一批的度数怎么来的：逐批曲线、本批五维打分，以及五个维度的稳定定义——定义不随批次改动，分数才可比。",
};

/** 稳定映射：这五条定义写死在这里，逐批复用。改定义 = 改这一页，并在此标注改动批次。 */
const MAP: Record<string, { measures: string; how: string; high: string; low: string; not: string }> = {
  信息密度: {
    measures: "单位消息里装了多少有效信息。",
    how: "长文率（超阈值消息占比）× 均长（字/条）。",
    high: "一条消息值得读完，长论多、废话少。",
    low: "表情包与「收到」「+1」占了大头。",
    not: "不度量观点对不对，只度量信息厚不厚。",
  },
  互动质量: {
    measures: "这是一场对话，还是几个人在广播。",
    how: "话题轮转率（不同人交替发言的比例）+ @提及次数。",
    high: "有人接话、有人反驳，话题在人之间转。",
    low: "一个人连发十条，没人接。",
    not: "不度量气氛好不好，吵架也算高互动。",
  },
  知识贡献: {
    measures: "沉淀下来、别人能拿走复用的东西。",
    how: "知识型消息占比（含链接 / 工具 / 方法 / 代码）+ 小作文篇数。",
    high: "有链接、有方法、有可复制的做法。",
    low: "聊得热闹，第二天什么也搜不到。",
    not: "不度量知识对不对，链接是错的也计数。",
  },
  参与均衡: {
    measures: "发言权散在多少人手里。",
    how: "TOP3 发言占比取反——占比越低，此分越高。",
    high: "更多人愿意开口，不是几个人的主场。",
    low: "少数人贡献了大半内容。",
    not: "不度量谁说得对；均衡低不等于内容差。",
  },
  深度输出: {
    measures: "有没有人真的坐下来写长东西。",
    how: "超 200 字的消息条数（小作文 / 长论）。",
    high: "有人愿意花时间把想法写完整。",
    low: "全是碎片，没人展开。",
    not: "不度量写得好不好，只度量有没有人写。",
  },
};

export default function QualityPage() {
  const ledgers = getAllLedgers();                   // 新 → 旧
  const asc = [...ledgers].sort((a, b) => a.issue - b.issue);
  const latest = asc[asc.length - 1];
  const q = latest.quality;
  const points = asc.map((l) => ({ issue: l.issue, date: l.date, overall: l.quality.overall, grade: l.quality.grade }));
  const single = asc.length === 1;
  const sum = q.dimensions.reduce((s, d) => s + d.score, 0);
  const avg = sum / q.dimensions.length;

  return (
    <PageShell>
      <PageHead
        title="度数"
        lead="度数是给这一锅内容打的分，不是给人打的。这一页把打分过程摊开：逐批的度数走势、本批五维的原始分，以及五个维度各自量的到底是什么——定义写死在这里，逐批复用，分数才有可比性。"
        fields={[
          { k: "本批度数", v: <span className="text-amber-text">{q.overall}°</span> },
          { k: "等级", v: `${q.grade} 级` },
          { k: "已评批次", v: `${asc.length} 批` },
          { k: "评判于", v: latest.credits.generated_at }
        ]}
        note={
          <>
            度数 = 五维<b>算术平均</b>，没有加权：<span className="num">{q.dimensions.map((d) => d.score).join(" + ")} = {sum}</span>，<span className="num">{sum} ÷ {q.dimensions.length} = {avg.toFixed(1)}</span> → 取整 <span className="num font-semibold text-amber-text">{q.overall}°</span>。分级 <span className="num">A≥80 · B≥60 · C≥40</span>。
          </>
        }
      />

      <Section id="run" label="逐批度数" sub="一批一个点 · 蓝带是等级区间">
        <ScrollHint>图较宽，可左右滑动</ScrollHint>
        <DegreeRun points={points} ghost={5} />
        <div className="mt-5">
          {single ? (
            <GapNote>
              <b>曲线从第 002 批开始。</b>现在只有一个点——一个点连不成线，所以这里没有走势可读，也不做任何「上升 / 下降」的判断。右边的虚线圈是接下来几批的位置。
            </GapNote>
          ) : (
            <p className="font-sans text-[13px] text-ink-3">共 {asc.length} 批入图。点上的数字是该批度数，蓝带是等级区间。</p>
          )}
        </div>
      </Section>

      <Section id="dims" label={`第 ${pad3(latest.issue)} 批五维`} sub="悬停任一行看这一维的证据">
        <ScoreGrid dims={q.dimensions} overall={q.overall} grade={q.grade} basis={q.basis} />
        <p className="mt-6 font-sans text-[13px] text-ink-3">
          这一批是这么算出来的：{q.basis}。整锅台账见 <Link href={`/ledger/${latest.date}/`} className="text-blue-text no-underline hover:underline">第 {pad3(latest.issue)} 批 · {latest.title}</Link>。
        </p>
      </Section>

      <Section id="mapping" label="稳定映射" sub="定义不随批次改 · 改了会在这里标注">
        <p className="prose-sheet mb-7 text-[16.5px] leading-[1.85] text-ink-2">
          分数要能跨期比较，前提是<b>尺子不换</b>。下面五条是这把尺子的刻度说明：每一维量什么、怎么算、高分低分各意味着什么，以及<span className="hand">它明确不量什么</span>——最后一条尤其重要，很多误读都来自把「没量的东西」当成量了。
        </p>
        <div className="divide-y divide-rule border-y border-rule">
          {q.dimensions.map((d) => {
            const m = MAP[d.name];
            return (
              <article key={d.name} className="grid gap-x-8 gap-y-3 py-6 lg:grid-cols-[minmax(0,180px)_minmax(0,1fr)]">
                <div>
                  <h3 className="font-serif text-[19px] font-bold text-ink">{d.name}</h3>
                  <div className="mt-1.5 flex items-baseline gap-2">
                    <span className="num font-sans text-[24px] font-semibold leading-none text-amber-text">{d.score}</span>
                    <span className="num font-sans text-[12.5px] font-semibold text-ink-3">{d.grade} 级 · 本批</span>
                  </div>
                </div>
                <div className="min-w-0">
                  {m ? (
                    <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
                      <div><dt className="label">量什么</dt><dd className="prose-sheet mt-1 text-[15.5px] leading-[1.8]">{m.measures}</dd></div>
                      <div><dt className="label">怎么算</dt><dd className="mt-1 font-sans text-[14px] leading-[1.7] text-ink-2">{m.how}</dd></div>
                      <div><dt className="label">高分意味着</dt><dd className="prose-sheet mt-1 text-[15.5px] leading-[1.8]">{m.high}</dd></div>
                      <div><dt className="label">低分意味着</dt><dd className="prose-sheet mt-1 text-[15.5px] leading-[1.8]">{m.low}</dd></div>
                      <div className="sm:col-span-2">
                        <dt className="label">不度量</dt>
                        <dd className="hand mt-1 text-[16px] leading-[1.8]">{m.not}</dd>
                      </div>
                    </dl>
                  ) : (
                    <GapNote>这一维还没有写稳定定义——数据里出现了新维度「{d.name}」，定义待补。</GapNote>
                  )}
                  <p className="mt-4 border-l-2 border-blue-wash-2 pl-4 font-sans text-[13px] leading-[1.75] text-ink-3">
                    <span className="label mr-2">本批实测</span>{d.detail}
                  </p>
                </div>
              </article>
            );
          })}
        </div>
        <p className="mt-7 font-sans text-[13px] leading-relaxed text-ink-3">
          这五条从第 001 批起就是这么定的，一直没改过。哪天真要改，我们会在这里写明白从哪一批开始改的、改了什么、以前的分数要不要重算——不会悄悄换一把尺子接着量。
        </p>
      </Section>
    </PageShell>
  );
}
