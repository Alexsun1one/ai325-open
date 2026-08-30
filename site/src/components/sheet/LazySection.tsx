"use client";
import { useEffect, useRef, useState } from "react";

/** 页尾区块延迟加载：进入视口（提前 400px）才按需取整刊 JSON 并渲染。
 *  首屏 HTML 不再内嵌这些区块的 DOM 与数据；滚动到即补，取不到给人话占位。 */
export function LazySection<T>({ date, render, height = 120 }: { date: string; render: (data: T) => React.ReactNode; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let alive = true;
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        io.disconnect();
        fetch(`/ledger-data/${encodeURIComponent(date)}.json`)
          .then((r) => {
            if (!r.ok) throw new Error(String(r.status));
            return r.json();
          })
          .then((d: T) => { if (alive) setData(d); })
          .catch(() => { if (alive) setErr("这一块没取到，刷新一下试试。"); });
      },
      { rootMargin: "400px 0px" },
    );
    io.observe(el);
    return () => { alive = false; io.disconnect(); };
  }, [date]);

  return (
    <div ref={ref}>
      {data ? render(data) : err ? (
        <p className="font-sans text-[13px] text-ink-3">{err}</p>
      ) : (
        <div className="flex items-center justify-center" style={{ minHeight: height }} aria-hidden>
          <span className="font-sans text-[12.5px] text-ink-3">这块在往下取……</span>
        </div>
      )}
    </div>
  );
}
