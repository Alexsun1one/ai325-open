"use client";
import { useEffect, useState } from "react";
import { pad3 } from "@/lib/shared";

export interface ThreadRow {
  id: string;
  title: string;
  theme: string;
  status: "ongoing" | "closed";
  issues: number[];
  dates: string[];
}

const MATURITY = [
  { key: "seed", label: "幼苗", note: "只蒸过一次，还没有跨期证据" },
  { key: "grow", label: "生长", note: "已复蒸，主题在跨期承接" },
  { key: "ripe", label: "成熟", note: "四批以上反复出现，已成群里的常设议题" },
] as const;

function maturity(t: ThreadRow) {
  if (t.status === "closed") return { label: "封存", note: "已结案，不再复蒸", cls: "border-rule text-ink-3 bg-paper-2" };
  const n = t.issues.length;
  const m = n >= 4 ? MATURITY[2] : n >= 2 ? MATURITY[1] : MATURITY[0];
  const cls = n >= 4 ? "border-amber-deep/50 bg-amber-wash text-amber-text" : n >= 2 ? "border-teal/50 bg-teal-wash text-teal-text" : "border-blue-wash-2 bg-blue-wash text-blue-text";
  return { label: m.label, note: m.note, cls };
}

/** 线索图：行 = 主题线索，列 = 批次。点 = 该批出现，线把同一条线索连起来；右侧留出未来批次的空槽。 */
export function ThreadMap({ rows, issues, ghost = 5 }: { rows: ThreadRow[]; issues: number[]; ghost?: number }) {
  const [open, setOpen] = useState<string | null>(null);
  // 从首页「前情提要」带 hash 跳过来时，直接展开那一条
  useEffect(() => {
    const fromHash = () => { const h = decodeURIComponent(location.hash.replace(/^#thread-/, "")); if (h && rows.some((r) => r.id === h)) setOpen(h); };
    fromHash();
    addEventListener("hashchange", fromHash);
    return () => removeEventListener("hashchange", fromHash);
  }, [rows]);
  const cols = issues.length + ghost;
  const grid = { gridTemplateColumns: `minmax(132px, 190px) repeat(${cols}, minmax(0, 1fr))` };

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[560px]">
        {/* 表头 */}
        <div className="grid items-end gap-x-1 border-b border-rule pb-2" style={grid}>
          <div className="label">主题线索</div>
          {issues.map((n) => (
            <div key={n} className="text-center">
              <div className="num font-sans text-[12.5px] font-semibold text-blue-text">{pad3(n)}</div>
            </div>
          ))}
          {Array.from({ length: ghost }, (_, i) => (
            <div key={`g${i}`} className="text-center">
              <div className="num font-sans text-[12.5px] text-ink-3/55">{pad3(issues[issues.length - 1] + i + 1)}</div>
            </div>
          ))}
        </div>

        {/* 行 */}
        <div className="divide-y divide-rule-soft border-b border-rule">
          {rows.map((t) => {
            const isOpen = open === t.id;
            const m = maturity(t);
            const first = Math.min(...t.issues);
            const last = Math.max(...t.issues);
            return (
              <div key={t.id} id={`thread-${t.id}`} className="scroll-mt-24">
                <button
                  type="button"
                  onClick={() => setOpen(isOpen ? null : t.id)}
                  aria-expanded={isOpen}
                  className={`grid w-full items-center gap-x-1 py-3 text-left transition-colors ${isOpen ? "bg-paper-2/70" : "hover:bg-paper-2/40"}`}
                  style={grid}
                >
                  <span className="flex min-w-0 items-center gap-1.5 pr-2">
                    <svg aria-hidden width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" className={`shrink-0 text-ink-3 transition-transform ${isOpen ? "rotate-90" : ""}`}><path d="M9 6l6 6-6 6" /></svg>
                    <span className="truncate font-sans text-[13.5px] font-semibold text-ink">{t.title}</span>
                  </span>
                  {/* 真实批次列 */}
                  {issues.map((n, i) => {
                    const on = t.issues.includes(n);
                    const prevOn = i > 0 && t.issues.includes(issues[i - 1]);
                    return (
                      <span key={n} className="relative flex h-6 items-center justify-center">
                        {prevOn && on && <span aria-hidden className="absolute top-1/2 h-[1.5px] -translate-y-1/2 bg-amber" style={{ left: "-50%", right: "50%" }} />}
                        {on ? (
                          <span aria-label={`第 ${pad3(n)} 批出现`} className="relative z-[1] h-[11px] w-[11px] rounded-full border-2 border-amber-deep bg-amber" />
                        ) : (
                          <span aria-hidden className="h-[5px] w-[5px] rounded-full bg-rule" />
                        )}
                      </span>
                    );
                  })}
                  {/* 未来批次空槽：虚线，等着被填 */}
                  {Array.from({ length: ghost }, (_, i) => (
                    <span key={`g${i}`} className="relative flex h-6 items-center justify-center">
                      {i === 0 && t.status === "ongoing" && t.issues.includes(issues[issues.length - 1]) && (
                        <span aria-hidden className="absolute top-1/2 -translate-y-1/2 border-t border-dashed border-amber-deep/50" style={{ left: "-50%", right: "50%" }} />
                      )}
                      <span aria-hidden className="h-[9px] w-[9px] rounded-full border border-dashed border-rule" />
                    </span>
                  ))}
                </button>

                {isOpen && (
                  <div className="grid gap-x-1 pb-5" style={grid}>
                    <div className="pl-6 sm:pl-7" style={{ gridColumn: "2 / -1" }}>
                      <dl className="grid gap-x-8 gap-y-3 font-sans text-[13px] sm:grid-cols-4">
                        <div><dt className="label">首蒸于</dt><dd className="num mt-0.5 text-ink">第 {pad3(first)} 批</dd></div>
                        <div><dt className="label">最近复蒸于</dt><dd className="num mt-0.5 text-ink">{last === first ? <span className="text-ink-3">尚无复蒸</span> : `第 ${pad3(last)} 批`}</dd></div>
                        <div><dt className="label">成熟度</dt><dd className="mt-0.5"><span className={`inline-flex rounded-[4px] border px-2 py-[2px] text-[12px] font-semibold ${m.cls}`}>{m.label}</span></dd></div>
                        <div><dt className="label">关联批次</dt><dd className="num mt-0.5 text-ink">{t.issues.map(pad3).join(" · ")}</dd></div>
                      </dl>
                      <p className="mt-3 font-sans text-[12.5px] leading-relaxed text-ink-3">{m.note}。本期落在<span className="text-ink-2">「{t.theme}」</span>。</p>
                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-sans text-[13px]">
                        {t.dates.map((d, i) => (
                          <a key={d} href={`/ledger/${d}/#themes`} className="text-blue-text no-underline hover:underline">
                            第 {pad3(t.issues[i])} 批 · {d}
                          </a>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
