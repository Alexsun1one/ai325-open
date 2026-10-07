"use client";
import Link from "next/link";
import { useState } from "react";
import { useReadingState } from "@/lib/reading-state";
import { KNOWLEDGE_KINDS, type KnowledgeData } from "@/lib/knowledge";
import { Icon } from "@/components/ui/Icon";
import motion from "./motion.module.css";
const control = "min-h-11 rounded-md border border-rule bg-paper px-3 font-sans text-[14px] text-ink";
const plain = (text: string) => text.replace(/<[^>]*>/g, "");
export function KnowledgeGarden({ data }: { data: KnowledgeData }) {
  const reading = useReadingState();
  const [savedOnly, setSavedOnly] = useState(false);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [topic, setTopic] = useState("");
  const [kind, setKind] = useState("");
  const [query, setQuery] = useState("");
  const entries = data.entries.filter(item => (!savedOnly || reading.saved.includes(item.id)) && (!unreadOnly || !reading.read.includes(item.id)) && (!topic || topic === item.topicId) && (!kind || kind === item.kind) &&
    `${item.title} ${item.text} ${item.steps.join(" ")}`.toLowerCase().includes(query.trim().toLowerCase()));
  const reset = () => { setTopic(""); setKind(""); setQuery(""); setSavedOnly(false); setUnreadOnly(false); };
  const byId = new Map(data.entries.map(entry => [entry.id, entry]));
  const countOf = (id: string) => data.entries.filter(entry => entry.topicId === id).length;
  const kindIcon = { insight: "quote", method: "method", principle: "principle" } as const;
  return <div>
    <details className="mb-4 border-y border-rule"><summary className="flex min-h-11 cursor-pointer items-center text-[14px] text-blue-text">按主题深入学习 · {data.topics.length} 个主题</summary><nav aria-label="学习主题路线" className="flex flex-wrap gap-x-6 gap-y-1 pb-2">
      {data.topics.map(t => (
        <Link key={t.id} href={`/learn/topics/${t.id}/`} className={`group inline-flex min-h-11 items-baseline gap-2 text-[14px] ${motion.pressable}`}>
          <span className="text-blue-text group-hover:underline">{t.title} →</span>
          <span className="num text-[12px] text-ink-3">{countOf(t.id)} 条</span>
        </Link>
      ))}
    </nav></details>
    <label className="grid gap-2 text-[13px] text-ink-2">想弄明白什么？<input className={control} value={query} onChange={e => setQuery(e.target.value)} placeholder="搜问题、方法、金句" type="search" /></label>
    <details className="mt-2"><summary className="flex min-h-11 cursor-pointer items-center text-[13px] text-blue-text">筛选与阅读状态{(topic || kind || savedOnly || unreadOnly) ? " · 已启用筛选" : ""}</summary>
    <div className="grid items-end gap-3 sm:grid-cols-2">
      <label className="grid gap-2 text-[13px] text-ink-2">学习主题<select className={control} value={topic} onChange={e => setTopic(e.target.value)}><option value="">全部主题</option>{data.topics.map(t => <option value={t.id} key={t.id}>{t.title}（{countOf(t.id)}）</option>)}</select></label>
      <label className="grid gap-2 text-[13px] text-ink-2">内容类型<select className={control} value={kind} onChange={e => setKind(e.target.value)}><option value="">金句、方法与原则</option>{Object.entries(KNOWLEDGE_KINDS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
    </div>
    <div className="mt-4 flex flex-wrap items-center gap-5 text-[13px]"><label className="inline-flex min-h-11 items-center gap-2"><input type="checkbox" checked={savedOnly} onChange={e=>setSavedOnly(e.target.checked)} />只看收藏（{data.entries.filter(e=>reading.saved.includes(e.id)).length}）</label><label className="inline-flex min-h-11 items-center gap-2"><input type="checkbox" checked={unreadOnly} onChange={e=>setUnreadOnly(e.target.checked)} />只看未读</label><span className="text-ink-3">本机已读 {data.entries.filter(e=>reading.read.includes(e.id)).length} / {data.entries.length} · 状态只存在这台设备</span></div>
    </details>
    {topic && <p className="mt-4 border-l-2 border-blue-wash-2 pl-3 text-[14px] leading-relaxed text-ink-2">{data.topics.find(t => t.id === topic)?.description}</p>}
    <p aria-live="polite" className="my-5 font-sans text-[13px] text-ink-3">找到 {entries.length} / {data.entries.length} 条 · 编辑提炼不是群友原话，暂定原则不代表全体共识。</p>
    {!entries.length && <div className="border-y border-rule py-10"><p>还没有对应的沉淀。</p><button onClick={reset} className={`mt-4 min-h-11 text-blue-text ${motion.pressable}`}>清除筛选</button></div>}
    <div className="grid gap-px border-y border-rule bg-rule lg:grid-cols-2">
      {entries.map(item => <article key={item.id} id={item.id} className="scroll-mt-28 flex flex-col bg-paper p-5">
        <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 font-sans text-[12px]">
          <span className="inline-flex items-center gap-1.5 font-semibold text-blue-text"><Icon name={kindIcon[item.kind]} size={15} />{KNOWLEDGE_KINDS[item.kind]}</span>
          <span className="text-ink-3">{data.topics.find(t => t.id === item.topicId)?.title}</span>
          {(reading.read.includes(item.id) || reading.saved.includes(item.id)) && (
            <span className="ml-auto text-ink-3">{reading.read.includes(item.id) && "已读"}{reading.read.includes(item.id) && reading.saved.includes(item.id) && " · "}{reading.saved.includes(item.id) && "已收藏"}</span>
          )}
        </div>
        <h2 className="font-serif text-[20px] font-bold leading-snug"><Link className={`hover:text-blue-text ${motion.pressable}`} href={`/learn/entries/${item.id}/`}>{item.title}</Link></h2>
        <p className="prose-sheet mt-2 line-clamp-4 text-[15px] leading-[1.8] text-ink-2">{item.text}</p>
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 font-sans text-[13px]">
          <Link href={`/learn/entries/${item.id}/`} className={`inline-flex min-h-11 items-center text-blue-text ${motion.pressable}`}>{item.steps.length ? `阅读 ${item.steps.length} 步实践与依据` : "阅读全文、收藏与导出"} →</Link>
          <details className="group sm:relative">
            <summary className={`inline-flex min-h-11 cursor-pointer list-none items-center text-blue-text ${motion.pressable}`}>依据与边界</summary>
            <div className={`${motion.reveal} mt-1 w-[calc(100vw-72px)] max-w-[26rem] border border-rule bg-paper p-4 sm:absolute sm:left-0 sm:top-11 sm:z-10 sm:mt-0 sm:w-[min(26rem,85vw)]`}>
              <p className="text-[13px] leading-relaxed text-ink-2"><b>适用边界：</b>{item.counterpoint}</p>
              <ul className="mt-2">{item.sources.map(source => <li key={source.date + source.themeTitle}><Link href={`/ledger/${source.date}/`} className="inline-flex min-h-11 items-center text-[12.5px] text-blue-text underline">{source.date} · {plain(source.themeTitle)}</Link></li>)}</ul>
              <ul className="mt-2 text-[11.5px] text-ink-3">{item.revisions.map((revision, index) => <li key={index}>{revision.date} · {revision.note}</li>)}</ul>
            </div>
          </details>
        </div>
        {item.relatedIds.length > 0 && <div className="flex flex-wrap gap-x-4 text-[13px]">{item.relatedIds.map(id => byId.get(id)).filter(x => !!x).map(related => <Link onClick={reset} key={related.id} href={`/learn/entries/${related.id}/`} className={`inline-flex min-h-11 items-center text-blue-text ${motion.pressable}`}>继续学：{related.title} →</Link>)}</div>}
        <div className="mt-4 border-l-2 border-amber-deep pl-3"><p className="text-[13.5px] leading-relaxed">{item.question}</p><Link href={`/community/?topic=${encodeURIComponent(item.id)}&title=${encodeURIComponent(item.question)}`} className={`mt-1 inline-flex min-h-11 items-center font-sans text-[13px] font-semibold text-blue-text ${motion.pressable}`}>带着证据讨论这条观点 →</Link></div>
      </article>)}
    </div>
  </div>;
}
