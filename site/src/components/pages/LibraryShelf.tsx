"use client";
import { Fragment, useEffect, useMemo, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { ApiError, apiFetch, getToken } from "@/lib/auth";
import { Note } from "./FormBits";
import { GapNote } from "./PageHead";

interface Item { name: string; ext: string; size: number; month: string; mtime: string }
interface Payload { items: Item[]; count: number }

function fmtBytes(n: number) {
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  if (n >= 1024) return `${Math.round(n / 1024)} KB`;
  return `${n} B`;
}

/** 类型章：像品鉴单上的小印刷标签，不是彩色徽章。 */
function ExtStamp({ ext }: { ext: string }) {
  const label = ext.toUpperCase().slice(0, 5);
  return (
    <span className="inline-flex w-[52px] shrink-0 items-center justify-center rounded-[3px] border border-blue-wash-2 bg-blue-wash px-1.5 py-[3px] font-sans text-[10.5px] font-semibold tracking-[0.08em] text-blue-text">
      {label}
    </span>
  );
}

function Row({ f, i }: { f: Item; i: number }) {
  const reduce = useReducedMotion();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const take = async () => {
    setBusy(true); setErr("");
    try {
      const r = await fetch(`/api/library/file?month=${encodeURIComponent(f.month)}&name=${encodeURIComponent(f.name)}`, {
        headers: { authorization: `Bearer ${getToken()}` },
      });
      if (!r.ok) throw new Error(r.status === 401 ? "登录态过期了，重新登录再取" : `取件失败（HTTP ${r.status}）`);
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = f.name;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "取件失败");
    } finally {
      setBusy(false);
    }
  };
  return (
    <motion.li
      initial={reduce ? false : { opacity: 0, y: 10 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-30px" }}
      transition={{ duration: 0.4, delay: Math.min(i, 12) * 0.03, ease: [0.16, 1, 0.3, 1] }}
      className="grid grid-cols-[52px_minmax(0,1fr)] items-baseline gap-x-4 gap-y-1 py-4 sm:grid-cols-[52px_minmax(0,1fr)_auto_auto]"
    >
      <ExtStamp ext={f.ext} />
      <span className="min-w-0">
        <span className="block break-all font-serif text-[16px] font-bold leading-[1.5] text-ink">{f.name}</span>
        {err && <span className="mt-1 block font-sans text-[12px] text-amber-text">{err}</span>}
      </span>
      <span className="num col-start-2 font-sans text-[12px] text-ink-3 sm:col-start-3 sm:text-right">{fmtBytes(f.size)} · {f.mtime} 收</span>
      <button
        type="button"
        onClick={take}
        disabled={busy}
        className="col-start-2 w-fit rounded-md border border-blue bg-blue-wash px-3 py-1 font-sans text-[12.5px] font-semibold text-blue-text transition-colors hover:bg-blue-wash-2 disabled:opacity-40 sm:col-start-4"
      >
        {busy ? "取件中…" : "取件"}
      </button>
    </motion.li>
  );
}

/** 文库：群里分享过的原件档案。一行一件，不做卡片墙；按收件月份分组。 */
export function LibraryShelf() {
  const [data, setData] = useState<Payload | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    apiFetch<Payload>("/api/library")
      .then((d) => { if (alive) setData(d); })
      .catch((e) => { if (alive) setErr(e instanceof ApiError ? e.message : "读取失败"); });
    return () => { alive = false; };
  }, []);

  const months = useMemo(() => {
    const g = new Map<string, Item[]>();
    for (const f of data?.items ?? []) {
      if (!g.has(f.month)) g.set(f.month, []);
      g.get(f.month)!.push(f);
    }
    return Array.from(g.entries());
  }, [data]);

  if (err) return <Note tone="bad">{err}</Note>;
  if (!data) return <p className="py-10 font-sans text-[14px] text-ink-3">正在开柜……</p>;
  if (!data.items.length) {
    return <GapNote><b>柜里还是空的。</b>群里还没归档到文件——不是这一页坏了，是真的还没收到。</GapNote>;
  }

  const total = data.items.reduce((s, f) => s + f.size, 0);
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-end justify-between gap-x-6 gap-y-1">
        <p className="font-sans text-[13px] text-ink-3">群里传过的原件，按<b className="text-ink-2">收件月份</b>归档。点「取件」下载到本机。</p>
        <p className="num font-sans text-[13px] text-ink-3">
          <span className="font-semibold text-amber-text">{data.count}</span> 件 · 合计 <span className="font-semibold text-amber-text">{fmtBytes(total)}</span>
        </p>
      </div>
      {months.map(([month, files]) => (
        <Fragment key={month}>
          <div className="mt-6 flex items-baseline gap-3 border-b border-rule pb-2">
            <span className="label text-[12px] font-semibold">{month}</span>
            <span className="num font-sans text-[11.5px] text-ink-3">{files.length} 件</span>
          </div>
          <ul className="divide-y divide-rule-soft">
            {files.map((f, i) => <Row key={`${f.month}/${f.name}`} f={f} i={i} />)}
          </ul>
        </Fragment>
      ))}
      <p className="mt-8 font-sans text-[12.5px] leading-relaxed text-ink-3">
        这些是群友在群里分享的原件，只对登录群友开放，别转出群外。哪件特别值得读，说一声，给它写导读挂到军火库去。
      </p>
    </div>
  );
}
