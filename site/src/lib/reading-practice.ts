/* 阅读→练习预填的纯数据逻辑：静态索引校验 + 白名单查条目。
 * 索引只带预填字段，不带正文与私密路径；客户端不把 query 文字当可信来源。 */

export interface PracticeIndexEntry {
  title: string;
  outcome: string;
  next_step: string;
  source_url: string;
  source_title: string;
}

export interface PracticeIndex {
  version: number;
  entries: Record<string, PracticeIndexEntry>;
}

const ENTRY_ID = /^[a-z0-9-]+$/;

function isEntry(v: unknown): v is PracticeIndexEntry {
  const e = v as PracticeIndexEntry;
  return !!e && typeof e === "object"
    && typeof e.title === "string" && typeof e.outcome === "string"
    && typeof e.next_step === "string" && typeof e.source_url === "string"
    && typeof e.source_title === "string";
}

/** 解析索引响应；形状不对返回 null（调用方走诚实重试，不猜数据） */
export function parsePracticeIndex(raw: unknown): PracticeIndex | null {
  const d = raw as PracticeIndex;
  if (!d || typeof d !== "object" || d.version !== 1 || !d.entries || typeof d.entries !== "object") return null;
  const entries: Record<string, PracticeIndexEntry> = {};
  for (const [id, e] of Object.entries(d.entries)) {
    if (ENTRY_ID.test(id) && isEntry(e)) entries[id] = e;
  }
  return { version: 1, entries };
}

/** 白名单查条目：id 先过形态校验再按自有键查，query 注入拿不到东西 */
export function practiceIndexFor(idx: PracticeIndex, id: string): PracticeIndexEntry | null {
  if (!ENTRY_ID.test(id) || !Object.hasOwn(idx.entries, id)) return null;
  return idx.entries[id];
}
