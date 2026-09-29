"use client";
import dynamic from "next/dynamic";
import { useCallback, useId, useRef, useState, useSyncExternalStore, type KeyboardEvent, type ReactNode } from "react";
import { RichMessage } from "./RichMessage";
import type { PioneerSticker } from "@/lib/pioneer-stickers";
import styles from "./MarkdownComposer.module.css";

/* 评论编辑框：加粗/引用/列表等基础排版键 + 先锋队表情 + 预览；草稿按 draftKey 留在本机
   localStorage，发出成功才清。工具按钮触区 44px，320 宽可横排不溢出。
   draftKey 由调用方带上当前用户标识，避免换账号看到上一账号草稿。
   表情面板首次展开才挂载；插入只写 token 文本、落在当前选区，不自动提交。 */

const PioneerStickerPicker = dynamic(() => import("./PioneerStickerPicker"), { ssr: false });

const DRAFT_PREFIX = "xf-draft:";

function loadDraft(key: string): string {
  if (typeof window === "undefined") return "";
  try { return window.localStorage.getItem(DRAFT_PREFIX + key) ?? ""; } catch { return ""; }
}
function saveDraft(key: string, value: string) {
  try {
    if (value) window.localStorage.setItem(DRAFT_PREFIX + key, value);
    else window.localStorage.removeItem(DRAFT_PREFIX + key);
  } catch { /* 隐私模式写不进就算了，不挡输入 */ }
}

export type Wrap = "bold" | "quote" | "list" | "code" | "link";
export interface Edit { next: string; s: number; e: number }

/** 纯函数：在选区上套/去 Markdown 记号，返回新值与恢复选区。不碰 DOM。 */
export function wrapRange(value: string, s: number, e: number, kind: Wrap): Edit {
  const selected = value.slice(s, e);
  if (kind === "bold" || kind === "code") {
    const mark = kind === "bold" ? "**" : "`";
    if (selected) {
      const next = `${mark}${selected}${mark}`;
      const start = s + mark.length;
      return { next: value.slice(0, s) + next + value.slice(e), s: start, e: start + selected.length };
    }
    const hint = kind === "bold" ? "要点" : "代码";
    const next = `${mark}${hint}${mark}`;
    return { next: value.slice(0, s) + next + value.slice(e), s: s + mark.length, e: s + mark.length + hint.length };
  }
  if (kind === "link") {
    const label = selected || "链接文字";
    const url = "https://example.com";
    const prefix = `[${label}](`;
    const next = `${prefix}${url})`;
    const start = s + prefix.length;
    return { next: value.slice(0, s) + next + value.slice(e), s: start, e: start + url.length };
  }
  // 行首记号：作用于选区覆盖的整行；整段已带记号则去掉
  const mark = kind === "quote" ? "> " : "- ";
  const start = value.lastIndexOf("\n", s - 1) + 1;
  const nl = value.indexOf("\n", e);
  const end = e > s && value[e - 1] === "\n" ? e - 1 : (nl === -1 ? value.length : nl);
  const lines = value.slice(start, end).split("\n");
  const allMarked = lines.every((l) => !l.trim() || l.startsWith(mark));
  const next = lines.map((l) => (!l.trim() ? l : allMarked ? l.slice(mark.length) : mark + l)).join("\n");
  return { next: value.slice(0, start) + next + value.slice(end), s: start, e: start + next.length };
}

const noopSubscribe = () => () => {};

type ControlledProps = {
  value: string;
  onChange: (value: string) => void;
  label: string;
  placeholder?: string;
  maxLength?: number;
  disabled?: boolean;
  rows?: number;
  id?: string;
  onSubmit?: (text: string) => Promise<void>;
};

type LegacyProps = {
  draftKey: string;
  onSubmit: (text: string) => Promise<void>;
  placeholder?: string;
  submitLabel?: string;
  busy?: boolean;
  maxLength?: number;
  label?: string;
};

/** 受控编辑器是论坛接口；LegacyProps 仅保留已有文章评论调用的兼容层。 */
export function MarkdownComposer(props: ControlledProps | LegacyProps) {
  const controlled = "value" in props;
  const draftKey = controlled ? "" : (props as LegacyProps).draftKey;
  const placeholder = props.placeholder;
  const maxLength = props.maxLength ?? 500;
  const disabled = controlled ? (props as ControlledProps).disabled === true : (props as LegacyProps).busy === true;
  const submitLabel = controlled ? "发表" : ((props as LegacyProps).submitLabel ?? "发表");
  const onSubmit = props.onSubmit;
  const controlledValue = controlled ? (props as ControlledProps).value : "";
  const controlledOnChange = controlled ? (props as ControlledProps).onChange : undefined;
  const controlledId = controlled ? (props as ControlledProps).id : undefined;
  const controlledRows = controlled ? ((props as ControlledProps).rows ?? 3) : 3;
  // 草稿恢复：SSR/首帧渲染用服务端快照（空），挂载后 getSnapshot 读 localStorage——无 hydration 冲突
  const restored = useSyncExternalStore(
    noopSubscribe,
    () => controlled ? "" : loadDraft(draftKey),
    () => "",
  );
  const [typed, setTyped] = useState<string | null>(null); // null = 还没动过，用恢复值
  const [prevKey, setPrevKey] = useState(draftKey);
  const [preview, setPreview] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [insertNote, setInsertNote] = useState("");
  const stickerBtn = useRef<HTMLButtonElement>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const composing = useRef(false);
  const generatedId = useId();
  const textareaId = controlledId ?? generatedId;
  if (prevKey !== draftKey) { // 渲染期纠偏（React 官方模式）：换了草稿位就重头再来
    setPrevKey(draftKey);
    setTyped(null);
    setPreview(false);
  }
  const draft = controlled ? controlledValue : typed ?? restored;

  const change = useCallback((value: string) => {
    if (controlled) controlledOnChange?.(value);
    else {
      setTyped(value);
      saveDraft(draftKey, value);
    }
  }, [controlled, controlledOnChange, draftKey]);

  const over = draft.length > maxLength;

  const submit = async () => {
    const text = draft.trim();
    if (!text || disabled || over || !onSubmit) return;
    try {
      await onSubmit(text); // 失败由父级展示；只有成功才清草稿
    } catch {
      return;
    }
    setTyped("");
    setPreview(false);
    saveDraft(draftKey, "");
  };

  const applyTool = (kind: Wrap) => {
    const el = area.current;
    if (!el || disabled || preview) return;
    const edit = wrapRange(el.value, el.selectionStart, el.selectionEnd, kind);
    change(edit.next); // 显式进 state/localStorage，不依赖合成事件回读 DOM
    const { s, e } = edit;
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(s, e); });
  };
  const tool = (kind: Wrap) => () => applyTool(kind);

  // 表情插入：token 落在当前选区（选区被替换、光标移到 token 后），不覆盖其余草稿、
  // 不自动提交；disabled/预览中/IME 合成中/插入会超长时守卫——超长时显式提示而非沉默。
  const insertSticker = (s: PioneerSticker) => {
    const el = area.current;
    if (!el || disabled || preview || composing.current) return;
    const st = el.selectionStart, en = el.selectionEnd;
    const next = draft.slice(0, st) + s.token + draft.slice(en);
    if (next.length > maxLength) {
      setInsertNote("表情放不下了，先删几个字再插");
      return;
    }
    setInsertNote("");
    change(next);
    const caret = st + s.token.length;
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(caret, caret); });
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    const native = event.nativeEvent;
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "b" && !native.isComposing && !composing.current) {
      event.preventDefault();
      applyTool("bold");
    }
  };

  const tools: { kind: Wrap; label: string; title: string; node: ReactNode }[] = [
    { kind: "bold", label: "加粗所选", title: "加粗 **…**", node: <b aria-hidden>B</b> },
    { kind: "quote", label: "引用所选行", title: "引用 >", node: <span aria-hidden className={styles.glyph}>“</span> },
    { kind: "list", label: "把所选行变成列表", title: "列表 -", node: <span aria-hidden className={styles.glyph}>≡</span> },
    { kind: "code", label: "行内代码", title: "行内代码 `…`", node: <span aria-hidden className={styles.mono}>`·`</span> },
    { kind: "link", label: "插入链接并编辑 URL", title: "链接 [文字](URL)", node: <span aria-hidden className={styles.glyph}>↗</span> },
  ];

  return (
    <div className={styles.box}>
      <div className={styles.bar} role="toolbar" aria-label="排版">
        {tools.map((t) => (
          <button key={t.kind} type="button" className={styles.tool} onClick={tool(t.kind)} disabled={disabled || preview}
            aria-label={t.label} title={t.title}>{t.node}</button>
        ))}
        <button
          ref={stickerBtn}
          type="button"
          className={`${styles.tool} ${styles.sticker}`}
          onClick={() => setPickerOpen((v) => !v)}
          disabled={disabled || preview}
          aria-expanded={pickerOpen}
          aria-label="先锋队表情"
          title="先锋队表情"
        >
          <span aria-hidden className={styles.glyph}>☺</span> 表情
        </button>
        <button type="button" className={`${styles.tool} ${styles.preview}`} aria-pressed={preview}
          onClick={() => setPreview((v) => !v)} disabled={!draft.trim() && !preview}>
          {preview ? "继续编辑" : "预览"}
        </button>
      </div>
      {pickerOpen && !disabled && !preview && (
        <PioneerStickerPicker
          onPick={insertSticker}
          onClose={() => { setPickerOpen(false); requestAnimationFrame(() => stickerBtn.current?.focus()); }}
        />
      )}
      {insertNote && <p className={styles.note} role="status">{insertNote}</p>}
      {props.label && <label className={styles.hint} htmlFor={textareaId}>{props.label}</label>}
      {preview ? (
        <div className={styles.previewPane} aria-live="polite">
          {draft.trim() ? <RichMessage text={draft} /> : <p className={styles.empty}>还没有内容可预览。</p>}
        </div>
      ) : (
        <textarea
          ref={area}
          id={textareaId}
          value={draft}
          onChange={(e) => change(e.target.value)}
          rows={controlledRows}
          maxLength={maxLength} // 输入硬上限；工具插入/草稿恢复可超限，由提交前拦截+提示兜底
          disabled={disabled}
          placeholder={placeholder}
          aria-label={props.label ? undefined : "评论内容"}
          onKeyDown={onKeyDown}
          onCompositionStart={() => { composing.current = true; }}
          onCompositionEnd={() => { composing.current = false; }}
          className={styles.area}
          aria-invalid={over || undefined}
        />
      )}
      <div className={styles.foot}>
        <span className={`num ${over ? styles.over : ""}`} role={over ? "alert" : undefined}>
          {over ? `超出 ${draft.length - maxLength} 字，删掉一些再发` : `${draft.length}/${maxLength}`}
        </span>
        {onSubmit && <button type="button" onClick={() => void submit()} disabled={disabled || !draft.trim() || over} className={styles.send}>
          {disabled ? "发送中…" : submitLabel}
        </button>}
      </div>
    </div>
  );
}
