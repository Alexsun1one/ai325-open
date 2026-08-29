import type { Metadata } from "next";
import Link from "next/link";
import { getLatestLedger, pad3 } from "@/lib/content";
import { Section } from "@/components/sheet/Section";
import { PageHead, PageShell } from "@/components/pages/PageHead";
import { TodoCheck } from "@/components/pages/TodoCheck";
import { readEvents, artExists, STATUS_STYLE } from "@/components/pages/eventdata";
import { EventsLive } from "@/components/pages/EventsLive";

export const metadata: Metadata = {
  title: "活动专区",
  description: "群里正在跑的事：VI 设计大赛、小作文入群仪式、纪念徽章墙，以及本期的行动打卡。",
};

export default function EventsPage() {
  const events = readEvents();
  const l = getLatestLedger();
  const todoCount = l.growth.todo.reduce((s, p) => s + p.items.length, 0);
  const seeded = events.map((e) => ({ ...e, hasCover: artExists(e.cover) }));

  return (
    <PageShell>
      <PageHead
        title="活动专区"
        lead="群里正在跑的事都在这儿。每一件都能点进去看规矩、看进度、交东西、看别人交了什么。这一页只放真在跑的——没人报名就不写报名人数，没定截止就写没定。"
        fields={[
          { k: "在跑", v: `${events.length} 件` },
          { k: "本期", v: `第 ${pad3(l.issue)} 批` },
          { k: "谁能参加", v: "群友", num: false },
          { k: "怎么交", v: "登录后直接传", num: false },
        ]}
      />

      <Section id="list" label="正在跑" sub="点进去参加">
        <EventsLive seeded={seeded} statusStyle={STATUS_STYLE} />
      </Section>

      <Section id="todo" label="本期行动打卡" sub={`第 ${pad3(l.issue)} 批 · ${todoCount} 项`}>
        <p className="prose-sheet mb-7 text-[16.5px] leading-[1.85] text-ink-2">
          本期读完能带走的事都在这儿，可以直接勾。它和<Link href={`/ledger/${l.date}/#growth`} className="text-blue-text no-underline hover:underline">本期那份清单</Link>是同一份——勾在哪边都一样。
        </p>
        <TodoCheck todo={l.growth.todo} date={l.date} />
        <p className="mt-7 font-sans text-[12.5px] leading-relaxed text-ink-3">
          勾了什么<b>只留在你这台设备上</b>：不上传、不汇总，换个浏览器或清了缓存就没了。所以你不会在站上看到「本群完成率」这种数——那得收集每个人的打勾记录，我们不收。
        </p>
      </Section>
    </PageShell>
  );
}
