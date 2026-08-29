"use client";
import { useEffect, useState } from "react";
import type { Glossary } from "@/lib/shared";

/** 黑话悬停释义：监听正文里的 dfn[data-term]，就地弹出词典释义。 */
export function TermHover({ glossary }: { glossary: Glossary[] }) {
  const [pop, setPop] = useState<{ x: number; y: number; term: string; def: string; below: boolean } | null>(null);
  useEffect(() => {
    const map = new Map(glossary.map((g) => [g.term, g.def]));
    let hideT: number | undefined;
    const show = (el: HTMLElement) => {
      const term = el.dataset.term || ""; const def = map.get(term); if (!def) return;
      const r = el.getBoundingClientRect();
      const below = r.top < 160;
      setPop({ x: Math.min(Math.max(r.left + r.width / 2, 150), window.innerWidth - 150), y: below ? r.bottom + 8 : r.top - 8, term, def, below });
    };
    const over = (e: Event) => { const t = (e.target as HTMLElement).closest?.("dfn[data-term]") as HTMLElement | null; if (t) { window.clearTimeout(hideT); show(t); } };
    const out = (e: Event) => { const t = (e.target as HTMLElement).closest?.("dfn[data-term]"); if (t) hideT = window.setTimeout(() => setPop(null), 120); };
    const click = (e: Event) => { const t = (e.target as HTMLElement).closest?.("dfn[data-term]") as HTMLElement | null; if (t) { e.preventDefault(); show(t); } else setPop(null); };
    document.addEventListener("mouseover", over); document.addEventListener("mouseout", out); document.addEventListener("click", click);
    document.querySelectorAll<HTMLElement>("dfn[data-term]").forEach((el) => { el.tabIndex = 0; el.setAttribute("role", "button"); el.setAttribute("aria-label", `黑话：${el.dataset.term}`); });
    const onKey = (e: KeyboardEvent) => { const t = e.target as HTMLElement; if (t?.dataset?.term && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); show(t); } else if (e.key === "Escape") setPop(null); };
    document.addEventListener("keydown", onKey);
    const onScroll = () => setPop(null); window.addEventListener("scroll", onScroll, { passive: true });
    return () => { document.removeEventListener("keydown", onKey); document.removeEventListener("mouseover", over); document.removeEventListener("mouseout", out); document.removeEventListener("click", click); window.removeEventListener("scroll", onScroll); };
  }, [glossary]);
  if (!pop) return null;
  return (
    <div role="tooltip" className="note-pop pointer-events-none fixed z-50 w-[300px] rounded-[10px] border border-rule bg-paper px-4 py-3" style={{ left: pop.x, top: pop.y, transform: `translate(-50%, ${pop.below ? "0" : "-100%"})` }}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-serif text-[15px] font-bold text-ink">{pop.term.replace(/(?:\s|→|💡|😄|🔥)+$/u, "")}</span>
        <span className="label">黑话词典</span>
      </div>
      <p className="prose-sheet mt-1 text-[14px] leading-[1.75] text-ink-2" dangerouslySetInnerHTML={{ __html: pop.def }} />
    </div>
  );
}
