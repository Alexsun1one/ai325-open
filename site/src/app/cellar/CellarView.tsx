"use client";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { CellarList } from "@/components/pages/CellarList";
import { CellarUnit } from "@/components/pages/CellarUnit";

/** 窖藏页：默认目录；带 ?unit=N 时进入单块考究阅读（凭证下钻用 /cellar/?unit=N&at=M）。 */
function CellarView() {
  const params = useSearchParams();
  const unit = Number(params?.get("unit") ?? 0) || 0;
  if (unit > 0) return <CellarUnit id={unit} />;
  return <CellarList date="2026-08-23" />;
}

export default function CellarPageClient() {
  return (
    <Suspense fallback={<p className="py-8 font-sans text-[14px] text-ink-3">正在开窖……</p>}>
      <CellarView />
    </Suspense>
  );
}
