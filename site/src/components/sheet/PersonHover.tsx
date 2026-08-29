"use client";
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ToneTag } from "./ToneTag";
import type { Tone } from "@/lib/shared";

export interface Person { name: string; slug: string; aliases: string[]; role: string; msgs: number; tone: Tone; quote: string; tags: string[]; avatar: string | null }
let cache: Person[] | null = null; let inflight: Promise<Person[]> | null = null;
export function loadPeople(): Promise<Person[]> {
  if (cache) return Promise.resolve(cache);
  if (!inflight) inflight = fetch("/people.json").then((r) => r.json()).then((d: Person[]) => (cache = d)).catch(() => (cache = []));
  return inflight;
}

/** 人名章：正文里 [data-person] 悬停出名片（头像 / 角色 / 条数 / 语气 / 一句话），点进群像。 */
export function PersonHover() {
  const reduce = useReducedMotion();
  const [pop, setPop] = useState<{ p: Person; x: number; y: number; below: boolean } | null>(null);
  const hide = useRef<number | undefined>(undefined);
  useEffect(() => {
    const show = async (el: HTMLElement) => {
      const name = el.dataset.person; if (!name) return;
      const people = await loadPeople(); const p = people.find((x) => x.name === name); if (!p) return;
      const r = el.getBoundingClientRect(); const below = r.top < 200;
      setPop({ p, x: Math.min(Math.max(r.left + r.width / 2, 170), window.innerWidth - 170), y: below ? r.bottom + 10 : r.top - 10, below });
    };
    const over = (e: Event) => { const t = (e.target as HTMLElement).closest?.("[data-person]") as HTMLElement | null; if (t) { window.clearTimeout(hide.current); show(t); } };
    const out = (e: Event) => { if ((e.target as HTMLElement).closest?.("[data-person]")) hide.current = window.setTimeout(() => setPop(null), 180); };
    const click = (e: Event) => { const t = (e.target as HTMLElement).closest?.("[data-person]") as HTMLElement | null; if (t) { e.preventDefault(); show(t); } else if (!(e.target as HTMLElement).closest?.("[data-personcard]")) setPop(null); };
    const onScroll = () => setPop(null);
    // 键盘可达：人名章可聚焦，Enter/Space 打开名片
    document.querySelectorAll<HTMLElement>("[data-person]").forEach((el) => { if (!el.hasAttribute("tabindex")) { el.tabIndex = 0; el.setAttribute("role", "button"); el.setAttribute("aria-label", `${el.dataset.person} 的名片`); } });
    const onKey = (e: KeyboardEvent) => { const t = (e.target as HTMLElement); if (t?.dataset?.person && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); show(t); } else if (e.key === "Escape") setPop(null); };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mouseover", over); document.addEventListener("mouseout", out); document.addEventListener("click", click); window.addEventListener("scroll", onScroll, { passive: true });
    return () => { document.removeEventListener("keydown", onKey); document.removeEventListener("mouseover", over); document.removeEventListener("mouseout", out); document.removeEventListener("click", click); window.removeEventListener("scroll", onScroll); };
  }, []);
  return (
    <AnimatePresence>
      {pop && (
        <motion.div key={pop.p.slug} data-personcard role="tooltip" aria-label={`${pop.p.name} 名片`}
          initial={reduce ? false : { opacity: 0, y: pop.below ? -4 : 4, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={reduce ? { opacity: 0 } : { opacity: 0, y: pop.below ? -4 : 4 }} transition={reduce ? { duration: 0 } : { duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          onMouseEnter={() => window.clearTimeout(hide.current)} onMouseLeave={() => { hide.current = window.setTimeout(() => setPop(null), 160); }}
          className="note-pop fixed z-50 w-[340px] rounded-[12px] border border-rule bg-paper px-4 py-3.5" style={{ left: pop.x, top: pop.y, transform: `translate(-50%, ${pop.below ? "0" : "-100%"})` }}>
          <div className="flex items-start gap-3">
            {pop.p.avatar ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={pop.p.avatar} alt="" width={44} height={44} className="h-11 w-11 shrink-0 rounded-full border border-rule object-cover" />
            ) : (
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-blue bg-blue-wash font-serif text-[17px] font-bold text-blue-text">{pop.p.name.slice(0, 1)}</span>
            )}
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate font-serif text-[16px] font-bold text-ink">{pop.p.name}</span>
                <span className="num shrink-0 font-sans text-[11.5px] text-ink-3">{pop.p.msgs} 条</span>
              </div>
              <div className="mt-0.5 truncate font-sans text-[12px] text-blue-text">{pop.p.role}</div>
            </div>
          </div>
          {pop.p.quote && <p className="prose-sheet mt-2.5 text-[13.5px] leading-[1.7] text-ink-2">「{pop.p.quote}」 <ToneTag g={pop.p.tone} /></p>}
          <div className="mt-2.5 flex items-center justify-between">
            <div className="flex flex-wrap gap-1">{pop.p.tags.slice(0, 3).map((t) => <span key={t} className="rounded-[3px] bg-blue-wash px-1.5 py-[2px] font-sans text-[10.5px] text-blue-text">{t}</span>)}</div>
            <a href={`/members/#p-${pop.p.slug}`} className="font-sans text-[12px] font-medium text-blue-text no-underline hover:underline">群像全貌 →</a>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** 署名处用：把人名渲染成可悬停的人名章。 */
export function PersonName({ name, className = "" }: { name: string; className?: string }) {
  return <span data-person={name} className={className}>{name}</span>;
}
