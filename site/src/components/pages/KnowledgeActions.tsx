"use client";
import { Icon } from "@/components/ui/Icon";
import { useState } from "react";
import { toggleReading, useReadingState } from "@/lib/reading-state";
import type { KnowledgeEntry } from "@/lib/knowledge";
const button = "inline-flex items-center gap-2 min-h-11 rounded-md border border-rule px-4 text-[13px] hover:bg-paper-2 focus-visible:outline-2 focus-visible:outline-blue";
export function KnowledgeActions({ entry }: { entry: KnowledgeEntry }) {
  const state = useReadingState();
  const [message, setMessage] = useState("");
  const toggle = (field: "saved" | "read") => { try { toggleReading(entry.id, field); setMessage(""); } catch { setMessage("浏览器未允许保存，当前操作没有记住。"); } };
  const exportText = () => {
    const source = entry.sources.map(s => `- ${s.date} · ${s.themeTitle}\n  https://www.ai325.com/ledger/${s.date}/`).join("\n");
    const text = `# ${entry.title}\n\n编辑整理 · 可修订观点\n\n${entry.text}\n\n${entry.steps.map((s,i) => `${i+1}. ${s}`).join("\n")}\n\n## 适用边界\n${entry.counterpoint}\n\n## 来源\n${source}\n\n## 继续讨论\n${entry.question}\n\nhttps://www.ai325.com/learn/entries/${entry.id}/\n`;
    const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
    const a = document.createElement("a"); a.href = url; a.download = `${entry.id}.md`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <div className="my-6 border-y border-rule py-4 font-sans">
    <div className="flex flex-wrap gap-3"><button className={button} aria-pressed={state.saved.includes(entry.id)} onClick={() => toggle("saved")}><Icon name="save" size={16} />{state.saved.includes(entry.id) ? "已收藏 · 取消" : "收藏这条"}</button><button className={button} aria-pressed={state.read.includes(entry.id)} onClick={() => toggle("read")}><Icon name="check" size={16} />{state.read.includes(entry.id) ? "已读 · 标为未读" : "标为已读"}</button><button className={button} onClick={exportText}><Icon name="download" size={16} />导出 Markdown</button></div>
    <p className="mt-3 text-[12px] text-ink-3">收藏和已读仅保存在当前浏览器，不会同步到其他设备。</p><p role="status" className="mt-2 text-[13px] text-amber-text">{message}</p>
  </div>;
}
