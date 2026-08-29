import type { Metadata } from "next";
import { Section } from "@/components/sheet/Section";
import { PageHead, PageShell } from "@/components/pages/PageHead";
import { Gate } from "@/components/pages/Gate";
import { AccountsAdmin } from "@/components/pages/AccountsAdmin";

export const metadata: Metadata = {
  title: "成员账号后台",
  description: "群主用的成员账号台：给群成员发账号、重置密码、禁用启用、绑定微信身份。",
  robots: { index: false, follow: false },
};

export default function AccountsPage() {
  return (
    <PageShell>
      <PageHead
        title="成员账号后台"
        lead="给群成员发账号：一人一微信身份。生成账号时密码只显示一次；注册没对上微信的人在这里补绑，头像和发言归属就能对上。"
        fields={[
          { k: "可见性", v: "仅群主（admin）", num: false },
          { k: "生成方式", v: "按群成员", num: false },
          { k: "微信身份", v: "member_key 绑定", num: false },
          { k: "密码", v: "一次性显示", num: false },
        ]}
      />
      <Section id="accounts" label="账号台" sub="生成 / 重置 / 禁用 / 绑定">
        <Gate
          what="成员账号后台"
          why="这是给群成员发账号的地方：谁有号、谁没号、谁登录过，一目了然。只对群主（admin）开放；普通群友登录后也看不到内容。"
        >
          <AccountsAdmin />
        </Gate>
      </Section>
    </PageShell>
  );
}
