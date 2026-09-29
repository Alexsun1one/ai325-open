"use client";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { CellarList } from "@/components/pages/CellarList";
import { CellarUnit } from "@/components/pages/CellarUnit";
import { Note } from "@/components/pages/FormBits";

const UNIT_ID_RE = /^cu-\d{8}-\d{4}$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** 窖藏页：目录（默认最新有块的一天，?date=YYYY-MM-DD 深链）；带 ?unit=cu-YYYYMMDD-NNNN 时进入单块考究阅读。 */
function CellarView() {
  const params = useSearchParams();
  const unit = params?.get("unit")?.trim() ?? "";
  if (unit) {
    if (!UNIT_ID_RE.test(unit)) {
      return <Note tone="bad">这个窖藏编号不对。请从日报的「凭证」链接进入，编号应为 cu-YYYYMMDD-NNNN。</Note>;
    }
    return <CellarUnit key={unit} id={unit} />;
  }
  const dateParam = params?.get("date")?.trim() ?? "";
  if (dateParam && !DATE_RE.test(dateParam)) {
    return <Note tone="bad">日期格式应为 YYYY-MM-DD。</Note>;
  }
  // 无 date 时 CellarList 自动取可用日期列表的最新一天（不写死）
  return <CellarList date={dateParam || undefined} />;
}

export default function CellarPageClient() {
  return (
    <Suspense fallback={<p className="py-8 font-sans text-[14px] text-ink-3">正在开窖……</p>}>
      <CellarView />
    </Suspense>
  );
}
