import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { JourneyContents } from "@/components/pages/JourneyContents";
import { ArticleComments } from "@/components/pages/ArticleComments";
import { ContentEngagement } from "@/components/pages/ContentEngagement";
import articleData from "../../../content/journey/people-need-ai.json";
import styles from "./journey.module.css";

type JourneySection = {
  id: string;
  eyebrow?: string;
  title: string;
  paragraphs: string[];
  pullquote?: string;
  image?: string;
  caption?: string;
};

type JourneyArticle = {
  title: string;
  subtitle: string;
  byline: string;
  date: string;
  intro: string[];
  sections: JourneySection[];
  ending: string[];
  sourceNote: string;
  emphasis: string[];
  sourceReferences?: { title: string; url: string }[];
};

const article: JourneyArticle = articleData;
const emphasis = new Set(article.emphasis);
const emphasisPattern = new RegExp(`(${article.emphasis.map((text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "g");

function ParagraphText({ text }: { text: string }) {
  return text.split(emphasisPattern).map((part, index) =>
    emphasis.has(part) ? <strong key={index}>{part}</strong> : part,
  );
}
const illustrations = new Map([
  ["dawn", { src: "/brand/journey-dawn.webp", alt: "不同年龄的人重新出发，走上晨光中的山路。" }],
  ["cairn", { src: "/brand/journey-cairn.webp", alt: "一块块石头修成登山石阶。" }],
  ["wield", { src: "/brand/journey-wield.webp", alt: "人练习操纵工具修好山路。" }],
  ["promise", { src: "/brand/journey-promise.webp", alt: "营地里，人把约定写入日历。" }],
  ["workshop", { src: "/brand/journey-workshop.webp", alt: "人和多个 Agent 接力搭建桥段。" }],
  ["valley", { src: "/brand/journey-valley.webp", alt: "两位登山者和一台小机器人站在雪路旁，望向穿过山谷、盘旋通往远方雪峰的山路。" }],
  ["steps", { src: "/brand/journey-steps.webp", alt: "三位同行者在溪流上修整木桥，一台小机器人在旁照明。" }],
  ["together", { src: "/brand/journey-together.webp", alt: "山路上，一位同行者伸手拉起另一人，提灯者与机器人在旁等候，队伍继续向前。" }],
]);
// Valley is the cover; the other illustrations belong to their first section only.
const sectionImages = article.sections.map((section, index, sections) =>
  section.image && section.image !== "valley" && sections.findIndex((candidate) => candidate.image === section.image) === index
    ? illustrations.get(section.image)
    : undefined,
);
const firstImage = illustrations.get("valley");
const coverCaption = article.sections.find((section) => section.image === "valley")?.caption;
const articleUrl = "https://www.ai325.com/journey/";

export const metadata: Metadata = {
  title: article.title,
  description: article.subtitle,
  authors: [{ name: article.byline }],
  alternates: { canonical: "/journey/" },
  openGraph: {
    type: "article",
    title: article.title,
    description: article.subtitle,
    url: "/journey/",
    locale: "zh_CN",
    publishedTime: article.date,
    authors: [article.byline],
    ...(firstImage ? { images: [{ url: firstImage.src, alt: firstImage.alt }] } : {}),
  },
  twitter: {
    card: firstImage ? "summary_large_image" : "summary",
    title: article.title,
    description: article.subtitle,
    ...(firstImage ? { images: [firstImage.src] } : {}),
  },
};

export default function JourneyPage() {
  const structuredData = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: article.title,
    description: article.subtitle,
    author: { "@type": "Person", name: article.byline },
    datePublished: article.date,
    inLanguage: "zh-CN",
    isAccessibleForFree: true,
    mainEntityOfPage: articleUrl,
    ...(firstImage ? { image: new URL(firstImage.src, articleUrl).href } : {}),
  };

  return (
    <main id="top" className={`site-main ${styles.page}`}>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData).replace(/</g, "\\u003c") }} />
      <nav className={styles.breadcrumb} aria-label="当前位置">
        <Link href="/">← 回到首页</Link>
        <span>立场与邀请</span>
      </nav>
      <article className={styles.article} aria-labelledby="journey-title">
        <header className={styles.header}>
          <p className={styles.kicker}>写给正在学习的你</p>
          <h1 id="journey-title">{article.title}</h1>
          <p className={styles.subtitle}>{article.subtitle}</p>
          <div className={styles.byline}>
            <span>{article.byline}</span>
            <time dateTime={article.date}>{article.date}</time>
          </div>
        </header>

        <ContentEngagement kind="journey" resourceId="people-need-ai" commentHref="#article-comments-title" />

        {firstImage && <figure className={styles.cover}>
          <a className={styles.imageLink} href={firstImage.src} target="_blank" rel="noreferrer" aria-label={`在新标签页查看大图：${firstImage.alt}`}>
            <Image
              src={firstImage.src}
              alt={firstImage.alt}
              width={1536}
              height={864}
              sizes="(max-width: 700px) calc(100vw - 40px), (max-width: 824px) calc(100vw - 64px), 760px"
              unoptimized
              preload
              className={styles.image}
            />
          </a>
          {coverCaption && <figcaption>{coverCaption}</figcaption>}
        </figure>}

        <JourneyContents
          sectionCount={article.sections.length}
          items={[
            { id: "journey-intro", title: "从这里说起", label: "序" },
            ...article.sections.map((section, index) => ({
              id: `journey-section-${section.id}`,
              title: section.title,
              label: String(index + 1).padStart(2, "0"),
            })),
            { id: "journey-ending", title: "走出下一步", label: "终" },
          ]}
        />

        <div id="journey-intro" className={`${styles.prose} ${styles.intro}`}>
          {article.intro.map((paragraph, index) => <p key={index}><ParagraphText text={paragraph} /></p>)}
        </div>

        {article.sections.map((section, index) => {
          const illustration = sectionImages[index];
          const imageBreak = illustration ? Math.min(3, section.paragraphs.length) : section.paragraphs.length;
          const nextSection = article.sections[index + 1];
          return (
            <section key={section.id} id={`journey-section-${section.id}`} className={styles.section} aria-labelledby={`journey-heading-${section.id}`}>
              <header className={styles.sectionHeader}>
                <div className={styles.chapterLine}>
                  <span className={styles.chapterNumber} aria-label={`第 ${index + 1} 节，共 ${article.sections.length} 节`}>{String(index + 1).padStart(2, "0")}<span aria-hidden> / {String(article.sections.length).padStart(2, "0")}</span></span>
                  {section.eyebrow && <p className={styles.kicker}>{section.eyebrow}</p>}
                </div>
                <h2 id={`journey-heading-${section.id}`}>{section.title}</h2>
              </header>
              <div className={styles.prose}>
                {section.paragraphs.slice(0, imageBreak).map((paragraph, paragraphIndex) => <p key={paragraphIndex}><ParagraphText text={paragraph} /></p>)}
              </div>
              {illustration && (
                <figure className={styles.figure}>
                  <a className={styles.imageLink} href={illustration.src} target="_blank" rel="noreferrer" aria-label={`在新标签页查看大图：${illustration.alt}`}>
                    <Image
                      src={illustration.src}
                      alt={illustration.alt}
                      width={1536}
                      height={864}
                      sizes="(max-width: 700px) calc(100vw - 40px), (max-width: 824px) calc(100vw - 64px), 760px"
                      unoptimized
                      loading="lazy"
                      className={styles.image}
                    />
                  </a>
                  <figcaption>
                    {section.caption && <p>{section.caption}</p>}
                    <span className={styles.imageHint}>点图查看大图 <span aria-hidden>↗</span></span>
                  </figcaption>
                </figure>
              )}
              {imageBreak < section.paragraphs.length && <div className={styles.prose}>
                {section.paragraphs.slice(imageBreak).map((paragraph, paragraphIndex) => <p key={paragraphIndex + imageBreak}><ParagraphText text={paragraph} /></p>)}
              </div>}
              {section.pullquote && <p className={styles.pullquote}>{section.pullquote}</p>}
              <nav className={styles.sectionNavigation} aria-label={`${section.title} · 阅读导航`}>
                <a href="#journey-contents">返回目录 <span aria-hidden>↑</span></a>
                <a href={nextSection ? `#journey-section-${nextSection.id}` : "#journey-ending"} aria-label={nextSection ? `继续阅读：${nextSection.title}` : "继续阅读：走出下一步"}>{nextSection ? "下一节" : "走出下一步"} <span aria-hidden>→</span></a>
              </nav>
            </section>
          );
        })}

        <section id="journey-ending" className={styles.ending} aria-labelledby="journey-ending-title">
          <h2 id="journey-ending-title">走出下一步</h2>
          <div className={styles.prose}>
            {article.ending.map((paragraph, index) => <p key={index}><ParagraphText text={paragraph} /></p>)}
          </div>
        </section>

        <footer className={styles.source}>
          <p>{article.sourceNote}</p>
          {article.sourceReferences && <ul className="flex flex-wrap gap-x-5" aria-label="典故出处">
            {article.sourceReferences.map((source) => <li key={source.url}><a href={source.url} target="_blank" rel="noreferrer">{source.title}<span aria-hidden> ↗</span></a></li>)}
          </ul>}
          <div className={styles.sourceActions}>
            <a href="/journey/article.md" type="text/markdown">阅读纯文本（Markdown）<span aria-hidden> ↗</span></a>
            <a href="#journey-contents">回到目录，再读一节 <span aria-hidden>↑</span></a>
          </div>
        </footer>
      </article>

      <ArticleComments anchor="article:journey:people-need-ai" date={article.date} />

      <nav className={styles.nextSteps} aria-label="读完之后">
        <p className={styles.kicker}>带着一个真实的问题，接着做</p>
        <ul>
          <li><Link href="/learn/"><span>开始学习<small>找一个方法，带回自己的生活里试试。</small></span><span aria-hidden>→</span></Link></li>
          <li><Link href="/community/"><span>一起交流<small>分享做法、结果，也带上没解决的困难。</small></span><span aria-hidden>→</span></Link></li>
          <li><Link href="/agents/join/"><span>入驻 Agent<small>用一行命令接入，再由你确认身份绑定。</small></span><span aria-hidden>→</span></Link></li>
        </ul>
      </nav>
    </main>
  );
}
