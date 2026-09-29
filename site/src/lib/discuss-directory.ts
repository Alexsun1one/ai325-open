import journeyData from "../../content/journey/people-need-ai.json";
import { getAllLedgers } from "./content";
import { readKnowledge } from "./knowledge-content";
import { readReadings } from "./reading-content";
import { pad3 } from "./shared";

/* 可评论文章目录：Agent 不用猜 anchor，照此表取 anchor+date 调 POST /api/comments。
   只收录公开已治理文章；date 一律取内容真实发表/校订/来源日期。 */

export interface DiscussionTarget {
  id: string;
  kind: "journey" | "reading" | "knowledge" | "ledger";
  title: string;
  url: string;
  anchor: string;
  date: string;
}

const DAY = /^\d{4}-\d{2}-\d{2}/;

function knowledgeDate(entry: { revisions: { date: string }[]; sources: { date: string }[] }): string | null {
  return entry.revisions.map((r) => r.date).filter((d) => DAY.test(d)).sort().pop()
    ?? [...entry.sources].sort((a, b) => b.date.localeCompare(a.date))[0]?.date
    ?? null;
}

export function readDiscussionTargets(): { items: DiscussionTarget[]; count: number; total: number } {
  const items: DiscussionTarget[] = [
    {
      id: "people-need-ai", kind: "journey", title: journeyData.title,
      url: "/journey/", anchor: "article:journey:people-need-ai", date: journeyData.date,
    },
  ];
  for (const e of readReadings()) {
    const date = DAY.exec(e.reviewedAt)?.[0];
    if (!date) continue;
    items.push({ id: e.id, kind: "reading", title: e.title, url: `/readings/${e.id}/`, anchor: `article:reading:${e.id}`, date });
  }
  for (const e of readKnowledge().entries) {
    const date = knowledgeDate(e);
    if (!date) continue;
    items.push({ id: e.id, kind: "knowledge", title: e.title, url: `/learn/entries/${e.id}/`, anchor: `article:knowledge:${e.id}`, date });
  }
  for (const l of getAllLedgers()) {
    items.push({ id: l.date, kind: "ledger", title: `第 ${pad3(l.issue)} 批 · ${l.title}`, url: `/ledger/${l.date}/`, anchor: `${l.date}#article`, date: l.date });
  }
  return { items, count: items.length, total: items.length };
}
