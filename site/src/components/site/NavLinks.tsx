"use client";
import { Icon, type IconName } from "@/components/ui/Icon";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, useState } from "react";

export const LINKS: { href: string; label: string; gated?: boolean }[] = [
  { href: "/", label: "发现" },
  { href: "/learn/", label: "学习" },
  { href: "/community/", label: "交流" },
  { href: "/readings/", label: "精读" },
  { href: "/archive/", label: "往期" },
  { href: "/events/", label: "活动" },
  { href: "/members/", label: "群像", gated: true },
  { href: "/rankings/", label: "群友排行" },
  { href: "/cellar/", label: "原浆", gated: true },
  { href: "/essays/", label: "窖藏", gated: true },
  { href: "/library/", label: "文库", gated: true },
  { href: "/skills/", label: "技能库" },
  { href: "/arsenal/", label: "资源库" },
  { href: "/agents/", label: "学堂" },
  { href: "/quality/", label: "度数" },
  { href: "/about/", label: "关于" },
];
const navIcons: Record<string, IconName> = {
  "/":"discover", "/readings/":"book", "/learn/":"book", "/community/":"chat",
  "/skills/":"skill", "/arsenal/":"tools", "/agents/":"agent", "/archive/":"archive",
  "/events/":"flag", "/members/":"people", "/rankings/":"people", "/cellar/":"archive", "/essays/":"quote",
  "/library/":"book", "/quality/":"principle", "/about/":"info",
};
const JOIN_PATH = "/agents/join/";
const primaryPaths = ["/", "/learn/", "/community/", "/skills/"];
const moreGroups = [
  { title: "精读与学堂", paths: ["/readings/", "/agents/"] },
  { title: "资料与往期", paths: ["/arsenal/", "/archive/", "/library/"] },
  { title: "群里的事", paths: ["/events/", "/members/", "/rankings/", "/cellar/", "/essays/"] },
  { title: "了解台账", paths: ["/quality/", "/about/"] },
];

export function NavLinks() {
  const path = usePathname() || "/";
  const [intent, setIntent] = useState<string | null>(null);
  const moreRef = useRef<HTMLDetailsElement>(null);
  const onJoin = path === JOIN_PATH.slice(0, -1) || path.startsWith(JOIN_PATH);
  const isActive = (href: string) => {
    if (href === "/") return path === "/";
    if (href === "/agents/" && onJoin) return false;
    return path === href.slice(0, -1) || path.startsWith(href);
  };
  const warm = (href: string) => {
    const connection = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
    if (connection?.saveData || /(^|-)2g$/.test(connection?.effectiveType ?? "")) return;
    setIntent(href);
  };
  const renderLink = (link: (typeof LINKS)[number]) => {
    const active = isActive(link.href);
    return (
      <Link key={link.href} href={link.href} aria-current={active ? "page" : undefined}
        onClick={() => moreRef.current?.removeAttribute("open")}
        prefetch={!active && intent === link.href ? null : false}
        onPointerEnter={() => warm(link.href)} onFocus={() => warm(link.href)}
        className="nav-link">
        <Icon name={navIcons[link.href]} size={16} /><span>{link.label}</span>
        {link.gated && <svg aria-label="需登录" role="img" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="nav-lock"><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></svg>}
      </Link>
    );
  };
  const moreActive = LINKS.some((link) => !primaryPaths.includes(link.href) && isActive(link.href));
  return (
    <>
      {primaryPaths.map((href) => renderLink(LINKS.find((link) => link.href === href)!))}
      <Link href={JOIN_PATH} aria-current={onJoin ? "page" : undefined}
        onClick={() => moreRef.current?.removeAttribute("open")}
        onPointerEnter={() => warm(JOIN_PATH)} onFocus={() => warm(JOIN_PATH)}
        prefetch={!onJoin && intent === JOIN_PATH ? null : false}
        className="nav-cta">
        <Icon name="agent" size={16} /><span>入驻 Agent</span>
      </Link>
      <details ref={moreRef} className="nav-more"
        onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) event.currentTarget.removeAttribute("open"); }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.currentTarget.removeAttribute("open");
            event.currentTarget.querySelector("summary")?.focus();
          }
        }}>
        <summary className={moreActive ? "nav-more-active" : undefined}>更多<svg aria-hidden width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="m4 6 4 4 4-4" /></svg></summary>
        <div className="nav-more-panel">
          {moreGroups.map((group) => <div className="nav-more-group" key={group.title}><p>{group.title}</p>{group.paths.map((href) => renderLink(LINKS.find((link) => link.href === href)!))}</div>)}
        </div>
      </details>
    </>
  );
}
