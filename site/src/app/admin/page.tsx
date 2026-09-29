import type { Metadata } from "next";
import { Section } from "@/components/sheet/Section";
import { PageHead, PageShell } from "@/components/pages/PageHead";
import { Gate } from "@/components/pages/Gate";
import { AdminDashboard } from "@/components/pages/AdminDashboard";

export const metadata: Metadata = {
  title: "管理员后台",
  description: "群主用的管理后台入口：数据大盘与运营台。",
  robots: { index: false, follow: false },
};

/** 管理后台总入口：保持旧 /admin/ 链接可用，数据仍由同一只读大盘 API 提供。 */
export default function AdminPage() {
  return (
    <PageShell>
      <PageHead
        title="管理员后台"
        lead="看站务、看社群、管出刊。这里是群主入口；具体数据仍按数据大盘的真值口径读取。"
        fields={[
          { k: "可见性", v: "仅群主（admin）", num: false },
          { k: "数据", v: "nginx + xf.db 聚合", num: false },
          { k: "入口", v: "大盘 / 运营台", num: false },
        ]}
      />
      <Section id="admin" label="管理员后台" sub="数据大盘">
        <Gate
          what="管理员后台"
          why="这里集中查看站务数据与社群趋势。只对群主（admin）开放。"
        >
          <AdminDashboard />
        </Gate>
      </Section>
    </PageShell>
  );
}
