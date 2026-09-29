import type { Metadata } from "next";
import { Suspense } from "react";
import { PageShell } from "@/components/pages/PageHead";
import { MeCenter } from "@/components/pages/MeCenter";

export const metadata: Metadata = {
  title: "我的成长",
  description: "你的工作区：实践与共练、收藏与笔记、酒力、订阅与账号。登录后可见。",
  robots: { index: false, follow: false },
};

export default function MePage() {
  return (
    <PageShell>
      <header className="pb-1 pt-8 sm:pt-12">
        <h1 className="font-serif text-[32px] font-black leading-[1.2] tracking-[0.01em] text-ink sm:text-[40px]">我的成长</h1>
        <p className="prose-sheet mt-3 max-w-[40em] text-[16px] leading-[1.7] text-ink-2">私人笔记和草稿只归你；只有你主动提交或发布的内容，才会被其他群友看到。</p>
      </header>
      <Suspense fallback={<p className="py-10 font-sans text-[14px] text-ink-3">正在准备你的工作区……</p>}>
        <MeCenter />
      </Suspense>
    </PageShell>
  );
}
