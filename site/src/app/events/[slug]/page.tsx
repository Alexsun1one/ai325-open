import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import fs from "node:fs";
import path from "node:path";
import { getLatestLedger } from "@/lib/content";
import { Section } from "@/components/sheet/Section";
import { PageHead, PageShell, GapNote } from "@/components/pages/PageHead";
import { Markdown } from "@/components/pages/Markdown";
import { EventBoard } from "@/components/pages/EventBoard";
import { BadgeWall, type Badge } from "@/components/pages/BadgeWall";
import { readEvents, artExists, STATUS_STYLE } from "@/components/pages/eventdata";

export function generateStaticParams() {
  return readEvents().map((e) => ({ slug: e.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const e = readEvents().find((x) => x.slug === slug);
  if (!e) return { title: "活动" };
  return { title: e.title, description: e.one_line ?? e.title };
}

function readBadges(): Badge[] {
  const p = path.join(process.cwd(), "public", "badges", "manifest.json");
  if (!fs.existsSync(p)) return [];
  return (JSON.parse(fs.readFileSync(p, "utf-8")).files ?? []) as Badge[];
}

export default async function EventPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const e = readEvents().find((x) => x.slug === slug);
  if (!e) notFound();
  const cover = artExists(e.cover) ? e.cover : null;
  const l = getLatestLedger();

  return (
    <PageShell>
      <nav className="pt-8 font-sans text-[13px]">
        <Link href="/events/" className="inline-flex min-h-11 items-center gap-1.5 text-blue-text no-underline hover:underline sm:min-h-0">
          <svg aria-hidden width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M15 6l-6 6 6 6" /></svg>
          活动专区
        </Link>
      </nav>

      <PageHead
        title={e.title}
        lead={e.one_line ?? ""}
        fields={[
          { k: "状态", v: <span className={`inline-flex rounded-[4px] border px-2 py-[2px] text-[11.5px] font-semibold ${STATUS_STYLE[e.status] ?? STATUS_STYLE["筹备中"]}`}>{e.status}</span>, num: false },
          { k: "开始", v: e.starts_at || "—" },
          { k: "截止", v: e.ends_at ? e.ends_at : <span className="text-ink-3">还没定</span> },
          { k: "给什么", v: e.reward || "—", num: false },
        ]}
      />

      {cover && (
        <figure className="mb-4 overflow-hidden rounded-[12px] border border-rule bg-paper-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={`/art/${cover}`} alt="" width={1600} height={900} className="block aspect-[21/9] w-full object-cover" />
        </figure>
      )}

      {e.rules_md && (
        <Section id="rules" label="怎么回事" sub="规矩与由来">
          <Markdown src={e.rules_md} />
          {e.links && e.links.length > 0 && (
            <div className="mt-7 flex flex-wrap gap-x-6 gap-y-2 border-t border-rule pt-5 font-sans text-[14px]">
              {e.links.map((x) => (
                <Link key={x.href} href={x.href} className="text-blue-text no-underline hover:underline">{x.label} →</Link>
              ))}
            </div>
          )}
        </Section>
      )}

      {e.timeline && e.timeline.length > 0 && (
        <Section id="timeline" label="到哪一步了" sub="按北京时间">
          <ol className="border-l border-rule pl-6">
            {e.timeline.map((t, i) => (
              <li key={i} className="relative pb-8 last:pb-0">
                <span aria-hidden className="absolute -left-[27px] top-[7px] h-[9px] w-[9px] rounded-full border-2 border-amber-deep bg-amber" />
                <div className="num font-sans text-[12.5px] font-semibold text-blue-text">{t.t}</div>
                <div className="mt-1 font-serif text-[18px] font-bold text-ink">{t.h}</div>
                <p className="prose-sheet mt-1.5 text-[16px] leading-[1.8] text-ink-2">{t.d}</p>
              </li>
            ))}
          </ol>
        </Section>
      )}

      {e.participants && e.participants.length > 0 && (
        <Section id="who" label="已经动手的人" sub="来自本期大事记">
          <ul className="grid gap-x-8 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
            {e.participants.map((p) => (
              <li key={p.name} className="border-l-2 border-blue-wash-2 pl-4">
                <div className="font-serif text-[18px] font-bold text-ink">{p.name}</div>
                {p.note && <div className="mt-0.5 font-sans text-[13.5px] text-ink-2">{p.note}</div>}
              </li>
            ))}
          </ul>
          <p className="mt-6 font-sans text-[12.5px] leading-relaxed text-ink-3">
            这几位是<Link href={`/ledger/${l.date}/#timeline`} className="text-blue-text no-underline hover:underline">本期大事记</Link>里写到的，不是一份报名表——所以这不是完整名单，交了东西的人会出现在下面的作品墙上。
          </p>
        </Section>
      )}

      {slug === "onboarding-essay" && (
        <Section id="progress" label="交到哪了" sub="已交 / 已答应">
          <div className="flex items-baseline justify-between gap-4">
            <div className="flex items-baseline gap-2">
              <span className="num text-[46px] font-semibold leading-none text-amber-text">{l.stats.essays}</span>
              <span className="num text-[17px] font-medium text-ink-3">/ {l.stats.essays + l.stats.essays_open} 篇</span>
            </div>
            <span className="num font-sans text-[13px] text-ink-3">还欠 {l.stats.essays_open} 篇</span>
          </div>
          <div className="mt-3 flex h-[10px] w-full overflow-hidden rounded-full border border-rule bg-paper">
            <div className="h-full bg-amber" style={{ width: `${(l.stats.essays / (l.stats.essays + l.stats.essays_open)) * 100}%` }} />
            <div className="h-full bg-cinnabar-wash" style={{ width: `${(l.stats.essays_open / (l.stats.essays + l.stats.essays_open)) * 100}%` }} />
          </div>
          <p className="mt-5 font-sans text-[12.5px] leading-relaxed text-ink-3">
            分母是<b>「已交 + 已经答应要交」</b>，不是群里的 {l.stats.members} 个人。没被点名、也没答应过的不算进来——拿全群当分母，会算出一个不存在的完成率。
          </p>
        </Section>
      )}

      {slug === "badge-wall" && (
        <Section id="badges" label="12 枚铭牌" sub="条件先公开">
          <BadgeWall badges={readBadges()} />
          <div className="mt-6">
            <GapNote>
              <b>现在还看不到谁拿了哪一枚。</b>要判定这个，得先把大家的发言统计（累计条数、凌晨时段、被谁引用过……）算出来，那部分还没做好。所以 12 枚全是灰的——不是你没拿到，是还没开始算。算好之后这面墙会按人显示。
            </GapNote>
          </div>
        </Section>
      )}

      <Section id="board" label="交东西 / 看别人交的" sub="登录后可以交">
        <EventBoard slug={slug} fallback={e.participants ?? []} />
      </Section>
    </PageShell>
  );
}
