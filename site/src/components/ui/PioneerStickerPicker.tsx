"use client";
import { useEffect, useRef, type KeyboardEvent } from "react";
import { PIONEER_STICKERS, PIONEER_STICKER_PACK_URL, type PioneerSticker } from "@/lib/pioneer-stickers";
import styles from "./PioneerStickerPicker.module.css";

/* 表情选择面板：由 MarkdownComposer 首次展开时才挂载（dynamic import）。
   只做静态小图 + 中文名按钮；Esc 关闭并回焦输入框。 */

export default function PioneerStickerPicker({
  onPick,
  onClose,
}: {
  onPick: (sticker: PioneerSticker) => void;
  onClose: () => void;
}) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // 展开即把焦点放进第一格，键盘流不丢
    box.current?.querySelector<HTMLButtonElement>("button")?.focus();
  }, []);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      onClose();
    }
  };

  return (
    <div ref={box} className={styles.panel} role="group" aria-label="先锋队表情" onKeyDown={onKeyDown}>
      {PIONEER_STICKERS.map((s) => (
        <button
          key={s.id}
          type="button"
          className={styles.cell}
          onClick={() => onPick(s)}
          aria-label={`插入表情「${s.name}」`}
          title={s.name}
        >
          <img
            src={s.src}
            alt=""
            width={40}
            height={40}
            loading="lazy"
            decoding="async"
            className={styles.face}
          />
          <span className={styles.name}>{s.name}</span>
        </button>
      ))}
      <a
        className={styles.pack}
        href={PIONEER_STICKER_PACK_URL}
        download
      >
        下载整套表情
      </a>
    </div>
  );
}
