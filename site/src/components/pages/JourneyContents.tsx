"use client";

import { useEffect, useRef, useState } from "react";
import styles from "./JourneyContents.module.css";

type ContentsItem = { id: string; title: string; label: string };

export function JourneyContents({ items, sectionCount }: { items: ContentsItem[]; sectionCount: number }) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const railNav = useRef<HTMLElement>(null);

  useEffect(() => {
    // Links work without this enhancement. Only observation updates the current section.
    if (!("IntersectionObserver" in window)) return;
    const targets = items.flatMap((item) => {
      const element = document.getElementById(item.id);
      return element ? [{ id: item.id, element }] : [];
    });
    if (!targets.length) return;

    let observer: IntersectionObserver | undefined;
    let frame = 0;
    let readingLine = 0;
    const update = () => {
      frame = 0;
      let current = targets[0].id;
      for (const target of targets) {
        if (target.element.getBoundingClientRect().top <= readingLine + 1) current = target.id;
        else break;
      }
      setActiveId(current);
    };
    const schedule = () => {
      if (!frame) frame = window.requestAnimationFrame(update);
    };
    const observe = () => {
      observer?.disconnect();
      const viewportHeight = Math.max(4, document.documentElement.clientHeight);
      const headerHeight = Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--nav-h")) || 110;
      const top = Math.min(headerHeight + 24, Math.max(0, viewportHeight - 2));
      readingLine = Math.min(viewportHeight - 2, top + Math.min(160, (viewportHeight - top) / 4));
      observer = new IntersectionObserver(schedule, {
        rootMargin: `-${top}px 0px -${Math.max(0, viewportHeight - readingLine)}px 0px`,
        threshold: 0,
      });
      targets.forEach(({ element }) => observer?.observe(element));
      schedule();
    };

    observe();
    window.addEventListener("resize", observe);
    window.addEventListener("hashchange", schedule);
    window.addEventListener("pageshow", schedule);
    const resizeObserver = typeof ResizeObserver === "undefined" ? undefined : new ResizeObserver(schedule);
    const article = targets[0].element.closest("article");
    if (article) resizeObserver?.observe(article);
    return () => {
      observer?.disconnect();
      resizeObserver?.disconnect();
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", observe);
      window.removeEventListener("hashchange", schedule);
      window.removeEventListener("pageshow", schedule);
    };
  }, [items]);

  useEffect(() => {
    const nav = railNav.current;
    if (!nav || !nav.getClientRects().length) return;
    const current = nav.querySelector<HTMLElement>('a[aria-current="location"]');
    // Scroll only the directory, never the document or keyboard focus.
    if (!current || nav.contains(document.activeElement)) return;
    const linkRect = current.getBoundingClientRect();
    const navRect = nav.getBoundingClientRect();
    if (linkRect.top < navRect.top) nav.scrollTop -= navRect.top - linkRect.top;
    else if (linkRect.bottom > navRect.bottom) nav.scrollTop += linkRect.bottom - navRect.bottom;
  }, [activeId]);

  const activeItem = items.find((item) => item.id === activeId);
  const links = (
    <ol className={styles.list}>
      {items.map((item) => (
        <li key={item.id}>
          <a href={`#${item.id}`} aria-current={activeId === item.id ? "location" : undefined}>
            <span className={styles.number} aria-hidden="true">{item.label}</span>
            <span>{item.title}</span>
          </a>
        </li>
      ))}
    </ol>
  );

  return (
    <div id="journey-contents" className={styles.root}>
      <details className={styles.mobile}>
        <summary>文章目录<span>{sectionCount} 个小节，展开选读</span></summary>
        <nav aria-label="文章目录">{links}<a className={styles.back} href="#top">返回顶部 <span aria-hidden="true">↑</span></a></nav>
      </details>
      <aside className={styles.rail} aria-label="阅读目录">
        <div className={styles.sticky}>
          <div className={styles.heading}>
            <h2>文章目录</h2>
            <span>{sectionCount} 个小节</span>
          </div>
          <p className={styles.current}><span>{activeItem ? "当前位置" : "从这里选读"}</span>{activeItem?.title ?? "沿着目录，找到你关心的一节。"}</p>
          <nav ref={railNav} className={styles.railNav} aria-label="文章目录">{links}</nav>
          <a className={styles.back} href="#top">返回顶部 <span aria-hidden="true">↑</span></a>
        </div>
      </aside>
    </div>
  );
}
