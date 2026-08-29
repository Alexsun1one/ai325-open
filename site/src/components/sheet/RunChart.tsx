"use client";
import { useMemo, useRef, useState } from "react";
import { motion, useInView, useReducedMotion } from "motion/react";
import { computeCuts, hh } from "@/lib/cuts";
import type { Event } from "@/lib/shared";
import { fmtInt } from "@/lib/shared";
import { ScrollHint } from "@/components/pages/PageHead";

const W = 960, H = 320, PAD_L = 42, PAD_R = 12, PAD_T = 76, PAD_B = 36;
const EASE: [number, number, number, number] = [0.16, 1, 0.3, 1];

function eventHour(t: string): number | null {
  const m = t.match(/(\d{2}):(\d{2})/);
  return m ? parseInt(m[1], 10) : null;
}

/** 漂亮刻度：找一个 1/2/2.5/5 × 10^n 的整步长，让顶格是整数、格数 ≤6。 */
function niceScale(max: number): { top: number; ticks: number[] } {
  const mag = Math.pow(10, Math.floor(Math.log10(Math.max(max, 1))));
  let step = mag;
  for (const m of [0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10]) {
    const s = m * mag;
    if (s < 1) continue;
    if (Math.ceil(max / s) <= 6) { step = s; break; }
  }
  const top = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let v = step; v <= top + step * 1e-6; v += step) ticks.push(Math.round(v));
  return { top, ticks };
}

/** 24 小时蒸馏曲线：琥珀柱；酒头 / 酒心 / 酒尾 三段括号；悬停看该小时发生了什么。 */
export function RunChart({ hours, events, caption }: { hours: Record<string, number>; events: Event[]; caption?: string }) {
  const cuts = useMemo(() => computeCuts(hours), [hours]);
  const [hover, setHover] = useState<number | null>(null);
  const [kb, setKb] = useState<number | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });
  const reduce = useReducedMotion();
  const max = Math.max(...cuts.hours.map((x) => x.n), 1);
  const { top: yTop, ticks } = useMemo(() => niceScale(max), [max]);
  const bw = (W - PAD_L - PAD_R) / 24;
  const y = (n: number) => PAD_T + (H - PAD_T - PAD_B) * (1 - n / yTop);
  const byHour = useMemo(() => {
    const m = new Map<number, Event[]>();
    for (const e of events) { const h = eventHour(e.t); if (h == null) continue; m.set(h, [...(m.get(h) ?? []), e]); }
    return m;
  }, [events]);
  const segs = [
    { key: "head", label: "酒头", ...cuts.head },
    { key: "heart", label: "酒心", ...cuts.heart },
    { key: "tail", label: "酒尾", ...cuts.tail },
  ];
  const active = hover != null ? cuts.hours[hover] : null;
  const activeSeg = active ? segs.find((s) => active.h >= s.from && active.h <= s.to) : null;
  const activeList = active ? byHour.get(active.h) ?? [] : [];
  const activePct = active && cuts.total ? Math.round((active.n / cuts.total) * 100) : 0;

  /* 整个 svg 一次 hit-test：按 x 反算小时。指针与手指走同一条路，不再靠 24 个透明 rect。 */
  const pick = (clientX: number) => {
    const el = svgRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    if (!r.width) return;
    const i = Math.floor((((clientX - r.left) / r.width) * W - PAD_L) / bw);
    setHover(i >= 0 && i < 24 ? i : kb);
  };

  return (
    <div ref={ref} className="relative">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div>
          <div className="font-sans text-[14px] font-semibold text-ink">24 小时消息心跳 · 北京时间</div>
          <div className="mt-1 font-sans text-[12.5px] leading-relaxed text-ink-3">柱高 = 该小时消息量；括号是蒸馏的三段切分。峰值 <span className="num font-semibold text-amber-text">{hh(cuts.peak.h)} 时 · {fmtInt(cuts.peak.n)} 条</span>。曲线按有时间戳的 {fmtInt(cuts.total)} 条算 · <a href="#caliber" className="text-blue-text">怎么数的</a></div>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 font-sans text-[12px] text-ink-3">
          <span className="inline-flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[2px] bg-amber" />酒心</span>
          <span className="inline-flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[2px] bg-amber-wash-2" />酒头 / 酒尾</span>
          <span className="inline-flex items-center gap-1.5"><i className="inline-block h-[5px] w-[5px] rounded-full bg-blue-2" />有大事记</span>
        </div>
      </div>

      <div className="relative mt-4 border-y border-rule py-2 sm:py-3">
        <ScrollHint>心跳图较宽，可左右滑动</ScrollHint>
        <div className="overflow-x-auto">
          <svg
            ref={svgRef}
            viewBox={`0 0 ${W} ${H}`}
            className="block h-auto w-full min-w-[720px] sm:min-w-0"
            role="group"
            aria-label={`24 小时消息量柱状图，峰值 ${hh(cuts.peak.h)} 时 ${cuts.peak.n} 条`}
            onPointerMove={(e) => pick(e.clientX)}
            onPointerDown={(e) => pick(e.clientX)}
            onPointerLeave={() => setHover(kb)}
            onPointerCancel={() => setHover(kb)}
          >
            {/* 横向刻度线 */}
            {ticks.map((v) => (
              <g key={v}>
                <line x1={PAD_L} x2={W - PAD_R} y1={y(v)} y2={y(v)} stroke="var(--rule-soft)" strokeWidth="1" />
                <text x={PAD_L - 9} y={y(v) + 3.5} textAnchor="end" fontFamily="var(--font-sans)" fontSize="11" fill="var(--ink-3)" className="num">{fmtInt(v)}</text>
              </g>
            ))}

            {/* 三段括号：左右沿与首末柱的柱身严格对齐 */}
            {segs.map((s) => {
              const x1 = PAD_L + s.from * bw + 3, x2 = PAD_L + (s.to + 1) * bw - 3;
              const share = cuts.total ? Math.round((s.n / cuts.total) * 100) : 0;
              const heart = s.key === "heart";
              return (
                <g key={s.key}>
                  <path d={`M${x1},42 v6 H${x2} v-6`} fill="none" stroke={heart ? "var(--amber-deep)" : "var(--blue-2)"} strokeWidth={heart ? 1.6 : 1} opacity={heart ? 1 : 0.75} />
                  <text x={(x1 + x2) / 2} y={20} textAnchor="middle" fontFamily="var(--font-sans)" fontSize="12.5" fontWeight="700" fill={heart ? "var(--amber-text)" : "var(--blue-text)"} letterSpacing="1.2">
                    {s.label} {hh(s.from)}–{hh(s.to)} 时
                  </text>
                  <text x={(x1 + x2) / 2} y={35} textAnchor="middle" fontFamily="var(--font-sans)" fontSize="11" fontWeight="500" fill={heart ? "var(--amber-text)" : "var(--ink-3)"} className="num">
                    {fmtInt(s.n)} 条 · {share}%
                  </text>
                </g>
              );
            })}

            {/* 悬停指示线：一条细蓝竖线压在当前柱中心 */}
            {active && (
              <line
                x1={PAD_L + active.h * bw + bw / 2} x2={PAD_L + active.h * bw + bw / 2}
                y1={PAD_T - 20} y2={y(0)}
                stroke="var(--blue-2)" strokeWidth="1" opacity="0.38"
              />
            )}

            {/* 柱 */}
            {cuts.hours.map((x, i) => {
              const inHeart = i >= cuts.heart.from && i <= cuts.heart.to;
              const bx = PAD_L + i * bw + 3, bwid = bw - 6;
              const top = y(x.n), base = y(0);
              const has = byHour.has(i);
              const isHover = hover === i;
              return (
                <g
                  key={i}
                  tabIndex={0}
                  aria-label={`${hh(i)} 时 ${x.n} 条`}
                  onFocus={() => { setKb(i); setHover(i); }}
                  onBlur={() => { setKb(null); setHover(null); }}
                  className="cursor-default outline-none"
                >
                  {kb === i && (
                    <rect x={PAD_L + i * bw + 0.75} y={PAD_T - 20} width={bw - 1.5} height={H - PAD_T - PAD_B + 20} rx="2" fill="none" stroke="var(--blue-2)" strokeWidth="1.5" />
                  )}
                  <motion.rect
                    x={bx} width={bwid} rx="2"
                    initial={reduce ? { y: top, height: base - top } : { y: base, height: 0 }}
                    animate={inView ? { y: top, height: Math.max(base - top, x.n ? 2 : 0) } : undefined}
                    transition={{
                      duration: reduce ? 0 : 0.85,
                      delay: reduce ? 0 : 0.2 + i * 0.018,
                      ease: EASE,
                      opacity: { duration: reduce ? 0 : 0.18, delay: 0, ease: EASE },
                    }}
                    fill={inHeart ? "var(--amber)" : "var(--amber-wash-2)"}
                    opacity={hover == null || isHover ? 1 : 0.5}
                  />
                  {/* 有大事记：柱顶上方一枚蓝点，不是描边 */}
                  {has && (
                    <circle
                      cx={bx + bwid / 2} cy={top - 8} r="2.1"
                      fill="var(--blue-2)"
                      opacity={hover == null || isHover ? 1 : 0.4}
                    />
                  )}
                  {x.h === cuts.peak.h && (
                    <text x={bx + bwid / 2} y={top - (has ? 17 : 8)} textAnchor="middle" fontFamily="var(--font-sans)" fontSize="11.5" fontWeight="700" fill="var(--amber-text)" className="num">{fmtInt(x.n)}</text>
                  )}
                  <text x={bx + bwid / 2} y={H - 13} textAnchor="middle" fontFamily="var(--font-sans)" fontSize="11" fontWeight={isHover ? 700 : 400} fill={isHover ? "var(--ink)" : "var(--ink-3)"} className="num">{hh(i)}</text>
                </g>
              );
            })}
            <line x1={PAD_L} x2={W - PAD_R} y1={y(0)} y2={y(0)} stroke="var(--rule)" strokeWidth="1" />
          </svg>
        </div>

        {/* 悬停读数：左边时间大字，右边事件两列对齐 */}
        <div className="mt-3 min-h-[68px] border-t border-rule-soft pt-3 font-sans text-[13px] text-ink-2" aria-live="polite">
          {active ? (
            <div className="grid gap-2 sm:grid-cols-[136px_minmax(0,1fr)] sm:gap-6">
              <div className="sm:border-r sm:border-rule-soft sm:pr-6">
                <div className="num text-[22px] font-semibold leading-none text-ink">{hh(active.h)}:00</div>
                <div className="mt-1.5 num text-[12px] leading-none text-ink-3">
                  {fmtInt(active.n)} 条 · 占全天 {activePct}%
                  {activeSeg && <span className={`ml-1.5 ${activeSeg.key === "heart" ? "text-amber-text" : "text-blue-text"}`}>{activeSeg.label}</span>}
                </div>
              </div>
              <div className="min-w-0">
                {activeList.length ? (
                  <ul className="grid gap-1">
                    {activeList.map((e, i) => (
                      <li key={i} className="grid grid-cols-[76px_minmax(0,1fr)] items-baseline gap-x-3">
                        <span className="num text-[12px] text-blue-text">{e.t}</span>
                        <span className="truncate font-serif text-ink" dangerouslySetInnerHTML={{ __html: e.h }} />
                      </li>
                    ))}
                  </ul>
                ) : (
                  <span className="text-ink-3">这一小时没有记进大事记的事件。</span>
                )}
              </div>
            </div>
          ) : (
            <span className="text-ink-3">把手指或指针放到任一小时，看那会儿发生了什么。</span>
          )}
        </div>
      </div>
      {caption && <p className="prose-sheet mt-5 text-[16px] leading-[1.85] text-ink-2" dangerouslySetInnerHTML={{ __html: caption }} />}
    </div>
  );
}
