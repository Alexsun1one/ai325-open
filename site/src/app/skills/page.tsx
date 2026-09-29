import { AgentDirectoryLink } from "@/components/pages/AgentDirectoryLink";
import { Suspense } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { readSkillLibrary } from "@/lib/skill-content";
import { PageHead, PageShell } from "@/components/pages/PageHead";
import { SkillLibrary } from "@/components/pages/SkillLibrary";

export const metadata: Metadata = {
  title: "Skill 技能库",
  description: "给 Agent 挑一项手艺：内容创作、视觉设计、视频动画、界面交互。查看用途，下载技能包，带回自己的工作流。",
};

export default function SkillsPage() {
  const data = readSkillLibrary();
  const downloadable = data.items.filter((item) => item.downloadUrl).length;
  return (
    <PageShell>
      <PageHead compact title="Skill 技能库" lead="从官方与维护者的技能库里挑选工作方法，查看来源，再交给你的 Agent。"
        fields={[
          { k: "收录技能", v: `${data.items.length} 项` },
          { k: "提供下载", v: `${downloadable} 项` },
          { k: "内容类别", v: `${new Set(data.items.map((item) => item.category)).size} 类` },
          { k: "目录更新", v: new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Shanghai" }).format(new Date(data.generatedAt)) },
        ]} />
      <div className="mb-7 flex flex-wrap items-center gap-x-6 gap-y-2 border-y border-rule py-3 font-sans text-[13px]">
        <Link href="/agents/" className="inline-flex min-h-11 items-center text-blue-text no-underline hover:underline">← 回 Agent 学堂</Link>
        <Link href="/arsenal/" className="inline-flex min-h-11 items-center text-blue-text no-underline hover:underline">提示词与方法，去军火库 →</Link>
        <AgentDirectoryLink />
      </div>
      <p className="mb-5 font-sans text-[13px] leading-relaxed text-ink-2">优先收录官方维护、用途明确、有完整文档的技能。来源核验不代表效果实测；适用工具、依赖与许可证请以原目录为准。</p>
      <Suspense fallback={<p>正在读取技能目录……</p>}><SkillLibrary items={data.items} /></Suspense>
    </PageShell>
  );
}
