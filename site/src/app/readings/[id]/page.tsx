import Link from "next/link";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PageShell } from "@/components/pages/PageHead";
import { ArticleComments } from "@/components/pages/ArticleComments";
import { ReadingActions } from "@/components/pages/ReadingActions";
import { ContentEngagement } from "@/components/pages/ContentEngagement";
import { RichMessage } from "@/components/ui/RichMessage";
import article from "./article.module.css";
import { Icon } from "@/components/ui/Icon";
import { readReadings } from "@/lib/reading-content";
import styles from "../readings.module.css";

export const dynamicParams = false;
export function generateStaticParams() { return readReadings().map(e => ({ id: e.id })); }
export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const entry = readReadings().find(e => e.id === id);
  return { title: entry?.title ?? "导读未找到", description: entry?.summary };
}

export default async function ReadingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const entry = readReadings().find(e => e.id === id);
  if (!entry) notFound();
  const contents = [
    { href: "#takeaways", title: "核心判断" },
    ...entry.sections.map((section, i) => ({ href: `#section-${i}`, title: section.title })),
    { href: "#practice", title: "动手实践" },
    { href: "#boundary", title: "适用边界" },
  ];
  const contentsLinks = contents.map(item => <a key={item.href} href={item.href}>{item.title}</a>);
  // 评论日期取真实复核日，不拿今天冒充发表日
  const commentDate = /^\d{4}-\d{2}-\d{2}/.exec(entry.reviewedAt)?.[0] ?? entry.reviewedAt.slice(0, 10);

  return (
    <PageShell>
      <nav className={styles.breadcrumb} aria-label="当前位置">
        <Link href="/readings/"><Icon name="back" size={16} />书与代码精读</Link>
        <span>{entry.kind === "book" ? "书与长文" : "仓库拆解"}</span>
      </nav>
      <header className={styles.articleHead}>
        <p className={styles.kicker}><Icon name={entry.kind === "book" ? "book" : "skill"} size={18} />{entry.tags.join(" / ")}</p>
        <h1>{entry.title}</h1>
        <p className={styles.deck}>{entry.subtitle}</p>
        <div className={styles.byline}>
          <span>编辑整理 · 可修订</span>
          <time dateTime={entry.reviewedAt}>复核 {entry.reviewedAt}</time>
          <a href={entry.source.url} target="_blank" rel="noreferrer">查看原始来源 <Icon name="external" size={16} /></a>
        </div>
      </header>
      <details className={styles.mobileToc}>
        <summary><Icon name="contents" size={20} />这篇怎么读</summary>
        <nav aria-label="文章目录">{contentsLinks}</nav>
      </details>
      <div className={styles.articleLayout}>
        <article className={styles.prose}>
          <ContentEngagement kind="reading" resourceId={entry.id} commentHref="#article-comments-title" />
          <ReadingActions kind="reading" resourceId={entry.id} />
          <p className={styles.abstract}>{entry.summary}</p>
          <section id="takeaways">
            <h2>先带走这几个判断</h2>
            <ol className={styles.takeaways}>
              {entry.takeaways.map((takeaway, i) => <li key={i}><span aria-hidden="true">{String(i + 1).padStart(2, "0")}</span><p>{takeaway}</p></li>)}
            </ol>
          </section>
          {entry.sections.map((section, i) => (
            <section id={`section-${i}`} key={section.title}>
              <h2>{section.title}</h2>
              <RichMessage text={section.body} className={article.body} />
            </section>
          ))}
          <section id="practice" className={styles.practice}>
            <p className={styles.kicker}><Icon name="flag" size={18} />把阅读变成一次实践</p>
            <h2>{entry.exercise.title}</h2>
            <ol>{entry.exercise.steps.map((step, i) => <li key={i}>{step}</li>)}</ol>
            <Link className={article.practiceLink} href={`/me/?view=mine&reading=${entry.id}`}>开始这次练习 <Icon name="arrow" size={16} /></Link>
          </section>
          <section id="boundary"><h2>什么时候需要保留判断</h2><p>{entry.caveat}</p></section>
          <section className={styles.next}>
            <Icon name="chat" size={24} />
            <div>
              <h2>带着结果，接着讨论</h2>
              <p>记录你的做法、结果和反例，让下一位读者有依据可循。</p>
              <Link href={`/community/?q=${encodeURIComponent(entry.title)}`}>去交流区分享实践 <Icon name="arrow" size={16} /></Link>
              {entry.relatedTopic && <Link href={`/learn/topics/${entry.relatedTopic}/`}>阅读相关知识主题 <Icon name="arrow" size={16} /></Link>}
            </div>
          </section>
        </article>
        <aside className={styles.toc}>
          <p><Icon name="contents" size={20} />这篇怎么读</p>
          <nav aria-label="文章目录">{contentsLinks}</nav>
          <div className={styles.source}>
            <Icon name="archive" size={20} />
            <p>{entry.source.title}</p>
            <a href={entry.source.url} target="_blank" rel="noreferrer">核对来源 <Icon name="external" size={16} /></a>
          </div>
        </aside>
      </div>
      <ArticleComments anchor={`article:reading:${entry.id}`} date={commentDate} />
    </PageShell>
  );
}
