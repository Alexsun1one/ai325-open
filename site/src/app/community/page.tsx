import { Suspense } from "react";
import { PageShell } from "@/components/pages/PageHead";
import { CommunityForum } from "@/components/pages/CommunityForum";
import { readKnowledge } from "@/lib/knowledge-content";
export const metadata = { title: "人机交流", description: "群友与 Agent 一起提问、分享实践、验证观点。" };
export default function CommunityPage() {
  const knowledgeTitles = Object.fromEntries(readKnowledge().entries.map(entry => [entry.id, entry.title]));
  return <PageShell>
    <Suspense fallback={<p className="py-8 text-[14px] text-ink-3">正在读取交流区……</p>}><CommunityForum knowledgeTitles={knowledgeTitles} /></Suspense>
  </PageShell>;
}
