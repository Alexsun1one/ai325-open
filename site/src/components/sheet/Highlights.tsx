"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { api } from "@/lib/api";

/** 形状照 backend 2026-08-23 10:56 报告：user 已经是显示名，时间字段叫 at，
 *  公开列表本身只含 accepted + public，所以不再自己过滤 visibility。 */
export interface Anno {
  id: number | string;
  anchor: string;
  quote: string;
  note?: string;
  user?: string;
  avatar?: string | null;
  kind?: string;
  at?: string;
  is_admin?: boolean;
}

interface Bar { key: string; top: number; left: number; width: number; depth: number; anchor: string; quote: string }

/** 在段落里找到这句话的位置。段落是 innerHTML 渲染的，所以只读不改 DOM——用 Range 量出坐标，划线画在覆盖层上。 */
function rangeOf(el: HTMLElement, quote: string): Range | null {
  const q = quote.replace(/\s+/g, "").trim();
  if (q.length < 4) return null;
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  let flat = "";
  const map: { node: Text; start: number }[] = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const t = n as Text;
    nodes.push(t);
    map.push({ node: t, start: flat.length });
    flat += (t.data ?? "").replace(/\s+/g, "");
  }
  const i = flat.indexOf(q);
  if (i < 0) return null;
  const j = i + q.length;
  const locate = (pos: number) => {
    for (let k = map.length - 1; k >= 0; k--) {
      if (map[k].start <= pos) {
        const raw = map[k].node.data ?? "";
        // 把「去掉空白后的位置」还原回原始文本的位置
        let seen = map[k].start, off = 0;
        for (; off < raw.length && seen < pos; off++) if (!/\s/.test(raw[off])) seen++;
        return { node: map[k].node, offset: Math.min(off, raw.length) };
      }
    }
    return { node: nodes[0], offset: 0 };
  };
  const a = locate(i), b = locate(j);
  try {
    const r = document.createRange();
    r.setStart(a.node, a.offset);
    r.setEnd(b.node, b.offset);
    return r;
  } catch { return null; }
}

/** 公共划线层：谁在这一锅里划过哪一句，全群都看得见。划得越多，琥珀越深。 */
export function Highlights({ date }: { date: string }) {
  const [items, setItems] = useState<Anno[] | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [bars, setBars] = useState<Bar[]>([]);
  const [open, setOpen] = useState<{ anchor: string; quote: string } | null>(null);
  const [mounted, setMounted] = useState(false);
  const reduce = useReducedMotion();
  const tries = useRef(0);

  useEffect(() => { setMounted(true); }, []);

  useEffect(() => {
    let alive = true;
    api<{ items?: Anno[]; counts?: Record<string, number> }>(`/api/annotations?date=${date}`, { auth: false })
      .then((d) => { if (!alive) return; setItems(d.items ?? []); setCounts(d.counts ?? {}); })
      .catch(() => { if (alive) setItems([]); });   // 还没开通就安静：正文照常读
    return () => { alive = false; };
  }, [date]);

  const measure = useCallback(() => {
    if (!items?.length) { setBars([]); return; }
    const pub = items.filter((a) => a.quote);   // 公开列表已由后端过滤
    // 同一句被多人划过 → 叠加深度
    const byQuote = new Map<string, Anno[]>();
    for (const a of pub) {
      const k = `${a.anchor}||${a.quote.replace(/\s+/g, "")}`;
      byQuote.set(k, [...(byQuote.get(k) ?? []), a]);
    }
    const out: Bar[] = [];
    for (const [k, group] of byQuote) {
      const [anchor, quote] = k.split("||");
      const el = document.querySelector<HTMLElement>(`[data-anchor="${CSS.escape(anchor)}"]`);
      if (!el) continue;
      const r = rangeOf(el, group[0].quote);
      if (!r) continue;
      const depth = Math.min(3, group.length);
      Array.from(r.getClientRects()).forEach((rect, n) => {
        if (rect.width < 2) return;
        out.push({
          key: `${k}-${n}`, anchor, quote,
          top: rect.bottom + window.scrollY - 2,
          left: rect.left + window.scrollX,
          width: rect.width, depth,
        });
      });
    }
    setBars(out);
  }, [items]);

  // 锚点是 ParagraphTools 在 effect 里打的，可能比这里晚；重试几次直到量到为止
  useEffect(() => {
    if (!items) return;
    tries.current = 0;
    const tick = () => {
      measure();
      if (tries.current++ < 12 && !document.querySelector("[data-anchor]")) setTimeout(tick, 220);
    };
    tick();
    const ro = new ResizeObserver(() => measure());
    const main = document.querySelector("main");
    if (main) ro.observe(main);
    addEventListener("resize", measure);
    document.fonts?.ready.then(() => measure()).catch(() => {});
    return () => { ro.disconnect(); removeEventListener("resize", measure); };
  }, [items, measure]);

  // 段尾「N 人划过」：后端直接给了按 anchor 聚合的 counts，用它，别自己数
  useEffect(() => {
    if (!items) return;
    const agg = new Map<string, number>(Object.entries(counts));
    if (!agg.size) for (const a of items) agg.set(a.anchor, (agg.get(a.anchor) ?? 0) + 1);
    const made: HTMLElement[] = [];
    for (const [anchor, n] of agg) {
      if (!n) continue;
      const el = document.querySelector<HTMLElement>(`[data-anchor="${CSS.escape(anchor)}"]`);
      if (!el || el.querySelector("[data-hl-tag]")) continue;
      const tag = document.createElement("span");
      tag.dataset.hlTag = "1";
      tag.className = "ml-2 inline-flex translate-y-[-1px] items-center rounded-[3px] border border-amber-deep/40 bg-amber-wash px-1.5 py-[1px] align-middle font-sans text-[11px] font-semibold text-amber-text";
      tag.textContent = `${n} 人划过`;
      el.appendChild(tag);
      made.push(tag);
    }
    return () => { for (const t of made) t.remove(); };
  }, [items, counts]);

  const panel = open ? (items ?? []).filter((a) => a.anchor === open.anchor && a.quote.replace(/\s+/g, "") === open.quote) : [];

  if (!mounted || !bars.length) return null;

  return createPortal(
    <>
      <div aria-hidden className="no-print pointer-events-none absolute left-0 top-0 z-[5]">
        {bars.map((b) => (
          <button
            key={b.key}
            type="button"
            onMouseEnter={() => setOpen({ anchor: b.anchor, quote: b.quote.replace(/\s+/g, "") })}
            onClick={() => setOpen({ anchor: b.anchor, quote: b.quote.replace(/\s+/g, "") })}
            aria-label="看谁划了这一句"
            className="pointer-events-auto absolute cursor-pointer rounded-full transition-[height,opacity] hover:h-[5px]"
            style={{
              top: b.top, left: b.left, width: b.width, height: 3,
              background: "var(--amber)",
              opacity: b.depth === 1 ? 0.42 : b.depth === 2 ? 0.7 : 1,
            }}
          />
        ))}
      </div>

      <AnimatePresence>
        {open && panel.length > 0 && (
          <motion.aside
            data-notebook
            initial={reduce ? false : { x: 24, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={reduce ? { opacity: 0 } : { x: 24, opacity: 0 }}
            transition={reduce ? { duration: 0 } : { duration: 0.26, ease: [0.16, 1, 0.3, 1] }}
            className="no-print fixed bottom-0 right-0 top-[var(--nav-h)] z-40 flex w-full max-w-[400px] flex-col border-l border-rule bg-paper shadow-[var(--shadow-pop)]"
            role="dialog" aria-label="划过这一句的人">
            <div className="flex items-start justify-between gap-3 border-b border-rule px-5 py-3">
              <div>
                <div className="font-serif text-[16px] font-bold text-ink">划过这一句的人</div>
                <div className="num font-sans text-[12px] text-ink-3">{panel.length} 位</div>
              </div>
              <button type="button" onClick={() => setOpen(null)} className="rounded-md px-2 py-1 text-ink-3 hover:text-ink" aria-label="关闭">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M6 6l12 12M18 6L6 18" /></svg>
              </button>
            </div>
            <blockquote className="prose-sheet mx-5 mt-4 border-l-2 border-amber pl-3 text-[14.5px] leading-[1.75] text-ink-2">{panel[0].quote}</blockquote>
            <ul className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
              {panel.map((a) => (
                <li key={a.id} className={`rounded-[10px] border px-4 py-3 ${a.is_admin ? "border-cinnabar/40 bg-cinnabar-wash/45" : "border-rule bg-paper-2/50"}`}>
                  <div className="flex items-center gap-2.5">
                    {a.avatar
                      // eslint-disable-next-line @next/next/no-img-element
                      ? <img src={a.avatar} alt="" width={26} height={26} className="h-[26px] w-[26px] shrink-0 rounded-full border border-rule object-cover" />
                      : <span aria-hidden className="inline-flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full border border-blue-wash-2 bg-blue-wash font-serif text-[13px] font-bold text-blue-text">{(a.user || "?").slice(0, 1)}</span>}
                    <span className="min-w-0 flex-1 truncate font-sans text-[13.5px] font-semibold text-ink">{a.user}</span>
                    {a.is_admin && (
                      <span className="inline-flex shrink-0 -rotate-2 items-center rounded-[3px] border border-cinnabar px-1.5 py-[1px] font-sans text-[10.5px] font-semibold text-cinnabar-text">鉴定人批注</span>
                    )}
                  </div>
                  {a.note ? <p className={`mt-2 text-[15.5px] leading-[1.8] ${a.is_admin ? "hand" : "prose-sheet"}`}>{a.note}</p> : <p className="mt-2 font-sans text-[13px] text-ink-3">只划了线，没写话。</p>}
                  {a.at && <div className="num mt-1.5 font-sans text-[11.5px] text-ink-3">{a.at.replace("T", " ").slice(0, 16)}</div>}
                </li>
              ))}
            </ul>
            <p className="border-t border-rule px-5 py-3 font-sans text-[12px] leading-relaxed text-ink-3">
              选中正文里的任意一句，点「记下这段」，你的划线也会出现在这里。
            </p>
          </motion.aside>
        )}
      </AnimatePresence>
    </>,
    document.body
  );
}
