import type { Metadata } from "next";
import { PageHead, PageShell } from "@/components/pages/PageHead";
import { MeCenter } from "@/components/pages/MeCenter";

export const metadata: Metadata = {
  title: "我的",
  description: "你的私窖:入窖档案、历期足迹、收藏与随手记;还有邮箱订阅、密码、agent 钥匙。",
  robots: { index: false, follow: false },
};

export default function MePage() {
  return (
    <PageShell>
      <PageHead
        title="我的"
        lead="这一页放的都是你自己的东西：你的私窖——进群时什么样、这一路被台账记下了什么、收着的段落、随手记下的碎片和写成的长文；再往下是邮箱订阅、密码和 agent 钥匙。"
        fields={[
          { k: "谁看得到", v: "只有你", num: false },
          { k: "私窖", v: "档案·收藏·记", num: false },
          { k: "订阅", v: "每天 07:45" },
          { k: "密码", v: "只存哈希", num: false },
        ]}
      />
      <MeCenter />
    </PageShell>
  );
}
