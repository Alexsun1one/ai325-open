"use client";
import { useState } from "react";
import { Prose } from "@/components/pages/Prose";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import type { Theme, Thread } from "@/lib/shared";
import { pad3 } from "@/lib/shared";
import { LensPlate } from "./LensPlate";

const EASE = [0.16, 1, 0.3, 1] as const;

function ThreadChip({ t, issue }: { t: Thread; issue: number }) {
  return (
    <a
      href={`/archive/#thread-${t.id}`}
      className="group/chip inline-flex items-center gap-1.5 rounded-full border border-blue-wash-2 bg-blue-wash px-2.5 py-1 font-sans text-[12px] font-medium text-blue-text no-underline transition-colors duration-200 ease-[var(--ease-out-expo)] hover:border-blue-2 hover:bg-blue-wash-2 active:bg-blue-wash-2"
    >
      <svg
        width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden
        className="shrink-0 transition-transform duration-200 ease-[var(--ease-out-expo)] group-hover/chip:translate-x-[2px] motion-reduce:transition-none motion-reduce:group-hover/chip:translate-x-0"
      >
        <path d="M4 12h16M14 6l6 6-6 6" />
      </svg>
      线索 · {t.title} · 首蒸于第 {pad3(issue)} 批
    </a>
  );
}

/** 幕标题：「第二幕」用蓝色小字、正名用宋体大字，同一行。 */
function ActTitle({ h }: { h: string }) {
  const m = h.match(/^(第[一二三四五六七八九十\d]+幕)\s*[·•]\s*(.+)$/);
  if (!m) return <>{h}</>;
  return (
    <>
      <span className="mr-3 inline-block translate-y-[-3px] font-sans text-[12.5px] font-semibold tracking-[0.14em] text-blue-text">{m[1]}</span>
      {m[2]}
    </>
  );
}

function DeepDive({ html }: { html: string }) {
  const [open, setOpen] = useState(true);
  const reduce = useReducedMotion();
  return (
    <div className="mt-6 border-l border-amber-deep/60 pl-5 sm:pl-6">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="group/dd -mx-1.5 inline-flex items-center gap-2 rounded-[5px] px-1.5 py-1 text-left transition-colors duration-200 ease-[var(--ease-out-expo)] hover:bg-amber-wash/70 active:bg-amber-wash"
      >
        <span className="label">深潜 · 没说破的</span>
        <span className="font-sans text-[12px] text-ink-3 transition-colors duration-200 ease-[var(--ease-out-expo)] group-hover/dd:text-ink-2">{open ? "收起" : "展开"}</span>
        <svg
          width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden
          className={`shrink-0 text-ink-3 transition-transform duration-300 ease-[var(--ease-out-expo)] group-hover/dd:text-ink-2 motion-reduce:transition-none ${open ? "" : "-rotate-90"}`}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="d"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: reduce ? 0 : 0.32, ease: EASE }}
            className="overflow-hidden"
          >
            <Prose html={html} className="hand mt-2 max-w-[38em] text-[18px] leading-[1.9]" />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** 品评项：每一幕 = 幕名 + 时段 + 线索 + 重织正文 + 手写深潜 + 逐字原声。 */
export function Themes({ themes, threads, issue, illus = [] }: { themes: Theme[]; threads: Thread[]; issue: number; illus?: (string | null)[] }) {
  return (
    <div className="space-y-16">
      {themes.map((t, i) => {
        const th = threads.find((x) => x.theme === t.h);
        return (
          <article key={i} id={`theme-${i + 1}`} className="scroll-mt-24">
            {illus[i] && (
              <figure className="mb-7 overflow-hidden border-y border-rule bg-paper-2 sm:mb-8">
                <LensPlate src={illus[i]!} />
              </figure>
            )}
            {/* 窄屏时段落到标题下一行、仍靠左起排；宽屏与标题同基线、贴右栏边 */}
            <header className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1.5">
              <h3 className="min-w-0 font-serif text-[24px] font-bold leading-[1.35] text-ink sm:text-[26px]"><ActTitle h={t.h} /></h3>
              <span className="num shrink-0 font-sans text-[12.5px] font-medium tracking-[0.04em] text-blue-text">{t.when}</span>
            </header>
            {th && <div className="mt-3">{<ThreadChip t={th} issue={issue} />}</div>}
            <Prose html={t.body} dropcap className="mt-4 text-[17px] leading-[1.9]" />
            <DeepDive html={t.deep} />
            {t.voices.length > 0 && (
              <ul className="mt-6 space-y-2.5 border-l border-rule pl-5 sm:pl-6">
                {t.voices.map((v, j) => (
                  <li key={j} className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
                    <span data-person={v.a} className="shrink-0 font-sans text-[13px] font-semibold text-blue-text">{v.a}</span>
                    {/* 「」压紧 0.18em：CJK 引号自带侧边空隙，不压就会与人名、正文各拉开一个空格 */}
                    <p className="prose-sheet min-w-0 flex-1 text-[16px] leading-[1.8] text-ink-2">
                      <span className="-mr-[0.18em] text-ink-3">「</span>
                      <span dangerouslySetInnerHTML={{ __html: v.v }} />
                      <span className="-ml-[0.18em] text-ink-3">」</span>
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </article>
        );
      })}
    </div>
  );
}
