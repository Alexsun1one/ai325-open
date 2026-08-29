"use client";
import { useState, type ReactNode } from "react";

/* 极简 Markdown 渲染：只支持我们内容里真实用到的语法——标题、段落、有序/无序列表、
   ``` 围栏代码块（保留换行与全角，带复制按钮）、表格、引用、分隔线、行内 **粗** `码` [链接]。
   不引第三方库：站点是静态导出，正文全部来自我们自己写的 JSON，语法可控。 */

/** 只放行 http(s)、mailto、站内相对路径与页内锚点。 */
function safeHref(raw: string): string | null {
  const v = (raw || "").trim();
  if (!v) return null;
  if (/^(https?:\/\/|mailto:)/i.test(v)) return v;
  if (/^[/#]/.test(v) && !/^\/\//.test(v)) return v;
  return null;
}

function inline(src: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*)|(`[^`]+`)|(\[[^\]]+\]\([^)]+\))/g;
  let last = 0, m: RegExpExecArray | null, i = 0;
  while ((m = re.exec(src))) {
    if (m.index > last) out.push(src.slice(last, m.index));
    const t = m[0];
    if (t.startsWith("**")) out.push(<b key={`${key}-b${i}`}>{t.slice(2, -2)}</b>);
    else if (t.startsWith("`")) out.push(<code key={`${key}-c${i}`} className="num rounded-[3px] border border-rule bg-paper-2 px-1 py-[1px] text-[0.88em] text-ink-2">{t.slice(1, -1)}</code>);
    else {
      const mm = /\[([^\]]+)\]\(([^)]+)\)/.exec(t)!;
      const href = safeHref(mm[2]);
      // 协议不在白名单里就不给可点的链接，只留文字——正文虽然是自产的，但一行就能堵住
      out.push(href
        ? <a key={`${key}-a${i}`} href={href} target="_blank" rel="noopener noreferrer" className="text-blue-text underline underline-offset-2">{mm[1]}</a>
        : <span key={`${key}-a${i}`} className="text-ink-2">{mm[1]}</span>);
    }
    last = m.index + t.length; i++;
  }
  if (last < src.length) out.push(src.slice(last));
  return out;
}

export function CodeBlock({ code, lang }: { code: string; lang?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 1800); } catch {}
  };
  return (
    <div className="group relative my-5 overflow-hidden rounded-[8px] border border-rule bg-paper-2/70">
      <div className="flex items-center justify-between border-b border-rule-soft px-3 py-1.5">
        <span className="num font-sans text-[11px] tracking-[0.1em] text-ink-3">{lang || "文本"}</span>
        <button type="button" onClick={copy} className="inline-flex min-h-11 items-center px-1 font-sans text-[12px] font-semibold text-blue-text transition-opacity hover:opacity-75 sm:min-h-0 sm:px-0">
          {copied ? "已复制" : "复制"}
        </button>
      </div>
      <pre className="overflow-x-auto px-3.5 py-3 text-[13px] leading-[1.75]"><code className="num whitespace-pre text-ink">{code}</code></pre>
    </div>
  );
}

export function Markdown({ src, className = "" }: { src: string; className?: string }) {
  const lines = (src || "").replace(/\r\n/g, "\n").split("\n");
  const out: ReactNode[] = [];
  let i = 0, k = 0;

  const flushList = (ordered: boolean, items: string[]) => {
    const Tag = ordered ? "ol" : "ul";
    out.push(
      <Tag key={`l${k++}`} className={`my-4 space-y-2 ${ordered ? "list-none" : "list-none"}`}>
        {items.map((it, n) => (
          <li key={n} className="grid grid-cols-[26px_1fr] gap-2">
            <span className={`num pt-[2px] font-sans text-[13px] font-semibold ${ordered ? "text-blue-text" : "text-amber-text"}`}>{ordered ? `${n + 1}.` : "·"}</span>
            <span>{inline(it, `l${k}-${n}`)}</span>
          </li>
        ))}
      </Tag>
    );
  };

  while (i < lines.length) {
    const line = lines[i];

    if (/^\s*$/.test(line)) { i++; continue; }

    // 围栏代码块
    if (/^\s*```/.test(line)) {
      const lang = line.replace(/^\s*```/, "").trim();
      const body: string[] = [];
      i++;
      while (i < lines.length && !/^\s*```/.test(lines[i])) { body.push(lines[i]); i++; }
      i++; // 收尾的 ```
      out.push(<CodeBlock key={`k${k++}`} code={body.join("\n")} lang={lang} />);
      continue;
    }

    // 表格
    if (line.includes("|") && i + 1 < lines.length && /^\s*\|?[\s:-]*-[-\s:|]*\|/.test(lines[i + 1])) {
      const cells = (r: string) => r.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map((c) => c.trim());
      const head = cells(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) { rows.push(cells(lines[i])); i++; }
      out.push(
        <div key={`t${k++}`} className="my-5 overflow-x-auto">
          <table className="w-full border-collapse text-[14px]">
            <thead>
              <tr className="border-y border-rule">{head.map((h, n) => <th key={n} className="label whitespace-nowrap py-2 pr-5 text-left">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-rule-soft">
              {rows.map((r, n) => (
                <tr key={n}>{r.map((c, m) => <td key={m} className="py-2.5 pr-5 align-top font-sans leading-relaxed text-ink-2">{inline(c, `t${n}-${m}`)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    // 标题
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      const lv = h[1].length;
      // # / ## → h2，### → h3，#### → h4。正文里不再出现第二个 h1。
      const Tag = (lv <= 2 ? "h2" : lv === 3 ? "h3" : "h4") as "h2" | "h3" | "h4";
      const cls = lv <= 2 ? "mt-8 font-serif text-[21px] font-bold text-ink" : lv === 3 ? "mt-6 font-serif text-[18px] font-bold text-ink" : "mt-5 font-serif text-[16.5px] font-bold text-ink-2";
      out.push(<Tag key={`h${k++}`} className={cls}>{inline(h[2], `h${k}`)}</Tag>);
      i++; continue;
    }

    // 分隔线
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) { out.push(<hr key={`r${k++}`} className="my-7 border-t border-rule" />); i++; continue; }

    // 引用
    if (/^\s*>\s?/.test(line)) {
      const body: string[] = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) { body.push(lines[i].replace(/^\s*>\s?/, "")); i++; }
      out.push(<blockquote key={`q${k++}`} className="my-5 border-l-2 border-amber-wash-2 pl-4 text-ink-2">{inline(body.join(" "), `q${k}`)}</blockquote>);
      continue;
    }

    // 列表
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*\d+\.\s+/, "")); i++; }
      flushList(true, items); continue;
    }
    if (/^\s*[-*·]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*·]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*·]\s+/, "")); i++; }
      flushList(false, items); continue;
    }

    // 段落
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^\s*(#{1,4}\s|```|>|\d+\.\s|[-*·]\s|-{3,})/.test(lines[i]) && !(lines[i].includes("|") && i + 1 < lines.length && /^\s*\|?[\s:-]*-[-\s:|]*\|/.test(lines[i + 1]))) {
      para.push(lines[i]); i++;
    }
    if (para.length) out.push(<p key={`p${k++}`} className="my-4 leading-[1.9]">{inline(para.join(""), `p${k}`)}</p>);
    else i++;
  }

  return <div className={`prose-sheet text-[16.5px] ${className}`}>{out}</div>;
}
