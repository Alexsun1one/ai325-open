import type { Metadata } from "next";
import Link from "next/link";
import { getAllLedgers } from "@/lib/content";
import { Section } from "@/components/sheet/Section";
import { PageHead, PageShell } from "@/components/pages/PageHead";
import { ArsenalShelf } from "@/components/pages/ArsenalShelf";
import { readArsenal, artFile, SHELVES } from "@/components/pages/arsenaldata";
import { ArsenalSubmit } from "@/components/pages/ArsenalSubmit";

export const metadata: Metadata = {
  title: "军火库",
  description: "群里说的「军火库」：提示词、方法、值得读的东西——一一每天采集蒸馏，Sun 亲自添砖。",
};

function daysAgo(d: string) {
  const t = Date.parse(`${d}T00:00:00+08:00`);
  return Number.isNaN(t) ? 999 : Math.floor((Date.now() - t) / 86400000);
}

export default function ArsenalPage() {
  const items = readArsenal();
  const fresh = items.filter((x) => daysAgo(x.collected_at) <= 7).sort((a, b) => (a.collected_at < b.collected_at ? 1 : -1));
  const featured = items.filter((x) => x.status === "featured").slice(0, 4);
  const cover = artFile("arsenal-hero.webp") ?? artFile("arsenal-hero.png");

  // 线索 id → 中文名，用来把 chip 显示成人看得懂的字
  const threads: Record<string, string> = {};
  for (const l of getAllLedgers()) for (const t of l.threads) threads[t.id] = t.title;

  const kinds = [...new Set(items.map((i) => i.kind))];

  return (
    <PageShell>
      <PageHead
        title="军火库"
        lead="群里说的「军火库」：提示词、方法、值得读的东西——一一每天采集蒸馏，Sun 亲自添砖。不是收藏夹，是一架能直接取下来用的东西：每一件都写清楚它解决什么、谁该看、拿走哪几条。"
        fields={[
          { k: "在架", v: `${items.length} 件` },
          { k: "分几架", v: `${kinds.length} 架` },
          { k: "最近七天", v: `${fresh.length} 件新到` },
          { k: "谁在添", v: "一一 · Sun · Claude", num: false },
        ]}
      />

      {cover && (
        <figure className="mb-6 overflow-hidden rounded-[12px] border border-rule bg-paper-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={cover} alt="" className="block aspect-[21/9] w-full object-cover" />
        </figure>
      )}

      {fresh.length > 0 && (
        <div className="mb-2 border-y border-rule py-3">
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <span className="label shrink-0">新到</span>
            <span className="num font-sans text-[12.5px] text-ink-3">最近七天 {fresh.length} 件</span>
          </div>
          <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1.5">
            {fresh.slice(0, 8).map((x) => (
              <li key={x.id}>
                <Link href={`#kb-${x.id}`} className="inline-flex min-h-11 items-center font-sans text-[13.5px] text-ink-2 no-underline hover:text-blue-text sm:min-h-0">
                  <span className="num mr-1.5 text-ink-3">{x.collected_at.slice(5)}</span>{x.title}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      {featured.length > 0 && (
        <Section id="featured" label="先看这四件" sub="架上最该先取的">
          <div className="grid gap-x-10 gap-y-8 sm:grid-cols-2">
            {featured.map((x, i) => (
              <Link key={x.id} href={`#kb-${x.id}`} className="group block no-underline">
                <div className="num font-sans text-[12.5px] font-semibold text-blue-text">{String(i + 1).padStart(2, "0")} · {x.kind}</div>
                <h3 className="mt-2 font-serif text-[23px] font-black leading-tight text-ink transition-colors group-hover:text-blue-text sm:text-[25px]">{x.title}</h3>
                <p className="prose-sheet mt-2.5 text-[16px] leading-[1.8] text-ink-2">{x.one_line}</p>
                <p className="mt-2 font-sans text-[12.5px] text-ink-3">{x.for_whom}</p>
              </Link>
            ))}
          </div>
        </Section>
      )}

      <Section id="shelves" label="全部在架" sub="按类型分架 · 点开取用">
        <ArsenalShelf items={items} shelves={SHELVES} threads={threads} />
        <p className="mt-10 font-sans text-[12.5px] leading-relaxed text-ink-3">
          带琥珀圆点的「Sun 的沉淀」是群主自己写的，没有外链，全文就在展开里。其余的都注明了出处。要点是我们用自己的话重写的，不是原文摘抄——想看原样就看「全文」那一段。
        </p>
      </Section>

      <Section id="submit" label="上架一件" sub="你手上好用的，别只自己用">
        <p className="prose-sheet mb-7 text-[16.5px] leading-[1.85] text-ink-2">
          你有一段真好用的提示词、一个自己摸出来的方法、一件能直接给 agent 用的技能——交上来。
          <span className="hand">这一架不是收藏夹，是大家轮流往上放东西的地方。</span>放上去的东西群友能取，agent 也能取。
        </p>
        <ArsenalSubmit />
      </Section>
    </PageShell>
  );
}
