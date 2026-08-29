"use client";
import { useRef, useState } from "react";
import { motion, useInView, useReducedMotion } from "motion/react";
import type { Dimension } from "@/lib/shared";

const EASE: [number, number, number, number] = [0.16, 1, 0.3, 1];

/** 五维打分：每行 10 格，按分数注入琥珀；右侧度数。悬停/点按看证据。 */
export function ScoreGrid({ dims, overall, grade, basis }: { dims: Dimension[]; overall: number; grade: string; basis: string }) {
  const [active, setActive] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  const reduce = useReducedMotion();
  return (
    <div ref={ref} className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_260px] lg:gap-10">
      <div>
        <div className="divide-y divide-rule-soft border-y border-rule">
          {dims.map((d, r) => {
            const cells = Array.from({ length: 10 }, (_, c) => Math.max(0, Math.min(1, d.score / 10 - c)));
            const on = active === r;
            return (
              <button
                key={d.name}
                type="button"
                onMouseEnter={() => setActive(r)}
                onFocus={() => setActive(r)}
                onClick={() => setActive(r)}
                aria-pressed={on}
                className={`grid w-full grid-cols-[80px_minmax(0,1fr)_58px] items-center gap-4 border-l-2 py-3 pl-2 pr-2 text-left transition-colors duration-200 ease-[var(--ease-out-expo)] sm:grid-cols-[96px_minmax(0,1fr)_72px] ${on ? "border-l-amber bg-paper-2/55" : "border-l-transparent hover:bg-paper-2/35"}`}
              >
                <span className={`font-sans text-[13.5px] font-semibold transition-colors duration-200 ${on ? "text-ink" : "text-ink-2"}`}>{d.name}</span>
                <span className="flex gap-[5px]" aria-hidden>
                  {cells.map((f, c) => (
                    <span key={c} className="relative h-[18px] flex-1 overflow-hidden rounded-[3px] border border-rule-soft bg-paper">
                      <motion.span
                        className="absolute inset-y-0 left-0 bg-amber"
                        initial={reduce ? { width: `${f * 100}%` } : { width: 0 }}
                        animate={inView ? { width: `${f * 100}%` } : undefined}
                        transition={{ duration: reduce ? 0 : 0.5, delay: reduce ? 0 : 0.08 + r * 0.07 + c * 0.028, ease: EASE }}
                      />
                    </span>
                  ))}
                </span>
                {/* 分数与等级分两格，数字永远靠同一条右边线对齐 */}
                <span className="flex items-baseline justify-end gap-1.5">
                  <span className="num font-sans text-[15px] font-semibold text-ink">{d.score}</span>
                  <span className="w-[9px] shrink-0 text-left font-sans text-[12px] font-medium text-ink-3">{d.grade}</span>
                </span>
              </button>
            );
          })}
        </div>
        <div className="mt-4 min-h-[72px] font-sans text-[14px] leading-relaxed text-ink-2" aria-live="polite">
          <span className="mr-2 font-semibold text-ink">{dims[active]?.name}</span>{dims[active]?.detail}
        </div>
      </div>
      <div className="order-first flex flex-col justify-between border-b border-rule pb-6 lg:order-none lg:border-b-0 lg:border-l lg:pb-0 lg:pl-8">
        <div>
          <div className="label">本批度数</div>
          <div className="mt-2 flex items-start gap-1.5 sm:gap-2">
            <span className="num text-[64px] font-semibold leading-none tracking-[-0.02em] text-amber-text sm:text-[88px]">{overall}</span>
            <span className="num mt-0.5 text-[30px] font-semibold leading-none text-amber-text sm:mt-1 sm:text-[40px]">°</span>
          </div>
          <div className="mt-3 inline-flex items-center gap-2 rounded-[4px] border border-blue bg-blue-wash px-2.5 py-1 font-sans text-[13px] font-semibold text-blue-text">
            <span className="num">{grade}</span> 级
          </div>
        </div>
        <p className="mt-6 font-sans text-[12.5px] leading-relaxed text-ink-3">{basis}（按评分当时的统计 · <a href="#caliber" className="text-blue-text">怎么数的</a>）。度数是给这一锅内容打的，不是给人打的：五维取平均，A≥80 · B≥60 · C≥40。</p>
      </div>
    </div>
  );
}
