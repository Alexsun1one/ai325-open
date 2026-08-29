"use client";
import { useState } from "react";
import { AnimatePresence, motion, useMotionValue, useSpring, useTransform, useReducedMotion } from "motion/react";

export interface Face { name: string; role: string; avatar?: string }

/** 头像：没有头像的人用姓名首字 + 蓝色印刷底，不用彩色随机块。 */
export function Avatar({ f, size = 40, ring = true }: { f: Face; size?: number; ring?: boolean }) {
  const ch = (f.name || "?").trim().slice(0, 1);
  const cls = `shrink-0 overflow-hidden rounded-full ${ring ? "border" : ""}`;
  if (f.avatar) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={f.avatar} alt="" width={size} height={size} loading="lazy" className={`${cls} ${ring ? "border-rule bg-paper-2" : ""} object-cover`} style={{ width: size, height: size }} />;
  }
  return (
    <span className={`${cls} inline-flex items-center justify-center ${ring ? "border-blue-wash-2" : ""} bg-blue-wash`} style={{ width: size, height: size }} aria-hidden>
      <span className="font-serif font-bold text-blue-text" style={{ fontSize: size * 0.44 }}>{ch}</span>
    </span>
  );
}

/** 头像行：全员渲染，不截断。人数少（≤24）用叠排 + 大头像；人多自动切紧凑流式（小头像、留间距、多行），悬停名牌保留。 */
export function AvatarRow({ faces }: { faces: Face[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const reduce = useReducedMotion();
  const x = useMotionValue(0);
  const rotate = useSpring(useTransform(x, [-60, 60], [-9, 9]), { stiffness: 110, damping: 14 });
  const tx = useSpring(useTransform(x, [-60, 60], [-16, 16]), { stiffness: 110, damping: 14 });
  const many = faces.length > 24;
  const size = many ? 32 : 44;
  return (
    <div className={`flex flex-wrap items-center ${many ? "gap-x-1.5 gap-y-3" : ""}`}>
      {faces.map((f, i) => (
        <div
          key={`${f.name}-${i}`}
          className={`relative transition-transform duration-200 hover:z-20 hover:-translate-y-1 ${many ? "" : "-mr-2"}`}
          onMouseEnter={() => setHover(i)}
          onMouseLeave={() => setHover(null)}
          onMouseMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); x.set(e.clientX - r.left - r.width / 2); }}
        >
          <AnimatePresence>
            {hover === i && (
              <motion.div
                initial={reduce ? { opacity: 1 } : { opacity: 0, y: 6, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={reduce ? { opacity: 0 } : { opacity: 0, y: 4, scale: 0.96 }}
                transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                style={reduce ? undefined : { rotate, translateX: tx }}
                className="pointer-events-none absolute -top-1 left-1/2 z-30 w-max max-w-[220px] -translate-x-1/2 -translate-y-full rounded-[6px] border border-blue-wash-2 bg-paper px-2.5 py-1.5 shadow-[var(--shadow-pop)]"
              >
                <div className="font-sans text-[13px] font-semibold leading-tight text-ink">{f.name}</div>
                <div className="mt-0.5 font-sans text-[11.5px] leading-tight text-ink-3">{f.role}</div>
              </motion.div>
            )}
          </AnimatePresence>
          <Avatar f={f} size={size} />
        </div>
      ))}
    </div>
  );
}
