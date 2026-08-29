import type { Metadata } from "next";
import { Section } from "@/components/sheet/Section";
import { PageHead, PageShell } from "@/components/pages/PageHead";
import { Gate } from "@/components/pages/Gate";
import { LibraryShelf } from "@/components/pages/LibraryShelf";

export const metadata: Metadata = {
  title: "文库",
  description: "群里分享过的原件档案：PDF、电子书、整理稿。需邀请码登录，登录后可取件。",
};

export default function LibraryPage() {
  return (
    <PageShell>
      <PageHead
        title="文库"
        lead="群里传过的文件不该沉在聊天记录里。这里按月归档群友分享的原件——书、报告、整理稿、讲义——登录就能取。哪件值得精读，会另配导读进军火库。"
        fields={[
          { k: "收什么", v: "群里分享的原件", num: false },
          { k: "可见性", v: "需邀请码登录", num: false },
          { k: "排列", v: "按收件月份", num: false },
          { k: "去向", v: "值得精读的进军火库", num: false },
        ]}
      />
      <Section id="shelf" label="档案柜" sub="一行一件 · 点「取件」下载">
        <Gate
          what="文库"
          why="这些文件是群友分享给群内的，拿到公开互联网上再分发就越权了。所以文库只对拿到邀请码的群友开放，取件请自用、别转出群外。"
        >
          <LibraryShelf />
        </Gate>
      </Section>
    </PageShell>
  );
}
