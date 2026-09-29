import type { Metadata } from "next";
import { Section } from "@/components/sheet/Section";
import { PageHead, PageShell } from "@/components/pages/PageHead";
import { Gate } from "@/components/pages/Gate";
import { AdminDashboard } from "@/components/pages/AdminDashboard";

export const metadata: Metadata = {
  title: "数据大盘",
  description: "群主用的访问量、社群趋势与出刊健康台。数字来自 nginx 增量聚合表，不是埋点。",
  robots: { index: false, follow: false },
};

export default function AdminDashboardPage() {
  return (
    <PageShell>
      <PageHead
        title="数据大盘"
        lead="看今天有没有人来、群里还在不在说话、出刊断没断。访问量从服务器 nginx 日志增量聚合，不往页面塞埋点；图表是站内琥珀与蓝的 SVG，不引重型库。"
        fields={[
          { k: "可见性", v: "仅群主（admin）", num: false },
          { k: "访问量", v: "nginx 零埋点", num: false },
          { k: "刷新", v: "10 分钟增量", num: false },
          { k: "图表", v: "SVG 手绘", num: false },
        ]}
      />
      <Section id="dashboard" label="大盘" sub="访问量 / 社群 / 出刊">
        <Gate
          what="数据大盘"
          why="这是给群主看站务的地方：谁来过、群聊热不热、出刊健康。只对群主（admin）开放；普通群友登录后也看不到内容。"
        >
          <AdminDashboard />
        </Gate>
      </Section>
    </PageShell>
  );
}
