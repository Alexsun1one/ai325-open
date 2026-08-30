"use client";
import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";

/** 路由切换的顶部细进度条：琥珀 2px 细线（酒液色，不是默认蓝）。
 *  站内链接点击 → 启动伪进度；usePathname 变化（导航完成）→ 走满渐隐。 */
export function RouteProgress() {
  const [w, setW] = useState(0);
  const [show, setShow] = useState(false);
  const path = usePathname();
  const prev = useRef(path);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    if (prev.current !== path) {
      prev.current = path;
      setW(100);
      timers.current.push(setTimeout(() => { setShow(false); setW(0); }, 300));
    }
  }, [path]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      const a = (e.target as HTMLElement).closest?.('a[href]') as HTMLAnchorElement | null;
      if (!a) return;
      const href = a.getAttribute("href") || "";
      if (!href || href.startsWith("http") || href.startsWith("mailto") || href.startsWith("tel") || href.startsWith("#") || href.startsWith("/uploads")) return;
      if (a.target && a.target !== "_self") return;
      if (a.hasAttribute("download")) return;
      // 站内导航：启动伪进度（导航完成由 usePathname 收尾）
      timers.current.forEach(clearTimeout); timers.current = [];
      setShow(true); setW(8);
      timers.current.push(setTimeout(() => setW(55), 60));
      timers.current.push(setTimeout(() => setW(88), 420));
    };
    document.addEventListener("click", onClick, true);
    return () => { document.removeEventListener("click", onClick, true); timers.current.forEach(clearTimeout); };
  }, []);

  if (!show) return null;
  return (
    <div data-route-progress aria-hidden className="pointer-events-none fixed inset-x-0 top-0 z-[100] h-[2px]">
      <div className="h-full bg-amber transition-[width] duration-300 ease-[var(--ease-out-expo)]" style={{ width: `${w}%`, boxShadow: "0 0 6px var(--amber)" }} />
    </div>
  );
}
