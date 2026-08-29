/**
 * 渲染层智能分段：把「一整坨没有换行的正文」按句读切成几段，只影响显示，不动数据。
 *
 * 为什么不在数据里加换行：日报是 LLM 蒸出来的，每天重跑；在数据里排版会被下一次覆盖，
 * 而且同一段文字在不同宽度下该怎么断本来就该由渲染层决定。
 */

const TERMINATORS = "。！？!?…";
/** 成对符号：在里面遇到句号也不能断（引文里的句号属于引文） */
const OPENERS = "「『（(《〈【[“‘";
const CLOSERS = "」』）)》〉】]”’";
/** 句末标点后面还可能跟着的收尾符号，要一起留在上一句 */
const TRAILERS = "」』）)》〉】]”’…、";
const VOID = new Set(["br", "img", "hr", "input", "wbr", "meta", "link"]);

export interface SegmentOptions {
  /** 低于这个长度就不拆——短段落本来就读得动 */
  min?: number;
  /** 一段大约多少字（汉字数），用来推算该分几段 */
  per?: number;
}

/** 把一段 HTML 按句子切开；标签内部、成对符号内部、以及尚未闭合的元素内部永不切断。 */
function sentences(html: string): string[] {
  const out: string[] = [];
  let buf = "";
  let inTag = false;
  let quote = 0;          // 「」『』（）… 的嵌套深度
  const open: string[] = []; // 尚未闭合的 HTML 元素栈
  let tag = "";

  const flushable = () => quote === 0 && open.length === 0;

  for (let i = 0; i < html.length; i++) {
    const ch = html[i];
    buf += ch;
    if (ch === "<") { inTag = true; tag = ""; continue; }
    if (inTag) {
      if (ch !== ">") { tag += ch; continue; }
      inTag = false;
      const m = /^\s*(\/?)\s*([a-zA-Z][\w-]*)/.exec(tag);
      const selfClosing = /\/\s*$/.test(tag);
      if (m && !selfClosing) {
        if (m[1]) { const k = open.lastIndexOf(m[2].toLowerCase()); if (k >= 0) open.splice(k, 1); }
        else if (!VOID.has(m[2].toLowerCase())) open.push(m[2].toLowerCase());
      }
      continue;
    }
    if (OPENERS.includes(ch)) { quote++; continue; }
    if (CLOSERS.includes(ch)) { quote = Math.max(0, quote - 1); continue; }
    if (!TERMINATORS.includes(ch) || !flushable()) continue;

    // 句末标点后面紧跟的收尾符号、以及紧接的闭合标签，都留在这一句
    let j = i + 1;
    for (;;) {
      if (j < html.length && TRAILERS.includes(html[j])) { buf += html[j]; j++; continue; }
      if (html[j] === "<" && html[j + 1] === "/") {
        const k = html.indexOf(">", j);
        if (k < 0) break;
        const name = /^<\/\s*([a-zA-Z][\w-]*)/.exec(html.slice(j, k + 1))?.[1]?.toLowerCase();
        if (name) { const idx = open.lastIndexOf(name); if (idx >= 0) open.splice(idx, 1); }
        buf += html.slice(j, k + 1);
        j = k + 1;
        continue;
      }
      break;
    }
    i = j - 1;
    if (!flushable()) continue;
    out.push(buf);
    buf = "";
  }
  if (buf.trim()) out.push(buf);
  return out;
}

/** 只数中文与字母，标点不计——用来判断「这一段够不够长」。 */
function weight(s: string) {
  return s.replace(/<[^>]+>/g, "").replace(/[\s\p{P}]/gu, "").length;
}

/**
 * 返回分好的段落数组。已经带 <p>、<br> 或空行的内容原样保留（作者已经排过版）。
 * 分段目标：每段约 2–3 行（CJK 约 60–90 字），并让各段长度尽量均匀。
 */
export function segment(html: string, opts: SegmentOptions = {}): string[] {
  const src = (html ?? "").trim();
  if (!src) return [];
  if (/<p[\s>]|<br\s*\/?>|\n\s*\n/i.test(src)) {
    return src.split(/\n\s*\n|<br\s*\/?>\s*<br\s*\/?>/i).map((x) => x.trim()).filter(Boolean);
  }
  const min = opts.min ?? 80;
  const per = opts.per ?? 85;          // 一段大约多少字
  const total = weight(src);
  if (total <= min) return [src];

  const ss = sentences(src);
  if (ss.length < 2) return [src];

  // 先定段数，再由段数反推目标长度——这样各段长度均匀，不会出现「长长长短」
  const n = Math.max(2, Math.min(ss.length, Math.round(total / per)));
  if (n < 2) return [src];
  const target = total / n;

  const paras: string[] = [];
  let cur = "";
  for (let i = 0; i < ss.length; i++) {
    cur += ss[i];
    const rest = ss.slice(i + 1).join("");
    const left = paras.length + 1;     // 收了这段之后已有几段
    // 尾巴用绝对下限守，不用比例——比例会让「刚好差一两个字」的段落整个断不开
    if (left < n && weight(cur) >= target * 0.75 && weight(rest) >= 22) {
      paras.push(cur); cur = "";
    }
  }
  if (cur.trim()) {
    if (paras.length && weight(cur) < 26) paras[paras.length - 1] += cur;
    else paras.push(cur);
  }
  return paras.length ? paras : [src];
}
