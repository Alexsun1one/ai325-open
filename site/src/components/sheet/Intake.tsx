"use client";
import { useEffect, useRef } from "react";
import { animate, useInView, useReducedMotion } from "motion/react";
import { fmtInt } from "@/lib/shared";

function Count({ to, delay = 0 }: { to: number; delay?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const reduce = useReducedMotion();
  useEffect(() => {
    const el = ref.current; if (!el) return;
    if (reduce) { el.textContent = fmtInt(to); return; }
    const c = animate(0, to, { duration: 1.1, delay, ease: [0.16, 1, 0.3, 1], onUpdate: (v) => { el.textContent = fmtInt(Math.round(v)); } });
    return () => c.stop();
  }, [to, delay, reduce]);
  return <span ref={ref} className="num">{fmtInt(to)}</span>;
}

export interface IntakeField { k: string; v: number; suffix?: string; note?: string }

/**
 * 进料字段：表单式格子。标签印在左上角，数字是填进去的。
 * 格线由「每格都画上/左边线 + 整体负 1px 位移 + 外层裁切」得到：
 * 首行的上边线与首列的左边线被裁掉，任何列数（2 / 3 / 6）下都只在格与格之间留线。
 */
export function Intake({ fields }: { fields: IntakeField[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  return (
    <div ref={ref} className="overflow-hidden border-y border-blue-wash-2">
      <div className="-ml-px -mt-px grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6">
        {fields.map((f, i) => (
          <div
            key={f.k}
            className="relative flex flex-col border-l border-t border-blue-wash-2 px-3.5 pb-3 pt-2.5 transition-colors duration-200 ease-[var(--ease-out-expo)] hover:bg-paper-2/50"
          >
            <div className="label">{f.k}</div>
            <div className="mt-1.5 flex items-baseline gap-1 border-b border-dotted border-rule pb-1 text-[24px] font-semibold leading-none text-ink sm:text-[26px]">
              {inView ? <Count to={f.v} delay={0.15 + i * 0.08} /> : <span className="num">{fmtInt(f.v)}</span>}
              {/* 后缀是悬案信号（如「+1 悬」），用琥珀说话 */}
              {f.suffix && <span className="num text-[13px] font-medium leading-none text-amber-text">{f.suffix}</span>}
            </div>
            {f.note && <div className="mt-auto truncate pt-1.5 font-sans text-[11px] leading-snug text-ink-3" title={f.note}>{f.note}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
