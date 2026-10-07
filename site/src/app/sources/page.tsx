import type { Metadata } from "next";
import { PageShell } from "@/components/pages/PageHead";
import { readExternalSources } from "@/lib/external-sources";
import { readExternalCuration } from "@/lib/external-curation";
import { CuratedBoard } from "./CuratedBoard";
import { SourcesBoard } from "./SourcesBoard";

export const metadata: Metadata = {
  title: "外部知识来源",
  description: "从公开的研究、工程与产品来源阅读 AI 新进展。保留出处、发布时间和原文链接。",
};

export default function SourcesPage() {
  return (
    <PageShell>
      <CuratedBoard data={readExternalCuration()} />
      <SourcesBoard data={readExternalSources()} />
    </PageShell>
  );
}
