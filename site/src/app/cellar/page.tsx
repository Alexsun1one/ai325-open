import type { Metadata } from "next";
import { PageHead, PageShell } from "@/components/pages/PageHead";
import CellarPageClient from "./CellarView";

export const metadata: Metadata = {
  title: "窖藏 · 原浆",
  description: "蒸馏前的原话，按话题装坛。治理是蒸馏液，这里是窖藏原浆——逐字未动，只做脱敏。",
};

export default function CellarPage() {
  return (
    <PageShell>
      <PageHead
        title="窖藏 · 原浆"
        lead="日报是蒸出来的酒，这里存的是蒸之前的那锅原浆：群里一段一段的原话，按话题装成坛，逐字未动。想看一句金句是不是真的那么说——下到窖里对原浆。"
        fields={[
          { k: "一坛", v: "一段话题原话", num: false },
          { k: "可见性", v: "群友可下窖", num: false },
          { k: "蒸馏", v: "在日报，不在这", num: false },
          { k: "2026-08-23", v: "先装这一天", num: true },
        ]}
      />
      <section className="pb-16">
        <CellarPageClient />
      </section>
    </PageShell>
  );
}
