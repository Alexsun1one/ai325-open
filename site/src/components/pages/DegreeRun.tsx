"use client";
import { useRef } from "react";
import { motion, useInView, useReducedMotion } from "motion/react";
import { pad3 } from "@/lib/shared";

export interface DegreePoint { issue: number; date: string; overall: number; grade: string }

const W = 920, H = 300, PAD_L = 40, PAD_R = 16, PAD_T = 20, PAD_B = 44;
const BANDS = [
  { from: 80, to: 100, grade: "A", label: "A 级 · 80 度以上" },
  { from: 60, to: 80, grade: "B", label: "B 级 · 60–79 度" },
  { from: 40, to: 60, grade: "C", label: "C 级 · 40–59 度" },
];

/** 逐批度数：一批一个点。只有一批时不假装成曲线——照实画点，右边留出未来批次的空位。 */
export function DegreeRun({ points, ghost = 5 }: { points: DegreePoint[]; ghost?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });
  const reduce = useReducedMotion();
  const slots = points.length + ghost;
  const step = (W - PAD_L - PAD_R) / slots;
  const x = (i: number) => PAD_L + step * (i + 0.5);
  const y = (v: number) => PAD_T + (H - PAD_T - PAD_B) * (1 - v / 100);
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.overall)}`).join(" ");
  const last = points[points.length - 1];

  return (
    <div ref={ref}>
      <div className="rounded-[10px] border border-rule bg-paper/70 p-2 sm:p-3">
        <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={`逐批度数：已出 ${points.length} 批，最新第 ${pad3(last.issue)} 批 ${last.overall} 度`}>
          {/* 等级带 */}
          {BANDS.map((b) => (
            <g key={b.grade}>
              <rect x={PAD_L} y={y(b.to)} width={W - PAD_L - PAD_R} height={y(b.from) - y(b.to)} fill="var(--blue-wash)" opacity={b.grade === "B" ? 0.5 : 0.22} />
              <text x={W - PAD_R - 6} y={y(b.to) + 14} textAnchor="end" fontFamily="var(--font-sans)" fontSize="10.5" fontWeight="600" fill="var(--blue-text)" opacity="0.85">{b.label}</text>
            </g>
          ))}
          {[0, 20, 40, 60, 80, 100].map((v) => (
            <g key={v}>
              <line x1={PAD_L} x2={W - PAD_R} y1={y(v)} y2={y(v)} stroke="var(--rule-soft)" strokeWidth="1" />
              <text x={PAD_L - 8} y={y(v) + 4} textAnchor="end" fontFamily="var(--font-sans)" fontSize="10" fill="var(--ink-3)" className="num">{v}</text>
            </g>
          ))}
          {/* 已出批次的线（一个点时无线可画） */}
          {points.length > 1 && (
            <motion.path d={path} fill="none" stroke="var(--amber)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
              initial={reduce ? false : { pathLength: 0 }} animate={inView ? { pathLength: 1 } : undefined} transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }} />
          )}
          {/* 向未来延伸的虚线：明说「还没有」 */}
          <line x1={x(points.length - 1)} x2={x(points.length)} y1={y(last.overall)} y2={y(last.overall)} stroke="var(--amber-deep)" strokeWidth="1.2" strokeDasharray="4 5" opacity="0.55" />
          {/* 点 */}
          {points.map((p, i) => (
            <g key={p.issue}>
              <motion.circle cx={x(i)} cy={y(p.overall)} r="7" fill="var(--amber)" stroke="var(--amber-deep)" strokeWidth="2"
                initial={reduce ? false : { scale: 0, opacity: 0 }} animate={inView ? { scale: 1, opacity: 1 } : undefined} transition={{ delay: 0.25 + i * 0.1, duration: 0.45, ease: [0.16, 1, 0.3, 1] }} style={{ transformOrigin: `${x(i)}px ${y(p.overall)}px` }} />
              <text x={x(i)} y={y(p.overall) - 16} textAnchor="middle" fontFamily="var(--font-sans)" fontSize="14" fontWeight="700" fill="var(--amber-text)" className="num">{p.overall}°</text>
            </g>
          ))}
          {/* 横轴：真实批次 + 未来空位 */}
          {Array.from({ length: slots }, (_, i) => {
            const real = i < points.length;
            const n = real ? points[i].issue : points[points.length - 1].issue + (i - points.length + 1);
            return (
              <g key={i}>
                {!real && <circle cx={x(i)} cy={y(last.overall)} r="4.5" fill="none" stroke="var(--rule)" strokeWidth="1" strokeDasharray="2.5 2.5" />}
                <text x={x(i)} y={H - 22} textAnchor="middle" fontFamily="var(--font-sans)" fontSize="11.5" fontWeight={real ? 700 : 400} fill={real ? "var(--blue-text)" : "var(--ink-3)"} className="num" opacity={real ? 1 : 0.6}>{pad3(n)}</text>
                {real && <text x={x(i)} y={H - 8} textAnchor="middle" fontFamily="var(--font-sans)" fontSize="10" fill="var(--ink-3)" className="num">{points[i].date.slice(5)}</text>}
              </g>
            );
          })}
          <line x1={PAD_L} x2={W - PAD_R} y1={y(0)} y2={y(0)} stroke="var(--rule)" strokeWidth="1" />
        </svg>
      </div>
    </div>
  );
}
