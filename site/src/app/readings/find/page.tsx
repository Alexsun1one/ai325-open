import type { Metadata } from "next";
import { Suspense } from "react";
import { PageHead, PageShell } from "@/components/pages/PageHead";
import { RepositoryFinder } from "@/components/pages/RepositoryFinder";

export const metadata: Metadata = {
  title: "按问题找实现",
  description: "说一句想做的事，从已拆过的仓库精读里找到对应的项目与已核验源码入口。",
};

export default function FindPage() {
  return (
    <PageShell>
      <PageHead
        title="按问题找实现"
        lead="别背项目名——说一句想做的事。这里把已经拆过的仓库精读按问题检索，命中就给出出处片段、适用条件和已核验的源码入口；答不了的题老实说答不了。"
        fields={[
          { k: "第一步", v: "说出任务", num: false },
          { k: "第二步", v: "查看源码", num: false },
          { k: "第三步", v: "对照导读", num: false },
        ]}
      />
      <Suspense fallback={<p className="py-10 font-sans text-[14px] text-ink-3">正在准备检索台……</p>}>
        <RepositoryFinder />
      </Suspense>
    </PageShell>
  );
}
