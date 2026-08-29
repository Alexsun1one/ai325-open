"use client";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ApiError, apiFetch } from "@/lib/auth";
import { fmtInt } from "@/lib/shared";
import { Note } from "./FormBits";
import { GapNote } from "./PageHead";
import { segment } from "./segment";

export interface Essay { title: string; author: string; date: string; body: string; word_count: number }
interface Payload { items: Essay[] }

function daysSince(d: string) {
  const t = Date.parse(`${d}T00:00:00+08:00`);
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.floor((Date.now() - t) / 86400000));
}

/** 一瓶：蓝色线稿瓶身 + 琥珀液位（液位 = 字数）。悬停时液面轻微起伏，瓶身起一层薄雾。 */
function Bottle({ level, hovered }: { level: number; hovered: boolean }) {
  const reduce = useReducedMotion();
  const TOP = 10, BOT = 96, L = 9, R = 31;
  const lo = BOT - (BOT - 34) * Math.max(0.08, Math.min(0.94, level));
  return (
    <svg viewBox="0 0 40 104" className="block h-full w-auto" aria-hidden>
      <defs>
        <clipPath id={`bt-${Math.round(level * 1000)}`}>
          <path d="M16 10 h8 v14 c0 4 7 7 7 14 v52 c0 6 -3 9 -9 9 h-4 c-6 0 -9 -3 -9 -9 v-52 c0 -7 7 -10 7 -14 z" />
        </clipPath>
      </defs>
      {/* 酒液 */}
      <g clipPath={`url(#bt-${Math.round(level * 1000)})`}>
        <rect x={L - 2} y={lo} width={R - L + 4} height={BOT - lo + 6} fill="var(--amber)" opacity="0.9" />
        <motion.path
          d={`M${L - 2} ${lo} q5 -2 10 0 t10 0 t10 0 v6 h-30 z`}
          fill="var(--amber-2)"
          animate={reduce ? undefined : { y: hovered ? [0, -1.1, 0.6, 0] : 0 }}
          transition={{ duration: 2.2, repeat: hovered ? Infinity : 0, ease: "easeInOut" }}
        />
      </g>
      {/* 瓶身线稿 */}
      <path d="M16 10 h8 v14 c0 4 7 7 7 14 v52 c0 6 -3 9 -9 9 h-4 c-6 0 -9 -3 -9 -9 v-52 c0 -7 7 -10 7 -14 z"
        fill="none" stroke="var(--blue)" strokeWidth="1.6" strokeLinejoin="round" />
      <path d={`M15 ${TOP - 3} h10`} stroke="var(--blue)" strokeWidth="1.6" strokeLinecap="round" />
      {/* 封签 */}
      <rect x="13" y="48" width="14" height="18" rx="1.5" fill="none" stroke="var(--blue)" strokeWidth="0.9" opacity="0.55" />
    </svg>
  );
}

function Slot({ e, i, max, onOpen }: { e: Essay; i: number; max: number; onOpen: () => void }) {
  const [hover, setHover] = useState(false);
  const reduce = useReducedMotion();
  const level = 0.15 + 0.75 * (max ? e.word_count / max : 0.5);
  const age = daysSince(e.date);
  return (
    <motion.button
      type="button"
      onClick={onOpen}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onFocus={() => setHover(true)}
      onBlur={() => setHover(false)}
      initial={reduce ? false : { opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.5, delay: Math.min(i, 16) * 0.04, ease: [0.16, 1, 0.3, 1] }}
      className="group relative flex h-full flex-col items-center border-b border-r border-rule px-3 pb-4 pt-5 text-center transition-colors hover:bg-paper-2/50"
    >
      <span className="relative block h-[104px]">
        <Bottle level={level} hovered={hover} />
        {/* 起雾：一层纸色薄雾，不是发光 */}
        <motion.span
          aria-hidden
          className="pointer-events-none absolute inset-[-6px] rounded-[10px] bg-paper backdrop-blur-[1.5px]"
          initial={false}
          animate={{ opacity: hover && !reduce ? 0.22 : 0 }}
          transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
        />
      </span>
      <span className="mt-3 line-clamp-2 font-serif text-[15px] font-bold leading-snug text-ink">{e.title}</span>
      <span className="mt-1 font-sans text-[12px] text-ink-2">{e.author}</span>
      <span className="num mt-1.5 font-sans text-[11px] leading-tight text-ink-3">
        {e.date} · {fmtInt(e.word_count)} 字{age != null && <> · 陈 {age} 天</>}
      </span>
    </motion.button>
  );
}

/** 单篇阅读：宋体 17px、约 38 字/行、行高 1.9。这是这一页真正的产品面。 */
function Reader({ e, onBack, index, total, onGo }: { e: Essay; onBack: () => void; index: number; total: number; onGo: (i: number) => void }) {
  const reduce = useReducedMotion();
  // 先按作者自己的换行分段；某一段还是一整坨的（很多人一口气打完不换行），再按句读切开。
  // 「（引用 …）」是清洗微信引用消息时抠出的被引用原文，整行保留、单独成块。
  const paras = useMemo(
    () => e.body.split(/\n+/).map((s) => s.trim()).filter(Boolean).flatMap((p) => (p.startsWith("（引用") ? [p] : segment(p, { min: 110, per: 105 }))),
    [e.body],
  );
  const drop = !!paras[0] && /^[\p{Script=Han}A-Za-z0-9]/u.test(paras[0]);
  const age = daysSince(e.date);
  return (
    <motion.article
      initial={reduce ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
    >
      <button type="button" onClick={onBack} className="inline-flex items-center gap-1.5 font-sans text-[13px] font-semibold text-blue-text hover:underline">
        <svg aria-hidden width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M15 6l-6 6 6 6" /></svg>
        回格架
      </button>
      <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-3 border-y border-rule py-3 font-sans text-[13px] sm:grid-cols-4">
        <div><dt className="label">作者</dt><dd className="mt-0.5 text-ink">{e.author}</dd></div>
        <div><dt className="label">入窖</dt><dd className="num mt-0.5 text-ink">{e.date}</dd></div>
        <div><dt className="label">字数</dt><dd className="num mt-0.5 text-ink">{fmtInt(e.word_count)}</dd></div>
        <div><dt className="label">陈年</dt><dd className="num mt-0.5 text-ink">{age != null ? `${age} 天` : "—"}</dd></div>
      </dl>
      <h2 className="mt-8 font-serif text-[30px] font-black leading-[1.25] text-ink sm:text-[36px]">{e.title}</h2>

      {/* 名片行：这是一个人写的，先让读者看见这个人 */}
      <div className="mt-6 flex items-center gap-3 border-b border-rule pb-5">
        <span aria-hidden className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-blue-wash-2 bg-blue-wash font-serif text-[17px] font-bold text-blue-text">
          {(e.author || "?").trim().slice(0, 1)}
        </span>
        <span className="min-w-0">
          <span className="block font-serif text-[16.5px] font-bold leading-tight text-ink">{e.author}</span>
          <span className="num block font-sans text-[12.5px] leading-tight text-ink-3">
            {e.date} 入窖{age != null && <> · 陈 {age} 天</>} · {fmtInt(e.word_count)} 字
          </span>
        </span>
      </div>

      {/* max-width 用行内样式：`.prose-sheet` 自带的 max-width 同为类选择器，会盖掉 Tailwind 的工具类。
          38em × 17px = 646px，实测每行 38 字。 */}
      <div className={`prose-sheet ${drop ? "prose-drop" : ""} mt-8 text-[17px] leading-[1.9]`} style={{ maxWidth: "38em" }}>
        {paras.map((p, i) => {
          const q = p.match(/^（引用(?:\s+(.+?))?）([\s\S]*)$/);
          return (
            <Fragment key={i}>
              {/* 每四段给一次呼吸：一条很短的格线，不是装饰，是让眼睛有地方歇 */}
              {i > 0 && i % 4 === 0 && <span aria-hidden className="my-10 block h-px w-16 bg-rule" />}
              {q ? (
                <blockquote className={`border-l-2 border-amber-deep/60 pl-4 text-left text-[15.5px] leading-[1.85] text-ink-2 ${i ? "mt-[1.75em]" : ""}`}>
                  <span className="label block text-[11px]">引用{q[1] ? ` · ${q[1]}` : ""}</span>
                  <span className="mt-1 block">{q[2]}</span>
                </blockquote>
              ) : (
                <p className={i ? "mt-[1.75em]" : ""}>{p}</p>
              )}
            </Fragment>
          );
        })}
      </div>
      <nav className="mt-12 flex items-center justify-between gap-4 border-t border-rule pt-5 font-sans text-[13.5px]">
        <button type="button" disabled={index <= 0} onClick={() => onGo(index - 1)} className="text-blue-text disabled:cursor-not-allowed disabled:text-ink-3/60 hover:enabled:underline">← 上一瓶</button>
        <span className="num text-ink-3">{index + 1} / {total}</span>
        <button type="button" disabled={index >= total - 1} onClick={() => onGo(index + 1)} className="text-blue-text disabled:cursor-not-allowed disabled:text-ink-3/60 hover:enabled:underline">下一瓶 →</button>
      </nav>
    </motion.article>
  );
}

export function EssayCellar() {
  const [data, setData] = useState<Payload | null>(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    apiFetch<Payload>("/api/governed/essays")
      .then((d) => { if (alive) setData(d); })
      .catch((e) => { if (alive) setErr(e instanceof ApiError ? e.message : "读取失败"); });
    return () => { alive = false; };
  }, []);

  // 按入窖日期排架：早入窖的在前
  const items = useMemo(() => (data?.items ?? []).slice().sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.author.localeCompare(b.author))), [data]);
  const max = useMemo(() => Math.max(1, ...items.map((e) => e.word_count)), [items]);

  const go = useCallback((i: number) => {
    setOpen(i);
    if (typeof window !== "undefined") { history.replaceState(null, "", `#essay-${i + 1}`); window.scrollTo({ top: 0, behavior: "smooth" }); }
  }, []);
  const back = useCallback(() => { setOpen(null); if (typeof window !== "undefined") history.replaceState(null, "", "#rack"); }, []);

  useEffect(() => {
    if (!items.length) return;
    const m = location.hash.match(/^#essay-(\d+)$/);
    if (m) { const i = parseInt(m[1], 10) - 1; if (i >= 0 && i < items.length) setOpen(i); }
  }, [items.length]);

  if (err) return <Note tone="bad">{err}</Note>;
  if (!data) return <p className="py-10 font-sans text-[14px] text-ink-3">正在开窖……</p>;
  if (!items.length) {
    return <GapNote><b>窖里还没有瓶子。</b>一篇小作文都还没收进来——不是这一页坏了，是真的还空着。</GapNote>;
  }

  const totalWords = items.reduce((s, e) => s + e.word_count, 0);

  return (
    <AnimatePresence mode="wait" initial={false}>
      {open != null && items[open] ? (
        <div key="reader"><Reader e={items[open]} index={open} total={items.length} onBack={back} onGo={go} /></div>
      ) : (
        <motion.div key="rack" id="rack" initial={false}>
          <div className="mb-5 flex flex-wrap items-end justify-between gap-x-6 gap-y-1">
            <p className="font-sans text-[13px] text-ink-3">
              按<b className="text-ink-2">入窖日期</b>排架，早入窖的在前。瓶身液位 = 这一篇的字数（相对本窖最长的一篇）。
            </p>
            <p className="num font-sans text-[13px] text-ink-3">
              <span className="font-semibold text-amber-text">{items.length}</span> 瓶 · 合计 <span className="font-semibold text-amber-text">{fmtInt(totalWords)}</span> 字
            </p>
          </div>
          <div className="grid grid-cols-2 border-l border-t border-rule sm:grid-cols-3 lg:grid-cols-5">
            {items.map((e, i) => <Slot key={`${e.author}-${e.date}-${i}`} e={e} i={i} max={max} onOpen={() => go(i)} />)}
          </div>
          <p className="mt-6 font-sans text-[12.5px] leading-relaxed text-ink-3">
            点任意一瓶开读。阅读版按宋体 17px、约 38 字一行、行高 1.9 排——这些是给人读完的东西，不是摘要。
          </p>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
