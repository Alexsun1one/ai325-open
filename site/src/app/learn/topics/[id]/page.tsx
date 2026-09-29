import Link from "next/link";
import { notFound } from "next/navigation";
import { readKnowledge } from "@/lib/knowledge-content";
import { KNOWLEDGE_KINDS } from "@/lib/knowledge";
import { PageHead, PageShell } from "@/components/pages/PageHead";
export function generateStaticParams() { return readKnowledge().topics.map(t => ({ id:t.id })); }
export default async function TopicPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params; const data=readKnowledge(); const topic=data.topics.find(t=>t.id===id); if(!topic) notFound();
  const entries=data.entries.filter(e=>e.topicId===id); const dates=[...new Set(entries.flatMap(e=>e.sources.map(s=>s.date)))].sort();
  return <PageShell><Link href="/learn/" className="mt-6 inline-flex min-h-11 items-center text-[13px] text-blue-text">← 全部学习主题</Link><PageHead compact title={topic.title} lead={topic.description} fields={[{k:"知识条目",v:entries.length},{k:"讨论跨度",v:`${dates[0]} — ${dates.at(-1)}`},{k:"来源期数",v:dates.length},{k:"内容性质",v:"编辑整理 · 持续修订",num:false}]} />
    <p className="border-y border-rule py-4 text-[14px] text-ink-2">先理解观点，再选一个方法实践，最后用结果检验原则。完成一条后可标记已读，或带着反例进入讨论。</p>
    {(["insight","method","principle"] as const).map((kind,index)=><section key={kind} className="my-8"><h2 className="font-serif text-[23px] font-bold"><span className="num mr-3 text-amber-text">0{index+1}</span>{KNOWLEDGE_KINDS[kind]}</h2><ul className="mt-4 divide-y divide-rule border-y border-rule">{entries.filter(e=>e.kind===kind).map(e=><li key={e.id} className="py-5"><Link href={`/learn/entries/${e.id}/`} className="font-serif text-[20px] font-bold text-blue-text hover:underline">{e.title} →</Link><p className="mt-3 max-w-[800px] text-[16px] leading-relaxed text-ink-2">{e.text}</p><p className="mt-3 text-[12px] text-ink-3">{e.sources.length} 处讨论依据 · {e.relatedIds.length} 条关联知识</p></li>)}</ul>{!entries.some(e=>e.kind===kind)&&<p className="py-5 text-[14px] text-ink-3">这个主题暂未形成{KNOWLEDGE_KINDS[kind]}，等更多实践证据。</p>}</section>)}
  </PageShell>;
}
