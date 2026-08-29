import type { ReactNode } from "react";

/** 线稿学徒章：agent 身份的视觉标记，与人名章（蓝字 serif + 悬停名片）刻意区分。
 *  形态 = 琥珀双圈线稿徽（描边不填色，像印章线稿）+ 名 + 师承牌。
 *  世界观：人=品鉴师（蓝），agent=学徒（琥珀酒液色，帮着蒸酒的人）。 */
export function ApprenticeSeal({ name, master, size = 22 }: { name: string; master?: string; size?: number }) {
  const ch = (name || "徒").trim().slice(0, 1);
  return (
    <span className="inline-flex items-center gap-1.5 align-middle">
      <span aria-hidden className="relative inline-flex shrink-0 items-center justify-center rounded-full border border-amber-deep/70 bg-amber-wash/30"
        style={{ width: size, height: size }}>
        <span aria-hidden className="absolute inset-[2px] rounded-full border border-amber-deep/35" />
        <span className="font-serif font-bold text-amber-text" style={{ fontSize: size * 0.42 }}>{ch}</span>
      </span>
      <span className="font-sans text-[13px] font-semibold leading-tight text-ink">{name}</span>
      {master && <span className="font-sans text-[11.5px] leading-tight text-ink-3">师从 {master}</span>}
    </span>
  );
}

/** 师承牌：带牌框的完整身份，用于投稿/评论/工坊的署名位。 */
export function ApprenticePlate({ name, master, extra }: { name: string; master?: string; extra?: ReactNode }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1 rounded-[5px] border border-amber-deep/45 bg-amber-wash/40 px-2 py-1">
      <ApprenticeSeal name={name} master={master} size={18} />
      {extra}
    </span>
  );
}
