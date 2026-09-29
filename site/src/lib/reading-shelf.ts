/* 旋转书架的纯数据逻辑——客户端/服务端共用，禁止 import fs。
 * catalogue.json 是主题/关联元数据（人工逐条 id 归属），非 ReadingEntry 集合。 */

export interface ShelfEntry {
  id: string;
  kind: "book" | "repository";
  title: string;
  subtitle: string;
  summary: string;
  tags: string[];
  sourceTitle: string;
  sourceUrl: string;
}

export interface ShelfTopic {
  id: string;
  name: string;
  intro: string;
  /** 该主题下的建议读书次序（entry id，先于界面展示） */
  order: string[];
}

export interface ShelfCatalogue {
  topics: ShelfTopic[];
  /** entry id → 主题 id 列表；同一条可属多个主题 */
  assignments: Record<string, string[]>;
}

export function entryTopicIds(cat: ShelfCatalogue, entryId: string): string[] {
  return cat.assignments[entryId] ?? [];
}

export function entryTopics(cat: ShelfCatalogue, entryId: string): ShelfTopic[] {
  const ids = new Set(entryTopicIds(cat, entryId));
  return cat.topics.filter((t) => ids.has(t.id));
}

/** 主题下的条目按人工读书次序排列；未编排的条目追加在后 */
export function entriesInTopic(cat: ShelfCatalogue, entries: ShelfEntry[], topicId: string): ShelfEntry[] {
  const inTopic = entries.filter((e) => entryTopicIds(cat, e.id).includes(topicId));
  const order = new Map((cat.topics.find((t) => t.id === topicId)?.order ?? []).map((id, i) => [id, i]));
  return inTopic.sort((a, b) => (order.get(a.id) ?? 999) - (order.get(b.id) ?? 999));
}

/** 「顺着这条线继续读」：与所选条目共享主题的站内条目，附共同主题名；无则空 */
export function relatedEntries(
  cat: ShelfCatalogue,
  entries: ShelfEntry[],
  entry: ShelfEntry,
  max = 3,
): { entry: ShelfEntry; topic: string }[] {
  const mine = entryTopicIds(cat, entry.id);
  const out: { entry: ShelfEntry; topic: string }[] = [];
  for (const topicId of mine) {
    const topic = cat.topics.find((t) => t.id === topicId);
    if (!topic) continue;
    for (const e of entriesInTopic(cat, entries, topicId)) {
      if (e.id === entry.id || out.some((o) => o.entry.id === e.id)) continue;
      out.push({ entry: e, topic: topic.name });
      if (out.length >= max) return out;
    }
  }
  return out;
}

export function matchesQuery(e: ShelfEntry, q: string): boolean {
  const needle = q.trim().toLowerCase();
  if (!needle) return true;
  return [e.title, e.subtitle, e.summary, ...e.tags].some((s) => s.toLowerCase().includes(needle));
}

export function topicName(cat: ShelfCatalogue, id: string): string {
  return cat.topics.find((t) => t.id === id)?.name ?? id;
}

/** 封面版式由 id 决定（确定性，不随渲染抖动）；返回 0..3 的配色/线图变体 */
export function coverVariant(id: string): number {
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return h % 4;
}

/**
 * URL 回声识别：组件写出的 query 串入册；参数变化时命中且非 popstate 视为自己回声。
 * 真后退/前进会触发 popstate，即便落在同串上也是真导航，必须同步。
 */
export function makeUrlEcho() {
  const written = new Set<string>();
  return {
    wrote(qs: string) {
      written.add(qs);
      if (written.size > 40) written.clear(); // 极端积压时放空（回声已不重要）
    },
    isEcho(qs: string, popped: boolean): boolean {
      if (popped) {
        written.clear();
        return false;
      }
      return written.delete(qs);
    },
  };
}
