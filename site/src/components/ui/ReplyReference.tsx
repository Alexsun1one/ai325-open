"use client";
import { useCallback, useEffect, useRef } from "react";
import { pioneerStickerText } from "@/lib/pioneer-stickers";
import styles from "./ReplyReference.module.css";

/* Discord 式回复引用：圆角折线 + 被回复者 + 原文短摘。点击/Enter/Space 跳回原消息
   并短暂高亮聚焦（键盘激活与 reduce-motion 都不平滑滚动）。摘录是截断纯文本。
   targetId 为空或父消息不在已读数据里 → 「原消息暂不可见」，不发明原文、不补请求。 */

const EXCERPT_MAX = 80;

function excerptOf(text?: string | null): string {
  // 先过共享 pioneerStickerText——已知 :xf-…: 变 [名称]，未知 token 原样，引用不裸 token
  const flat = pioneerStickerText(text ?? "").replace(/\s+/g, " ").trim();
  return flat.length > EXCERPT_MAX ? `${flat.slice(0, EXCERPT_MAX)}…` : flat;
}

export function ReplyReference({ targetId, name, text }: {
  targetId?: string | null;
  name?: string | null;
  text?: string | null;
}) {
  const timer = useRef<number | undefined>(undefined);
  const flashEl = useRef<HTMLElement | null>(null); // 卸载时连描边一起撤，不留残影
  useEffect(() => () => {
    window.clearTimeout(timer.current);
    flashEl.current?.classList.remove("reply-flash");
  }, []);

  const jump = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
    const el = targetId ? document.getElementById(targetId) : null;
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const keyboard = e.detail === 0; // 键盘激活无指针坐标，滚动立刻到位
    el.scrollIntoView({ behavior: reduce || keyboard ? "auto" : "smooth", block: "center" });
    el.focus({ preventScroll: true });
    el.classList.add("reply-flash");
    flashEl.current = el;
    window.clearTimeout(timer.current); // 重复点同一目标：计时重置，描边再亮 1.6s
    timer.current = window.setTimeout(() => { el.classList.remove("reply-flash"); flashEl.current = null; }, 1600);
  }, [targetId]);

  const quote = excerptOf(text);
  if (!targetId) {
    return (
      <span className={`${styles.ref} ${styles.missing}`}>
        <span className={styles.elbow} aria-hidden />原消息暂不可见
      </span>
    );
  }
  return (
    <button type="button" className={styles.ref} onClick={jump}
      aria-label={name ? `回到 ${name} 的原话` : "回到原话"}>
      <span className={styles.elbow} aria-hidden />
      {name ? <span className={styles.who}>{name}</span> : null}
      {quote ? <span className={styles.quote}>{quote}</span> : null}
    </button>
  );
}
