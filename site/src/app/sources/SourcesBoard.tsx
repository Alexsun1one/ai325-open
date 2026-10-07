"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/ui/Icon";
import type { ExternalItem, ExternalSource, ExternalSourcesData } from "@/lib/external-sources";
import styles from "./sources.module.css";

function timestamp(value: string | null) {
  if (!value) return "尚无记录";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function dateLabel(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}

function statusLabel(source: ExternalSource) {
  if (source.status === "ok") return "已采集";
  if (source.lastSuccessAt) return "更新暂缓";
  return "暂未采到";
}

function sourceFromHash(hash: string, sources: ExternalSource[], items: ExternalItem[]) {
  const id = hash.replace(/^#/, "");
  if (!id || id === "sources-index") return "all";
  const bySection = sources.find((source) => source.id === id || `source-${source.id}` === id);
  if (bySection) return bySection.id;
  const item = items.find((entry) => entry.id === id);
  return item ? item.sourceId : "all";
}

export function SourcesBoard({ data }: { data: ExternalSourcesData }) {
  const [active, setActive] = useState("all");
  const counts = useMemo(() => {
    const map = new Map<string, number>();
    for (const item of data.items) map.set(item.sourceId, (map.get(item.sourceId) ?? 0) + 1);
    return map;
  }, [data.items]);

  useEffect(() => {
    const apply = () => {
      const next = sourceFromHash(window.location.hash, data.sources, data.items);
      setActive(next);
      const raw = window.location.hash.slice(1);
      if (!raw || raw === "sources-index") return;
      const node = document.getElementById(raw);
      if (node) requestAnimationFrame(() => node.scrollIntoView({ block: "start" }));
    };
    apply();
    window.addEventListener("hashchange", apply);
    return () => window.removeEventListener("hashchange", apply);
  }, [data.items, data.sources]);

  const select = (id: string) => {
    setActive(id);
    const next = id === "all" ? "/sources/" : `/sources/#source-${id}`;
    window.history.replaceState(null, "", next);
  };

  if (data.sources.length === 0) {
    return (
      <section className={styles.empty} aria-labelledby="empty-title">
        <h2 id="empty-title">公开来源正在整理</h2>
        <p>完成首次采集后，文章和来源状态会出现在这里。</p>
        <Link href="/readings/">先去读书与代码精读 <span aria-hidden>→</span></Link>
      </section>
    );
  }

  return (
    <>
      <header className={styles.heading}>
        <p className={styles.eyebrow}>公开资料 · 不是群聊</p>
        <h1>外部知识来源</h1>
        <p className={styles.intro}>研究、工程与产品的公开更新。标题和摘要留在这里，核对请回原文。</p>
        <div className={styles.edition}>
          <span>{data.sources.length} 个来源 · {data.items.length} 条收录</span>
          <span>最近采集 {timestamp(data.updatedAt)}（北京时间）</span>
          <Link href="/">返回发现 <Icon name="arrow" size={14} /></Link>
        </div>
      </header>

      <div className={styles.layout} id="sources-index">
        <aside className={styles.sidebar} aria-label="来源筛选与采集状态">
          <h2>按来源看</h2>
          <div className={styles.filter} role="group" aria-label="按来源筛选">
            <button
              type="button"
              className={styles.filterLink}
              aria-pressed={active === "all"}
              onClick={() => select("all")}
            >
              <span>全部来源</span>
              <span className={styles.count}>{data.items.length}</span>
            </button>
            {data.sources.map((source) => (
              <button
                type="button"
                className={styles.filterLink}
                key={source.id}
                aria-pressed={active === source.id}
                onClick={() => select(source.id)}
              >
                <span>{source.name}</span>
                <span className={styles.count}>{counts.get(source.id) ?? 0}</span>
                <small>{statusLabel(source)}</small>
              </button>
            ))}
          </div>
          <p className={styles.about}>
            这些是公开外部来源的索引。群内讨论的当天整理在
            <Link href="/archive/">往期</Link>
            ，不是原始聊天。
          </p>
          <a className={styles.dataset} href="/data/external-knowledge.json">查看公开数据 <Icon name="arrow" size={14} /></a>
        </aside>

        <div className={styles.content}>
          {data.sources.map((source) => {
            const items = data.items.filter((item) => item.sourceId === source.id);
            const visible = active === "all" || active === source.id;
            return (
              <section
                className={styles.sourceSection}
                key={source.id}
                id={`source-${source.id}`}
                hidden={!visible}
                aria-labelledby={`title-${source.id}`}
              >
                <header className={styles.sourceHead}>
                  <div>
                    <p className={styles.sourceLabel}>
                      {source.tags.join(" · ")} · {statusLabel(source)}
                    </p>
                    <h2 id={`title-${source.id}`}>{source.name}</h2>
                  </div>
                  <a href={source.homepage} target="_blank" rel="noopener noreferrer">
                    访问原站 <Icon name="arrow" size={16} />
                  </a>
                </header>
                {source.status === "failed" && (
                  <p className={styles.notice}>
                    {source.lastSuccessAt
                      ? `这个来源本次未能更新，下方保留最近一次收录。最近成功采集：${timestamp(source.lastSuccessAt)}。`
                      : "这个来源暂时未能采集，仍可前往原站阅读。"}
                  </p>
                )}
                {items.length === 0 ? (
                  <p className={styles.noItems}>暂时没有可展示的条目。</p>
                ) : (
                  <ol className={styles.articles}>
                    {items.map((item) => (
                      <li key={item.id} id={item.id} className={styles.article}>
                        <div className={styles.date}>
                          {item.publishedAt
                            ? <time dateTime={item.publishedAt}>{dateLabel(item.publishedAt)}</time>
                            : <span>未提供发布时间</span>}
                        </div>
                        <div className={styles.articleBody}>
                          <h3>
                            <a href={item.canonicalUrl} target="_blank" rel="noopener noreferrer">
                              {item.title}
                              <span aria-hidden className={styles.arrow}>↗</span>
                            </a>
                          </h3>
                          {item.summary && <p>{item.summary}</p>}
                          <a className={styles.original} href={item.canonicalUrl} target="_blank" rel="noopener noreferrer">
                            阅读原文 <Icon name="arrow" size={14} />
                          </a>
                        </div>
                      </li>
                    ))}
                  </ol>
                )}
              </section>
            );
          })}
        </div>
      </div>
    </>
  );
}
