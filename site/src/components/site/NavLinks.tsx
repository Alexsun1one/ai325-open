"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

export const LINKS: { href: string; label: string; gated?: boolean }[] = [
  { href: "/", label: "本期" },
  { href: "/archive/", label: "往期" },
  { href: "/events/", label: "活动" },
  { href: "/members/", label: "群像", gated: true },
  { href: "/cellar/", label: "原浆", gated: true },
  { href: "/essays/", label: "窖藏", gated: true },
  { href: "/library/", label: "文库", gated: true },
  { href: "/arsenal/", label: "军火库" },
  { href: "/agents/", label: "工坊" },
  { href: "/quality/", label: "度数" },
  { href: "/about/", label: "关于" },
];

export function NavLinks() {
  const path = usePathname() || "/";
  const isActive = (h: string) => (h === "/" ? path === "/" || path.startsWith("/ledger/") : path.startsWith(h));
  return (
    <>
      {LINKS.map((l) => {
        const on = isActive(l.href);
        return (
          <Link key={l.href} href={l.href} aria-current={on ? "page" : undefined}
            className={`group relative inline-flex min-h-11 items-center whitespace-nowrap rounded-md px-2 py-2 font-sans text-[13px] font-medium transition-colors sm:min-h-0 sm:px-2.5 sm:py-1.5 sm:text-[13.5px] ${on ? "text-ink" : "text-ink-2 hover:bg-paper-2 hover:text-ink active:bg-paper-3"}`}>
            {l.label}
            {l.gated && (
              <svg aria-label="需登录" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" className="ml-1 inline-block -translate-y-[1px] text-ink-3"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>
            )}
            <span aria-hidden className={`absolute inset-x-2 -bottom-[3px] h-[2px] rounded-full bg-blue transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] sm:-bottom-[9px] ${on ? "scale-x-100" : "scale-x-0 group-hover:scale-x-50"}`} style={{ transformOrigin: "center" }} />
          </Link>
        );
      })}
    </>
  );
}
