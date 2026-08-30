"use client";
import { useEffect } from "react";

/** 静态导出下的导航预取：Next Link 在 output:export 下不执行 RSC prefetch（无服务端端点），
 *  这里补浏览器级 <link rel=prefetch>——nav 链接进入视口或悬停时预取目标页静态 HTML，跳转即命中缓存。 */
export function NavPrefetch() {
  useEffect(() => {
    const seen = new Set<string>();
    const prefetch = (href: string) => {
      if (!href || seen.has(href)) return;
      seen.add(href);
      const l = document.createElement("link");
      l.rel = "prefetch"; l.href = href;
      document.head.appendChild(l);
    };
    const check = () => {
      document.querySelectorAll<HTMLAnchorElement>('a[href]').forEach((a) => {
        const href = a.getAttribute("href") || "";
        if (!href || href.startsWith("http") || href.startsWith("mailto") || href.startsWith("tel") || href.startsWith("#") || href.startsWith("/uploads") || href.startsWith("data:")) return;
        if (a.target && a.target !== "_self") return;
        const r = a.getBoundingClientRect();
        if (r.top < window.innerHeight + 120 && r.bottom > -120) prefetch(href); // 视口内
      });
    };
    const over = (e: Event) => {
      const a = (e.target as HTMLElement).closest?.('a[href]') as HTMLAnchorElement | null;
      if (a) prefetch(a.getAttribute("href") || "");
    };
    check();
    document.addEventListener("mouseover", over);
    window.addEventListener("scroll", check, { passive: true });
    window.addEventListener("resize", check);
    const iv = window.setInterval(check, 3000); // 懒加载补出的区块里的链接也覆盖到
    return () => {
      document.removeEventListener("mouseover", over);
      window.removeEventListener("scroll", check);
      window.removeEventListener("resize", check);
      window.clearInterval(iv);
    };
  }, []);
  return null;
}
