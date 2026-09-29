import Link from "next/link";
import { notFound } from "next/navigation";
import { readKnowledge } from "@/lib/knowledge-content";
import { KNOWLEDGE_KINDS } from "@/lib/knowledge";
import { KnowledgeActions } from "@/components/pages/KnowledgeActions";
import { ArticleComments } from "@/components/pages/ArticleComments";
import { ContentEngagement } from "@/components/pages/ContentEngagement";
import { PageShell } from "@/components/pages/PageHead";
import { Icon } from "@/components/ui/Icon";
import styles from "../entry.module.css";

export function generateStaticParams() { return readKnowledge().entries.map(e => ({ id: e.id })); }
export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const entry = readKnowledge().entries.find(e => e.id === id);
  return { title: entry?.title ?? "知识未找到", description: entry?.text.slice(0, 150) };
}

export default async function KnowledgePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = readKnowledge();
  const entry = data.entries.find(e => e.id === id);
  if (!entry) notFound();
  const topic = data.topics.find(t => t.id === entry.topicId)!;
  const related = entry.relatedIds.map(key => data.entries.find(e => e.id === key)).filter(e => !!e);
  const contents = [
    ...(entry.steps.length ? [{ href: "#practice", title: "怎么实践" }] : []),
    { href: "#boundary", title: "适用边界" },
    { href: "#sources", title: "讨论来源" },
    { href: "#question", title: "继续实践" },
    ...(related.length ? [{ href: "#related", title: "接着学" }] : []),
  ];
  const contentsLinks = contents.map(item => <a key={item.href} href={item.href}>{item.title}</a>);
  // 评论日期取最近校订日，缺校订退回最新来源日——不拿今天冒充
  const commentDate =
    entry.revisions.map(r => r.date).filter(d => /^\d{4}-\d{2}-\d{2}$/.test(d)).sort().pop()
    ?? [...entry.sources].sort((a, b) => b.date.localeCompare(a.date))[0]?.date
    ?? "";

  return (
    <PageShell>
      <nav className={styles.breadcrumb} aria-label="当前位置">
        <Link href="/learn/"><Icon name="back" size={16} />知识目录</Link>
        <span aria-hidden="true">/</span>
        <Link href={`/learn/topics/${topic.id}/`}>{topic.title}</Link>
      </nav>
      <header className={styles.heading}>
        <p className={styles.kicker}>
          <Icon name={entry.kind === "insight" ? "quote" : entry.kind} size={18} />
          {KNOWLEDGE_KINDS[entry.kind]}<span>编辑整理 · 可修订</span>
        </p>
        <h1>{entry.title}</h1>
      </header>
      <details className={styles.mobileToc}>
        <summary><Icon name="contents" size={20} />这条知识怎么用</summary>
        <nav aria-label="知识目录">{contentsLinks}</nav>
      </details>
      <div className={styles.layout}>
        <article className={styles.prose}>
          <ContentEngagement kind="knowledge" resourceId={entry.id} commentHref="#article-comments-title" />
          <p className={styles.lead}>{entry.text}</p>
          <div className={styles.actions}><KnowledgeActions entry={entry} /></div>
          {entry.steps.length > 0 && (
            <section id="practice" className={styles.practice}>
              <h2><Icon name="method" size={24} />怎么实践</h2>
              <ol>{entry.steps.map(step => <li key={step}>{step}</li>)}</ol>
            </section>
          )}
          <section id="boundary" className={styles.boundary}>
            <h2>什么时候不适用</h2><p>{entry.counterpoint}</p>
          </section>
          <section id="sources">
            <h2><Icon name="archive" size={24} />从哪些讨论中长出来</h2>
            <p className={styles.note}>以下是编辑归纳的来源，不表示原作者逐字说过本文观点。</p>
            <ol className={styles.sources}>
              {[...entry.sources].sort((a, b) => a.date.localeCompare(b.date)).map(source => (
                <li key={source.date + source.themeTitle}>
                  <time dateTime={source.date}>{source.date}</time>
                  <Link href={`/ledger/${source.date}/`}>{source.themeTitle.replace(/<[^>]*>/g, "")}<Icon name="arrow" size={16} /></Link>
                </li>
              ))}
            </ol>
          </section>
          <section id="question" className={styles.question}>
            <h2><Icon name="chat" size={24} />带着一个问题继续做</h2>
            <p>{entry.question}</p>
            <Link className={styles.discuss} href={`/community/?topic=${entry.id}&title=${encodeURIComponent(entry.question)}`}>
              进入这条知识的讨论 <Icon name="arrow" size={16} />
            </Link>
          </section>
          {related.length > 0 && (
            <section id="related">
              <h2>接着学</h2>
              <ul className={styles.related}>
                {related.map(item => <li key={item.id}><Link href={`/learn/entries/${item.id}/`}>{item.title}<Icon name="arrow" size={16} /></Link></li>)}
              </ul>
            </section>
          )}
          <details className={styles.revisions}>
            <summary>修订记录 · {entry.revisions.length} 次</summary>
            <ul>{entry.revisions.map((revision, i) => <li key={i}><time dateTime={revision.date}>{revision.date}</time> · {revision.note}</li>)}</ul>
          </details>
        </article>
        <aside className={styles.toc}>
          <p><Icon name="contents" size={20} />这条知识怎么用</p>
          <nav aria-label="知识目录">{contentsLinks}</nav>
          <Link className={styles.topicLink} href={`/learn/topics/${topic.id}/`}>
            <span>所属主题</span>{topic.title}<Icon name="arrow" size={16} />
          </Link>
        </aside>
      </div>
      <ArticleComments anchor={`article:knowledge:${entry.id}`} date={commentDate} />
    </PageShell>
  );
}
