"use client";
import { useRef } from "react";
import { motion, useScroll, useSpring, useTransform, useReducedMotion } from "motion/react";
import type { Event } from "@/lib/shared";

/* 竖管与圆点共用同一条中心线：管 1px 落在 X，点 11px 落在 X-5，液柱 3px 落在 X-1。 */
const RAIL = "left-[4px] sm:left-[124px]";
const FILL = "left-[3px] sm:left-[123px]";
const DOT = "left-[-1px] sm:left-[119px]";

/** 大事记：左时间栏，中间一根细管，琥珀液随滚动上涨；经过的事件点亮。 */
export function Timeline({ events }: { events: Event[] }) {
  const ref = useRef<HTMLOListElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 70%", "end 60%"] });
  const reduce = useReducedMotion();
  // 减少动态时保留「读到哪了」这个状态，只把弹簧换成近乎即时的跟随——去掉回弹与滞后
  const fill = useSpring(scrollYProgress, reduce ? { stiffness: 2000, damping: 120, mass: 0.05 } : { stiffness: 120, damping: 26, mass: 0.4 });
  const scale = useTransform(fill, [0, 1], [0, 1]);
  return (
    <ol ref={ref} className="relative ml-[2px] list-none pl-0">
      <div aria-hidden className={`absolute bottom-3 top-3 w-px bg-rule ${RAIL}`} />
      <motion.div aria-hidden style={{ scaleY: scale }} className={`absolute bottom-3 top-3 w-[3px] origin-top rounded-full bg-amber ${FILL}`} />
      {events.map((e, i) => (
        <Item key={i} e={e} progress={fill} idx={i} total={events.length} />
      ))}
    </ol>
  );
}

/** "08-21 15:55–18:00" → ["08-21", "15:55–18:00"]；没有日期段时只返回时钟。 */
function splitStamp(t: string): [string | null, string] {
  const i = t.indexOf(" ");
  return i > 0 ? [t.slice(0, i), t.slice(i + 1).trim()] : [null, t];
}

function Item({ e, progress, idx, total }: { e: Event; progress: ReturnType<typeof useSpring>; idx: number; total: number }) {
  const threshold = (idx + 0.5) / total;
  const dot = useTransform(progress, (p) => (p >= threshold ? "var(--amber)" : "var(--paper)"));
  const ring = useTransform(progress, (p) => (p >= threshold ? "var(--amber-deep)" : "var(--rule)"));
  /* 走过的点再套一圈 1px 琥珀外圈，像印油晕开的一环 */
  const halo = useTransform(progress, (p) => (p >= threshold ? "var(--amber-wash-2)" : "transparent"));
  const [day, clock] = splitStamp(e.t);
  return (
    <li className="relative grid grid-cols-1 gap-x-6 py-3.5 pl-7 sm:grid-cols-[116px_minmax(0,1fr)] sm:gap-x-8 sm:pl-0">
      <div className="flex items-baseline gap-2 pt-[3px] sm:block sm:text-right">
        {day && <div className="num font-sans text-[11.5px] font-medium leading-[1.35] text-ink-3">{day}</div>}
        <div className="num whitespace-nowrap font-sans text-[12.5px] font-medium leading-[1.35] text-blue-text">{clock}</div>
      </div>
      <motion.span
        aria-hidden
        style={{ backgroundColor: dot, borderColor: ring, outlineColor: halo }}
        className={`absolute top-[9px] h-[11px] w-[11px] rounded-full border-[1.5px] outline outline-1 outline-offset-[1.5px] sm:top-[20px] ${DOT}`}
      />
      <div className="min-w-0 sm:pl-2">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <h3 className="font-serif text-[17px] font-semibold leading-snug text-ink" dangerouslySetInnerHTML={{ __html: e.h }} />
          {e.src === "digest" && (
            <span className="shrink-0 rounded-[3px] border border-blue-wash-2 bg-blue-wash px-1.5 py-px font-sans text-[10px] font-medium leading-[1.5] tracking-[0.1em] text-blue-text">建群日档案</span>
          )}
        </div>
        <p className="prose-sheet mt-1.5 text-[15.5px] leading-[1.8] text-ink-2" dangerouslySetInnerHTML={{ __html: e.d }} />
      </div>
    </li>
  );
}
