import type { Metadata } from "next";
import Link from "next/link";
import { Section } from "@/components/sheet/Section";
import { PageHead, PageShell } from "@/components/pages/PageHead";
import { Gate } from "@/components/pages/Gate";
import { MembersRoster } from "@/components/pages/MembersRoster";

export const metadata: Metadata = {
  title: "群像",
  description: "先锋队成员画像：角色、发言量、标签、主要语气、一句话与深读。需邀请码登录。",
};

export default function MembersPage() {
  return (
    <PageShell>
      <PageHead
        title="群像"
        lead="认识一起学习的人：浏览角色与标签，展开查看代表表达和整理者的观察。"
        fields={[
          { k: "范围", v: "成员画像" },
          { k: "可见性", v: "需邀请码登录", num: false },
          { k: "排序", v: "按发言量倒序", num: false },
          { k: "怎么来的", v: "从群聊整理", num: false },
        ]}
      />
      <p className="mb-6 font-sans text-[14px] text-ink-2">
        看谁正在把讨论做下去：<Link href="/rankings/" className="inline-flex min-h-11 items-center font-semibold text-blue-text underline-offset-2 hover:underline">群友排行 →</Link>
      </p>
      <Section id="roster" label="名册" sub="按角色筛选，展开了解一个人">
        <Gate
          what="群像"
          why="这些画像写的是具体的人——他的职业、说话习惯、在群里的位置。群友之间看是互相认识，放到公开互联网上就变成了对个人的公开画像。所以这一栏只对拿到邀请码的群友开放。"
        >
          <MembersRoster />
        </Gate>
      </Section>
    </PageShell>
  );
}
