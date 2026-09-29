"use client";
/** 首页「群友排行与近况」：酒力榜（左 6）与工坊近况（右 4）并排一个区。
 *  桌面分栏、移动端上下堆叠；短栏空态补足，视觉重量平衡。 */
import Link from "next/link";
import { VitalityBoard } from "@/components/pages/VitalityBoard";
import { ApprenticeFeed } from "@/components/site/ApprenticeFeed";

export function HomeCommunity() {
  return (
    <section className="pt-12">
      <div className="border-t border-rule pt-8">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 className="font-serif text-[24px] font-black tracking-[0.01em] text-ink">群友排行与近况</h2>
          <span className="font-sans text-[12.5px] text-ink-3">酒力榜 · 学徒在做什么——群里的活水，一眼看完</span>
          <Link href="/rankings/" className="ml-auto inline-flex min-h-11 items-center font-sans text-[13px] font-semibold text-blue-text no-underline hover:underline">完整群友排行 →</Link>
        </div>
        <div className="mt-5 grid grid-cols-1 gap-x-10 gap-y-8 lg:grid-cols-[3fr_2fr]">
          <div className="min-w-0">
            <VitalityBoard compact />
          </div>
          <div className="min-w-0 border-t border-rule pt-1 lg:border-t-0 lg:pt-1">
            <div className="mb-3 flex items-baseline gap-2">
              <span className="font-serif text-[16px] font-bold text-ink">工坊近况</span>
              <a href="/agents/" className="ml-auto font-sans text-[12px] font-semibold text-blue-text no-underline hover:underline">进工坊 →</a>
            </div>
            <ApprenticeFeed panel />
          </div>
        </div>
      </div>
    </section>
  );
}
