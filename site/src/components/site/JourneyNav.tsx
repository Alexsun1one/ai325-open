"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
const steps = [
  { href: "/", label: "发现内容", match: ["/skills", "/arsenal"] },
  { href: "/learn/", label: "理解与学习", match: ["/learn", "/readings"] },
  { href: "/community/", label: "实践与交流", match: ["/community"] },
  { href: "/agents/", label: "带 Agent 一起", match: ["/agents"] },
];
export function JourneyNav() {
  const path = usePathname() || "/";
  if (path === "/" || !steps.some(s => s.match.some(m => path.startsWith(m)))) return null;
  return <nav className="journey-nav no-print" aria-label="共同学习路径">
    {steps.map((step, i) => <Link key={step.href} href={step.href} prefetch={false} aria-current={step.match.some(m => path.startsWith(m)) ? "step" : undefined}>
      <span className="journey-number" aria-hidden>{String(i + 1).padStart(2, "0")}</span>{step.label}
      {i < steps.length - 1 && <span className="journey-arrow" aria-hidden>→</span>}
    </Link>)}
  </nav>;
}
