import type { Metadata } from "next";
import { Section } from "@/components/sheet/Section";
import { PageHead, PageShell } from "@/components/pages/PageHead";
import { Gate } from "@/components/pages/Gate";
import { MembersRoster } from "@/components/pages/MembersRoster";

export const metadata: Metadata = {
  title: "群像",
  description: "先锋队 51 人画像：角色、发言量、标签、主要语气、一句话与深读。需邀请码登录。",
};

export default function MembersPage() {
  return (
    <PageShell>
      <PageHead
        title="群像"
        lead="这个群里的人是谁。每个人一栏：他在群里扮演什么角色、说了多少、主要用什么语气说话、最值得记住的一句是什么，以及一段「没说破的」——那是整理者的延伸，不是他本人的话。"
        fields={[
          { k: "范围", v: "51 人画像" },
          { k: "可见性", v: "需邀请码登录", num: false },
          { k: "排序", v: "按发言量倒序", num: false },
          { k: "怎么来的", v: "从群聊整理", num: false },
        ]}
      />
      <Section id="roster" label="名册" sub="点「深读」展开那个人">
        <Gate
          what="群像"
          why="这 51 份画像写的是具体的人——他的职业、说话习惯、在群里的位置。群友之间看是互相认识，放到公开互联网上就变成了对个人的公开画像。所以这一栏只对拿到邀请码的群友开放。"
        >
          <MembersRoster />
        </Gate>
      </Section>
    </PageShell>
  );
}
