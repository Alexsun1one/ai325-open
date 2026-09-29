"use client";
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { api, token } from "@/lib/api";

/** 公开热区：只有段+人数+用于定位的原文；没有人、没有笔记。 */
interface HeatItem { anchor: string; count: number; quote?: string }
interface MineMark { anchor: string; quote: string }

interface Stroke {
  key: string;
  top: number;
  left: number;
  width: number;
  band: 1 | 3 | 6;
  mine: boolean;
  n: number;
  anchor: string;
  quote: string;
  dot?: boolean;
}

const DENSITY_RATIO = 0.3; // 超过此比例段落被划 → 只显 TOP

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

function bandOf(n: number): 1 | 3 | 6 {
  if (n >= 6) return 6;
  if (n >= 3) return 3;
  return 1;
}

function strokeStyle(band: 1 | 3 | 6, mine: boolean, dark: boolean): CSSProperties {
  const amber = dark ? "#d79a3a" : "#c37a14";
  const color =
    band === 6 ? (dark ? "#eab45a" : amber) :
    band === 3 ? (dark ? "#e0a84a" : amber) :
    amber;
  const opacity = band === 1 ? (dark ? 0.84 : 0.58) : band === 3 ? (dark ? 0.92 : 0.82) : 1;
  const height = band === 1 ? 1.5 : band === 3 ? 2.25 : 3;
  if (mine) {
    return { background: color, opacity, height };
  }
  // 别人的划：虚线描边
  return {
    height,
    opacity,
    backgroundImage: `repeating-linear-gradient(90deg, ${color} 0 5px, transparent 5px 9px)`,
    backgroundSize: "auto 100%",
  };
}

/** 琥珀下划线热区：Range 量句 → 基线描边；一段一线；>30% 只显 TOP。 */
export function Highlights({ date }: { date: string }) {
  const [items, setItems] = useState<HeatItem[] | null>(null);
  const [mine, setMine] = useState<MineMark[]>([]);
  const [strokes, setStrokes] = useState<Stroke[]>([]);
  const [open, setOpen] = useState<{ anchor: string; quote: string; n: number; mine: boolean } | null>(null);
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);
  const [mounted, setMounted] = useState(false);
  const [dark, setDark] = useState(false);
  const reduce = useReducedMotion();
  const tries = useRef(0);

  useEffect(() => { setMounted(true); }, []);
  useEffect(() => {
    const root = document.documentElement;
    const sync = () => setDark(root.getAttribute("data-theme") === "dark");
    sync();
    const mo = new MutationObserver(sync);
    mo.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
    return () => mo.disconnect();
  }, []);

  useEffect(() => {
    let alive = true;
    api<{ items?: HeatItem[]; mine?: MineMark[] }>(`/api/annotations/heatmap?date=${date}`, { auth: !!token() })
      .then((d) => {
        if (!alive) return;
        setItems(d.items ?? []);
        setMine(Array.isArray(d.mine) ? d.mine : []);
      })
      .catch(() => { if (alive) { setItems([]); setMine([]); } });
    return () => { alive = false; };
  }, [date]);

  const measure = useCallback(() => {
    if (!items?.length) { setStrokes([]); return; }
    const mineAnchors = new Set(mine.map((m) => m.anchor));
    const cands = items.map((it) => ({
      anchor: it.anchor,
      quote: it.quote || "",
      n: it.count,
      mine: mineAnchors.has(it.anchor),
      actors: it.count,
    }));

    const allAnchors = document.querySelectorAll("[data-anchor]").length || cands.length;
    const ratio = allAnchors ? cands.length / allAnchors : 0;
    let draw = cands;
    if (ratio > DENSITY_RATIO && allAnchors > 0) {
      const keep = Math.max(1, Math.ceil(allAnchors * DENSITY_RATIO));
      draw = [...cands].sort((a, b) => b.actors - a.actors).slice(0, keep);
    }
    const topSet = new Set(draw.map((c) => c.anchor));

    const out: Stroke[] = [];
    for (const c of cands) {
      if (!topSet.has(c.anchor)) continue;
      const el = document.querySelector<HTMLElement>(`[data-anchor="${CSS.escape(c.anchor)}"]`);
      if (!el) continue;
      const r = c.quote ? rangeOf(el, c.quote) : null;
      const rects = r ? Array.from(r.getClientRects()) : [el.getBoundingClientRect()];
      const b = bandOf(c.n);
      rects.forEach((rect, i) => {
        if (rect.width < 2) return;
        out.push({
          key: `${c.anchor}-${i}`,
          top: rect.bottom + window.scrollY - (b === 1 ? 1.5 : b === 3 ? 2.25 : 3),
          left: rect.left + window.scrollX,
          width: rect.width,
          band: b,
          mine: c.mine,
          n: c.n,
          anchor: c.anchor,
          quote: (c.quote || "").replace(/\s+/g, ""),
        });
      });
    }
    const lastByQuote = new Map<string, number>();
    out.forEach((s, i) => lastByQuote.set(`${s.anchor}||${s.quote}`, i));
    out.forEach((s, i) => { s.dot = Boolean(s.mine && lastByQuote.get(`${s.anchor}||${s.quote}`) === i); });
    setStrokes(out);
  }, [items, mine]);

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

  // 段尾「N 人划过」——counts 已是 unique user，匿名也画
  useEffect(() => {
    if (!items) return;
    const made: HTMLElement[] = [];
    for (const it of items) {
      if (!it.count) continue;
      const el = document.querySelector<HTMLElement>(`[data-anchor="${CSS.escape(it.anchor)}"]`);
      if (!el || el.querySelector("[data-hl-tag]")) continue;
      const tag = document.createElement("span");
      tag.dataset.hlTag = "1";
      tag.className = "ml-2 inline-flex translate-y-[-1px] items-center rounded-[3px] border border-amber-deep/40 bg-amber-wash px-1.5 py-[1px] align-middle font-sans text-[11px] font-semibold text-amber-text";
      tag.textContent = `${it.count} 人划过`;
      el.appendChild(tag);
      made.push(tag);
    }
    return () => { for (const t of made) t.remove(); };
  }, [items]);

  if (!mounted || !strokes.length) return null;

  const openQuote = open
    ? (items ?? []).find((it) => it.anchor === open.anchor)?.quote || open.quote
    : "";

  return createPortal(
    <>
      <div aria-hidden className="no-print pointer-events-none absolute left-0 top-0 z-[5]">
        {strokes.map((s) => (
          <button
            key={s.key}
            type="button"
            onMouseEnter={(e) => {
              setTip({ x: e.clientX + 8, y: e.clientY - 36, text: s.mine ? `${s.n} 人划过 · 你划过` : `${s.n} 人划过` });
            }}
            onFocus={(e) => {
              const r = e.currentTarget.getBoundingClientRect();
              setTip({ x: r.left, y: Math.max(8, r.top - 28), text: s.mine ? `${s.n} 人划过 · 你划过` : `${s.n} 人划过` });
            }}
            onBlur={() => setTip(null)}
            onMouseMove={(e) => setTip((t) => t ? { ...t, x: e.clientX + 8, y: Math.max(8, e.clientY - 36) } : t)}
            onMouseLeave={() => setTip(null)}
            onClick={() => setOpen({ anchor: s.anchor, quote: s.quote, n: s.n, mine: s.mine })}
            aria-label={`${s.n} 人划过这一句`}
            className="pointer-events-auto absolute cursor-pointer rounded-full"
            style={{
              top: s.top, left: s.left, width: s.width,
              ...strokeStyle(s.band, s.mine, dark),
            }}
          />
        ))}
        {strokes.filter((s) => s.dot).map((s) => (
          <span
            key={`${s.key}-dot`}
            aria-hidden
            className="absolute rounded-full"
            style={{
              top: s.top + (s.band === 1 ? 1.5 : s.band === 3 ? 2.25 : 3) / 2 - 2.5,
              left: s.left + s.width - 2,
              width: 5,
              height: 5,
              background: dark ? "#d79a3a" : "#c37a14",
            }}
          />
        ))}
      </div>

      {tip && (
        <div
          role="tooltip"
          className="no-print pointer-events-none fixed z-[60] rounded-md border border-rule bg-paper px-2.5 py-1 font-sans text-[12px] font-semibold text-ink shadow-[var(--shadow-pop)]"
          style={{ left: Math.min(tip.x, window.innerWidth - 160), top: tip.y }}
        >
          {tip.text}
        </div>
      )}

      <AnimatePresence>
        {open && (
          <motion.aside
            data-notebook
            initial={reduce ? false : { x: 24, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={reduce ? { opacity: 0 } : { x: 24, opacity: 0 }}
            transition={reduce ? { duration: 0 } : { duration: 0.26, ease: [0.16, 1, 0.3, 1] }}
            className="no-print fixed bottom-0 right-0 top-[var(--nav-h)] z-40 flex w-full max-w-[400px] flex-col border-l border-rule bg-paper shadow-[var(--shadow-pop)]"
            role="dialog" aria-label="这段被划过">
            <div className="flex items-start justify-between gap-3 border-b border-rule px-5 py-3">
              <div>
                <div className="font-serif text-[16px] font-bold text-ink">这段被划过</div>
                <div className="num font-sans text-[12px] text-ink-3">{open.n} 人划过{open.mine ? " · 你划过" : ""}</div>
              </div>
              <button type="button" onClick={() => setOpen(null)} className="rounded-md px-2 py-1 text-ink-3 hover:text-ink" aria-label="关闭">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M6 6l12 12M18 6L6 18" /></svg>
              </button>
            </div>
            {openQuote ? (
              <blockquote className="prose-sheet mx-5 mt-4 border-l-2 border-amber pl-3 text-[14.5px] leading-[1.75] text-ink-2">{openQuote}</blockquote>
            ) : null}
            <p className="mt-auto border-t border-rule px-5 py-3 font-sans text-[12px] leading-relaxed text-ink-3">
              选中正文里的任意一句，点「记下这段」，你的划线也会出现在这里。划线人只计人数，不公开是谁。
            </p>
          </motion.aside>
        )}
      </AnimatePresence>
    </>,
    document.body
  );
}
