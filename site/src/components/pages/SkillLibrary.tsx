"use client";
import { useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import type { LibrarySkill } from "@/lib/skill-library";
import { Icon } from "@/components/ui/Icon";
import motion from "./motion.module.css";

/** 根的契约扩展（可选字段，向后兼容旧数据）：详情 JSON 按需懒加载，不进首屏。 */
type SkillItem = LibrarySkill & { detailUrl?: string | null; repositoryUrl?: string | null; skillMarkdown?: string | null; repositoryStars?: number | null; starsCheckedAt?: string | null };
interface SkillEditorial { overview: string; useCases: string[]; inputs: string[]; outputs: string[]; steps: string[]; limitations: string[]; reviewedAt: string }
interface SkillDetail { skillMarkdown: string | null; sourceUrl: string | null; repositoryUrl: string | null; editorial?: SkillEditorial; redacted?: boolean; redactions?: string[] }
const detailCache = new Map<string, Promise<SkillDetail>>();
function fetchDetail(url: string): Promise<SkillDetail> {
  let pending = detailCache.get(url);
  if (!pending) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    pending = fetch(url, {signal: controller.signal}).then((res) => {
      if (!res.ok) throw new Error(`详情暂时读不到（${res.status}）`);
      return res.json() as Promise<SkillDetail>;
    }).finally(() => clearTimeout(timer));
    detailCache.set(url, pending);
    pending.catch(() => detailCache.delete(url));
  }
  return pending;
}

const PAGE_SIZE = 12;
const inputClass = "min-h-11 rounded-md border border-rule bg-paper px-3 font-sans text-[14px] text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue";
const buttonClass = "inline-flex min-h-11 items-center justify-center rounded-md border border-rule px-4 font-sans text-[13px] text-ink hover:bg-paper-2 disabled:cursor-not-allowed disabled:opacity-40";

function formatBytes(bytes: number) {
  return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`;
}

function SkillTile({ item }: { item: SkillItem }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [manualText, setManualText] = useState<string | null>(null);
  const repo = detail?.repositoryUrl ?? item.repositoryUrl;
  async function load() {
    if (detail) return detail;
    if (!item.detailUrl) return null;
    setLoading(true); setError("");
    try { const value = await fetchDetail(item.detailUrl); setDetail(value); return value; }
    catch { setError("详情暂时无法读取，请重试。"); return null; }
    finally { setLoading(false); }
  }
  async function copy(text: string, message: string) {
    try { await navigator.clipboard.writeText(text); setNote(message); setManualText(null); }
    catch { setNote("浏览器未允许复制，请选中下方文本手动复制。"); setManualText(text); }
  }
  async function copySkill() {
    const value = await load();
    if (value?.skillMarkdown) await copy(value.skillMarkdown, value.redacted ? "Skill 公开版本已复制，敏感示例已移除。" : "Skill 入口说明已复制。配套脚本和资源请从源仓库或完整包获取。");
    else setNote("暂时没有可复制的 Skill 全文，请查看源文档。");
  }
  const editorial = detail?.editorial;
  const action = `inline-flex min-h-11 items-center gap-1.5 text-blue-text disabled:opacity-50 ${motion.pressable}`;
  return <li className={`min-w-0 border-b border-rule bg-paper p-4 sm:border-r ${open ? "sm:col-span-2 lg:col-span-3" : ""}`}>
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-sans text-[12px] text-ink-3">
      <span className="inline-flex items-center gap-2 text-blue-text"><Icon name="skill" size={17} />{item.category}</span>
      {item.hasEditorial && <span className="text-teal-text">本站导读</span>}
      <span className="ml-auto">{item.author}</span>
    </div>
    <h2 className="mt-3 break-words font-serif text-[20px] font-bold leading-snug text-ink">{item.name}</h2>
    <p className={`mt-2 break-words font-sans text-[14px] leading-[1.75] text-ink-2 ${open ? "" : "line-clamp-3"}`}>{item.description}</p>
    {typeof item.repositoryStars === "number" && <p className="mt-3 font-sans text-[12px] text-ink-3"><span className="num text-amber-text">仓库 ★ {item.repositoryStars.toLocaleString("en-US")}</span>{item.starsCheckedAt && <span className="ml-2">快照 {item.starsCheckedAt.slice(0,10)}</span>}</p>}
    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-rule-soft pt-2 font-sans text-[13px]">
      <button type="button" className={action} disabled={!item.detailUrl || loading} onClick={() => void copySkill()}><Icon name="save" size={15} />复制 Skill</button>
      {repo && <button type="button" className={action} onClick={() => void copy(repo, "仓库地址已复制。")}>复制仓库地址</button>}
      <button type="button" className={`${action} ml-auto font-semibold`} aria-expanded={open} onClick={() => { setOpen(!open); if (!open) void load(); }}><Icon name="book" size={16} />{open ? "收起详情" : "展开详情"}</button>
    </div>
    {note && <p role="status" className="mt-2 font-sans text-[13px] leading-relaxed text-ink-2">{note}</p>}
    {manualText !== null && <textarea aria-label="手动复制内容" readOnly rows={4} value={manualText} onFocus={event => event.currentTarget.select()} className="mt-2 w-full min-w-0 border border-rule bg-paper-2 p-3 text-[13px]" />}
    {error && <p role="alert" className="mt-3 text-[13px] text-amber-text">{error} <button className="min-h-11 underline" onClick={() => void load()}>重新读取</button></p>}
    {loading && <p role="status" className="mt-2 text-[13px] text-ink-3">正在读取详情……</p>}
    {open && detail && <div className={`${motion.reveal} mt-4 grid min-w-0 gap-6 border-t border-rule pt-5 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]`}>
      <div className="min-w-0 font-sans text-[14px] leading-[1.85] text-ink-2">
        {editorial ? <>
          <h3 className="mb-3 text-[17px] font-semibold text-ink">本站导读 <span className="ml-2 text-[12px] font-normal text-ink-3">整理于 {editorial.reviewedAt}</span></h3>
          <p className="whitespace-pre-line">{editorial.overview}</p>
          <h4 className="mb-2 mt-5 font-semibold text-ink">使用步骤</h4>
          <ol className="list-decimal space-y-2 pl-5">{editorial.steps.map(step => <li key={step}>{step}</li>)}</ol>
        </> : <p>本站长介绍尚待整理，可以先阅读下面的 Skill 全文和原始来源。</p>}
        <details className="mt-5 border-t border-rule-soft pt-2">
          <summary className="min-h-11 cursor-pointer py-3 text-blue-text">{detail.redacted ? "Skill 公开版本 · 已移除敏感示例" : "查看 Skill 全文"}</summary>
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words border-l-2 border-blue-wash-2 pl-4 font-mono text-[12px] leading-[1.8]">{detail.skillMarkdown || "暂无全文，请查看源文档。"}</pre>
        </details>
      </div>
      <aside className="min-w-0 border-l-2 border-blue-wash-2 pl-4 font-sans text-[13px] leading-[1.8] text-ink-2">
        {editorial && <>{[["适用场景",editorial.useCases],["准备什么",editorial.inputs],["得到什么",editorial.outputs],["使用边界",editorial.limitations]].map(([title, values]) => <section key={title as string} className="mb-5"><h4 className="mb-1 font-semibold text-ink">{title}</h4><ul className="list-disc space-y-1 pl-4">{(values as string[]).map(value => <li key={value}>{value}</li>)}</ul></section>)}</>}
        <p className="text-ink-3">许可证：{item.license}</p>
        {item.packageBytes !== null && <p className="num text-ink-3">完整包 {formatBytes(item.packageBytes)}</p>}
        <div className="mt-2 flex flex-wrap gap-x-4">
          {item.sourceUrl && <a className={action} href={item.sourceUrl} target="_blank" rel="noopener noreferrer">查看源文档 ↗</a>}
          {item.downloadUrl && <a className={action} href={item.downloadUrl} download><Icon name="download" size={15} />下载完整包</a>}
        </div>
      </aside>
    </div>}
  </li>;
}

export function SkillLibrary({ items }: { items: SkillItem[] }) {
  const params = useSearchParams();
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [category, setCategory] = useState("");
  const [author, setAuthor] = useState("");
  const [downloadsOnly, setDownloadsOnly] = useState(false);
  const [editorialOnly, setEditorialOnly] = useState(false);
  const [page, setPage] = useState(1);
  const resultsHeading = useRef<HTMLParagraphElement>(null);
  const categories = useMemo(() => [...new Set(items.map((item) => item.category))], [items]);
  const authors = useMemo(() => [...new Set(items.map((item) => item.author))].sort(), [items]);
  const matches = useMemo(() => {
    const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    return items.filter((item) => {
      if (category && item.category !== category) return false;
      if (author && item.author !== author) return false;
      if (downloadsOnly && !item.downloadUrl) return false;
      if (editorialOnly && !item.hasEditorial) return false;
      const text = [item.name, item.description, item.author, item.category, ...item.tags].join(" ").toLocaleLowerCase();
      return terms.every((term) => text.includes(term));
    }).sort((a,b) => Number(Boolean(b.hasEditorial)) - Number(Boolean(a.hasEditorial)));
  }, [items, query, category, author, downloadsOnly, editorialOnly]);
  const pageCount = Math.max(1, Math.ceil(matches.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const start = (currentPage - 1) * PAGE_SIZE;
  const visible = matches.slice(start, start + PAGE_SIZE);
  const reset = () => { setQuery(""); setCategory(""); setAuthor(""); setDownloadsOnly(false); setEditorialOnly(false); setPage(1); };
  const turnPage = (next: number) => {
    setPage(next);
    resultsHeading.current?.focus({ preventScroll: true });
    resultsHeading.current?.scrollIntoView({ block: "start" });
  };

  return (
    <div className="pb-14">
      <div className="grid items-end gap-4 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_170px_190px]">
        <label className="flex min-w-0 flex-col gap-2 font-sans text-[13px] text-ink-2">想让 Agent 做什么？
          <input type="search" value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder="搜用途、技能名，例如：封面、video、React" className={inputClass} />
        </label>
        <label className="flex flex-col gap-2 font-sans text-[13px] text-ink-2">按类别浏览
          <select value={category} onChange={(event) => { setCategory(event.target.value); setPage(1); }} className={inputClass}>
            <option value="">全部类别（{items.length}）</option>
            {categories.map((name) => <option key={name} value={name}>{name}（{items.filter((item) => item.category === name).length}）</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-2 font-sans text-[13px] text-ink-2">按维护者浏览
          <select value={author} onChange={(event) => { setAuthor(event.target.value); setPage(1); }} className={inputClass}>
            <option value="">全部维护者</option>
            {authors.map((name) => <option key={name} value={name}>{name}（{items.filter((item) => item.author === name).length}）</option>)}
          </select>
        </label>
      </div>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-x-5 gap-y-2 border-b border-rule pb-3 font-sans text-[12px] text-ink-3">
        <p ref={resultsHeading} tabIndex={-1} className="scroll-mt-28" role="status" aria-live="polite">找到 <span className="num text-ink">{matches.length}</span> 项{matches.length > 0 && `，显示 ${start + 1}–${start + visible.length} 项`}</p>
        <div className="flex flex-wrap items-center gap-4">
          <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 text-[13px] text-ink-2">
            <input type="checkbox" checked={downloadsOnly} onChange={(event) => { setDownloadsOnly(event.target.checked); setPage(1); }} className="h-4 w-4 accent-blue" />只看可下载
          </label>
          <label className="inline-flex min-h-11 items-center gap-2 text-[13px] text-ink-2"><input type="checkbox" checked={editorialOnly} onChange={event => { setEditorialOnly(event.target.checked); setPage(1); }} className="h-4 w-4 accent-blue" />本站导读（{items.filter(item => item.hasEditorial).length}）</label>
          {(query || category || author || downloadsOnly || editorialOnly) && <button type="button" onClick={reset} className={`min-h-11 px-2 text-blue-text hover:underline ${motion.pressable}`}>清除筛选</button>}
        </div>
      </div>
      {visible.length === 0 ? (
        <div className="border-b border-rule py-14 text-center">
          <h2 className="font-serif text-[22px] font-bold text-ink">暂时没有匹配的技能</h2>
          <p className="mt-3 font-sans text-[14px] text-ink-2">换个用途关键词，或清除筛选看看其他手艺。</p>
          <button type="button" className={`${buttonClass} mt-5`} onClick={reset}>查看全部技能</button>
        </div>
      ) : <ul className="grid border-y border-rule bg-paper sm:grid-cols-2 lg:grid-cols-3">
        {visible.map((item) => <SkillTile key={item.id} item={item} />)}
      </ul>}
      {pageCount > 1 && <nav aria-label="技能分页" className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-rule pt-5">
        <button type="button" className={`${buttonClass} ${motion.pressable}`} disabled={currentPage === 1} onClick={() => turnPage(currentPage - 1)}>上一页</button>
        <span className="num font-sans text-[13px] text-ink-3">第 {currentPage} / {pageCount} 页</span>
        <button type="button" className={`${buttonClass} ${motion.pressable}`} disabled={currentPage === pageCount} onClick={() => turnPage(currentPage + 1)}>下一页</button>
      </nav>}
    </div>
  );
}
