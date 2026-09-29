"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import styles from "@/app/home.module.css";

export function JourneyInvitation({ title, subtitle }: { title: string; subtitle: string }) {
  const entryRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const entry = entryRef.current;
    if (!entry || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const observer = new IntersectionObserver(([observed]) => {
      if (observed.isIntersecting) {
        entry.dataset.visible = "true";
        observer.disconnect();
      }
    }, { threshold: 0.6 });
    observer.observe(entry);
    return () => observer.disconnect();
  }, []);

  return <section ref={entryRef} className={styles.journeyEntry} aria-labelledby="journey-entry-title">
    <div>
      <p className={styles.journeyLabel}>写给正在学习的你</p>
      <h2 id="journey-entry-title"><Link href="/journey/"><span className={styles.journeyTitle}>{title}</span><span className={styles.journeyArrow} aria-hidden>→</span></Link></h2>
    </div>
    <p className={styles.journeySummary}>{subtitle}</p>
  </section>;
}
