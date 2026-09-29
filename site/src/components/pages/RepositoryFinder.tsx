"use client";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { search, type IndexDoc, type SearchHit } from "@/lib/repository-retrieval";
import styles from "./RepositoryFinder.module.css";

/** 「按问题找实现」工作台：本地静态索引 + 透明概念词典检索。
 *  ?q= 可分享/刷新/后退；输入防抖 replace、提交 push；IME 组合期间不打扰；
 *  索引只在搜索页懒取一次；Abort/重试/过期响应作废。 */

interface IndexPayload { version: number; total: number; withCodeRefs: number; capabilitiesLoaded: boolean; docs: IndexDoc[] }

/** 例子均可在当前已晋升精读里得到真实结果（不虚构能答而答不了的题）。 */
const EXAMPLES = [
  "把 PDF 里的表格提取成结构化数据",
  "让 Agent 长任务中断后能接着跑",
  "给网页流程做自动化测试并留证据",
  "搭一个能查到出处的知识库问答",
  "让多个 Agent 按协议协作",
  "把重复的手工流程连成自动化",
];

const escapeReg = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** 高亮：React 节点拼接，不走 innerHTML。 */
function hl(text: string, terms: string[]): React.ReactNode[] {
  const pats = [...new Set(terms)].filter((t) => t.length >= 2).sort((a, b) => b.length - a.length);
  if (!pats.length || !text) return [text];
  const re = new RegExp(`(${pats.map(escapeReg).join("|")})`, "gi");
  const out: React.ReactNode[] = [];
  let last = 0; let k = 0;
  for (const m of text.matchAll(re)) {
    const i = m.index;
    if (i > last) out.push(text.slice(last, i));
    out.push(<mark key={k++}>{m[0]}</mark>);
    last = i + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function Result({ hit }: { hit: SearchHit }) {
  const { doc } = hit;
  return (
    <li className={styles.result}>
      <div className={styles.resultTop}>
        <Link href={doc.href} className={styles.resultTitle}>{doc.title}</Link>
        <span className={styles.chips}>
          {hit.matchedFields.map((f) => <span key={f} className={styles.chip}>{f}</span>)}
          {hit.concepts.map((c) => <span key={c} className={`${styles.chip} ${styles.chipGray}`}>{c}</span>)}
        </span>
      </div>
      <p className={styles.resultWhy}>{doc.subtitle || doc.summary}</p>
      {hit.excerpt && <p className={styles.excerpt}>{hl(hit.excerpt, hit.matchedTerms)}</p>}
      <div className={styles.refs}>
        {doc.codeRefs.length > 0
          ? doc.codeRefs.map((r) => (
            <div key={r.url + r.path} className={styles.ref}>
              <a href={r.url} target="_blank" rel="noreferrer noopener">{r.label}</a>
              <code className={styles.refPath}>{r.path}</code>
              <span className={styles.refNote}>{r.note}（{r.verifiedAt} @ {r.ref}）</span>
            </div>
          ))
          : <p className={styles.noRef}>暂无核验源码入口——先看导读里的做法。</p>}
      </div>
      {(doc.prerequisites.length > 0 || doc.notFor) && (
        <p className={styles.fit}>
          {doc.prerequisites.length > 0 && <>适用：<b>{doc.prerequisites.join("；")}</b></>}
          {doc.prerequisites.length > 0 && doc.notFor && "　"}
          {doc.notFor && <>不适合：<b>{doc.notFor}</b></>}
        </p>
      )}
      <div className={styles.more}>
        <Link href={doc.href} className={styles.textBtn}>完整导读 →</Link>
      </div>
    </li>
  );
}

export function RepositoryFinder() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname() || "/readings/find/";
  const q = params.get("q") ?? "";
  const [input, setInput] = useState(q);
  const [idx, setIdx] = useState<IndexPayload | null>(null);
  const [loadErr, setLoadErr] = useState("");
  const composing = useRef(false);
  const seq = useRef(0);
  const loadCtl = useRef<AbortController | null>(null);
  const committedQ = useRef(q); // 本组件写过的 q：区分 URL 回声与 popstate/外改

  /** 输入→URL 的唯一出口：防抖 replace 与提交 push 共用，先记回声再导航。 */
  const commitInput = useCallback((v: string, push: boolean) => {
    const trimmed = v.trim();
    const next = new URLSearchParams(params.toString());
    if (trimmed) next.set("q", trimmed); else next.delete("q");
    committedQ.current = trimmed;
    const url = `${pathname}?${next.toString()}`;
    if (push) router.push(url); else router.replace(url);
  }, [params, pathname, router]);

  // 静态索引只在搜索页懒取一次；重试/卸载时取消在途请求
  const load = useCallback(async () => {
    const s = ++seq.current;
    loadCtl.current?.abort();
    const c = new AbortController();
    loadCtl.current = c;
    try {
      const res = await fetch("/readings/search-index.json", { signal: c.signal, cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as IndexPayload;
      if (s !== seq.current) return; // 过期响应作废
      setIdx(data); setLoadErr("");
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      // 原生 fetch 错误信息（Failed to fetch 之类）不给用户看——统一中文提示+重试
      if (s === seq.current) setLoadErr(e instanceof Error && e.message.startsWith("HTTP") ? `索引服务暂时不可用（${e.message}）。` : "索引暂时加载失败，可能是网络问题。"); // 只让当前请求写错
    }
  }, []);
  useEffect(() => {
    const t = setTimeout(() => void load(), 0);
    return () => { clearTimeout(t); seq.current += 1; loadCtl.current?.abort(); };
  }, [load]);

  // q 变化：自己提交的（committedQ）是回声，跳过；popstate/外改才同步进输入框
  useEffect(() => {
    if (q === committedQ.current) return;
    const t = setTimeout(() => { committedQ.current = q; setInput(q); }, 0);
    return () => clearTimeout(t);
  }, [q]);

  // 输入防抖 350ms → URL replace（不堆历史）；IME 组合期间不动，结束时由 compositionEnd 补发
  useEffect(() => {
    const t = setTimeout(() => {
      if (composing.current || input.trim() === q) return;
      commitInput(input, false);
    }, 350);
    return () => clearTimeout(t);
  }, [input, q, commitInput]);

  // 检索在效果回调里跑（计时是副作用）；setTimeout 0 保持「异步外部系统」语义
  const [searched, setSearched] = useState<{ hits: SearchHit[]; ms: number } | null>(null);
  useEffect(() => {
    const t = setTimeout(() => {
      if (!idx || !q.trim()) { setSearched(null); return; }
      const t0 = performance.now();
      const hits = search(idx.docs, q);
      setSearched({ hits, ms: performance.now() - t0 });
    }, 0);
    return () => clearTimeout(t);
  }, [idx, q]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    commitInput(input, true); // 提交才压历史，后退能回到上一个问题
  };

  return (
    <div className={styles.wrap}>
      <form className={styles.searchBox} onSubmit={submit} role="search">
        <input
          className={styles.input}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onCompositionStart={() => { composing.current = true; }}
          onCompositionEnd={(e) => { composing.current = false; commitInput(e.currentTarget.value, false); }}
          placeholder="想实现什么？比如：把扫描 PDF 里的表格提出来"
          aria-label="想实现什么"
          maxLength={300}
        />
        <button type="submit" className={styles.go} disabled={!input.trim()}>找</button>
      </form>

      <div className={styles.examples}>
        <span className={styles.examplesLabel}>试试这些：</span>
        {EXAMPLES.map((x) => (
          <button key={x} type="button" className={styles.example} onClick={() => { setInput(x); commitInput(x, true); }}>{x}</button>
        ))}
      </div>

      <p className={styles.meta}>
        {idx
          ? <>收录 <b>{idx.total}</b> 个仓库精读，其中 <b>{idx.withCodeRefs}</b> 个已标注核验源码入口{!idx.capabilitiesLoaded && "（源码入口标注进行中）"}；按任务、能力和正文线索匹配，命中可查看出处。</>
          : loadErr ? "索引暂时没取到。" : "正在读索引……"}
        {searched && q.trim() && <>　命中 {searched.hits.length} 条<span className={styles.metaDim}>（{searched.ms.toFixed(0)}ms）</span>。</>}
      </p>

      {loadErr ? (
        <div className={styles.state}>{loadErr}<button type="button" onClick={() => void load()}>重试</button></div>
      ) : !idx ? (
        <div className={styles.state}>正在读索引……</div>
      ) : searched === null ? (
        <div className={styles.state}>输入一个想做的事——越具体越好，比如任务、材料、约束条件。</div>
      ) : searched.hits.length === 0 ? (
        <div className={styles.state}>
          这个问题没有匹配到已拆的仓库。换个更具体的任务试试（说清材料、输入输出、约束），或者<Link href="/readings/">翻全部精读</Link>。
        </div>
      ) : (
        <ul className={styles.results}>
          {searched.hits.map((h) => <Result key={h.doc.id} hit={h} />)}
        </ul>
      )}
    </div>
  );
}
