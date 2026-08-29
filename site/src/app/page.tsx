import { getLatestLedger, getNeighbors, getSpotIllustrations, getThemeIllustrations, listLedgerDates } from "@/lib/content";
import { LedgerSheet } from "@/components/sheet/LedgerSheet";
import { FontPreload } from "@/components/site/FontPreload";
import type { Ledger } from "@/lib/shared";

/** 整页字体预载计划：宋体 400（正文）/700（小标题/粗体）/900（刊名）+ 文楷（深潜/批注）。 */
function fontPlan(l: Ledger) {
  const strip = (h: string) => h.replace(/<[^>]+>/g, "");
  const body = [l.lead, ...l.events.map((e) => e.h + e.d), ...l.themes.flatMap((t) => [t.body, ...t.voices.map((v) => v.a + v.v)]), ...l.insights.map((i) => i.body), ...l.quotes.map((q) => q.t + q.a), ...l.tone_notes.map((n) => n.body), ...l.growth.takeaways, ...l.growth.todo.flatMap((p) => p.items), ...l.glossary.map((g) => g.term + g.def), ...l.docket.map((d) => d.h + d.d), ...l.clashes.map((c) => c.sides), ...l.members_focus.map((m) => m.name + m.role + m.quote)].map(strip).join("");
  const heads = [l.title, ...l.themes.map((t) => t.h), ...l.insights.map((i) => i.h), ...l.events.map((e) => e.h), ...l.clashes.map((c) => c.h), "先锋队台账 六件随身装备 行动清单 资源弹药库 新面孔 本期感谢"].map(strip).join("");
  const hand = [...l.themes.map((t) => t.deep), ...l.insights.map((i) => i.body), ...l.clashes.map((c) => c.verdict)].map(strip).join("");
  return [
    { text: `${l.title}先锋队台账`, weight: 900, cap: 6 },
    { text: body, weight: 400, cap: 26 },
    { text: heads, weight: 700, cap: 10 },
    { text: hand, family: "LXGW WenKai", weight: 400, cap: 12 },
  ];
}

export default function Home() {
  const l = getLatestLedger();
  const nb = getNeighbors(l.date);
  return (<><FontPreload plan={fontPlan(l)} /><LedgerSheet l={l} totalIssues={listLedgerDates().length} prev={nb.prev} next={nb.next} prevOpen={nb.prevOpen} illus={getThemeIllustrations(l.themes.length)} spots={getSpotIllustrations()} /></>);
}
