"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { makeUrlEcho } from "@/lib/reading-shelf";
import { BookCover } from "@/components/ui/BookCover";
import styles from "./BookLibrary.module.css";

interface SlimItem { id: string; title: string; author: string; category: string; tags?: string[]; chars: number; year: string | number }
interface SlimIndex { total: number; categories: Record<string, number>; items: SlimItem[] }

const PAGE = 50;
const norm = (v: string) => v.normalize("NFKC").toLowerCase().replace(/\s+/g, " ").trim();
const asPage = (v: string | null) => { const n = Number(v); return Number.isSafeInteger(n) && n > 0 ? n : 1; };

function validIndex(d: unknown): d is SlimIndex {
  const v = d as SlimIndex;
  return !!v && typeof v.total === "number" && !!v.categories && Array.isArray(v.items)
    && v.items.every((i) => i && typeof i.id === "string" && typeof i.title === "string" && typeof i.category === "string");
}

/** 客户端检索/分页：按需拉一次精简索引，无 JS 时由服务端静态目录兜底。 */
export function BookLibrary({ fallback }: { fallback: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [data, setData] = useState<SlimIndex | null>(null);
  const [err, setErr] = useState(false);
  const [tick, setTick] = useState(0);
  const composing = useRef(false);
  const [draft, setDraft] = useState(() => params.get("q") ?? "");   // 输入框受控值；过滤/URL 只由已提交的 q 驱动
  const qTimer = useRef<number | undefined>(undefined);   // 输入 debounce；导航/分类/翻页/后退一律先清掉
  const listRef = useRef<HTMLDivElement>(null);
  const paged = useRef(false);

  const urlRef = useRef(params.toString());
  const echo = useRef(makeUrlEcho());
  const popped = useRef(false);
  const qLive = useRef(params.get("q") ?? "");
  const [q, setQ] = useState(() => params.get("q") ?? "");
  const [cat, setCat] = useState(() => params.get("cat") ?? "");
  const [page, setPage] = useState(() => asPage(params.get("page")));
  const [view, setView] = useState<"covers" | "list">("covers");

  const load = useCallback((signal: AbortSignal) => {
    fetch("/book-notes/index.json", { signal })
      .then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then((d: unknown) => {
        if (signal.aborted) return;   // JSON 解析完成后旧请求也可能已被作废（重试/卸载）
        if (!validIndex(d)) throw new Error("bad index");
        setData(d); setErr(false);
      })
      .catch((e) => { if (!signal.aborted && e?.name !== "AbortError") setErr(true); });
  }, []);

  // tick 变化（重试）与卸载都会 abort 旧请求，旧响应不会回写
  useEffect(() => {
    const ac = new AbortController();
    load(ac.signal);
    return () => ac.abort();
  }, [load, tick]);

  // popstate 只由真实前进/后退触发 → 标记外部导航
  useEffect(() => {
    const onPop = () => { popped.current = true; window.clearTimeout(qTimer.current); };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // 参数变化：自己回声跳过；外部导航 → 全量同步回本地
  useEffect(() => {
    const qs = params.toString();
    if (echo.current.isEcho(qs, popped.current)) return;
    popped.current = false;
    window.clearTimeout(qTimer.current);
    urlRef.current = qs;
    const t = window.setTimeout(() => {
      const qp = params.get("q") ?? "";
      qLive.current = qp;
      setQ(qp); setDraft(qp);
      setCat(params.get("cat") ?? "");
      setPage(asPage(params.get("page")));
    }, 0);
    return () => window.clearTimeout(t);
  }, [params]);

  const write = useCallback((next: Record<string, string | null>, mode: "push" | "replace") => {
    const sp = new URLSearchParams(urlRef.current);
    for (const [k, v] of Object.entries(next)) {
      if (v === null || v === "" || v === "all") sp.delete(k); else sp.set(k, v);
    }
    if (!("q" in next)) {
      if (qLive.current) sp.set("q", qLive.current); else sp.delete("q");
    }
    const qs = sp.toString();
    urlRef.current = qs;
    echo.current.wrote(qs);
    const url = qs ? `${pathname}?${qs}` : pathname;
    (mode === "push" ? router.push : router.replace)(url, { scroll: false });
  }, [pathname, router]);

  // 输入：本地即时过滤；URL 停顿后 replace；IME 合成中不落 URL
  const onQuery = (v: string) => {
    qLive.current = v;
    setQ(v); setPage(1);
    window.clearTimeout(qTimer.current);
    qTimer.current = window.setTimeout(() => write({ q: v || null, page: null }, "replace"), 350);
  };

  const pickCat = (c: string) => {
    window.clearTimeout(qTimer.current);   // 未落 URL 的输入随本次 push 一并写入（write 读 qLive），不再单独触发
    setCat(c); setPage(1);
    write({ cat: c || null, page: null }, "push");
  };
  const gotoPage = (p: number) => {
    paged.current = true;
    window.clearTimeout(qTimer.current);
    setPage(p);
    write({ page: p > 1 ? String(p) : null }, "push");
  };
  const clearAll = useCallback(() => {
    window.clearTimeout(qTimer.current);
    qLive.current = "";
    setQ(""); setDraft(""); setCat(""); setPage(1);
    write({ q: null, cat: null, page: null }, "push");
  }, [write]);

  useEffect(() => () => window.clearTimeout(qTimer.current), []);

  // 检索字段只在索引到达时标准化一次；查询按空白拆词 AND 匹配
  const prepared = useMemo(
    () => (data ? data.items.map((i) => ({ i, hay: norm(`${i.title} ${i.author ?? ""} ${(i.tags ?? []).join(" ")}`) })) : []),
    [data],
  );
  const needles = useMemo(() => norm(q).split(" ").filter(Boolean), [q]);
  const cats = data ? Object.keys(data.categories) : [];
  const unknownCat = !!data && !!cat && !cats.includes(cat);   // 未知分类：忽略并给出可恢复提示
  const filtered = useMemo(
    () => prepared.filter(({ i, hay }) => (!cat || unknownCat || i.category === cat) && needles.every((n) => hay.includes(n))).map((x) => x.i),
    [prepared, cat, unknownCat, needles],
  );
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE));
  const cur = Math.min(page, pages);

  // 页码越界 → 收敛到真实页（replace，不新增历史）
  useEffect(() => {
    if (!data || page === cur) return;
    // 只同步 URL（外部系统）；界面已由派生的 cur 显示真实页，无需再 setState
    const want = cur > 1 ? String(cur) : null;
    if (new URLSearchParams(urlRef.current).get("page") !== want) write({ page: want }, "replace");
  }, [data, page, cur, write]);

  // 翻页后把视线与焦点送到新列表顶部，键盘用户不必回头找
  useEffect(() => {
    if (!paged.current) return;
    paged.current = false;
    const el = listRef.current;
    if (!el) return;
    el.scrollIntoView({ block: "start" });
    el.focus({ preventScroll: true });
  }, [cur]);

  if (err) {
    return (
      <div className={styles.errBox} role="alert">
        <p>书库检索暂时没加载出来，下方目录仍可使用。</p>
        <button type="button" className={styles.retry}
          onClick={() => { setErr(false); setData(null); setTick((t) => t + 1); }}>
          重试
        </button>
        <div className={styles.fallWrap}>{fallback}</div>
      </div>
    );
  }
  if (!data) return <><p className={styles.status} role="status">正在载入完整书库检索……下方目录可直接点开。</p>{fallback}</>;

  const slice = filtered.slice((cur - 1) * PAGE, cur * PAGE);

  return (
    <div className={styles.lib}>
      <p className={styles.tier}>全量研读目录 · 全库 {data.total} 本。精选书架见 <Link href="/readings/">精读书架</Link>。</p>
      <div className={styles.controls}>
        <input
          type="search" value={draft} placeholder="搜书名 / 作者 / 主题…" enterKeyHint="search" autoComplete="off"
          onChange={(e) => { setDraft(e.target.value); if (!composing.current) onQuery(e.target.value); }}
          onCompositionStart={() => { composing.current = true; window.clearTimeout(qTimer.current); }}
          onCompositionEnd={(e) => { composing.current = false; onQuery(e.currentTarget.value); }}
          aria-label="搜索书库" className={styles.search}
        />
        <div className={styles.cats} role="group" aria-label="分类">
          <button type="button" aria-pressed={!cat || unknownCat} className={!cat || unknownCat ? styles.catOn : ""} onClick={() => pickCat("")}>全部 {data.total}</button>
          {cats.map((c) => (
            <button type="button" key={c} aria-pressed={cat === c} className={cat === c ? styles.catOn : ""}
              onClick={() => pickCat(c)}>{c} {data.categories[c]}</button>
          ))}
        </div>
      </div>
      <div className={styles.viewBar} role="group" aria-label="书库视图">
        <span>排列方式</span>
        <button type="button" aria-pressed={view === "covers"} className={view === "covers" ? styles.viewOn : ""} onClick={() => setView("covers")}>封面书架</button>
        <button type="button" aria-pressed={view === "list"} className={view === "list" ? styles.viewOn : ""} onClick={() => setView("list")}>目录清单</button>
      </div>
      {unknownCat && (
        <p className={styles.notice} role="status">没有「{cat}」这个分类，已显示全部。<button type="button" className={styles.clearBtn} onClick={() => pickCat("")}>清除分类</button></p>
      )}
      <p className={styles.range} aria-live="polite">
        {filtered.length
          ? `共 ${filtered.length} 本${(needles.length > 0 || (cat && !unknownCat)) ? `（全库 ${data.total} 本）` : ""} · 第 ${cur}/${pages} 页（${(cur - 1) * PAGE + 1}–${Math.min(cur * PAGE, filtered.length)}）`
          : "没有匹配的研读笔记"}
        {(q.trim() || (cat && !unknownCat)) && filtered.length === 0 && (
          <button type="button" className={styles.clearBtn} onClick={clearAll}>清空筛选</button>
        )}
      </p>
      <div ref={listRef} tabIndex={-1} className={styles.listWrap}>
      {view === "covers" ? (
        <ol className={styles.coverList} start={(cur - 1) * PAGE + 1}>
          {slice.map((i) => (
            <li key={i.id} className={styles.coverItem}>
              <Link href={`/readings/books/${i.id}/`} prefetch={false} className={styles.coverLink} aria-label={`打开《${i.title}》`}>
                <BookCover id={i.id} title={i.title} author={i.author} category={i.category} kind="book" size="library" />
                <span className={styles.coverTitle}>{i.title}</span>
                <span className={styles.coverMeta}>{[i.author, i.year !== "" ? String(i.year) : "", i.category, `${Math.round(i.chars / 1000)}k字`].filter(Boolean).join(" · ")}</span>
              </Link>
            </li>
          ))}
        </ol>
      ) : (
        <ol className={styles.list} start={(cur - 1) * PAGE + 1}>
          {slice.map((i) => (
            <li key={i.id}>
              <Link href={`/readings/books/${i.id}/`} prefetch={false} className={styles.item}>
                <span className={styles.itemTitle}>{i.title}</span>
                <span className={styles.itemMeta}>{[i.author, i.year !== "" ? String(i.year) : "", i.category, `${Math.round(i.chars / 1000)}k字`].filter(Boolean).join(" · ")}</span>
              </Link>
            </li>
          ))}
        </ol>
      )}
      </div>
      {pages > 1 && (
        <nav className={styles.pager} aria-label="分页">
          <button type="button" disabled={cur <= 1} onClick={() => gotoPage(cur - 1)}>上一页</button>
          <span>{cur} / {pages}</span>
          <button type="button" disabled={cur >= pages} onClick={() => gotoPage(cur + 1)}>下一页</button>
        </nav>
      )}
    </div>
  );
}
