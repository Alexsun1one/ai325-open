import type { Metadata } from "next";
import { Section } from "@/components/sheet/Section";
import { PageHead, PageShell } from "@/components/pages/PageHead";
import { Gate } from "@/components/pages/Gate";
import { AdminOps } from "@/components/pages/AdminOps";

export const metadata: Metadata = {
  title: "运营台",
  description: "群主用的运营台：待办队列、成员筛选、出刊与门禁。批量认领链接不做。",
  robots: { index: false, follow: false },
};

export default function AdminOpsPage() {
  return (
    <PageShell>
      <PageHead
        title="运营台"
        lead="今天把待办处理完、找到人、管出刊。待审评论/投稿/兑换和身份候选集中在这一页；成员只做单人开号、认领链接、绑定、禁用。批量认领链接不做。"
        fields={[
          { k: "可见性", v: "仅群主（admin）", num: false },
          { k: "队列", v: "评论 / 投稿 / 兑换 / 身份", num: false },
          { k: "批量", v: "只许标记/导出清单", num: false },
          { k: "出刊", v: "手动触发 · 重蒸某日", num: false },
        ]}
      />
      <Section id="ops" label="运营台" sub="队列 · 成员 · 出刊">
        <Gate
          what="运营台"
          why="这里集中处理待审事项、找人、管出刊。只对群主开放；普通群友登录也看不到内容。"
        >
          <AdminOps />
        </Gate>
      </Section>
    </PageShell>
  );
}
