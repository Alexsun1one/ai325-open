import Link from "next/link";
import { Suspense } from "react";
import { readDiscovery } from "@/lib/discovery-content";
import { readKnowledge } from "@/lib/knowledge-content";
import { readReadings } from "@/lib/reading-content";
import { getLatestLedger } from "@/lib/content";
import { RssSubscribe } from "@/components/ui/RssSubscribe";
import { LearningDirectory, LearningHero } from "@/components/pages/LearningHero";
import { Icon } from "@/components/ui/Icon";
import { AgentAnswersPreview } from "@/components/pages/AgentAnswersPreview";
import { HomeCommunity } from "@/components/site/HomeCommunity";
import { JourneyInvitation } from "@/components/pages/JourneyInvitation";
import journeyArticle from "../../content/journey/people-need-ai.json";
import styles from "./home.module.css";
import { PlaygroundSpotlight } from "@/components/pages/PlaygroundSpotlight";

export default function Home() {
  const data = readDiscovery();
  const knowledge = readKnowledge();
  const latest = getLatestLedger();
  const readings = readReadings();
  // Collection order breaks review-date ties; no invented popularity ranking.
  const featured = [...readings].sort((a, b) => b.reviewedAt.localeCompare(a.reviewedAt))[0];
  const heroReading = featured ? { title: featured.title, subtitle: featured.subtitle, href: `/readings/${featured.id}/` } : undefined;
  const readingSelections = readings.filter((entry) => entry.id !== featured?.id).slice(0, 2);
  const resourceSelections = data.items.filter((entry) => entry.kind === "resource" && entry.url.startsWith("/arsenal/")).slice(0, 3);

  return (
    <main id="top" className={`site-main ${styles.home}`}>
      <Suspense fallback={<><LearningHero reading={heroReading} /><p role="status" className="py-4 text-sm text-ink-3">正在准备学习目录……</p></>}>
      <LearningDirectory data={data} aside={
        <aside className={styles.aside}>
          <section className={styles.ledger} aria-labelledby="ledger-title">
            <p className={styles.asideLabel}><Icon name="archive" size={16} /> 最近一期蒸馏</p>
            <time className={styles.date} dateTime={latest.date}>{latest.date}</time>
            <h2 id="ledger-title"><Link href={`/ledger/${latest.date}/`}>{latest.title}</Link></h2>
            <p>{latest.lead.replace(/<[^>]*>/g, "")}</p>
            <Link className={styles.readLink} href={`/ledger/${latest.date}/`}>阅读完整一期 <span aria-hidden>→</span></Link>
          </section>
          <section className={styles.provenance} aria-labelledby="provenance-title">
            <h2 id="provenance-title">每条知识，都有来处</h2>
            <p>知识是编辑提炼，资源保留官方来源。日期表示整理或修订时间；技能收录不代表逐项运行验证。</p>
            <p>目录最近内容日期<br /><time dateTime={data.updatedAt} className="num">{data.updatedAt.slice(0, 10)}</time></p>
            <RssSubscribe />
            <a href="/llms.txt">Agent 读取与检索说明 <span aria-hidden>↗</span></a>
          </section>
        </aside>
      }>
      <LearningHero reading={heroReading} />
      <JourneyInvitation title={journeyArticle.title} subtitle={journeyArticle.subtitle} />
      <AgentAnswersPreview />
      <div className={styles.selection}>
        <section className={styles.feature} aria-labelledby="featured-title">
          <div className={styles.sectionHead}>
            <p><Icon name="book" size={17} /> 精选精读</p>
            <Link href="/readings/">全部精读 <span aria-hidden>↗</span></Link>
          </div>
          {featured ? (
            <>
              <p className={styles.meta}>{featured.kind === "book" ? "书籍与文章" : "开源项目"}<span>复核于 <time dateTime={featured.reviewedAt}>{featured.reviewedAt.slice(0, 10)}</time></span></p>
              <h2 id="featured-title"><Link href={`/readings/${featured.id}/`}>{featured.title}</Link></h2>
              <p className={styles.subtitle}>{featured.subtitle}</p>
              <p className={styles.summary}>{featured.summary}</p>
              <div className={styles.featureFoot}>
                <Link className={styles.readLink} href={`/readings/${featured.id}/`}>读懂，再试一次 <span aria-hidden>→</span></Link>
                <a href={featured.source.url}>查看原始来源 <span aria-hidden>↗</span></a>
              </div>
              <ul className={styles.readingSelections} aria-label="更多精选精读">
                {readingSelections.map((entry) => <li key={entry.id}><Link href={`/readings/${entry.id}/`}><h3>{entry.title}<span aria-hidden> ↗</span></h3><p>{entry.subtitle || entry.summary}</p></Link></li>)}
              </ul>
            </>
          ) : (
            <><h2 id="featured-title">从有来源的知识开始</h2><p className={styles.summary}>精读内容正在整理。先选一个主题，查看方法、适用边界与原始出处。</p><Link className={styles.readLink} href="/learn/">进入学习 <span aria-hidden>→</span></Link></>
          )}
        </section>
        <section className={styles.topics} aria-labelledby="topics-title">
          <div className={styles.sectionHead}><h2 id="topics-title">选一个正在关心的问题</h2></div>
          <ul>{knowledge.topics.map((topic) => (
            <li key={topic.id}><Link href={`/learn/topics/${topic.id}/`}>
              <span>{topic.title}<small>{knowledge.entries.filter((entry) => entry.topicId === topic.id).length} 条知识</small></span>
              <span className={styles.topicArrow} aria-hidden>↗</span>
            </Link></li>
          ))}</ul>
          <Link className={styles.questionLink} href="/community/"><Icon name="chat" size={17} /> 带着你的问题来交流 <span aria-hidden>→</span></Link>
        </section>
      </div>
      {resourceSelections.length > 0 && <section className={styles.resources} aria-labelledby="resources-title">
        <div className={styles.sectionHead}><h2 id="resources-title">把想法用起来</h2><Link href="/arsenal/">全部资源 <span aria-hidden>↗</span></Link></div>
        <ul className={styles.resourceGrid}>{resourceSelections.map((entry) => <li key={entry.id}>
          <Link href={entry.url}><h3><Icon name="tools" size={18} />{entry.title}<span aria-hidden>↗</span></h3><p>{entry.summary}</p><span className={styles.resourceAction}>查看用途与来源 →</span></Link>
        </li>)}</ul>
      </section>}
      <HomeCommunity />
      </LearningDirectory>
      </Suspense>
      <PlaygroundSpotlight />
    </main>
  );
}
