import type { ReactNode } from "react";

/** 品鉴单的一节：左栏印刷标签（蓝）+ 右栏内容；上沿一条格线。 */
export function Section({ id, label, sub, children, className = "", spot }: { id: string; label: string; sub?: string; children: ReactNode; className?: string; spot?: string }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className={`relative grid scroll-mt-[calc(var(--nav-h)+12px)] grid-cols-1 gap-x-10 border-t border-rule pt-7 pb-12 lg:grid-cols-[168px_minmax(0,1fr)] lg:pt-8 lg:pb-16 ${className}`}>
      <div className="mb-5 lg:mb-0">
        <div className="lg:sticky lg:top-20">
          <h2 id={`${id}-h`} className="label text-[12.5px] font-semibold"><a href={`#${id}`} className="no-underline hover:text-blue-2">{label}</a></h2>
          <span aria-hidden className="mt-1.5 block h-px w-6 bg-blue/70" />
          {sub && <div className="mt-1.5 font-sans text-[12px] leading-snug text-ink-3 lg:max-w-[120px]">{sub}</div>}
          {spot && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={spot} alt="" loading="lazy" decoding="async" className="spot-illus mt-5 hidden h-[88px] w-[88px] object-cover lg:block" />
          )}
        </div>
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

export function H2({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <h2 className={`font-serif text-[26px] font-bold leading-snug tracking-[0.01em] text-ink sm:text-[30px] ${className}`}>{children}</h2>;
}
