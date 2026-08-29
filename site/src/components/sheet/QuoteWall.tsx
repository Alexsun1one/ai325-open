"use client";
import { useState } from "react";
import type { Quote } from "@/lib/shared";
import { ToneTag } from "./ToneTag";
import { renderShareCard } from "@/lib/sharecard";

/**
 * 按钮文案的 160ms 交叉淡入：两（三）个文案叠在同一个 grid 格里，
 * 格子宽度取最宽的那个，所以「复制 → 已复制」不会把整行推着走。
 */
function Swap({ labels, active }: { labels: string[]; active: number }) {
  return (
    <span className="grid">
      {labels.map((s, i) => (
        <span
          key={i}
          aria-hidden={i !== active}
          className={`col-start-1 row-start-1 text-center transition-opacity duration-[160ms] ease-[var(--ease-out-expo)] ${i === active ? "opacity-100" : "opacity-0"}`}
        >
          {s}
        </span>
      ))}
    </span>
  );
}

/** 逐字摘录：三栏瀑布；每条可复制、可生成分享卡。 */
export function QuoteWall({ quotes, issue, date, degree }: { quotes: Quote[]; issue: number; date: string; degree: number }) {
  const [busy, setBusy] = useState<number | null>(null);
  const [done, setDone] = useState<{ i: number; kind: "copy" | "card" } | null>(null);
  const url = "https://www.ai325.com";
  const copy = async (q: Quote, i: number) => {
    try { await navigator.clipboard.writeText(`「${q.t}」—— ${q.a}（先锋队台账 第 ${String(issue).padStart(3, "0")} 批）`); setDone({ i, kind: "copy" }); setTimeout(() => setDone(null), 1600); } catch {}
  };
  const card = async (q: Quote, i: number) => {
    setBusy(i);
    try {
      const blob = await renderShareCard({ text: q.t, author: q.a, tone: q.g, issue, date, degree, url });
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `先锋队台账-${date}-金句-${q.a}.png`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      setDone({ i, kind: "card" }); setTimeout(() => setDone(null), 1600);
    } finally { setBusy(null); }
  };
  // hover 时同时给底色和 1px 下划线：底色说「这块可按」，下划线说「这是个动作」。
  // 高度锁死 22px、下划线走 text-decoration，两者都不改盒子，所以不会推动署名行。
  const btn = "inline-flex h-[22px] items-center justify-center rounded-[5px] px-1.5 font-sans text-[12px] leading-none text-ink-3 decoration-1 underline-offset-[3px] transition-colors duration-200 ease-[var(--ease-out-expo)] hover:bg-paper-2 hover:text-ink hover:underline active:bg-paper-3 disabled:pointer-events-none disabled:text-ink-3/60 disabled:no-underline";
  return (
    <div className="columns-1 gap-10 border-b border-rule md:columns-2 xl:columns-3 [column-fill:balance]">
      {quotes.map((q, i) => (
        <figure key={i} className="mb-0 break-inside-avoid border-t border-rule px-1 pb-6 pt-4 transition-colors duration-200 ease-[var(--ease-out-expo)] hover:bg-paper-2/40">
          {/* 引号是这个世界的琥珀记号，但落在 color 上只能取 -text 变体；700 是真实字重，不是合成粗体 */}
          <blockquote className="font-serif text-[18px] leading-[1.8] text-ink">
            <span aria-hidden className="-mr-[0.12em] font-bold text-amber-text">「</span>{q.t}<span aria-hidden className="-ml-[0.12em] font-bold text-amber-text">」</span>
          </blockquote>
          <figcaption className="mt-3.5 flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
            <div className="flex min-w-0 items-center gap-2.5">
              <span data-person={q.a} className="truncate font-sans text-[13px] font-semibold text-blue-text">{q.a}</span>
              <ToneTag g={q.g} />
            </div>
            {/* 常显而非 hover 才现：触屏没有 hover，且 70% 透明度只是把字弄脏。安静=灰、可按=纸底 */}
            <div className="flex shrink-0 items-center gap-0.5 whitespace-nowrap" aria-live="polite">
              <button type="button" onClick={() => copy(q, i)} className={`${btn} min-w-[3.4em]`} aria-label="复制这句">
                <Swap labels={["复制", "已复制"]} active={done?.i === i && done.kind === "copy" ? 1 : 0} />
              </button>
              <button type="button" onClick={() => card(q, i)} disabled={busy === i} className={`${btn} min-w-[4.4em]`} aria-label="生成分享卡">
                <Swap labels={["分享卡", "生成中…", "已保存"]} active={busy === i ? 1 : done?.i === i && done.kind === "card" ? 2 : 0} />
              </button>
            </div>
          </figcaption>
        </figure>
      ))}
    </div>
  );
}
