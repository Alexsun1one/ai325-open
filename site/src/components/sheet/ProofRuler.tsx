"use client";
import { useEffect, useRef, useState, type RefObject } from "react";
import { AnimatePresence, motion, useMotionValueEvent, useScroll, useSpring, useTransform, useReducedMotion } from "motion/react";

/**
 * 酒精度标尺：液位管 + 目录合一的左栏仪表。
 * - 管左：度数刻度（每 5° 一格，20° 长格带数字，顶端 = 本期度数）；
 * - 管内：琥珀液位随阅读进度上升，底部实时读数；
 * - 管右：各节书签刻痕，按真实文档位置排布，液位涨到哪、哪节变蓝；
 * - 悬停/聚焦整根标尺 → 左侧弹出目录卡；移动端为底部抽屉。
 * 几何沿用液位管：容器 14px 宽，玻璃管 x 3–11，液柱通道 x 5–9。
 */
export function ProofRuler({ target, marks, degree, grade }: {
  target: RefObject<HTMLDivElement | HTMLElement | null>;
  marks: { id: string; label: string }[];
  degree: number;
  grade: string;
}) {
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll({ target, offset: ["start 70%", "end end"] });
  const p = useSpring(scrollYProgress, reduce ? { stiffness: 2000, damping: 120, mass: 0.05 } : { stiffness: 90, damping: 24, mass: 0.5 });
  const h = useTransform(p, [0, 1], ["0%", "100%"]);
  const capOpacity = useTransform(p, [0, 0.02], [0, 1]);

  // 各节起点在阅读进度轴上的占比（与 useScroll 的 offset 同一坐标系）
  const [fracs, setFracs] = useState<number[]>([]);
  const fracsRef = useRef<number[]>([]);
  useEffect(() => {
    const measure = () => {
      const c = target.current;
      if (!c) return;
      const vh = window.innerHeight;
      const rect = c.getBoundingClientRect();
      const top = rect.top + window.scrollY;
      const startY = top - vh * 0.7;
      const span = Math.max(1, top + rect.height - vh - startY);
      const next = marks.map((m) => {
        const el = document.getElementById(m.id);
        if (!el) return 0;
        const elTop = el.getBoundingClientRect().top + window.scrollY;
        return Math.min(1, Math.max(0, (elTop - vh * 0.35 - startY) / span));
      });
      fracsRef.current = next;
      setFracs(next);
    };
    measure();
    const ro = new ResizeObserver(measure);
    if (target.current) ro.observe(target.current);
    window.addEventListener("resize", measure);
    return () => { ro.disconnect(); window.removeEventListener("resize", measure); };
  }, [target, marks]);

  const [cur, setCur] = useState(0);
  const [activeIdx, setActiveIdx] = useState(0);
  useMotionValueEvent(p, "change", (v) => {
    setCur(Math.max(0, Math.min(degree, Math.round(v * degree))));
    let idx = 0;
    for (let i = 0; i < fracsRef.current.length; i++) if (fracsRef.current[i] <= v + 0.001) idx = i;
    setActiveIdx(idx);
  });

  const [open, setOpen] = useState(false);
  const [drawer, setDrawer] = useState(false);

  // 度数刻度：每 5° 一格，20° 长格带数字
  const ticks: { d: number; major: boolean }[] = [];
  for (let d = 0; d <= Math.floor(degree); d += 5) ticks.push({ d, major: d > 0 && d % 20 === 0 });

  return (
    <>
      {/* 桌面：左栏标尺 */}
      <div aria-hidden={false} className="no-print pointer-events-none absolute bottom-0 left-[148px] top-0 z-10 hidden w-[14px] lg:block">
        <div
          className="pointer-events-auto sticky top-[calc(50vh-200px)] h-[400px]"
          onMouseEnter={() => setOpen(true)}
          onMouseLeave={() => setOpen(false)}
          onFocus={() => setOpen(true)}
          onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setOpen(false); }}
        >
          {/* 顶端：本期度数（满刻度） */}
          <span className="num absolute -top-6 left-1/2 -translate-x-1/2 whitespace-nowrap font-sans text-[10px] font-medium text-ink-2">{degree}°{grade}</span>

          {/* 玻璃管：外壁 + 内壁双线 */}
          <div className="absolute inset-y-0 left-[3px] w-[8px] rounded-full border border-rule bg-paper" />
          <div className="absolute inset-y-[1px] left-[4px] w-[6px] rounded-full border border-rule-soft" />

          {/* 液柱：底部起涨；玻璃高光只画在酒液上 */}
          <div className="absolute inset-y-[2px] left-[5px] w-[4px] overflow-hidden rounded-full">
            <motion.div style={{ height: h }} className="absolute bottom-0 left-0 w-full rounded-b-full bg-amber">
              <span className="absolute inset-y-[3px] left-[0.6px] w-px rounded-full bg-paper opacity-45 dark:bg-ink dark:opacity-30" />
              <motion.span style={{ opacity: capOpacity }} className="absolute -top-[1px] left-0 h-[3px] w-full rounded-[50%] bg-amber-2" />
            </motion.div>
          </div>

          {/* 管左：度数刻度（0° 在底，本期度数在顶） */}
          <div className="absolute inset-y-[2px] left-0 right-0" aria-hidden>
            {ticks.map(({ d, major }) => {
              const y = (1 - d / degree) * 100;
              return (
                <span key={d} className="absolute left-0 w-0" style={{ top: `${y}%` }}>
                  <span className={`absolute h-px ${major ? "left-[-7px] w-[8px] bg-rule" : "left-[-4px] w-[4px] bg-rule-soft"}`} />
                  {major && <span className="num absolute left-[-30px] top-[-6px] w-[20px] text-right font-sans text-[9px] text-ink-3">{d}</span>}
                </span>
              );
            })}
          </div>

          {/* 管右：各节书签刻痕（按真实位置），当前节变蓝 */}
          <div className="absolute inset-y-[2px] left-0 right-0" aria-hidden>
            {fracs.map((f, i) => {
              const on = i === activeIdx;
              return (
                <span
                  key={marks[i].id}
                  className={`absolute transition-all duration-300 ${on ? "left-[13px] h-[2px] w-[8px] bg-blue" : "left-[13px] h-px w-[5px] bg-rule"}`}
                  style={{ top: `${(1 - f) * 100}%` }}
                />
              );
            })}
          </div>

          {/* 底部：当前液位读数 */}
          <span className="absolute -bottom-6 left-1/2 -translate-x-1/2 whitespace-nowrap font-sans text-[9.5px] tracking-[0.14em] text-ink-3">
            液位 <span className="num tracking-normal text-amber-text">{cur}°</span>
          </span>

          {/* 键盘可达：聚焦即展开目录卡 */}
          <button type="button" className="sr-only" onFocus={() => setOpen(true)} onClick={() => setOpen((v) => !v)}>展开本期目录</button>

          {/* 目录卡：悬停/聚焦展开在标尺左侧 */}
          <AnimatePresence>
            {open && (
              <motion.nav
                aria-label="本期目录"
                initial={reduce ? false : { opacity: 0, x: 6 }}
                animate={{ opacity: 1, x: 0 }}
                exit={reduce ? { opacity: 0 } : { opacity: 0, x: 6 }}
                transition={reduce ? { duration: 0 } : { duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
                className="absolute right-[24px] top-1/2 z-30 -translate-y-1/2 rounded-[12px] border border-rule bg-paper px-3 py-3 shadow-[var(--shadow-pop)]"
              >
                <div className="mb-1.5 flex items-center justify-end gap-1.5 whitespace-nowrap px-1 font-sans text-[11px] font-medium tracking-[0.12em] text-ink-3">
                  目录 <span className="num text-ink-2">{String(activeIdx + 1).padStart(2, "0")}/{marks.length}</span>
                </div>
                <ul className="space-y-[3px]">
                  {marks.map((s, i) => {
                    const on = i === activeIdx;
                    return (
                      <li key={s.id}>
                        <a href={`#${s.id}`} className="group flex items-center justify-end gap-2.5 rounded-md px-1 py-[3px] no-underline hover:bg-paper-2" aria-current={on ? "location" : undefined}>
                          <span className={`whitespace-nowrap font-sans text-[12.5px] ${on ? "font-semibold text-blue-text" : "text-ink-2"}`}>{s.label}</span>
                          <span className={`block h-px shrink-0 transition-all ${on ? "w-5 bg-blue" : "w-3 bg-rule group-hover:bg-ink-3"}`} />
                        </a>
                      </li>
                    );
                  })}
                </ul>
              </motion.nav>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* 移动端：底部抽屉 */}
      <div className="no-print fixed bottom-4 right-4 z-30 lg:hidden">
        <button type="button" onClick={() => setDrawer((v) => !v)} aria-expanded={drawer} className="inline-flex min-h-11 items-center gap-1.5 rounded-full border border-rule bg-paper px-4 py-2 font-sans text-[12.5px] font-medium text-ink-2 shadow-[var(--shadow-pop)]">
          目录 <span className="num text-ink-3">{String(activeIdx + 1).padStart(2, "0")}/{marks.length}</span>
          <span className="num text-amber-text">{cur}°</span>
        </button>
        {drawer && (
          <ul className="absolute bottom-12 right-0 w-[220px] rounded-[10px] border border-rule bg-paper p-2 shadow-[var(--shadow-pop)]">
            {marks.map((s, i) => (
              <li key={s.id}><a href={`#${s.id}`} onClick={() => setDrawer(false)} className={`block rounded-md px-3 py-1.5 font-sans text-[13px] no-underline ${i === activeIdx ? "bg-blue-wash text-blue-text" : "text-ink-2"}`}>{s.label}</a></li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
