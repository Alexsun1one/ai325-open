"use client";

/* 旋转扇形书架：封面沿圆弧排布可拨动，中央放大选中，下方编辑式详情。
 * 只渲染可见邻域（≤7 桌面 / ≤5 手机）；纯 transform/opacity 过渡；
 * 键盘仅书架焦点内生效，触摸横向拨动不抢纵向滚动（touch-action: pan-y）。
 * URL 状态 q/kind/topic/book/page：筛选与页码 push（返回可回退），选中书与搜索词 replace（不刷历史）。 */

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Icon } from "@/components/ui/Icon";
import { BookCover } from "@/components/ui/BookCover";
import {
  entriesInTopic, entryTopics, makeUrlEcho, matchesQuery, relatedEntries,
  type ShelfCatalogue, type ShelfEntry,
} from "@/lib/reading-shelf";
import styles from "./ReadingShelf.module.css";

const KINDS = [
  { id: "all", label: "全部" },
  { id: "book", label: "书与长文" },
  { id: "repository", label: "仓库" },
] as const;
const PAGE_SIZE = 12;

function useMedia(query: string): boolean {
  return useSyncExternalStore(
    useCallback((cb) => {
      const m = window.matchMedia(query);
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    }, [query]),
    () => window.matchMedia(query).matches,
    () => false,
  );
}

function slotTransform(d: number, compact: boolean): string {
  const step = compact ? 104 : 226;
  const angle = compact ? 9 : 10;
  const depth = compact ? 22 : 38;
  const drop = compact ? 4 : 8;
  // --drag 由 pointer 拖拽经 rAF 直写 DOM，不走 React 渲染
  return [
    "translateX(-50%)",
    `translateX(calc(${d * step}px + var(--drag, 0px)))`,
    `translateZ(${-Math.abs(d) * depth}px)`,
    `translateY(${Math.abs(d) * drop}px)`,
    `rotateY(${d * angle}deg)`,
  ].join(" ");
}

function CatBlock({ id, kind, entries, catalogue, page, onPage, open, onToggle }: {
  id: string; kind: "book" | "repository"; entries: ShelfEntry[];
  catalogue: ShelfCatalogue; page: number; onPage: (n: number) => void;
  open: boolean; onToggle: (open: boolean) => void;
}) {
  const pages = Math.max(1, Math.ceil(entries.length / PAGE_SIZE));
  const cur = Math.min(page, pages);
  const slice = entries.slice((cur - 1) * PAGE_SIZE, cur * PAGE_SIZE);
  return (
    <details className={styles.catDetails} id={id} open={open} onToggle={(e) => onToggle(e.currentTarget.open)}>
      <summary>{kind === "book" ? "书与长文" : "仓库拆解"} 精选目录 <span className={styles.catCount}>{entries.length} 条</span></summary>
      {entries.length === 0 ? <p className={styles.catEmpty}>当前筛选下没有{kind === "book" ? "书与长文" : "仓库拆解"}。</p> : (
        <>
          <ol className={styles.catList} start={(cur - 1) * PAGE_SIZE + 1}>
            {slice.map((e) => (
              <li key={e.id}>
                <Link href={`/readings/${e.id}/`} className={styles.catLink}>
                  <span className={styles.catTitle}>{e.title}</span>
                  <span className={styles.catTopics}>{entryTopics(catalogue, e.id).map((t) => t.name).join(" · ") || "未分主题"}</span>
                </Link>
              </li>
            ))}
          </ol>
          <p className={styles.catPager}>
            <button type="button" disabled={cur <= 1} onClick={() => onPage(cur - 1)}><Icon name="back" size={16} /> 上一页</button>
            <span>第 {cur} / {pages} 页 · 本页 {slice.length} 条</span>
            <button type="button" disabled={cur >= pages} onClick={() => onPage(cur + 1)}>下一页 <Icon name="arrow" size={16} /></button>
          </p>
        </>
      )}
    </details>
  );
}

export function ReadingShelf({ entries, catalogue }: { entries: ShelfEntry[]; catalogue: ShelfCatalogue }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const compact = useMedia("(max-width: 720px)");
  const reduce = useMedia("(prefers-reduced-motion: reduce)");

  // qLive=输入真值；urlRef=最新意图中的 URL 串（写基准，不用滞后 params）；
  // echo=已写串名册，配 popstate 区分「自己回声」与「真后退」。
  const qLive = useRef(params.get("q") ?? "");
  const urlRef = useRef(params.toString());
  const echo = useRef(makeUrlEcho());
  const popped = useRef(false);
  const [q, setQ] = useState(() => params.get("q") ?? "");
  const [kind, setKind] = useState<string>(() => params.get("kind") ?? "all");
  const [topic, setTopic] = useState<string>(() => params.get("topic") ?? "");
  const [page, setPage] = useState(() => Number(params.get("page")) || 1);
  const [selId, setSelId] = useState<string | null>(() => params.get("book"));
  const [keyboardInstant, setKeyboardInstant] = useState(false);
  const keyboardTimer = useRef<number | undefined>(undefined);
  const dragRef = useRef<{ x: number; moved: boolean } | null>(null);
  const dragX = useRef(0);            // 拖拽位移只经 rAF 写 CSS 变量，不进 React state
  const dragRaf = useRef(0);
  const movedRef = useRef(false); // 拖拽抬手后抑制紧随的 click（侧书选中/中央跳转都压掉）
  const stageRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const catRef = useRef<HTMLDivElement>(null);
  // 目录展开态：用户显式开合优先；否则有筛选（q/kind/topic）时自动展开有结果的类型
  const [catOpen, setCatOpen] = useState<Record<string, boolean>>({});

  const filtered = useMemo(
    () => entries.filter((e) =>
      (kind === "all" || e.kind === kind) &&
      (!topic || entryTopics(catalogue, e.id).some((t) => t.id === topic)) &&
      matchesQuery(e, q)),
    [entries, kind, topic, q, catalogue],
  );

  // 选中态 = 条目 id；序号在 filtered 内即时派生，越界/未命中收敛到 0（无 effect setState）
  const found = selId ? filtered.findIndex((e) => e.id === selId) : -1;
  const selIdx = found >= 0 ? found : 0;
  // popstate 只由真实前进/后退触发（pushState/replaceState 不发）→ 标记外部导航
  useEffect(() => {
    const onPop = () => { popped.current = true; };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // params 变化：自己写出的串回声跳过（不覆盖未提交输入）；否则外部导航 → 全量同步回本地。
  useEffect(() => {
    const qs = params.toString();
    if (echo.current.isEcho(qs, popped.current)) return;
    popped.current = false;
    urlRef.current = qs;
    const sp = params;
    const t = window.setTimeout(() => {
      setSelId(sp.get("book"));
      setKind(sp.get("kind") ?? "all");
      setTopic(sp.get("topic") ?? "");
      const qp = sp.get("q") ?? "";
      qLive.current = qp;
      setQ(qp);
      setPage(Number(sp.get("page")) || 1);
    }, 0);
    return () => window.clearTimeout(t);
  }, [params]);

  const write = useCallback((next: Record<string, string | null>, mode: "push" | "replace") => {
    const sp = new URLSearchParams(urlRef.current); // 以最新意图为基准，不丢在途输入
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

  // 搜索输入：本地状态即时过滤，URL 停顿后 replace（不每键导航、不掉焦点）
  const qTimer = useRef<number | undefined>(undefined);
  const onQuery = (v: string) => {
    qLive.current = v;
    setQ(v);
    window.clearTimeout(qTimer.current);
    qTimer.current = window.setTimeout(() => write({ q: v || null, book: null, page: null }, "replace"), 350);
  };

  /** 清除全部筛选：debounce 定时器 + qLive 输入真值 + 本地状态一次清零——
   *  否则下一次 write 会把 qLive 里的旧词带回 URL，在途 debounce 也会复活旧 q。 */
  const clearAll = useCallback(() => {
    window.clearTimeout(qTimer.current);
    qLive.current = "";
    setQ(""); setKind("all"); setTopic(""); setPage(1); setSelId(null);
    if (searchRef.current) searchRef.current.value = "";
    write({ q: null, kind: null, topic: null, book: null, page: null }, "push");
  }, [write]);

  const n = filtered.length;
  const select = useCallback((i: number) => {
    if (!n) return;
    const wrapped = ((i % n) + n) % n; // 圆环绕行：端点互相接通
    setSelId(filtered[wrapped]?.id ?? null);
    write({ book: filtered[wrapped]?.id ?? null }, "replace");
  }, [filtered, n, write]);

  const step = compact ? 104 : 226;
  const half = compact ? 1 : 2;
  const sel = filtered[selIdx] ?? null;
  const related = useMemo(
    () => (sel ? relatedEntries(catalogue, entries, sel) : []),
    [catalogue, entries, sel],
  );
  const selTopics = sel ? entryTopics(catalogue, sel.id) : [];

  // 卸载清理：debounce 定时器 + 拖拽 rAF + 残留的 --drag
  useEffect(() => () => {
    window.clearTimeout(qTimer.current);
    window.clearTimeout(keyboardTimer.current);
    cancelAnimationFrame(dragRaf.current);
    innerRef.current?.style.removeProperty("--drag");
  }, []);

  const onKeyDown = (e: React.KeyboardEvent) => {
    const keyboardSelect = (index: number) => {
      e.preventDefault();
      setKeyboardInstant(true);
      window.clearTimeout(keyboardTimer.current);
      keyboardTimer.current = window.setTimeout(() => setKeyboardInstant(false), 0);
      select(index);
    };
    if (e.key === "ArrowLeft") keyboardSelect(selIdx - 1);
    else if (e.key === "ArrowRight") keyboardSelect(selIdx + 1);
    else if (e.key === "Home") keyboardSelect(0);
    else if (e.key === "End") keyboardSelect(filtered.length - 1);
    else if (e.key === "Enter" && sel && e.target === e.currentTarget) {
      e.preventDefault(); router.push(`/readings/${sel.id}/`);
    }
  };

  const applyDrag = (px: number) => {
    dragX.current = px;
    if (!dragRaf.current) {
      dragRaf.current = requestAnimationFrame(() => {
        dragRaf.current = 0;
        innerRef.current?.style.setProperty("--drag", `${dragX.current}px`);
      });
    }
  };
  const onPointerDown = (e: React.PointerEvent) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    dragRef.current = { x: e.clientX, moved: false };
    movedRef.current = false;
    // 不在按下时捕获：确认横拖后再 capture，普通点击（封/按钮）保持原目标
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    if (!d.moved && Math.abs(dx) > 8) {
      d.moved = true; movedRef.current = true;
      stageRef.current?.setPointerCapture(e.pointerId);
    }
    if (d.moved) applyDrag(dx);
  };
  const onPointerUp = (e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    dragRef.current = null;
    const dx = dragX.current;
    cancelAnimationFrame(dragRaf.current); dragRaf.current = 0;
    dragX.current = 0;
    innerRef.current?.style.setProperty("--drag", "0px");
    if (stageRef.current?.hasPointerCapture(e.pointerId)) {
      stageRef.current.releasePointerCapture(e.pointerId);
    }
    if (d.moved) select(selIdx - Math.round(dx / step));
  };
  const onSlotClick = (i: number) => {
    if (movedRef.current) return; // 拖拽抬手不当点击
    select(i);
  };

  const bookEntries = useMemo(() => filtered.filter((e) => e.kind === "book"), [filtered]);
  const repoEntries = useMemo(() => filtered.filter((e) => e.kind === "repository"), [filtered]);
  const filtersOn = q.trim() !== "" || kind !== "all" || topic !== "";
  const catIsOpen = (id: string, count: number) => catOpen[id] ?? (filtersOn && count > 0);
  // 先真实展开，再等提交后定位；不能只跳锚点到折叠的 details
  const openCatalogue = () => {
    setCatOpen({ books: bookEntries.length > 0, repositories: repoEntries.length > 0 });
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const el = catRef.current;
      if (!el) return;
      // 立即定位：不用 smooth（长距离要 2s+），instant 也压过全局 scroll-behavior
      el.scrollIntoView({ behavior: "instant", block: "start" });
      el.focus({ preventScroll: true });
    }));
  };

  return (
    <section id="shelf" className={styles.shelfRoot} aria-label="可拨动的精读书架">
      <div className={styles.controls}>
        <div className={styles.kindSeg} role="group" aria-label="按类型筛选">
          {KINDS.map((k) => (
            <button
              key={k.id} type="button" aria-pressed={kind === k.id}
              className={kind === k.id ? styles.segOn : undefined}
              onClick={() => { setKind(k.id); write({ kind: k.id, book: null, page: null }, "push"); }}
            >{k.label}</button>
          ))}
        </div>
        <label className={styles.search}>
          <Icon name="search" size={16} />
          <input
            ref={searchRef} value={q} onChange={(e) => onQuery(e.target.value)}
            placeholder="搜书名、主题或仓库" aria-label="搜索精读" type="search"
          />
        </label>
        <Link href="/readings/find/" className={styles.findLink}>
          <Icon name="method" size={15} /> 按问题找实现
        </Link>
      </div>
      <div className={styles.topics} role="group" aria-label="按主题筛选">
        <button type="button" aria-pressed={!topic} className={!topic ? styles.segOn : undefined}
          onClick={() => { setTopic(""); write({ topic: null, book: null, page: null }, "push"); }}>全部主题</button>
        {catalogue.topics.map((t) => (
          <button key={t.id} type="button" aria-pressed={topic === t.id}
            className={topic === t.id ? styles.segOn : undefined} title={t.intro}
            onClick={() => { setTopic(t.id); write({ topic: t.id, book: null, page: null }, "push"); }}
          >{t.name}</button>
        ))}
      </div>
      {topic && (
        <p className={styles.topicIntro}>
          {catalogue.topics.find((t) => t.id === topic)?.intro}
        </p>
      )}

      {filtered.length === 0 ? (
        <div className={styles.empty}>
          <p>没有匹配的精读条目。</p>
          <button type="button" onClick={clearAll}>清除全部筛选</button>
        </div>
      ) : (
        <>
          <p className={styles.announce} aria-live="polite">
            第 {selIdx + 1} / 共 {filtered.length} 条 · {sel?.title}
          </p>
          <div
            ref={stageRef} className={styles.stage} role="group" tabIndex={0}
            aria-label="书架：方向键或左右拖动选择，回车开始精读"
            onKeyDown={onKeyDown}
            onPointerDown={onPointerDown} onPointerMove={onPointerMove}
            onPointerUp={onPointerUp} onPointerCancel={onPointerUp}
          >
            <div ref={innerRef} className={styles.stageInner}>
              {filtered.map((e, i) => {
                // 模距离：圆环绕行；条目数 ≤ 可见窗时全量不重复、对称排布
                let d = (((i - selIdx) % n) + n) % n;
                if (d > Math.floor(n / 2)) d -= n;
                if (Math.abs(d) > half) return null;
                return (
                  <div
                    key={e.id} className={styles.slot}
                    style={{
                      transform: slotTransform(d, compact),
                      zIndex: 10 - Math.abs(d),
                      transitionDuration: reduce || keyboardInstant ? "0s" : undefined,
                    }}
                  >
                    {d === 0 ? (
                      <Link
                        href={`/readings/${e.id}/`} className={styles.coverLink} aria-label={`开始精读《${e.title}》`}
                        draggable={false}
                        onDragStart={(ev) => ev.preventDefault()}
                        onClickCapture={(ev) => { if (movedRef.current) { ev.preventDefault(); ev.stopPropagation(); } }}
                      >
                      <BookCover id={e.id} title={e.title} kind={e.kind} size="shelf" active />
                      </Link>
                    ) : (
                      <button type="button" className={styles.coverLink} aria-label={`选中《${e.title}》`} onClick={() => onSlotClick(i)} tabIndex={-1}>
                        <BookCover id={e.id} title={e.title} kind={e.kind} size="shelf" />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
            <button type="button" className={`${styles.navBtn} ${styles.navPrev}`} aria-label="上一本"
              disabled={n <= 1} onClick={() => select(selIdx - 1)}><Icon name="back" size={18} /></button>
            <button type="button" className={`${styles.navBtn} ${styles.navNext}`} aria-label="下一本"
              disabled={n <= 1} onClick={() => select(selIdx + 1)}><Icon name="arrow" size={18} /></button>
          </div>
          <div className={styles.shelfBar}>
            <p className={styles.pos} aria-hidden="true">第 <b>{selIdx + 1}</b> / {filtered.length}</p>
            <p className={styles.hint}><Icon name="info" size={14} /> <span className={styles.hintText}>拖动书架，或使用左右方向键</span></p>
            <button type="button" className={styles.catBtn} aria-controls="catalogue" onClick={openCatalogue}>
              {filtersOn ? "筛选结果目录" : "精选目录"} · {filtered.length} 条 <Icon name="arrow" size={14} />
            </button>
          </div>

          {sel && (
            <div className={styles.detail} key={sel.id}>
              <div className={styles.detailMain}>
                <p className={styles.detailKind}>
                  <Icon name={sel.kind === "book" ? "book" : "skill"} size={16} />
                  {sel.kind === "book" ? "书与长文" : "仓库拆解"}
                  {selTopics.length > 0 && <span className={styles.detailTopics}> · {selTopics.map((t) => t.name).join(" / ")}</span>}
                </p>
                <h3>{sel.title}</h3>
                {sel.subtitle && <p className={styles.detailSub}>{sel.subtitle}</p>}
                <p className={styles.detailSummary}>{sel.summary}</p>
                {sel.tags.length > 0 && <p className={styles.detailTags}>{sel.tags.join(" / ")}</p>}
                <div className={styles.detailActions}>
                  <Link href={`/readings/${sel.id}/`} className={styles.readBtn}>开始精读 <Icon name="arrow" size={16} /></Link>
                  {sel.sourceUrl && (
                    <a href={sel.sourceUrl} target="_blank" rel="noopener noreferrer" className={styles.srcLink}>
                      {sel.sourceTitle || "原文来源"} <Icon name="external" size={14} />
                    </a>
                  )}
                </div>
              </div>
              <aside className={styles.detailAside}>
                <h4>顺着这条线，继续读</h4>
                {related.length > 0 ? (
                  <ul>
                    {related.map(({ entry: r, topic: tname }) => (
                      <li key={r.id}>
                        {/* related 取自全部条目，可能不在当前筛选内——直接 Link 进条目，
                            不用 filtered.indexOf（-1 会误选末条），也不吃拖拽 movedRef。 */}
                        <Link href={`/readings/${r.id}/`} className={styles.relBtn}>
                          <Icon name="arrow" size={14} /> {r.title}
                        </Link>
                        <span className={styles.relTopic}>共同主题：{tname}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className={styles.relEmpty}>这条线暂时没有同主题条目。换主题看看：</p>
                )}
                {related.length === 0 && catalogue.topics.filter((t) => entriesInTopic(catalogue, entries, t.id).length > 0).map((t) => (
                  <button key={t.id} type="button" className={styles.relBtn}
                    onClick={() => { setTopic(t.id); write({ topic: t.id, book: null, page: null }, "push"); }}>
                    <Icon name="arrow" size={14} /> {t.name}
                  </button>
                ))}
              </aside>
            </div>
          )}
        </>
      )}

      <div className={styles.catalogue} id="catalogue" ref={catRef} tabIndex={-1}>
        <CatBlock id="books" kind="book" entries={bookEntries} catalogue={catalogue} page={page}
          open={catIsOpen("books", bookEntries.length)} onToggle={(o) => { if (o !== catIsOpen("books", bookEntries.length)) setCatOpen((c) => ({ ...c, books: o })); }}
          onPage={(n) => { setPage(n); write({ page: String(n) }, "push"); }} />
        <CatBlock id="repositories" kind="repository" entries={repoEntries} catalogue={catalogue} page={page}
          open={catIsOpen("repositories", repoEntries.length)} onToggle={(o) => { if (o !== catIsOpen("repositories", repoEntries.length)) setCatOpen((c) => ({ ...c, repositories: o })); }}
          onPage={(n) => { setPage(n); write({ page: String(n) }, "push"); }} />
      </div>
    </section>
  );
}
