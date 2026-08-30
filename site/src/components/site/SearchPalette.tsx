"use client";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { API_BASE, getToken } from "@/lib/auth";

interface Related { source: string; title: string; url: string }
interface Hit { source: string; title: string; excerpt: string; url: string; date: string; issue: number | null; related?: Related[] }
interface IndexPayload { threads: { title: string; url: string; issue: number | null }[]; glossary: { title: string; url: string }[] }
interface Payload { items: Hit[]; count: number; gated_included: boolean; fuzzy?: boolean; index?: IndexPayload }

const SOURCE_ORDER = ["线索", "黑话", "品评项", "军火库", "深潜", "日报", "悬案", "对撞", "窖藏", "群像", "弹药", "大事记", "真伪鉴定", "逐字摘录"];

/** 命中词高亮：拆分渲染，不走 innerHTML。 */
function Mark({ text, terms }: { text: string; terms: string[] }) {
  const parts = useMemo(() => {
    if (!terms.length) return [{ t: text, on: false }];
    const re = new RegExp(`(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
    return text.split(re).filter(Boolean).map((t) => ({ t, on: terms.some((k) => t.toLowerCase() === k.toLowerCase()) }));
  }, [text, terms]);
  return <>{parts.map((p, i) => (p.on ? <b key={i} className="font-semibold text-blue-text">{p.t}</b> : <Fragment key={i}>{p.t}</Fragment>))}</>;
}

/** 站内检索：只检索治理产物。空查询 = 可浏览索引（线索 + 黑话），给第一次来的人一张地图。 */
export function SearchPalette() {
  const reduce = useReducedMotion();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [sel, setSel] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const seq = useRef(0);

  // 打开入口：按钮、/ 键、⌘K
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA" || (e.target as HTMLElement)?.isContentEditable;
      if ((e.key === "/" && !typing) || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k")) {
        e.preventDefault(); setOpen(true);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => { if (open) setTimeout(() => inputRef.current?.focus(), 30); }, [open]);

  // 防抖检索；空查询拿索引
  useEffect(() => {
    if (!open) return;
    const id = ++seq.current;
    const t = setTimeout(async () => {
      setBusy(true); setErr("");
      try {
        const token = getToken();
        const r = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(q.trim())}`, {
          headers: token ? { authorization: `Bearer ${token}` } : {},
        });
        if (!r.ok) throw new Error(`检索失败（HTTP ${r.status}）`);
        const d = (await r.json()) as Payload;
        if (seq.current === id) { setData(d); setSel(0); }
      } catch (e) {
        if (seq.current === id) setErr(e instanceof Error ? e.message : "检索失败");
      } finally {
        if (seq.current === id) setBusy(false);
      }
    }, q.trim() ? 220 : 0);
    return () => clearTimeout(t);
  }, [q, open]);

  const terms = useMemo(() => q.trim().split(/\s+/).filter(Boolean), [q]);
  const groups = useMemo(() => {
    const g = new Map<string, Hit[]>();
    for (const h of data?.items ?? []) {
      if (!g.has(h.source)) g.set(h.source, []);
      g.get(h.source)!.push(h);
    }
    return Array.from(g.entries()).sort((a, b) => {
      const ia = SOURCE_ORDER.indexOf(a[0]), ib = SOURCE_ORDER.indexOf(b[0]);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });
  }, [data]);
  const flat = useMemo(() => groups.flatMap(([, hs]) => hs), [groups]);

  const goto = useCallback((url: string) => { setOpen(false); window.location.href = url; }, []);

  const onInputKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, flat.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    if (e.key === "Enter" && flat[sel]) { e.preventDefault(); goto(flat[sel].url); }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex min-h-11 items-center gap-1.5 rounded-md px-2 py-2 font-sans text-[13px] font-medium text-ink-2 transition-colors hover:bg-paper-2 hover:text-ink sm:min-h-0 sm:py-1.5"
        aria-label="站内检索（快捷键 /）"
      >
        <svg aria-hidden width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.5-4.5" /></svg>
        <span className="hidden sm:inline">检索</span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            key="search"
            initial={reduce ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="no-print fixed inset-0 z-50 bg-ink/25 backdrop-blur-[2px]"
            onMouseDown={(e) => { if (e.target === e.currentTarget) setOpen(false); }}
          >
            <motion.div
              role="dialog"
              aria-modal="true"
              aria-label="站内检索"
              initial={reduce ? false : { y: -10, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
              className="mx-auto mt-[10vh] flex max-h-[72vh] w-[min(680px,calc(100vw-24px))] flex-col overflow-hidden rounded-[14px] border border-rule bg-paper shadow-[var(--shadow-pop)]"
            >
              <div className="flex items-center gap-3 border-b border-rule px-5 py-3.5">
                <svg aria-hidden width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" className="shrink-0 text-ink-3"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.5-4.5" /></svg>
                <input
                  ref={inputRef}
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  onKeyDown={onInputKey}
                  placeholder="搜关键词：某个话题、黑话、人名、工具……"
                  className="w-full bg-transparent font-sans text-[15px] text-ink outline-none placeholder:text-ink-3"
                  maxLength={60}
                />
                <kbd className="hidden shrink-0 rounded-[4px] border border-rule px-1.5 py-0.5 font-sans text-[10.5px] text-ink-3 sm:block">ESC</kbd>
              </div>

              <div className="min-h-0 overflow-y-auto px-2 py-2">
                {err && <p className="px-3 py-4 font-sans text-[13px] text-amber-text">{err}</p>}

                {/* 检索结果 */}
                {!err && q.trim() && (
                  flat.length ? (
                    <>
                      {data?.fuzzy && <p className="px-3 pb-1 pt-2 font-sans text-[12px] text-ink-3">没有整词命中，下面是按相近字面找到的：</p>}
                      {groups.map(([source, hits]) => (
                        <Fragment key={source}>
                          <div className="label px-3 pb-1 pt-3 text-[11px] font-semibold">{source}</div>
                          <ul>
                            {hits.map((h) => {
                              const gi = flat.indexOf(h);
                              return (
                                <li key={`${h.url}-${gi}`}>
                                  <a
                                    href={h.url}
                                    onClick={(e) => { e.preventDefault(); goto(h.url); }}
                                    onMouseEnter={() => setSel(gi)}
                                    className={`block rounded-[8px] px-3 py-2 no-underline ${gi === sel ? "bg-blue-wash" : "hover:bg-paper-2"}`}
                                    aria-current={gi === sel ? "true" : undefined}
                                  >
                                    <span className="flex items-baseline justify-between gap-3">
                                      <span className="min-w-0 truncate font-serif text-[15px] font-bold text-ink"><Mark text={h.title} terms={terms} /></span>
                                      {(h.issue || h.date) && <span className="num shrink-0 font-sans text-[11px] text-ink-3">{h.issue ? `第 ${String(h.issue).padStart(3, "0")} 批` : h.date}</span>}
                                    </span>
                                    {h.excerpt && <span className="mt-0.5 block truncate font-sans text-[12.5px] leading-relaxed text-ink-2"><Mark text={h.excerpt} terms={terms} /></span>}
                                  </a>
                                  {/* 关联词:线索↔军火库互指,样式同索引模式的线索 chips 但更小 */}
                                  {(h.related?.length ?? 0) > 0 && (
                                    <div className="flex flex-wrap items-center gap-1.5 px-3 pb-2 pt-0.5">
                                      <span aria-hidden className="font-sans text-[11px] text-ink-3">关联 →</span>
                                      {h.related!.map((r) => (
                                        <a key={`${r.url}-${r.title}`} href={r.url} onClick={(e) => { e.preventDefault(); goto(r.url); }}
                                          aria-label={`关联:${r.source}·${r.title}`}
                                          className="rounded-full border border-blue-wash-2 bg-blue-wash px-2 py-[1px] font-sans text-[11.5px] font-medium text-blue-text no-underline hover:bg-blue-wash-2">
                                          {r.source} · {r.title}
                                        </a>
                                      ))}
                                    </div>
                                  )}
                                </li>
                              );
                            })}
                          </ul>
                        </Fragment>
                      ))}
                    </>
                  ) : (
                    !busy && <p className="px-3 py-5 font-sans text-[13.5px] leading-relaxed text-ink-2">这个词没搜到。换个说法试试，或者去<a href="/archive/" className="text-blue-text">往期</a>按线索翻。</p>
                  )
                )}

                {/* 索引模式：空查询给一张地图 */}
                {!err && !q.trim() && data?.index && (
                  <div className="px-3 py-2">
                    {data.index.threads.length > 0 && (
                      <>
                        <div className="label pb-1.5 pt-1 text-[11px] font-semibold">线索 · 跨期在追的话题</div>
                        <div className="flex flex-wrap gap-1.5">
                          {data.index.threads.map((t) => (
                            <a key={t.url} href={t.url} onClick={(e) => { e.preventDefault(); goto(t.url); }}
                              className="rounded-full border border-blue-wash-2 bg-blue-wash px-2.5 py-1 font-sans text-[12px] font-medium text-blue-text no-underline hover:bg-blue-wash-2">
                              {t.title}
                            </a>
                          ))}
                        </div>
                      </>
                    )}
                    {data.index.glossary.length > 0 && (
                      <>
                        <div className="label pb-1.5 pt-4 text-[11px] font-semibold">黑话 · 想听懂这个群先学这些词</div>
                        <div className="flex flex-wrap gap-x-3 gap-y-1.5">
                          {data.index.glossary.map((g) => (
                            <a key={`${g.url}-${g.title}`} href={g.url} onClick={(e) => { e.preventDefault(); goto(g.url); }}
                              className="font-serif text-[14px] text-ink-2 no-underline [background:linear-gradient(transparent_62%,var(--amber-wash)_62%,var(--amber-wash)_92%,transparent_92%)] hover:text-ink">
                              {g.title}
                            </a>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                )}

                {busy && <p className="px-3 py-2 font-sans text-[12px] text-ink-3">检索中…</p>}
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-rule px-5 py-2.5 font-sans text-[11.5px] text-ink-3">
                <span>只检索蒸好的 · 原始聊天不进检索</span>
                <span>{data?.gated_included ? "已含窖藏与群像" : "登录后，窖藏与群像也会进检索"}</span>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
