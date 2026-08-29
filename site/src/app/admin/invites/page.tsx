import type { Metadata } from "next";
import { Section } from "@/components/sheet/Section";
import { PageHead, PageShell } from "@/components/pages/PageHead";
import { Gate } from "@/components/pages/Gate";
import { InvitesAdmin } from "@/components/pages/InvitesAdmin";

export const metadata: Metadata = {
  title: "邀请码后台",
  description: "群主用的邀请码发放台：生成、查看、撤销。",
  robots: { index: false, follow: false },
};

export default function InvitesPage() {
  return (
    <PageShell>
      <PageHead
        title="邀请码后台"
        lead="群主在这里发码：一人一码、带备注、可撤销。生成时完整码只显示一次，之后列表里只留后 4 位——码一旦贴到别处就不再是一人一码了。"
        fields={[
          { k: "可见性", v: "仅群主（admin）", num: false },
          { k: "发放方式", v: "一人一码", num: false },
          { k: "可撤销", v: "是", num: false },
          { k: "公开展示", v: "从不", num: false },
        ]}
      />
      <Section id="invites" label="发放台" sub="生成 / 列表 / 撤销">
        <Gate
          what="邀请码后台"
          why="这是发码的地方，能看到已经发出去的码和用码的人。只对群主账号（admin）开放；普通群友登录后也看不到内容。"
        >
          <InvitesAdmin />
        </Gate>
      </Section>
    </PageShell>
  );
}
