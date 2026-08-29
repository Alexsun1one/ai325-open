"use client";
import { motion, useReducedMotion } from "motion/react";

/** 中文版 text-generate：按分句逐段显现（blur 4px → 0，opacity），与批次章同一授权时刻。只在首屏用一次。 */
export function TypeReveal({ text, className = "", delay = 0.2, step = 0.09 }: { text: string; className?: string; delay?: number; step?: number }) {
  const reduce = useReducedMotion();
  const parts = text.split(/(?<=[，。、；：！？——…」])/).filter(Boolean);
  if (reduce) return <p className={className}>{text}</p>;
  return (
    <p className={className} aria-label={text}>
      {parts.map((s, i) => (
        <motion.span key={i} aria-hidden initial={{ opacity: 0, filter: "blur(4px)", y: 2 }} animate={{ opacity: 1, filter: "blur(0px)", y: 0 }} transition={{ delay: delay + i * step, duration: 0.5, ease: [0.16, 1, 0.3, 1] }} className="inline">
          {s}
        </motion.span>
      ))}
    </p>
  );
}
