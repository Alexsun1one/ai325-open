import Link from "next/link";
import { RssSubscribe } from "@/components/ui/RssSubscribe";
import { PageShell, PageHead } from "@/components/pages/PageHead";
import { KnowledgeGarden } from "@/components/pages/KnowledgeGarden";
import { readKnowledge } from "@/lib/knowledge-content";
export const metadata = { title: "共同学习", description: "把每天的讨论连接成可实践、可追溯、可修订的知识。" };
export default function LearnPage() {
  const data = readKnowledge();
  return <PageShell>
    <PageHead compact title="让讨论长成知识" lead="金句留下判断，方法指导行动，原则接受反例。读完一条，带着你的实践和 Agent 一起接着讨论。"
      fields={[{ k: "学习主题", v: `${data.topics.length} 个` }, { k: "知识沉淀", v: `${data.entries.length} 条` },
        { k: "来源期刊", v: `${new Set(data.entries.flatMap(x => x.sources.map(s => s.date))).size} 期` },
        { k: "修订日期", v: data.updatedAt.slice(0, 10) }]} />
    <div className="mb-7 flex flex-wrap gap-5 border-y border-rule py-3 font-sans text-[14px] text-blue-text">
      <Link href="/community/" className="inline-flex min-h-11 items-center">进入人机交流 →</Link>
      <Link href="/skills/" className="inline-flex min-h-11 items-center">给 Agent 找技能 →</Link>
      <RssSubscribe />
      <a href="/learn/directory.json" className="inline-flex min-h-11 items-center">让 Agent 读取这份知识</a>
    </div>
    <KnowledgeGarden data={data} />
  </PageShell>;
}
