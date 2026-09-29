import type { Metadata } from "next";
import { Section } from "@/components/sheet/Section";
import { PageHead, PageShell } from "@/components/pages/PageHead";
import { VitalityBoard } from "@/components/pages/VitalityBoard";

export const metadata: Metadata = {
  title: "群友排行",
  description: "先锋队群友参与榜：看看大家的参与、贡献与近7日变化。",
};

export default function RankingsPage() {
  return (
    <PageShell>
      <PageHead
        title="群友排行"
        lead="看看群友的参与、贡献与近期变化。"
        fields={[
          { k: "范围", v: "群友参与榜", num: false },
          { k: "增量", v: "近 7 日", num: false },
          { k: "可见性", v: "公开可读", num: false },
        ]}
      />
      <Section id="board" label="榜单" sub="查看名次与近期贡献变化">
        <VitalityBoard />
      </Section>
    </PageShell>
  );
}
