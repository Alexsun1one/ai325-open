"use client";
import { useState } from "react";
import { Icon } from "@/components/ui/Icon";

/** Keep machine-readable exports explicit instead of replacing the human page. */
export function AgentDirectoryLink() {
  const [message, setMessage] = useState("");
  const [address, setAddress] = useState("");
  const copy = async () => {
    const url = new URL("/skills/directory.json", window.location.origin).href;
    setAddress(url);
    try { await navigator.clipboard.writeText(url); setMessage("目录地址已复制，发给你的 Agent 即可读取。"); }
    catch { setMessage("浏览器未允许复制，请选中下方地址手动复制。"); }
  };
  return <details className="min-w-0 sm:ml-auto">
    <summary className="flex min-h-11 cursor-pointer items-center gap-2 text-blue-text"><Icon name="agent" size={16} />给 Agent 读取目录</summary>
    <div className="mt-2 max-w-md border-l-2 border-blue-wash-2 pl-3">
      <p className="leading-relaxed text-ink-2">这是供 Agent 读取的 JSON 数据目录。复制地址给它，或在新标签页查看原始数据。</p>
      <div className="mt-2 flex flex-wrap items-center gap-4">
        <button type="button" onClick={copy} className="min-h-11 text-blue-text underline underline-offset-4">复制目录地址</button>
        <a href="/skills/directory.json" target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center text-blue-text underline underline-offset-4">查看 JSON ↗</a>
      </div>
      {message && <p role="status" className="mt-1 leading-relaxed text-ink-2">{message}</p>}
      {address && <input aria-label="Agent 目录地址" readOnly value={address} onFocus={(event) => event.currentTarget.select()} className="my-2 min-h-11 w-full min-w-0 rounded border border-rule bg-paper px-2 text-ink" />}
    </div>
  </details>;
}
