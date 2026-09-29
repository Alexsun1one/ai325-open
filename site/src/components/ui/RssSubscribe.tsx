"use client";
import { useEffect, useRef, useState } from "react";
import styles from "./RssSubscribe.module.css";

/** 公开知识 feed 的 canonical 地址——SSR 恒定，不依赖 localStorage 或浏览器态。 */
const FEED_URL = "https://www.ai325.com/feed/learning.xml";

/** RSS 订阅入口：原生 details 小面板，说明 + 复制地址；点击才写剪贴板，
 *  失败降级为可选中的只读输入框手动复制。不自动复制、不新增请求。 */
export function RssSubscribe() {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  const [msg, setMsg] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(FEED_URL);
      setCopied(true);
      setFailed(false);
      setMsg("已复制——到 RSS 阅读器粘贴这个地址。");
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setMsg(""), 5000);
    } catch {
      setCopied(false);
      setFailed(true);
      setMsg("复制没成功——选中下面地址手动复制。");
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  };

  return (
    <details className={styles.rss}>
      <summary className={styles.summary}>RSS 订阅知识</summary>
      <div className={styles.panel}>
        <p className={styles.hint}>把这个地址复制到 RSS 阅读器，公开知识更新会自动送达。</p>
        <div className={styles.row}>
          <input
            ref={inputRef}
            className={styles.addr}
            readOnly
            value={FEED_URL}
            aria-label="RSS 地址"
            onFocus={(e) => e.target.select()}
          />
          <button type="button" className={styles.copy} onClick={() => void copy()}>
            {copied ? "已复制" : "复制地址"}
          </button>
        </div>
        <p className={styles.more}>
          <a href={FEED_URL} target="_blank" rel="noopener noreferrer">打开订阅源 ↗</a>
          {failed && <span className={styles.fail}> · 复制不可用，请手动选中地址复制</span>}
        </p>
        {msg && <p className={styles.msg} role="status">{msg}</p>}
      </div>
    </details>
  );
}
