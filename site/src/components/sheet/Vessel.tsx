"use client";
import { useEffect, useId, useState } from "react";
import { motion, useMotionValue, useSpring, useTransform, useReducedMotion, AnimatePresence } from "motion/react";

/**
 * 酿造器皿（精修 SVG）：一粒种子先微微上抬 → 落进量杯 → 涟漪 → 液位升到「累计批次」的高度
 * （到位时一个很轻的过冲）→ 液面稳住后开始冒泡。
 * 几何：视口 0 0 240 260；杯内壁 x 58–182，y 46–226；液柱可用高度 SPAN。
 */
const L = 58, R = 182, TOP = 46, BOT = 226, RAD = 16;
const SPAN = BOT - TOP - 10;
const INNER = `M${L},${TOP} V${BOT - RAD} Q${L},${BOT} ${L + RAD},${BOT} H${R - RAD} Q${R},${BOT} ${R},${BOT - RAD} V${TOP} Z`;

/** 气泡：位置/大小/周期/起始都不等距，避免「一排等间距圆点」的机械感。 */
const BUBBLES = [
  { t: 0.17, r: 1.0, dur: 4.6, d: 0.2, sway: 2.6 },
  { t: 0.33, r: 1.7, dur: 3.4, d: 1.5, sway: -1.8 },
  { t: 0.44, r: 0.9, dur: 5.5, d: 0.8, sway: 3.1 },
  { t: 0.61, r: 2.0, dur: 3.9, d: 2.7, sway: -2.4 },
  { t: 0.74, r: 1.2, dur: 6.2, d: 1.9, sway: 1.6 },
  { t: 0.87, r: 1.5, dur: 4.3, d: 3.4, sway: -3.0 },
];

export function Vessel({ issue, level, label }: { issue: number; level: number; label?: string }) {
  const uid = useId().replace(/:/g, "");
  const reduce = useReducedMotion();
  const target = Math.max(0.08, Math.min(0.92, level));
  const lv = useMotionValue(reduce ? target : 0.02);
  // 阻尼比 ≈ 0.75：液位到位时一个很轻的过冲，像真被注满后晃了一下
  const spring = useSpring(lv, { stiffness: 30, damping: 9, mass: 1.2 });
  const surfaceY = useTransform(spring, (v) => BOT - SPAN * v);
  const liquidH = useTransform(surfaceY, (y) => BOT - y);
  const capped = Math.round(target * 100);
  const pct = useTransform(spring, (v) => `${Math.min(capped, Math.round(v * 100))}%`);
  const [phase, setPhase] = useState<0 | 1 | 2 | 3>(reduce ? 3 : 0); // 0 悬停 1 预备上抬 2 下落 3 已入缸
  const [boiling, setBoiling] = useState(false);
  const [ripple, setRipple] = useState(0);

  useEffect(() => {
    if (reduce) return;
    const ts = [
      setTimeout(() => setPhase(1), 900),
      setTimeout(() => setPhase(2), 1160),
      setTimeout(() => { setRipple((r) => r + 1); lv.set(target); }, 1660),
      setTimeout(() => setPhase(3), 2100),
      setTimeout(() => setBoiling(true), 2700),
    ];
    return () => ts.forEach(clearTimeout);
  }, [reduce, target, lv]);
  useEffect(() => { if (reduce) lv.set(target); }, [reduce, target, lv]);

  const [pctText, setPctText] = useState("2%");
  useEffect(() => pct.on("change", (v) => setPctText(v)), [pct]);

  // 气泡最高只升到液面下 1px，液位低时自然就冒得短
  const travel = Math.max(6, SPAN * target - 5);

  return (
    <figure className="flex flex-col items-center">
      <svg viewBox="0 0 240 260" className="h-auto w-[150px] overflow-visible sm:w-[236px]" role="img" aria-label={`酿造器皿：第 ${issue} 批，液位 ${Math.round(level * 100)}%`}>
        <defs>
          <clipPath id={`clip-${uid}`}><path d={INNER} /></clipPath>
          {/* 酒色按杯身绝对高度渐深，不随液位拉伸 */}
          <linearGradient id={`liq-${uid}`} gradientUnits="userSpaceOnUse" x1="0" y1={TOP} x2="0" y2={BOT}>
            <stop offset="0" stopColor="var(--amber-2)" />
            <stop offset="1" stopColor="var(--amber-deep)" />
          </linearGradient>
          <linearGradient id={`glass-${uid}`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="var(--blue)" stopOpacity="0.12" />
            <stop offset="0.18" stopColor="var(--blue)" stopOpacity="0" />
            <stop offset="0.82" stopColor="var(--blue)" stopOpacity="0" />
            <stop offset="1" stopColor="var(--blue)" stopOpacity="0.1" />
          </linearGradient>
        </defs>

        {/* 杯影 */}
        <ellipse cx="120" cy={BOT + 10} rx="70" ry="5" fill="var(--ink)" opacity="0.07" />

        {/* 液体（裁在内壁里） */}
        <g clipPath={`url(#clip-${uid})`}>
          <motion.rect x={L} width={R - L} style={{ y: surfaceY, height: liquidH }} fill={`url(#liq-${uid})`} />

          {/* 液面：两层缓慢错相的波，波幅压到 2.2 / 1.1，只是「在动」不是「在浪」 */}
          <motion.g style={{ y: surfaceY }}>
            <g className={reduce ? "" : "vessel-wave"}>
              <path d="M-140,0 Q-120,-2.2 -100,0 T-60,0 T-20,0 T20,0 T60,0 T100,0 T140,0 T180,0 T220,0 T260,0 T300,0 T340,0 T380,0 V20 H-140 Z" fill="var(--amber-2)" opacity="0.9" />
            </g>
            <g className={reduce ? "" : "vessel-wave-2"}>
              <path d="M-140,1 Q-125,-1.1 -110,1 T-80,1 T-50,1 T-20,1 T10,1 T40,1 T70,1 T100,1 T130,1 T160,1 T190,1 T220,1 T250,1 T280,1 T310,1 T340,1 T370,1 V20 H-140 Z" fill="var(--paper)" opacity="0.14" />
            </g>
            {/* 液面的远沿 + 一段短高光：两条不同长度，才像光落在液面上 */}
            <ellipse cx="120" cy="1" rx={(R - L) / 2 - 2} ry="2.5" fill="none" stroke="var(--paper)" strokeOpacity="0.26" strokeWidth="1" />
            <path d="M74,-0.4 Q96,-2.4 118,-0.9" fill="none" stroke="var(--paper)" strokeOpacity="0.5" strokeWidth="1.1" strokeLinecap="round" />
            <path d="M146,0.6 Q156,-0.6 166,0.4" fill="none" stroke="var(--paper)" strokeOpacity="0.3" strokeWidth="0.9" strokeLinecap="round" />
          </motion.g>

          {/* 气泡：画在波带之上，液位很低时也看得见；升到液面下 1px 就散 */}
          {boiling && !reduce && BUBBLES.map((b, i) => (
            <motion.circle
              key={i}
              cx={L + 12 + (R - L - 24) * b.t}
              cy={BOT - 4}
              r={b.r}
              fill="var(--paper)"
              initial={{ y: 0, x: 0, opacity: 0 }}
              animate={{ y: [0, -travel], x: [0, b.sway, b.sway * -0.5, 0], opacity: [0, 0.5, 0.34, 0] }}
              transition={{
                y: { duration: b.dur, delay: b.d, repeat: Infinity, ease: "easeOut" },
                x: { duration: b.dur, delay: b.d, repeat: Infinity, ease: "easeInOut" },
                opacity: { duration: b.dur, delay: b.d, repeat: Infinity, ease: "linear", times: [0, 0.16, 0.72, 1] },
              }}
            />
          ))}

          {/* 涟漪 */}
          <AnimatePresence>
            {ripple > 0 && [0, 1].map((k) => (
              <motion.ellipse key={`${ripple}-${k}`} cx="120" style={{ y: surfaceY }} cy="0" fill="none" stroke="var(--amber-deep)" strokeWidth="1"
                initial={{ rx: 4, ry: 1.5, opacity: 0.7 }} animate={{ rx: 44 + k * 12, ry: 9 + k * 2, opacity: 0 }} transition={{ duration: 1.1 + k * 0.3, ease: "easeOut", delay: k * 0.15 }} />
            ))}
          </AnimatePresence>
        </g>

        {/* 玻璃壁：外轮廓 + 内壁厚度线 */}
        <path d={`M${L - 9},${TOP - 8} L${L},${TOP + 4} ${INNER.slice(INNER.indexOf("V"), INNER.lastIndexOf("Z"))} L${R + 9},${TOP - 8}`} fill={`url(#glass-${uid})`} stroke="var(--blue)" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
        <path d={`M${L + 4},${TOP + 10} V${BOT - RAD - 2} Q${L + 4},${BOT - 4} ${L + RAD + 2},${BOT - 4} H${R - RAD - 2} Q${R - 4},${BOT - 4} ${R - 4},${BOT - RAD - 2} V${TOP + 10}`} fill="none" stroke="var(--blue)" strokeWidth="0.8" opacity="0.45" />
        {/* 口沿加厚：左右对称的卷边 */}
        <path d={`M${L - 9},${TOP - 8} Q${L - 5},${TOP - 11.5} ${L},${TOP - 8}`} fill="none" stroke="var(--blue)" strokeWidth="1.6" strokeLinecap="round" />
        <path d={`M${R + 9},${TOP - 8} Q${R + 5},${TOP - 11.5} ${R},${TOP - 8}`} fill="none" stroke="var(--blue)" strokeWidth="1.6" strokeLinecap="round" />
        {/* 玻璃高光：一长一短两条，长短差才是玻璃，等长两条只是两根线 */}
        <path d={`M${L + 9},${TOP + 22} V${BOT - 58}`} stroke="var(--paper)" strokeWidth="2.4" strokeLinecap="round" opacity="0.5" />
        <path d={`M${L + 15},${TOP + 36} V${TOP + 76}`} stroke="var(--paper)" strokeWidth="1.1" strokeLinecap="round" opacity="0.32" />
        <path d={`M${L + 6},${BOT - 30} Q${L + 6},${BOT - 8} ${L + 22},${BOT - 8}`} fill="none" stroke="var(--paper)" strokeWidth="1.2" strokeLinecap="round" opacity="0.22" />
        {/* 底座 */}
        <path d={`M${L - 6},${BOT + 2} H${R + 6}`} stroke="var(--blue)" strokeWidth="2.2" strokeLinecap="round" />
        <path d={`M${L - 2},${BOT + 6} H${R + 2}`} stroke="var(--blue)" strokeWidth="1" strokeLinecap="round" opacity="0.5" />

        {/* 刻度：长短交替，右壁内侧。
            390 宽下整杯只有 150px（缩放 0.625），最短那一档只剩 3.7px / 半个像素的墨——藏起来，只留长/中两档；
            所有细线走 non-scaling-stroke，线宽不随缩放变细。 */}
        {Array.from({ length: 13 }).map((_, i) => {
          const y = BOT - (SPAN * i) / 12; const long = i % 4 === 0; const mid = i % 2 === 0;
          return <line key={i} className={mid ? undefined : "hidden sm:inline"} vectorEffect="non-scaling-stroke" x1={R - 6 - (long ? 16 : mid ? 10 : 6)} x2={R - 6} y1={y} y2={y} stroke="var(--blue)" strokeWidth={long ? 1.2 : 0.8} opacity={long ? 0.9 : 0.55} />;
        })}
        {/* 液位指示：字号随尺寸走（150px 下 15 单位 ≈ 9.4px，236px 下 10.5 单位 ≈ 10.3px），
            引线相应缩短，读数不越出 240 的画布 */}
        <motion.g style={{ y: surfaceY }}>
          <line x1={R + 10} x2={R + 26} y1="0" y2="0" stroke="var(--rule)" strokeDasharray="2 3" vectorEffect="non-scaling-stroke" />
          <text x={R + 29} y="0" dominantBaseline="central" fontFamily="var(--font-sans)" fontWeight="600" fill="var(--amber-text)" className="num text-[15px] sm:text-[10.5px]">{pctText}</text>
        </motion.g>

        {/* 种子（板栗，顶上一芽）：先微微上抬蓄力，再落下 */}
        <AnimatePresence>
          {phase < 3 && !reduce && (
            <motion.g
              initial={{ y: -36, opacity: 1, rotate: -12 }}
              animate={phase === 0 ? { y: 0 } : phase === 1 ? { y: -6, rotate: -16 } : { y: surfaceY.get() - TOP - 10, opacity: 0, rotate: 8 }}
              transition={
                phase === 0 ? { duration: 0.01 }
                  : phase === 1 ? { duration: 0.26, ease: [0.16, 1, 0.3, 1] }
                    : { y: { duration: 0.5, ease: [0.55, 0, 1, 0.45] }, rotate: { duration: 0.5, ease: "linear" }, opacity: { delay: 0.4, duration: 0.3 } }
              }
              style={{ originX: "120px", originY: `${TOP}px` }}
            >
              <g transform={`translate(120 ${TOP - 2})`}>
                <path d="M0,-10 C9,-8 10,4 0,9 C-10,4 -9,-8 0,-10 Z" fill="var(--amber-deep)" />
                <path d="M-7,4 Q0,8.5 7,4" fill="none" stroke="var(--amber-2)" strokeWidth="2.4" strokeLinecap="round" />
                <path d="M0,-10 Q3,-17 8,-18" fill="none" stroke="#3e8e5a" strokeWidth="1.8" strokeLinecap="round" />
                <path d="M8,-18 q4,-4 7,-1 q-3,4 -7,1Z" fill="#3e8e5a" />
              </g>
            </motion.g>
          )}
        </AnimatePresence>
      </svg>
      {/* 390 宽下把说明卡在 150px 内换两行：否则 figure 的 max-content 宽（≈190px）会把器皿挤到章的下一行 */}
      {label && <figcaption className="label label-ink -mt-1 max-w-[150px] text-center [text-indent:0.14em] sm:max-w-none">{label}</figcaption>}
    </figure>
  );
}
