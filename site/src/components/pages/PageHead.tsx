import type { ReactNode } from "react";

export interface HeadField { k: string; v: ReactNode; num?: boolean }

/** 分页刊头：与首页 SheetHeader 同一套表单语法——样品信息行 + 大标题 + 导语，右侧留给章/器皿。 */
export function PageHead({ fields, title, lead, aside, note }: { fields: HeadField[]; title: string; lead: string; aside?: ReactNode; note?: ReactNode }) {
  return (
    <header className={`relative grid gap-8 pb-10 pt-10 sm:pt-14 lg:gap-12 ${aside ? "lg:grid-cols-[minmax(0,1fr)_232px]" : ""}`}>
      <div className="min-w-0">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 border-y border-rule py-3 font-sans text-[13px] sm:grid-cols-4">
          {fields.map((f) => (
            <div key={f.k}>
              <dt className="label">{f.k}</dt>
              <dd className={`mt-0.5 text-ink ${f.num === false ? "" : "num"}`}>{f.v}</dd>
            </div>
          ))}
        </dl>
        <h1 className="mt-8 font-serif text-[36px] font-black leading-[1.18] tracking-[0.01em] text-ink sm:text-[46px] lg:text-[52px]">{title}</h1>
        <p className="prose-sheet mt-5 max-w-[40em] text-[17.5px] leading-[1.9] text-ink-2">{lead}</p>
        {note && <div className="mt-6 rounded-[10px] border border-blue-wash-2 bg-blue-wash/70 px-4 py-3 font-sans text-[13.5px] leading-relaxed text-ink-2">{note}</div>}
      </div>
      {aside && <div className="flex flex-row flex-wrap items-start gap-6 lg:flex-col lg:items-end lg:gap-4 lg:pt-2">{aside}</div>}
    </header>
  );
}

/** 页面主壳：与 LedgerSheet 同宽同边距。 */
export function PageShell({ children }: { children: ReactNode }) {
  return <main id="top" className="relative z-[1] mx-auto max-w-[1180px] px-5 sm:px-8">{children}</main>;
}

/** 诚实缺口条：数据没有就说没有，不用占位图糊过去。 */
export function GapNote({ children }: { children: ReactNode }) {
  return (
    <p className="inline-flex items-start gap-2 rounded-[6px] border border-amber-deep/45 bg-amber-wash px-3 py-2 font-sans text-[12.5px] leading-relaxed text-amber-text">
      <span aria-hidden className="mt-[2px] shrink-0">◆</span>
      <span>{children}</span>
    </p>
  );
}

/** 横向滚动提示：窄屏上表格/图会溢出，明说可以滑。 */
export function ScrollHint({ children = "表格较宽，可左右滑动" }: { children?: ReactNode }) {
  return (
    <div className="mb-2 flex items-center gap-1.5 font-sans text-[11.5px] text-ink-3 sm:hidden">
      <svg aria-hidden width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M8 7l-4 5 4 5M16 7l4 5-4 5" /></svg>
      {children}
    </div>
  );
}

/** 服务器 Hermes 对外叫「一一」。数据里两种写法都可能出现，渲染统一。 */
export function byName(v?: string): string {
  if (!v) return "";
  return v.replace(/Hermes\s*\(\s*dry-run\s*\)/gi, "一一").replace(/\bHermes\b/gi, "一一");
}
