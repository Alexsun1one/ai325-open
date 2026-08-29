"use client";
import { motion, useReducedMotion } from "motion/react";
import { pad3 } from "@/lib/shared";

/**
 * 环文：真章的排法——上弧顺时针正读（刊名），下弧逆时针也正读（英文 + 日期），左右两点各一枚菱形分隔。
 * 两条弧的半径分开定：上弧字头朝外（基线之上 8.2 个单位是墨），下弧字头朝内（基线之下 6.6 个单位是墨），
 * 同一条半径会让两行墨块一高一低。现在两行墨块都落在 r≈72–81 的环带里，
 * 与内圈 r=62、细外圈 r=88 各留 7–11 的空气。
 */
const R_RING_TOP = 72.5;
const R_RING_BOT = 79.5;
const R_MARK = 76;   // 左右菱形：落在环文墨带的正中
const TOP_ARC = `M${100 - R_RING_TOP},100 A${R_RING_TOP},${R_RING_TOP} 0 1,1 ${100 + R_RING_TOP},100`;   // 左 → 上 → 右（顺时针）
const BOT_ARC = `M${100 - R_RING_BOT},100 A${R_RING_BOT},${R_RING_BOT} 0 0,0 ${100 + R_RING_BOT},100`;   // 左 → 下 → 右（逆时针，字头朝圆心 = 正读）

/** 外圈只留 3 处极小断口（约 7 点 / 10 点半 / 1 点），间距刻意不等分；首尾两段接合成一段长弧。 */
const R_OUT = 94;
const C_OUT = 2 * Math.PI * R_OUT;
const OUT_SEG = [193.6, 3, 126.6, 2.4, 184.6, 3.4];
const OUT_DASH = [...OUT_SEG, C_OUT - OUT_SEG.reduce((a, b) => a + b, 0)].map((n) => n.toFixed(2)).join(" ");

/** 圆形批次章：蓝单色。中心度数，环文刊名。 */
export function Stamp({ issue, degree, grade, date, size = 196, delay = 0.9 }: { issue: number; degree: number; grade: string; date: string; size?: number; delay?: number }) {
  const reduce = useReducedMotion();
  const id = `stamp-ring-${issue}`;
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, scale: 1.22, rotate: -14 }}
      animate={reduce ? { opacity: 1, scale: 1, rotate: -7 } : { opacity: 1, scale: [1.22, 0.985, 1], rotate: [-14, -6.1, -7] }}
      transition={reduce ? { duration: 0 } : { delay, duration: 0.62, ease: [0.16, 1, 0.3, 1], times: [0, 0.74, 1], opacity: { delay, duration: 0.26, ease: "linear" } }}
      className="stamp-ink select-none"
      style={{ width: size, aspectRatio: "1 / 1", maxWidth: "100%" }}
      aria-label={`第 ${pad3(issue)} 批 · ${degree} 度 · ${grade} 级`}
      role="img"
    >
      <svg viewBox="0 0 200 200" width="100%" height="100%" className="overflow-visible">
        <defs>
          <path id={`${id}-top`} d={TOP_ARC} />
          <path id={`${id}-bot`} d={BOT_ARC} />
        </defs>

        {/* 章的笔画：主层 + 错位 0.7px 的淡层，模拟盖章时的墨色不均（不用滤镜） */}
        <g>
          <circle cx="100" cy="100" r={R_OUT} fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" opacity="0.92" strokeDasharray={OUT_DASH} />
          <circle cx="100" cy="100" r="88" fill="none" stroke="currentColor" strokeWidth="0.8" opacity="0.62" />
          <circle cx="100" cy="100" r="62" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.72" />
        </g>
        <g transform="translate(0.7 -0.5)" opacity="0.16">
          <circle cx="100" cy="100" r={R_OUT} fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeDasharray={OUT_DASH} />
          <circle cx="100" cy="100" r="88" fill="none" stroke="currentColor" strokeWidth="0.8" />
          <circle cx="100" cy="100" r="62" fill="none" stroke="currentColor" strokeWidth="1" />
        </g>

        {/* 环文：上弧刊名、下弧英文与日期，都正读；左右各一枚菱形 */}
        <text fill="currentColor" fontFamily="var(--font-sans)" fontSize="11" letterSpacing="2.6" fontWeight="600" opacity="0.95">
          <textPath href={`#${id}-top`} startOffset="50%" textAnchor="middle">先锋队台账 · 每日蒸馏刊</textPath>
        </text>
        <text fill="currentColor" fontFamily="var(--font-sans)" fontSize="9.5" letterSpacing="2.4" fontWeight="600" opacity="0.92" className="num">
          <textPath href={`#${id}-bot`} startOffset="50%" textAnchor="middle">TASTING SHEET · {date}</textPath>
        </text>
        <rect x="-1.7" y="-1.7" width="3.4" height="3.4" fill="currentColor" opacity="0.85" transform={`translate(${100 - R_MARK} 100) rotate(45)`} />
        <rect x="-1.7" y="-1.7" width="3.4" height="3.4" fill="currentColor" opacity="0.85" transform={`translate(${100 + R_MARK} 100) rotate(45)`} />

        {/* 中心三行：整块视觉居中（letter-spacing 的尾隙用 dx 补回） */}
        <text x="100" y="75" dx="1.5" textAnchor="middle" fill="currentColor" fontFamily="var(--font-sans)" fontSize="12" letterSpacing="3" fontWeight="600">第 {pad3(issue)} 批</text>
        <text x="100" y="114" textAnchor="middle" fill="currentColor" fontFamily="var(--font-sans)" fontSize="40" fontWeight="700" className="num">{degree}°</text>
        <text x="100" y="136" dx="1.5" textAnchor="middle" fill="currentColor" fontFamily="var(--font-sans)" fontSize="11" letterSpacing="3" fontWeight="600">{grade} 级 · 已鉴定</text>
      </svg>
    </motion.div>
  );
}
