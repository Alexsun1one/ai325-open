"use client";

import { useEffect, useState } from "react";
import type { ExternalCuration } from "@/lib/external-curation";
import styles from "./sources.module.css";

const statusText = { ok: "本轮精选已完成", partial: "部分资料仍待处理", budget_limited: "本轮处理额度已用完，余下资料待续", failed: "本轮更新未完成，保留上次内容" };
const editionText = { in_progress: "今日持续更新", complete: "已成刊", partial: "尚有资料待处理" };
function time(value: string | null) {
  return value ? new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value)) : "尚未完成首轮";
}

export function CuratedBoard({ data }: { data: ExternalCuration | null }) {
  const [view, setView] = useState<"digest" | "hot">("digest");
  const [day, setDay] = useState(data?.editions.find(e => e.items.length > 0)?.date ?? data?.editions[0]?.date ?? "");
  const [focusedEvent, setFocusedEvent] = useState("");
  useEffect(() => {
    const apply = () => {
      const id = window.location.hash.slice(1);
      if (data?.events.some(e => e.id === id)) { setFocusedEvent(id); setView("hot"); }
    };
    apply(); window.addEventListener("hashchange", apply);
    return () => window.removeEventListener("hashchange", apply);
  }, [data]);
  useEffect(() => {
    if (view === "hot" && focusedEvent) document.getElementById(focusedEvent)?.scrollIntoView({ block: "start" });
  }, [view, focusedEvent]);
  const edition = data?.editions.find(e => e.date === day);
  const events = data?.events.filter(e => e.heat > 0 || e.id === focusedEvent) ?? [];
  const hotCount = data?.events.filter(e => e.heat > 0).length ?? 0;
  const showingArchive = data?.events.some(e => e.id === focusedEvent && e.heat === 0) ?? false;
  return <section className={styles.curated} aria-labelledby="curated-title">
    <header className={styles.heading}>
      <p className={styles.eyebrow}>公开资料 · 自动精选 · 原文可查</p>
      <h1 id="curated-title">值得跟进的 AI 进展</h1>
      <p className={styles.intro}>先读发生了什么，再沿出处核对。多篇报道归到同一事件，新的进展单独跟进。</p>
    </header>
    {!data ? <p className={styles.notice}>首轮精选尚未完成。下方可以先阅读已采集的原始来源。</p> : <>
      <div className={styles.edition}>
        <span>{statusText[data.run.status]}</span>
        <span>最近尝试 {time(data.run.attemptedAt)} · 最近完整更新 {time(data.lastSuccessAt)}（北京时间）</span>
        <a href="/data/external-curated.json">读取公开数据</a>
      </div>
      {data.run.status !== "ok" && <p className={styles.notice} role="status">当前展示已通过筛选的内容。待处理 {data.run.counts.pending ?? 0} 条，处理失败 {data.run.counts.failed ?? 0} 条，采集异常 {data.run.failedSources} 个来源；未完成的资料不会作为精选发布。</p>}
      <div className={styles.curationTools}>
        <div className={styles.filter} aria-label="精选视图">
          <button className={styles.filterLink} aria-pressed={view === "digest"} onClick={() => setView("digest")}>每日精选</button>
          <button className={styles.filterLink} aria-pressed={view === "hot"} onClick={() => setView("hot")}>近期热点 <span className={styles.count}>{hotCount}</span></button>
        </div>
        {view === "digest" && <label>阅读日期 <select value={day} onChange={e => setDay(e.target.value)}>{data.editions.map(e => <option key={e.date} value={e.date}>{e.date} · {editionText[e.status]}</option>)}</select></label>}
      </div>
      {view === "digest" ? <div>
        <h2 className={styles.curationTitle}>{edition ? `${edition.date} · ${editionText[edition.status]}` : "暂无成刊"}</h2>
        {edition && <p className={styles.about}>本期 {edition.total} 个事件{edition.total > edition.items.length ? `，展示前 ${edition.items.length} 条` : ""}。{edition.revision > 1 ? `第 ${edition.revision} 版，内容或处理状态有更新。` : ""}</p>}
        {!edition?.items.length ? <p className={styles.noItems}>这一天暂时没有通过标准的新事件或新进展。可切换日期，或阅读下方原始来源。</p> : <ol className={styles.articles}>{edition.items.map((item, i) => <li className={styles.article} key={item.reportId}>
          <div className={styles.date}>{String(i + 1).padStart(2, "0")} / {item.development ? "后续进展" : "新事件"}</div>
          <div className={styles.articleBody}>
            <h3><a href={item.url} target="_blank" rel="noreferrer">{item.title} <span className={styles.arrow} aria-hidden>↗</span></a></h3>
            <p className={styles.fullSummary}>{item.summary}</p>
            <div className={styles.readReason}>{item.reason}</div>
            <a className={styles.original} href={item.url} target="_blank" rel="noreferrer">阅读 {item.sourceName} 原文</a>
            {data.events.some(e => e.id === item.eventId) && <a className={styles.related} href={`#${item.eventId}`} onClick={() => { setFocusedEvent(item.eventId); setView("hot"); }}>查看事件出处</a>}
          </div>
        </li>)}</ol>}
      </div> : <div>
        <h2 className={styles.curationTitle}>{showingArchive ? "事件出处与近期热点" : `最近 ${data.rules.hotWindowHours} 小时的热点`}</h2>
        <p className={styles.about}>按独立发布方的报道计算，同一家只计一次，权重每 {data.rules.hotHalfLifeHours} 小时减半。热度代表报道覆盖，收录不代表效果实测。</p>
        {!events.length && <p className={styles.noItems}>当前窗口内暂无通过筛选的热点。历史内容仍可在每日精选中阅读。</p>}
        <ol className={styles.articles}>{events.map((event, i) => <li className={styles.article} id={event.id} key={event.id}>
          <div className={styles.date}>{String(i + 1).padStart(2, "0")} / {event.heat === 0 ? "历史事件" : event.trend === "new" ? "新出现" : event.trend === "rising" ? "关注上升" : "持续关注"}<br />{time(event.updatedAt)}</div>
          <div className={styles.articleBody}>
            <h3>{event.title}</h3><p className={styles.fullSummary}>{event.summary}</p>
            <div className={styles.readReason}>{event.independentSources} 个独立发布方 · 热度 {event.heat.toFixed(2)}</div>
            <details className={styles.evidence}>
              <summary>查看 {event.reports.length} 篇报道与依据</summary>
              <ul>{event.reports.map(r => <li key={r.id}>
                <a href={r.url} target="_blank" rel="noreferrer">{r.sourceName} · {r.originalTitle} ↗</a>
                <small>{time(r.publishedAt)} · {r.relation === "development" ? "后续进展" : "事件报道"} · 两次评分 {r.scores.join(" / ")}</small>
                {r.evidenceQuotes.map(q => <blockquote key={q}>{q}</blockquote>)}
              </li>)}</ul>
            </details>
          </div>
        </li>)}</ol>
      </div>}
    </>}
    <a className={styles.original} href="#raw-sources">查看全部原始来源 ↓</a>
  </section>;
}
