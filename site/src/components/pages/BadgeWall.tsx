"use client";
import { useState } from "react";
import { motion, useReducedMotion } from "motion/react";

export interface Badge { file: string; slug: string; name: string; trigger: string; icon: string; accent: string }

/** 徽章墙：12 枚未点亮的铭牌。谁拿到了还没接线——不点亮就是不点亮，不拿假数据充数。 */
export function BadgeWall({ badges }: { badges: Badge[] }) {
  const [active, setActive] = useState<string | null>(null);
  const reduce = useReducedMotion();
  return (
    <div className="grid grid-cols-2 border-l border-t border-rule sm:grid-cols-3 lg:grid-cols-4">
      {badges.map((b, i) => {
        const on = active === b.slug;
        return (
          <button
            key={b.slug}
            type="button"
            onMouseEnter={() => setActive(b.slug)}
            onMouseLeave={() => setActive(null)}
            onFocus={() => setActive(b.slug)}
            onBlur={() => setActive(null)}
            onClick={() => setActive(on ? null : b.slug)}
            className={`group relative flex flex-col items-center border-b border-r border-rule px-3 pb-4 pt-5 text-center transition-colors ${on ? "bg-paper-2/70" : "hover:bg-paper-2/40"}`}
          >
            <motion.img
              src={`/badges/${b.file}`}
              alt=""
              width={200}
              height={200}
              loading="lazy"
              className="h-[78px] w-[78px] transition-[opacity,filter] duration-300"
              style={{ opacity: on ? 0.95 : 0.42, filter: on ? "none" : "saturate(0.35)" }}
              initial={reduce ? false : { opacity: 0, y: 8 }}
              whileInView={{ opacity: on ? 0.95 : 0.42, y: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ delay: 0.04 * i, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            />
            <div className="mt-2.5 font-sans text-[13.5px] font-semibold text-ink">{b.name}</div>
            <div className="mt-1 min-h-[32px] font-sans text-[11.5px] leading-snug text-ink-3">{b.trigger}</div>
            <span className="mt-2 inline-flex rounded-[4px] border border-rule bg-paper px-1.5 py-[2px] font-sans text-[10.5px] font-semibold text-ink-3">未点亮</span>
          </button>
        );
      })}
    </div>
  );
}
