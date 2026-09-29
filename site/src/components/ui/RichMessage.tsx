"use client";
import type { ReactNode } from "react";
import { STICKER_BY_TOKEN, STICKER_IMAGE_LIMIT, STICKER_SOLO_RE, STICKER_TOKEN_SRC } from "@/lib/pioneer-stickers";
import styles from "./RichMessage.module.css";

/* 评论/回复用的最小安全 Markdown：### 标题、> 引用、- / 1. 列表、``` 围栏代码、
   行内 **粗** `码` [链接](http/https)、先锋队表情 :xf-{id}:。全部按 token 渲染成
   React 节点——原文里的 HTML 与 script 只是纯文本，永远不会被执行；旧纯文本的
   单换行原样保留。表情只解析白名单 token（代码块/行内码不解析），单条最多
   STICKER_IMAGE_LIMIT 个图片，超出退化 [名称] 文本；图片 src 固定站内。 */

/** 用户内容只放行 http(s)；其他协议（javascript: 等）退化为纯文字。 */
function safeHref(raw: string): string | null {
  const v = (raw || "").trim();
  return /^https?:\/\/\S+$/i.test(v) ? v : null;
}

const INLINE_RE = new RegExp(
  `(\\*\\*[^*\\n]+(?:\\*(?!\\*)[^*\\n]*)*\\*\\*)|(\`[^\`\\n]+\`)|(\\[[^\\]\\n]+\\]\\([^)\\n]+\\))|(${STICKER_TOKEN_SRC})`,
  "g",
);

function inline(src: string, key: string, budget: { left: number }, solo = false): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0, i = 0;
  // matchAll 自带独立迭代器：bold 递归重入也不共享 lastIndex
  for (const m of src.matchAll(INLINE_RE)) {
    if (m.index > last) out.push(src.slice(last, m.index));
    const t = m[0];
    const sticker = STICKER_BY_TOKEN.get(t);
    if (sticker) {
      if (budget.left > 0) {
        budget.left -= 1;
        // solo 由调用方按整行判定：夹正文 48px，整行仅表情 96px
        out.push(
          <img
            key={`${key}-s${i}`}
            src={sticker.src}
            alt={sticker.name}
            width={solo ? 96 : 48}
            height={solo ? 96 : 48}
            loading="lazy"
            decoding="async"
            className={solo ? styles.stickerSolo : styles.sticker}
          />,
        );
      } else {
        out.push(`[${sticker.name}]`);
      }
    }
    else if (t.startsWith("**")) out.push(<strong key={`${key}-b${i}`}>{inline(t.slice(2, -2), `${key}-b${i}`, budget, solo)}</strong>);
    else if (t.startsWith("`")) out.push(<code key={`${key}-c${i}`} className={styles.code}>{t.slice(1, -1)}</code>);
    else {
      const mm = /\[([^\]\n]+)\]\(([^)\n]+)\)/.exec(t)!;
      const href = safeHref(mm[2]);
      out.push(href
        ? <a key={`${key}-a${i}`} href={href} target="_blank" rel="noopener noreferrer nofollow" className={styles.link}>{mm[1]}</a>
        : <span key={`${key}-a${i}`}>{mm[1]}</span>);
    }
    last = m.index + t.length; i++;
  }
  if (last < src.length) out.push(src.slice(last));
  return out;
}

/** 段落内逐行渲染：单换行就是换行，不折叠。整行仅表情 token 的行走 96px。 */
function lines(src: string, key: string, budget: { left: number }): ReactNode[] {
  return src.split("\n").flatMap((line, n) => {
    const nodes = inline(line, `${key}-${n}`, budget, STICKER_SOLO_RE.test(line));
    return n === 0 ? nodes : [<br key={`${key}-br${n}`} />, ...nodes];
  });
}

export function RichMessage({ text, className = "" }: { text: string; className?: string }) {
  const src = (text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const rows = src.split("\n");
  const out: ReactNode[] = [];
  const budget = { left: STICKER_IMAGE_LIMIT }; // 表情图片预算：本条消息全程共享
  let i = 0, k = 0;

  while (i < rows.length) {
    const line = rows[i];

    if (/^\s*$/.test(line)) { i++; continue; }

    // 围栏代码块
    if (/^\s*```/.test(line)) {
      const lang = line.replace(/^\s*```/, "").trim();
      const body: string[] = [];
      i++;
      while (i < rows.length && !/^\s*```/.test(rows[i])) { body.push(rows[i]); i++; }
      i++;
      out.push(
        <pre key={`c${k++}`} className={styles.block} data-lang={lang || undefined}>
          <code>{body.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    // 标题（评论里只用小标题一级外观）
    const h = /^\s*(#{1,6})\s+(.*)$/.exec(line);
    if (h) {
      out.push(<p key={`h${k++}`} className={styles.heading} role="heading" aria-level={3}>{inline(h[2], `h${k}`, budget, STICKER_SOLO_RE.test(h[2]))}</p>);
      i++; continue;
    }

    // 引用：连续 > 行
    if (/^\s*>\s?/.test(line)) {
      const body: string[] = [];
      while (i < rows.length && /^\s*>\s?/.test(rows[i])) { body.push(rows[i].replace(/^\s*>\s?/, "")); i++; }
      out.push(<blockquote key={`q${k++}`} className={styles.quote}>{lines(body.join("\n"), `q${k}`, budget)}</blockquote>);
      continue;
    }

    // 列表：连续同类行
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < rows.length && /^\s*\d+\.\s+/.test(rows[i])) { items.push(rows[i].replace(/^\s*\d+\.\s+/, "")); i++; }
      out.push(
        <ol key={`o${k++}`} className={styles.list}>
          {items.map((it, n) => <li key={n}><span className={styles.marker} aria-hidden>{n + 1}.</span><span>{inline(it, `o${k}-${n}`, budget, STICKER_SOLO_RE.test(it))}</span></li>)}
        </ol>,
      );
      continue;
    }
    if (/^\s*[-*·]\s+/.test(line)) {
      const items: string[] = [];
      while (i < rows.length && /^\s*[-*·]\s+/.test(rows[i])) { items.push(rows[i].replace(/^\s*[-*·]\s+/, "")); i++; }
      out.push(
        <ul key={`u${k++}`} className={styles.list}>
          {items.map((it, n) => <li key={n}><span className={styles.marker} aria-hidden>·</span><span>{inline(it, `u${k}-${n}`, budget, STICKER_SOLO_RE.test(it))}</span></li>)}
        </ul>,
      );
      continue;
    }

    // 普通段落：吃到下一个块级语法或空行
    const para: string[] = [];
    while (i < rows.length && rows[i].trim() && !/^\s*(#{1,6}\s|```|>\s?|\d+\.\s|[-*·]\s)/.test(rows[i])) {
      para.push(rows[i]); i++;
    }
    if (para.length) out.push(<p key={`p${k++}`} className={styles.para}>{lines(para.join("\n"), `p${k}`, budget)}</p>);
    else i++;
  }

  return <div className={`${styles.msg} ${className}`}>{out}</div>;
}
