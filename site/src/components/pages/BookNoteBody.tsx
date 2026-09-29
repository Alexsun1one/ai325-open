/* 书籍 Markdown 正文的安全服务端渲染（BOOK-BODY R1 冻结接口）。
 * 纯服务端组件：无 use client、无 dangerouslySetInnerHTML、原始 HTML 一律按文本转义。
 * 渲染与 bookNoteHeadings 共用同一 parseBlocks：标题 id（book-section-N）与目录一一对应。 */

import { Fragment, type ReactNode } from "react";
import styles from "./BookNoteBody.module.css";

type ListItem = { text: string; ordered: boolean; kids: ListItem[] };
type Block =
  | { t: "h"; level: number; id: string; text: string }
  | { t: "p"; text: string }
  | { t: "code"; lang: string; text: string }
  | { t: "quote"; paras: string[] }
  | { t: "table"; head: string[]; rows: string[][] }
  | { t: "list"; items: ListItem[] }
  | { t: "hr" };

const FENCE = /^\s{0,3}(`{3,}|~{3,})(.*)$/;
const HEAD = /^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$/;
const HR = /^\s{0,3}(-{3,}|\*{3,}|_{3,})\s*$/;
const LIST = /^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/;
const QUOTE = /^\s{0,3}>\s?(.*)$/;
const TABLE_SEP = /^\s*\|?(\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$/;

const isTableSep = (l: string) => l.includes("|") && l.includes("-") && TABLE_SEP.test(l);
/** 无表头表格行：首尾为未转义管道且确有多格（行内管道/转义管道不误当） */
const isRowLine = (l: string) => {
  const t = l.trim();
  if (t.length < 4 || !t.startsWith("|") || !t.endsWith("|") || t.endsWith("\\|")) return false;
  return splitRow(t).length >= 2;
};
/** Markdown 可转义标点（CommonMark ASCII punctuation）：\mathcal/\alpha 等字母序列不吞反斜杠 */
const ESCAPABLE = /[!"#$%&'()*+,\-./:;<=>?@[\]^_`{|}~]/;
const indentOf = (l: string) => (/^\s*/.exec(l)?.[0] ?? "").replace(/\t/g, "  ").length;

/** 未转义分隔符定位（转义管道 \|、\* 等不拆结构） */
function findUnescaped(s: string, token: string, from: number): number {
  for (let i = s.indexOf(token, from); i !== -1; i = s.indexOf(token, i + 1)) {
    if (i === 0 || s[i - 1] !== "\\") return i;
  }
  return -1;
}

/** 配对右括号：允许 URL 内含平衡括号 */
function findCloseParen(s: string, from: number): number {
  let depth = 0;
  for (let i = from; i < s.length; i++) {
    if (s[i] === "\\" && i + 1 < s.length && ESCAPABLE.test(s[i + 1])) { i++; continue; }
    if (s[i] === "(") depth++;
    else if (s[i] === ")") { if (depth === 0) return i; depth--; }
  }
  return -1;
}

/** 链接白名单：本站相对路径/锚点/http(s) 真主机；其余（javascript/data/vbscript/反斜杠/协议相对）拒收 */
function safeHref(raw: string): string | null {
  const v = raw.trim();
  if (!v || v.length > 2000 || v.includes("\\") || /[\x00-\x1f\x7f]/.test(v)) return null;
  if (v.startsWith("#")) return v;
  if (v.startsWith("/")) return v.startsWith("//") ? null : v;
  if (/^https?:\/\//i.test(v)) {
    try { return new URL(v).hostname ? v : null; } catch { return null; }
  }
  return null;
}

/** 行内解析：粗体/斜体/行内代码/链接/降级图片/转义；其余字符原样（React 自动转义原始 HTML） */
function inlineNodes(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let buf = "", i = 0, k = 0;
  const flush = () => { if (buf) { out.push(buf); buf = ""; } };
  while (i < text.length) {
    if (text[i] === "\\" && i + 1 < text.length && ESCAPABLE.test(text[i + 1])) { buf += text[i + 1]; i += 2; continue; }
    if (text.startsWith("**", i)) {
      const j = findUnescaped(text, "**", i + 2);
      if (j > i + 2) { flush(); out.push(<strong key={k++}>{inlineNodes(text.slice(i + 2, j))}</strong>); i = j + 2; continue; }
    }
    if (text[i] === "`") {
      const j = findUnescaped(text, "`", i + 1);
      if (j > i + 1) { flush(); out.push(<code key={k++} className={styles.ic}>{text.slice(i + 1, j)}</code>); i = j + 1; continue; }
    }
    if (text[i] === "*" || text[i] === "_") {
      const c = text[i];
      const before = i === 0 ? "" : text[i - 1];
      // 词内下划线不斜体（snake_case 保持原样）
      if (c === "_" && /[\p{L}\p{N}]/u.test(before)) { buf += c; i++; continue; }
      const j = findUnescaped(text, c, i + 1);
      const after = j + 1 < text.length ? text[j + 1] : "";
      if (j > i + 1 && !(c === "_" && /[\p{L}\p{N}]/u.test(after))) {
        flush(); out.push(<em key={k++}>{inlineNodes(text.slice(i + 1, j))}</em>); i = j + 1; continue;
      }
    }
    if (text.startsWith("![", i) || text[i] === "[") {
      const img = text[i] === "!";
      const open = i + (img ? 1 : 0);
      const close = findUnescaped(text, "](", open + 1);
      if (close > open + 1) {
        const end = findCloseParen(text, close + 2);
        if (end > close + 2) {
          const label = text.slice(open + 1, close);
          const url = text.slice(close + 2, end);
          flush();
          if (img) {
            // 源笔记图片不拉未知外链：降级为文字说明
            out.push(<span key={k++} className={styles.fig}>{`图：${label.trim() || "未命名"}`}</span>);
          } else {
            const href = safeHref(url);
            if (href) {
              const ext = /^https?:\/\//i.test(href);
              out.push(ext
                ? <a key={k++} className={styles.link} href={href} target="_blank" rel="noreferrer noopener">{inlineNodes(label)}</a>
                : <a key={k++} className={styles.link} href={href}>{inlineNodes(label)}</a>);
            } else {
              out.push(label); // 链接失效：保留文字，不输出 href
            }
          }
          i = end + 1; continue;
        }
      }
    }
    buf += text[i]; i++;
  }
  flush();
  return out;
}

/** 嵌套列表：按缩进递归；同级 ordered/unordered 连续段各自归组 */
function parseListItems(lines: string[], start: number): { items: ListItem[]; end: number } {
  const base = indentOf(lines[start]);
  const items: ListItem[] = [];
  let i = start;
  while (i < lines.length) {
    const m = LIST.exec(lines[i]);
    if (!m || indentOf(lines[i]) < base) break;
    if (indentOf(lines[i]) > base) {
      const sub = parseListItems(lines, i);
      if (items.length) items[items.length - 1].kids.push(...sub.items); else items.push(...sub.items);
      i = sub.end; continue;
    }
    items.push({ text: m[3], ordered: /\d/.test(m[2]), kids: [] });
    i++;
  }
  return { items, end: i };
}

function splitRow(line: string): string[] {
  let s = line.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|") && !s.endsWith("\\|")) s = s.slice(0, -1);
  const cells: string[] = [];
  let cur = "";
  for (let i = 0; i < s.length; i++) {
    if (s[i] === "\\" && i + 1 < s.length && ESCAPABLE.test(s[i + 1])) { cur += s[i + 1]; i++; continue; } // 可转义标点进文本
    if (s[i] === "|") { cells.push(cur); cur = ""; continue; }
    cur += s[i];
  }
  cells.push(cur);
  return cells.map((c) => c.trim());
}

function parseBlocks(markdown: string): Block[] {
  const lines = String(markdown ?? "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  const blocks: Block[] = [];
  let hseq = 0, i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    const f = FENCE.exec(line);
    if (f) {
      const mark = f[1][0];
      const lang = f[2].trim();
      const buf: string[] = [];
      i++;
      const closer = mark === "`" ? /^\s{0,3}`{3,}/ : /^\s{0,3}~{3,}/;
      while (i < lines.length && !closer.test(lines[i])) { buf.push(lines[i]); i++; }
      i++; // 跳过收尾 fence（EOF 未闭合则全部吃进代码块）
      blocks.push({ t: "code", lang, text: buf.join("\n") });
      continue;
    }
    if (line.includes("|")) {
      // 带表头表格：本行内容 + 下一行分隔（本行自己不能是分隔行）
      if (!isTableSep(line) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
        const head = splitRow(line);
        const rows: string[][] = [];
        i += 2;
        while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
          if (isTableSep(lines[i])) { i++; continue; } // 块中分隔线是噪声不是行
          rows.push(splitRow(lines[i])); i++;
        }
        blocks.push({ t: "table", head, rows });
        continue;
      }
      // 无表头表格/孤儿分隔：连续「首尾管道且≥2格」的行成 tbody 表，
      // 分隔行是结构噪声丢弃；只剩分隔线时整段吞掉不露管道原文
      if (isTableSep(line) || isRowLine(line)) {
        const rows: string[][] = [];
        while (i < lines.length) {
          const l2 = lines[i];
          if (!l2.trim()) break;
          if (isTableSep(l2)) { i++; continue; }
          if (isRowLine(l2)) { rows.push(splitRow(l2)); i++; continue; }
          break;
        }
        if (rows.length) blocks.push({ t: "table", head: [], rows });
        continue;
      }
      // 其余含 | 行（内联管道/单格/无尾管道）走段落，不伪造表格
    }
    const hd = HEAD.exec(line);
    if (hd) { blocks.push({ t: "h", level: hd[1].length, id: `book-section-${++hseq}`, text: hd[2] }); i++; continue; }
    if (HR.test(line)) { blocks.push({ t: "hr" }); i++; continue; }
    if (QUOTE.test(line)) {
      const paras: string[] = [];
      let cur: string[] = [];
      while (i < lines.length) {
        const m = QUOTE.exec(lines[i]);
        if (!m) break;
        if (!m[1].trim()) { if (cur.length) { paras.push(cur.join(" ")); cur = []; } }
        else cur.push(m[1]);
        i++;
      }
      if (cur.length) paras.push(cur.join(" "));
      blocks.push({ t: "quote", paras });
      continue;
    }
    if (LIST.test(line)) {
      const sub = parseListItems(lines, i);
      blocks.push({ t: "list", items: sub.items });
      i = sub.end;
      continue;
    }
    const buf: string[] = [];
    while (i < lines.length && lines[i].trim()
      && !FENCE.test(lines[i]) && !HEAD.test(lines[i]) && !HR.test(lines[i])
      && !QUOTE.test(lines[i]) && !LIST.test(lines[i])
      && !isTableSep(lines[i]) && !isRowLine(lines[i])
      && !(lines[i].includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1]))) {
      buf.push(lines[i]); i++;
    }
    if (buf.length) blocks.push({ t: "p", text: buf.join(" ") });
  }
  return blocks;
}

/** 目录提取与正文同源：跳过代码块的标题，id 顺序编号一致 */
export function bookNoteHeadings(markdown: string): Array<{ id: string; title: string; level: number }> {
  return parseBlocks(markdown)
    .filter((b): b is Extract<Block, { t: "h" }> => b.t === "h")
    .map((b) => ({ id: b.id, title: mdToText(b.text), level: b.level }));
}

function mdToText(s: string): string {
  return s
    .replace(/\\([!"#$%&'()*+,\-./:;<=>?@[\]^_`{|}~])/g, "$1")
    .replace(/!\[(.*?)\]\(.*?\)/g, "$1")
    .replace(/\[(.*?)\]\(.*?\)/g, "$1")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/`(.+?)`/g, "$1")
    .replace(/(^|[^_])_+([^_]+?)_+([^_]|$)/g, "$1$2$3")
    .trim();
}

function renderList(items: ListItem[]): ReactNode {
  const out: ReactNode[] = [];
  let k = 0, i = 0;
  while (i < items.length) {
    const ordered = items[i].ordered;
    const kids: ReactNode[] = [];
    let j = i;
    while (j < items.length && items[j].ordered === ordered) {
      const it = items[j];
      kids.push(<li key={k++}>{inlineNodes(it.text)}{it.kids.length ? renderList(it.kids) : null}</li>);
      j++;
    }
    out.push(ordered ? <ol key={k++}>{kids}</ol> : <ul key={k++}>{kids}</ul>);
    i = j;
  }
  return <>{out}</>;
}

function renderBlock(b: Block, key: number): ReactNode {
  switch (b.t) {
    case "h": {
      // 正文不制造第二个 h1：Markdown 一级标题渲染为 h2，其余级别照旧
      const Tag = (b.level === 1 ? "h2" : `h${b.level}`) as "h2" | "h3" | "h4" | "h5" | "h6";
      return <Tag key={key} id={b.id} className={styles.head}>{inlineNodes(b.text)}</Tag>;
    }
    case "p": return <p key={key}>{inlineNodes(b.text)}</p>;
    case "code":
      return (
        <pre key={key} className={styles.code}>
          {b.lang ? <span className={styles.codeLang}>{b.lang}</span> : null}
          <code>{b.text}</code>
        </pre>
      );
    case "quote":
      return <blockquote key={key} className={styles.quote}>{b.paras.map((p, i2) => <p key={i2}>{inlineNodes(p)}</p>)}</blockquote>;
    case "table":
      return (
        <div key={key} className={styles.tableWrap}>
          <table>
            {b.head.length ? <thead><tr>{b.head.map((c, i2) => <th key={i2}>{inlineNodes(c)}</th>)}</tr></thead> : null}
            <tbody>{b.rows.map((r, ri) => <tr key={ri}>{r.map((c, ci) => <td key={ci}>{inlineNodes(c)}</td>)}</tr>)}</tbody>
          </table>
        </div>
      );
    case "list": return <Fragment key={key}>{renderList(b.items)}</Fragment>;
    case "hr": return <hr key={key} className={styles.hr} />;
  }
}

export default function BookNoteBody({ markdown }: { markdown: string }) {
  const blocks = parseBlocks(markdown);
  return <div className={styles.body}>{blocks.map((b, i) => renderBlock(b, i))}</div>;
}
