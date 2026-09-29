"use client";
/* 「阅读与足迹」工作区（/me/?view=reading，READING-GROWTH R1）。
 * 两个分区按需切换取数：阅读记录（打开/收藏/读完真值 + 筛选 + 行内操作）/ 我的参与（现存互动归并）。
 * GET/变更均 alive+seq+Abort+busyRef 守卫；0/5xx 重取真值不盲乐观；
 * mutation/核对期间禁筛选禁加载更多；错误只提示不盖有效列表；删除在对应行内确认。 */
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/auth";
import { pioneerStickerText } from "@/lib/pioneer-stickers";
import {
  readingGrowthApi, type ActivityItem, type ActivityPage,
  type ProgressPage, type ReadingRecord,
} from "@/lib/reading-growth";
import styles from "./ReadingHistory.module.css";

const KIND_LABEL: Record<string, string> = { book_note: "研读笔记", reading: "导读" };
const TYPE_LABEL: Record<string, string> = {
  comment: "评论", question: "提问", reply: "回复",
  practice: "实践更新", practice_reply: "实践回复", paragraph_saved: "段落收藏",
};
const FILTERS = [
  { id: "all", label: "全部" }, { id: "saved", label: "已收藏" }, { id: "finished", label: "已读完" },
] as const;
const ZONES = [
  { id: "records", label: "阅读记录" }, { id: "activity", label: "我的参与" },
] as const;

const fmt = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "";

/** 摘录剥常用 Markdown 为纯文本（与 AgentAnswersPreview 同名实现同形，局部不复用不引依赖）；
 *  先过共享 pioneerStickerText——已知 :xf-…: 变 [名称]，未知 token 原样，不裸 token 进列表 */
function plainExcerpt(src: string): string {
  return pioneerStickerText(src || "")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/^\s*#{1,6}\s+/gm, "")
    .replace(/^\s*>\s?/gm, "")
    .replace(/^\s*(?:[-*·]|\d+\.)\s+/gm, "")
    .replace(/\*\*([^*\n]+(?:\*(?!\*)[^*\n]*)*)\*\*/g, "$1")
    .replace(/`([^`\n]*)`/g, "$1")
    .replace(/\[([^\]\n]+)\]\([^)\n]+\)/g, "$1")
    .replace(/[ \t]+/g, " ")
    .trim();
}

const recKey = (r: ReadingRecord) => `${r.kind}:${r.resource_id}`;

function Row({ r, busy, delKey, onPatch, onAskDel, onCancelDel, onDel }: {
  r: ReadingRecord; busy: string; delKey: string;
  onPatch: (r: ReadingRecord, f: "saved" | "finished", v: boolean) => void;
  onAskDel: (r: ReadingRecord) => void;
  onCancelDel: () => void;
  onDel: (r: ReadingRecord) => void;
}) {
  const confirming = delKey === recKey(r);
  return (
    <li className={styles.row}>
      <span className={styles.kind}>{KIND_LABEL[r.kind] ?? r.kind}</span>
      <span className={styles.main}>
        {r.url ? <a className={styles.title} href={r.url}>{r.title}</a>
               : <span className={styles.title}>{r.title}</span>}
        <span className={styles.meta}>
          {r.category && <span>{r.category}</span>}
          {!r.available && <span className={styles.off}>已下架</span>}
          {r.saved && <span className={styles.tag}>已收藏</span>}
          {r.finished && <span className={`${styles.tag} ${styles.tagDone}`}>读完这篇</span>}
          {r.updated_at && <span>最近操作 {fmt(r.updated_at)}</span>}
        </span>
      </span>
      {confirming ? (
        <span className={styles.confirm} role="alertdialog" aria-label={`删除《${r.title}》`}>
          <span className={styles.confirmText}>删《{r.title}》？收藏和已读标记一并移除，实践评论不动。</span>
          <button type="button" disabled={!!busy} onClick={() => onDel(r)}>
            {busy ? "…" : "确认删除"}
          </button>
          <button type="button" onClick={onCancelDel}>先留着</button>
        </span>
      ) : (
        <span className={styles.ops}>
          <button type="button" disabled={!!busy} onClick={() => onPatch(r, "saved", !r.saved)}>
            {busy === `${recKey(r)}:saved` ? "…" : r.saved ? "取消收藏" : "收藏"}
          </button>
          <button type="button" disabled={!!busy} onClick={() => onPatch(r, "finished", !r.finished)}>
            {busy === `${recKey(r)}:finished` ? "…" : r.finished ? "取消读完" : "读完这篇"}
          </button>
          <button type="button" disabled={!!busy} onClick={() => onAskDel(r)}>删除</button>
        </span>
      )}
    </li>
  );
}

function ActivityRow({ a }: { a: ActivityItem }) {
  return (
    <li className={styles.row}>
      <span className={styles.kind}>{TYPE_LABEL[a.type] ?? a.type}</span>
      <span className={styles.main}>
        {a.url ? <a className={styles.title} href={a.url}>{a.title}</a>
               : <span className={styles.title}>{a.title}</span>}
        {a.excerpt && <span className={styles.excerpt}>{plainExcerpt(a.excerpt)}</span>}
        <span className={styles.meta}><span>{fmt(a.at)}</span></span>
      </span>
    </li>
  );
}

export default function ReadingHistory() {
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []); // StrictMode 重挂先复位

  const [zone, setZone] = useState<"records" | "activity">("records");

  // —— 阅读记录 ——
  const [filter, setFilter] = useState<"all" | "saved" | "finished">("all");
  const [page, setPage] = useState<ProgressPage | null>(null);
  const [err, setErr] = useState("");            // 只提示，不盖有效列表
  const [loading, setLoading] = useState(false); // 加载/加载更多在途
  const [busy, setBusy] = useState("");          // mutation UI 态
  const busyRef = useRef(false);                 // mutation 同步闸
  const [unconfirmed, setUnconfirmed] = useState("");
  const [rechecking, setRechecking] = useState(false);
  const [delId, setDelId] = useState("");
  const pSeq = useRef(0); const pCtl = useRef<AbortController | null>(null);
  const mutLocked = !!busy || rechecking; // mutation/核对期间禁筛选+加载更多（渲染态用 busy，busyRef 只管事件闸）

  const loadPage = useCallback(async (offset = 0, append = false) => {
    const s = ++pSeq.current;
    pCtl.current?.abort();
    const c = new AbortController(); pCtl.current = c;
    setLoading(true);
    try {
      const d = await readingGrowthApi.list(filter, offset, 20, c.signal);
      if (s !== pSeq.current || !alive.current) return;
      setPage((prev) => append && prev
        ? { ...d, items: [...prev.items, ...d.items.filter((n) => !prev.items.some((o) => recKey(o) === recKey(n)))] }
        : d);
      setErr(""); setRechecking(false); setUnconfirmed("");
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      if (s === pSeq.current && alive.current) { setErr(e instanceof ApiError ? e.message : "阅读记录暂时没取到"); setRechecking(false); }
    } finally {
      if (s === pSeq.current && alive.current) setLoading(false);
    }
  }, [filter]);
  useEffect(() => {
    const t = window.setTimeout(() => { setPage(null); setErr(""); setDelId(""); void loadPage(); }, 0);
    return () => { window.clearTimeout(t); pSeq.current += 1; pCtl.current?.abort(); };
  }, [loadPage]);

  const reload = useCallback(() => loadPage(0), [loadPage]); // 变更后重取首页 20（limit≤50）；返回 Promise 供 await

  const beginMut = () => {
    if (busyRef.current) return false;
    busyRef.current = true;
    pSeq.current += 1;              // 作废在途 GET——旧响应不得盖 mutation 后重取的真值
    pCtl.current?.abort();
    setLoading(false);              // 被作废请求的 finally 不再清 loading——由发起方就地清
    setUnconfirmed("");
    return true;
  };

  const patch = async (r: ReadingRecord, field: "saved" | "finished", v: boolean) => {
    if (!beginMut()) return;
    setBusy(`${recKey(r)}:${field}`);
    try {
      await readingGrowthApi.patch(r.kind, r.resource_id, { [field]: v });
      if (alive.current) await reload(); // 锁持续到重取完成，不只停在 setRechecking
    } catch (e) {
      if (alive.current) {
        if (e instanceof ApiError && e.status >= 400 && e.status < 500) setErr(e.message);
        else { setUnconfirmed(r.title); setRechecking(true); await reload(); } // 0/5xx：没确认→锁内重取真值
      }
    } finally {
      busyRef.current = false;
      if (alive.current) setBusy("");
    }
  };

  const remove = async (r: ReadingRecord) => {
    if (!beginMut()) return;
    setBusy(`${recKey(r)}:del`);
    try {
      await readingGrowthApi.remove(r.kind, r.resource_id);
      if (alive.current) { setDelId(""); await reload(); }
    } catch (e) {
      if (alive.current) {
        if (e instanceof ApiError && e.status >= 400 && e.status < 500) setErr(e.message);
        else { setUnconfirmed(r.title); setRechecking(true); await reload(); }
      }
    } finally {
      busyRef.current = false;
      if (alive.current) setBusy("");
    }
  };

  // —— 我的参与（按需首取）——
  const [act, setAct] = useState<ActivityPage | null>(null);
  const [actErr, setActErr] = useState("");
  const [actLoading, setActLoading] = useState(false);
  const [actUsed, setActUsed] = useState(false);
  const aSeq = useRef(0); const aCtl = useRef<AbortController | null>(null);

  const loadAct = useCallback(async (offset = 0, append = false) => {
    const s = ++aSeq.current;
    aCtl.current?.abort();
    const c = new AbortController(); aCtl.current = c;
    setActLoading(true);
    try {
      const d = await readingGrowthApi.activity(offset, 20, c.signal);
      if (s !== aSeq.current || !alive.current) return;
      setAct((prev) => append && prev
        ? { ...d, items: [...prev.items, ...d.items.filter((n) => !prev.items.some((o) => o.id === n.id))] }
        : d);
      setActErr("");
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      if (s === aSeq.current && alive.current) setActErr(e instanceof ApiError ? e.message : "参与记录暂时没取到");
    } finally {
      if (s === aSeq.current && alive.current) setActLoading(false);
    }
  }, []);

  const switchZone = (z: "records" | "activity") => {
    setZone(z);
    if (z === "activity" && !actUsed) { setActUsed(true); void loadAct(); }
  };

  const sum = page?.summary;
  const aSum = act?.summary;
  return (
    <div>
      <h3 className={styles.h}>阅读与足迹</h3>
      <p className={styles.counts}>
        {sum ? `打开 ${sum.opened} · 收藏 ${sum.saved} · 读完 ${sum.finished}` : "正在读记录……"}
        {aSum ? ` ｜ 参与 ${aSum.contributions} · 完成实践 ${aSum.practices_completed} · 段落收藏 ${aSum.paragraphs_saved}` : ""}
        <span className={styles.priv}>只你可见 · 「读完」指本篇导读/笔记，不追补上线前的历史</span>
      </p>

      <div className={styles.tabs} aria-label="足迹分区">
        {ZONES.map((t) => (
          <button key={t.id} type="button" aria-pressed={zone === t.id} disabled={mutLocked}
            className={`${styles.tab} ${zone === t.id ? styles.tabOn : ""}`}
            onClick={() => switchZone(t.id)}>{t.label}</button>
        ))}
      </div>

      {zone === "records" ? (
        <>
          <div className={styles.subtabs}>
            {FILTERS.map((t) => (
              <button key={t.id} type="button" aria-pressed={filter === t.id} disabled={mutLocked}
                className={`${styles.stab} ${filter === t.id ? styles.stabOn : ""}`}
                onClick={() => setFilter(t.id)}>{t.label}</button>
            ))}
          </div>

          {err && <p className={styles.note}>{err} <button type="button" disabled={loading || mutLocked} onClick={() => void reload()}>重试</button></p>}
          {unconfirmed && <p className={styles.note}>《{unconfirmed}》上一步结果没确认{rechecking ? "——正在重新核对……" : "，重试也没取到，稍后再点。"}</p>}
          {page === null ? (err ? null : <p className={styles.note}>正在读记录……</p>)
            : !page.items.length ? (
              <p className={styles.note}>
                {filter === "all" ? "还没有阅读记录——打开任何一篇导读或研读笔记，停留片刻自动记下（只记功能上线后的足迹）。" : "这个状态下还没有记录。"}
              </p>
            ) : (
              <>
                <ul className={styles.list}>
                  {page.items.map((r) => (
                    <Row key={recKey(r)} r={r} busy={busy} delKey={delId}
                      onPatch={patch} onAskDel={(x) => setDelId(recKey(x))}
                      onCancelDel={() => setDelId("")} onDel={(x) => void remove(x)} />
                  ))}
                </ul>
                {page.has_more && (
                  <button type="button" className={styles.more} disabled={loading || mutLocked}
                    onClick={() => void loadPage(page.items.length, true)}>
                    {loading ? "加载中…" : `加载更多（还有 ${page.total - page.items.length} 条）`}
                  </button>
                )}
                <p className={styles.note}>共 {page.total} 条{page.items.length < page.total ? `，已显示前 ${page.items.length} 条` : ""}。</p>
              </>
            )}
        </>
      ) : (
        <>
          {actErr && <p className={styles.note}>{actErr} <button type="button" disabled={actLoading} onClick={() => void loadAct()}>重试</button></p>}
          {act === null ? (actErr ? null : <p className={styles.note}>正在读参与……</p>)
            : !act.items.length ? <p className={styles.note}>还没有参与记录——在导读、笔记或共练里发言、收藏段落就会出现在这里。</p>
            : (
              <>
                <ul className={styles.list}>
                  {act.items.map((a) => <ActivityRow key={a.id} a={a} />)}
                </ul>
                {act.has_more && (
                  <button type="button" className={styles.more} disabled={actLoading}
                    onClick={() => void loadAct(act.items.length, true)}>
                    {actLoading ? "加载中…" : `加载更多（还有 ${act.total - act.items.length} 条）`}
                  </button>
                )}
              </>
            )}
          <p className={styles.note}>这里归并的是你现有的互动记录与实践当前状态，不是完整事件日志。
            段落摘抄在「收藏与笔记」分区；这里的「收藏」是整篇的。</p>
        </>
      )}
    </div>
  );
}
