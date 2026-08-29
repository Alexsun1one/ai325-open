"use client";
import type { InputHTMLAttributes, ReactNode } from "react";

/** 表单字段：蓝标签印在上方，输入框是「填进去的那一格」——细下划线 + 纸色底，不是圆角胶囊。 */
export function Field({ label, hint, ...rest }: { label: string; hint?: ReactNode } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <input
        {...rest}
        className="mt-1.5 block min-h-11 w-full rounded-[4px] border border-rule bg-paper px-3 py-2 font-sans text-[15px] text-ink outline-none transition-colors placeholder:text-ink-3/70 focus:border-blue-2 focus:bg-paper-2/50"
      />
      {hint && <span className="mt-1.5 block font-sans text-[12px] leading-snug text-ink-3">{hint}</span>}
    </label>
  );
}

export function Btn({ children, busy, tone = "primary", ...rest }: { children: ReactNode; busy?: boolean; tone?: "primary" | "ghost" | "danger" } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const t = tone === "ghost"
    ? "border-rule bg-paper text-ink-2 hover:border-blue-wash-2 hover:text-ink"
    : tone === "danger"
      ? "border-cinnabar/50 bg-paper text-cinnabar-text hover:bg-cinnabar-wash"
      : "border-blue bg-blue text-paper hover:opacity-90";
  return (
    <button
      {...rest}
      disabled={busy || rest.disabled}
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-[5px] border px-5 py-2.5 font-sans text-[14px] font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-55 ${t}`}
    >
      {busy && <span aria-hidden className="inline-block h-3 w-3 animate-spin rounded-full border-[1.5px] border-paper/40 border-t-paper" />}
      {children}
    </button>
  );
}

export function Note({ tone = "ink", children }: { tone?: "ink" | "bad" | "good"; children: ReactNode }) {
  const cls = tone === "bad"
    ? "border-cinnabar/45 bg-cinnabar-wash text-cinnabar-text"
    : tone === "good"
      ? "border-teal/45 bg-teal-wash text-teal-text"
      : "border-rule bg-paper-2/70 text-ink-2";
  return <p role={tone === "bad" ? "alert" : undefined} className={`rounded-[6px] border px-3 py-2 font-sans text-[13px] leading-relaxed ${cls}`}>{children}</p>;
}
