import type { Metadata } from "next";
import { Section } from "@/components/sheet/Section";
import { PageHead, PageShell } from "@/components/pages/PageHead";
import { Gate } from "@/components/pages/Gate";
import { RewardsAdmin } from "@/components/pages/RewardsAdmin";

export const metadata: Metadata = {
  title: "奖励兑换后台",
  description: "群主用的奖励台：酒力兑换审核、发放激活码、库存与门槛设置。",
  robots: { index: false, follow: false },
};

export default function RewardsPage() {
  return (
    <PageShell>
      <PageHead
        title="奖励兑换后台"
        lead="群友拿酒力换奖品，Sun 审核发放。激活码明文只显示一次，系统只存哈希与掩码。"
        fields={[
          { k: "可见性", v: "仅群主（admin）", num: false },
          { k: "发放", v: "Sun 审核后人工录码", num: false },
          { k: "激活码", v: "只存哈希+掩码", num: false },
          { k: "库存/门槛", v: "后台可改", num: false },
        ]}
      />
      <Section id="rewards" label="酒力兑换台" sub="审核 · 发放 · 库存 · 门槛">
        <Gate what="奖励兑换后台" why="这里管真金白银（激活码），只有群主能进。">{null}</Gate>
        <RewardsAdmin />
      </Section>
    </PageShell>
  );
}
