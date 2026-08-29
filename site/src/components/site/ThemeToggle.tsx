"use client";
import { useEffect, useState } from "react";

type T = "light" | "dark";
function read(): T {
  if (typeof document === "undefined") return "light";
  return (document.documentElement.dataset.theme as T) || "light";
}

export function ThemeToggle() {
  const [t, setT] = useState<T>("light");
  useEffect(() => { setT(read()); }, []);
  const toggle = () => {
    const next: T = read() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("xf-theme", next); } catch {}
    setT(next);
  };
  const dark = t === "dark";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? "切换到日间纸面" : "切换到夜间台面"}
      title={dark ? "日间纸面" : "夜间台面"}
      className="relative inline-flex h-11 w-14 items-center rounded-full border border-rule bg-paper-2 px-1 transition-colors hover:border-blue-2 focus-visible:outline-2"
    >
      <span
        className="absolute left-1 top-1/2 -translate-y-1/2 h-6 w-6 rounded-full bg-paper shadow-[0_1px_2px_rgba(0,0,0,.15)] transition-transform duration-500 ease-[var(--ease-out-expo)] flex items-center justify-center"
        style={{ transform: dark ? "translateX(24px)" : "translateX(0)" }}
      >
        {dark ? (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="text-amber-text"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="text-amber-deep"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
        )}
      </span>
    </button>
  );
}
