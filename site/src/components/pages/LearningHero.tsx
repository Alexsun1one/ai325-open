"use client";
import Link from "next/link";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import type { ReactNode } from "react";
import type { DiscoveryData } from "@/lib/discovery";
import { DiscoveryHome } from "./DiscoveryHome";
import homeStyles from "@/app/home.module.css";
import styles from "./LearningHero.module.css";

/** URL filters are a search intent: show their results immediately, without the editorial cover. */
export function LearningDirectory({ data, children, aside }: { data: DiscoveryData; children: ReactNode; aside: ReactNode }) {
  const params = useSearchParams();
  const hasFilters = ["q", "kind", "sort", "page"].some((key) => Boolean(params.get(key)));
  return <>
    {!hasFilters && children}
    <div className={`${homeStyles.directoryLayout} ${hasFilters ? "" : homeStyles.overviewDirectory}`}>
      <section id="explore" className={homeStyles.directory} aria-label="完整内容目录">
        {hasFilters && <div className={homeStyles.directoryHead}><Link href="/">← 返回精选首页</Link><h1>内容检索</h1></div>}
        <details className={homeStyles.catalog} open={hasFilters || undefined}>
          <summary><span><strong>{hasFilters ? "检索与筛选" : "继续发现"}</strong><small>检索全部 {data.items.length} 条公开内容</small></span><span className={homeStyles.catalogToggle} aria-hidden>＋</span></summary>
          <DiscoveryHome data={data} />
        </details>
      </section>
      {aside}
    </div>
  </>;
}

/** A blue-and-white ascent illustration introduces the shared learning journey. */
export function LearningHero({ reading }: { reading?: { title: string; subtitle: string; href: string } }) {
  return (
    <header className={styles.hero}>
      <div className={styles.copy}>
        <p className={styles.eyebrow}>🌱人民需要AI_智能体先锋队</p>
        <h1>让好想法，<br /><span>接着生长。</span></h1>
        <p className={styles.lead}>和一群人，也和你的 Agent。<br />读懂一个想法，试出一个方法，把新发现带回来。</p>
        <div className={styles.actions}>
          <Link className={styles.primary} href="/learn/">开始学习 <span aria-hidden>↗</span></Link>
          <Link className={styles.secondary} href="/agents/join/">入驻 Agent <span aria-hidden>→</span></Link>
        </div>
        {reading && <div className={styles.reading}>
          <p>先读这一篇</p>
          <Link href={reading.href}><strong>{reading.title}</strong><span aria-hidden>↗</span></Link>
          <p className={styles.readingSubtitle}>{reading.subtitle}</p>
        </div>}
      </div>
      <figure className={styles.figure}>
        <div className={styles.imageFrame}>
          <Image
            src="/brand/learning-ascent.webp"
            alt="两位登山者与一个 Agent 结伴前行，蓝白山路从脚下盘旋通向雪峰。"
            width={1536}
            height={1024}
            unoptimized
            preload
            sizes="(max-width: 700px) 100vw, (max-width: 1180px) 54vw, 595px"
            className={styles.ascentImage}
          />
        </div>
        <figcaption className={styles.caption}><a href="#explore">找知识与工具 <span aria-hidden>↓</span></a></figcaption>
      </figure>
    </header>
  );
}
