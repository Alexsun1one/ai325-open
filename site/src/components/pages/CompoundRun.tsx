"use client";
import { useRef } from "react";
import { motion, useInView, useReducedMotion } from "motion/react";
import { fmtInt, pad3 } from "@/lib/shared";

export interface Series { k: string; unit: string; note: string; cum: number[] }

const W = 260, H = 74, PAD_X = 10, PAD_T = 12, PAD_B = 16;

/** 一格累积曲线：琥珀线 draw-in、点依次亮起、未来批次留虚线空位。 */
function Spark({ cum, ghost, delay }: { cum: number[]; ghost: number; delay: number }) {
  const reduce = useReducedMotion();
  const slots = cum.length + ghost;
  const step = (W - PAD_X * 2) / slots;
  const x = (i: number) => PAD_X + step * (i + 0.5);
  const max = Math.max(...cum, 1);
  const y = (v: number) => PAD_T + (H - PAD_T - PAD_B) * (1 - v / max);
  const d = cum.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
  const last = cum.length - 1;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mt-3 block h-auto w-full" aria-hidden>
      <line x1={PAD_X} x2={W - PAD_X} y1={y(0)} y2={y(0)} stroke="var(--rule-soft)" strokeWidth="1" />
      {/* 已出批次：累积只增不减，所以线永远向上 */}
      {cum.length > 1 && (
        <motion.path d={d} fill="none" stroke="var(--amber)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
          initial={reduce ? false : { pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1, delay: delay + 0.1, ease: [0.16, 1, 0.3, 1] }} />
      )}
      {/* 往未来延伸：还没有的东西用虚线，不假装 */}
      <line x1={x(last)} x2={x(last + 1)} y1={y(cum[last])} y2={y(cum[last])} stroke="var(--amber-deep)" strokeWidth="1" strokeDasharray="3 4" opacity="0.5" />
      {cum.map((v, i) => (
        <motion.circle key={i} cx={x(i)} cy={y(v)} r="4" fill="var(--amber)" stroke="var(--amber-deep)" strokeWidth="1.6"
          initial={reduce ? false : { scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
          transition={{ delay: delay + 0.2 + i * 0.12, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          style={{ transformOrigin: `${x(i)}px ${y(v)}px` }} />
      ))}
      {Array.from({ length: ghost }, (_, i) => (
        <circle key={`g${i}`} cx={x(cum.length + i)} cy={y(cum[last])} r="3.2" fill="none" stroke="var(--rule)" strokeWidth="1" strokeDasharray="2 2.5" />
      ))}
    </svg>
  );
}

function Row({ s, ghost, i, issues }: { s: Series; ghost: number; i: number; issues: number[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  return (
    <div ref={ref} className="relative border-b border-r border-rule px-4 pb-3 pt-3 transition-colors hover:bg-paper-2/60">
      <div className="label">{s.k}</div>
      <div className="mt-2 flex items-baseline gap-1.5">
        <span className="num text-[32px] font-semibold leading-none text-ink">{fmtInt(s.cum[s.cum.length - 1])}</span>
        <span className="num text-[14px] font-medium text-ink-3">{s.unit}</span>
      </div>
      <div className="mt-1 font-sans text-[11.5px] leading-snug text-ink-3">{s.note}</div>
      {inView ? <Spark cum={s.cum} ghost={ghost} delay={i * 0.12} /> : <div style={{ height: 0 }} className="mt-3 aspect-[260/74] w-full" />}
      <div className="num mt-0.5 flex justify-between font-sans text-[10px] text-ink-3/70">
        <span>{pad3(issues[0])}</span>
        <span>{pad3(issues[issues.length - 1] + ghost)}</span>
      </div>
    </div>
  );
}

/** 复利：四条累积线并排。每一锅不是独立的，是往同一个缸里添。 */
export function CompoundRun({ series, issues, ghost = 5 }: { series: Series[]; issues: number[]; ghost?: number }) {
  return (
    <div className="grid grid-cols-1 border-l border-t border-rule sm:grid-cols-2 lg:grid-cols-4">
      {series.map((s, i) => <Row key={s.k} s={s} ghost={ghost} i={i} issues={issues} />)}
    </div>
  );
}
