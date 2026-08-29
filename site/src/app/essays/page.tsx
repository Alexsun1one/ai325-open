import type { Metadata } from "next";
import { Section } from "@/components/sheet/Section";
import { PageHead, PageShell } from "@/components/pages/PageHead";
import { Gate } from "@/components/pages/Gate";
import { EssayCellar } from "@/components/pages/EssayCellar";

export const metadata: Metadata = {
  title: "窖藏",
  description: "入群小作文的酒窖：一篇一瓶，按入窖日期排架，点开是完整阅读版。需邀请码登录。",
};

export default function EssaysPage() {
  return (
    <PageShell>
      <PageHead
        title="窖藏"
        lead="入群要写一篇小作文：介绍自己、对 AI 的理解、擅长什么、想了解什么、对未来的展望。这些是这个群里最长、最慢、也最经得起放的东西——所以不摘要、不切片，整篇入窖，整篇取出。"
        fields={[
          { k: "内容", v: "入群小作文", num: false },
          { k: "可见性", v: "需邀请码登录", num: false },
          { k: "排架", v: "按入窖日期", num: false },
          { k: "阅读版", v: "宋体 17px · 约 38 字/行" },
        ]}
      />
      <Section id="cellar" label="格架" sub="一篇一瓶 · 液位 = 字数">
        <Gate
          what="窖藏"
          why="小作文是群友写给群友的自述——职业、经历、正在犯的难。写的时候默认读者是这个群里的人，不是公开互联网。所以整栏只对拿到邀请码的群友开放，也不做站外检索。"
        >
          <EssayCellar />
        </Gate>
      </Section>
    </PageShell>
  );
}
