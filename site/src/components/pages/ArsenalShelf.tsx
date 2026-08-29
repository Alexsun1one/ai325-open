"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Markdown, CodeBlock } from "./Markdown";
import { apiFetch } from "@/lib/auth";
import { byName } from "./PageHead";
import type { ArsenalItem } from "./arsenaldata";

const KIND_STYLE: Record<string, string> = {
  技能: "border-cinnabar/40 bg-cinnabar-wash text-cinnabar-text",
  提示词: "border-amber-deep/45 bg-amber-wash text-amber-text",
  方法: "border-blue-wash-2 bg-blue-wash text-blue-text",
  文章: "border-teal/45 bg-teal-wash text-teal-text",
  案例: "border-rule bg-paper-2 text-ink-2",
  工具: "border-blue-wash-2 bg-blue-wash text-blue-text",
  论文: "border-rule bg-paper-2 text-ink-2",
  拆书: "border-teal/45 bg-teal-wash text-teal-text",
};

function daysAgo(d: string) {
  const t = Date.parse(`${d}T00:00:00+08:00`);
  if (Number.isNaN(t)) return 999;
  return Math.floor((Date.now() - t) / 86400000);
}

function Source({ s }: { s: ArsenalItem["source"] }) {
  if (s.url) {
    return (
      <a href={s.url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center font-sans text-[12.5px] text-blue-text underline underline-offset-2 sm:min-h-0">
        {s.name}{s.author ? ` · ${s.author}` : ""}
      </a>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-[4px] border border-amber-deep/40 bg-amber-wash px-1.5 py-[2px] font-sans text-[11.5px] font-semibold text-amber-text">
      <svg aria-hidden width="9" height="9" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10" /></svg>
      {s.name}
    </span>
  );
}

function Row({ it: base, i, open, onToggle, threadTitle }: { it: ArsenalItem; i: number; open: boolean; onToggle: () => void; threadTitle: (id: string) => string }) {
  const reduce = useReducedMotion();
  const [detail, setDetail] = useState<ArsenalItem | null>(null);
  const it = detail ? { ...base, ...detail } : base;
  // 全文与 SKILL.md 只在详情里给，点开再取——列表不用背这些内容
  useEffect(() => {
    if (!open || detail || (base.body_md && base.kind !== "技能")) return;
    let alive = true;
    apiFetch<{ item?: ArsenalItem } & ArsenalItem>(`/api/arsenal/${encodeURIComponent(base.id)}`)
      .then((d) => { if (alive) setDetail((d.item ?? d) as ArsenalItem); })
      .catch(() => {});
    return () => { alive = false; };
  }, [open, detail, base]);
  return (
    <article id={`kb-${it.id}`} className="scroll-mt-24 border-b border-rule-soft">
      <button type="button" onClick={onToggle} aria-expanded={open}
        className={`grid w-full grid-cols-[16px_minmax(0,1fr)] items-start gap-x-3 py-4 text-left transition-colors sm:grid-cols-[16px_minmax(0,1fr)_auto] ${open ? "bg-paper-2/60" : "hover:bg-paper-2/35"}`}>
        <svg aria-hidden width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"
          className={`mt-[7px] text-ink-3 transition-transform ${open ? "rotate-90" : ""}`}><path d="M9 6l6 6-6 6" /></svg>
        <span className="min-w-0">
          <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="font-serif text-[18px] font-bold leading-snug text-ink">{it.title}</span>
            {daysAgo(it.collected_at) <= 7 && (
              <span className="rounded-[3px] border border-amber-deep/50 bg-amber-wash px-1.5 py-[1px] font-sans text-[10.5px] font-semibold text-amber-text">新到</span>
            )}
            {(it.via || it.origin === "market") && (
              <span className="rounded-[3px] border border-teal/45 bg-teal-wash px-1.5 py-[1px] font-sans text-[10.5px] font-semibold text-teal-text">{byName(it.via) || "群友"} 上架</span>
            )}
          </span>
          <span className="mt-1 block font-sans text-[13.5px] leading-relaxed text-ink-2">{it.one_line}</span>
          <span className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
            <Source s={it.source} />
            {it.tags.slice(0, 4).map((t) => (
              <span key={t} className="rounded-[3px] border border-rule px-1.5 py-[1px] font-sans text-[11px] text-ink-3">{t}</span>
            ))}
          </span>
        </span>
        <span className="num hidden shrink-0 pt-1 font-sans text-[11.5px] text-ink-3 sm:block">{it.collected_at.slice(5)} 收</span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={reduce ? { height: "auto", opacity: 1 } : { height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={reduce ? { opacity: 0 } : { height: 0, opacity: 0 }}
            transition={{ duration: 0.38, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden">
            <div className="grid gap-x-10 gap-y-7 pb-9 pl-7 pr-1 pt-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,280px)]">
              <div className="min-w-0">
                <div>
                  <div className="label">为什么值得看</div>
                  <p className="prose-sheet mt-1.5 text-[16px] leading-[1.85] text-ink-2">{it.why}</p>
                </div>
                <div className="mt-6">
                  <div className="label">拿走这几条</div>
                  <ol className="mt-2.5 space-y-2.5">
                    {it.takeaways.map((t, n) => (
                      <li key={n} className="grid grid-cols-[26px_1fr] gap-2">
                        <span className="num pt-[3px] font-sans text-[12.5px] font-semibold text-blue-text">{String(n + 1).padStart(2, "0")}</span>
                        <span className="prose-sheet text-[15.5px] leading-[1.8]">{t}</span>
                      </li>
                    ))}
                  </ol>
                </div>
                {it.quote && (
                  <blockquote className="mt-6 border-l-2 border-amber-wash-2 pl-4">
                    <p className="hand text-[17px] leading-[1.8]">「{it.quote}」</p>
                  </blockquote>
                )}
                {it.kind === "技能" && it.skill_md && (
                  <div className="mt-8 border-t border-rule pt-6">
                    <div className="label mb-1" style={{ color: "var(--cinnabar-text)" }}>SKILL.md 说了什么</div>
                    <Markdown src={it.skill_md} className="text-[15.5px]" />
                  </div>
                )}
                {it.files && it.files.length > 0 && (
                  <div className="mt-8 border-t border-rule pt-6">
                    <div className="label mb-2">包里有什么</div>
                    <ul className="divide-y divide-rule-soft border-y border-rule">
                      {it.files.map((f) => (
                        <li key={f.path} className="flex items-center justify-between gap-4 py-2">
                          <a href={f.url} className="num inline-flex min-h-11 items-center font-sans text-[13.5px] text-blue-text underline underline-offset-2 sm:min-h-0">{f.path}</a>
                          {f.size != null && <span className="num shrink-0 font-sans text-[12px] text-ink-3">{f.size < 1024 ? `${f.size} B` : `${Math.round(f.size / 1024)} KB`}</span>}
                        </li>
                      ))}
                    </ul>
                    {it.downloads != null && <p className="num mt-2 font-sans text-[12px] text-ink-3">已被取走 {it.downloads} 次</p>}
                  </div>
                )}
                {it.kind === "技能" && (
                  <div className="mt-8 rounded-[10px] border border-rule bg-paper-2/45 px-4 py-4">
                    <div className="label mb-2">给 agent 取用</div>
                    <p className="font-sans text-[13px] leading-relaxed text-ink-2">
                      这一件是给 agent 直接用的。让它自己取走，不用你复制粘贴：
                    </p>
                    <CodeBlock code={`ai325 arsenal raw ${it.id}`} lang="命令行" />
                    <CodeBlock code={`get_skill("${it.id}")`} lang="MCP 工具" />
                    <p className="font-sans text-[12px] leading-relaxed text-ink-3">
                      还没接进来？看<a href="/agents/" className="text-blue-text underline underline-offset-2">把你的 agent 接进来</a>。
                    </p>
                  </div>
                )}
                {it.body_md && (
                  <div className="mt-8 border-t border-rule pt-6">
                    <div className="label mb-1">全文</div>
                    <Markdown src={it.body_md} />
                  </div>
                )}
              </div>

              <aside className="h-max rounded-[10px] border border-rule bg-paper-2/45 px-4 py-4">
                <dl className="space-y-3.5 font-sans text-[13px]">
                  <div><dt className="label">谁该看</dt><dd className="mt-1 leading-relaxed text-ink-2">{it.for_whom}</dd></div>
                  <div><dt className="label">哪一架</dt><dd className="mt-1"><span className={`inline-flex rounded-[4px] border px-2 py-[2px] text-[12px] font-semibold ${KIND_STYLE[it.kind] ?? KIND_STYLE["案例"]}`}>{it.kind}</span></dd></div>
                  <div><dt className="label">谁收的</dt><dd className="num mt-1 text-ink-2">{byName(it.by)} · {it.collected_at}</dd></div>
                  {it.source.published_at && <div><dt className="label">原文日期</dt><dd className="num mt-1 text-ink-2">{it.source.published_at}</dd></div>}
                  {it.tags.length > 0 && (
                    <div><dt className="label">标签</dt><dd className="mt-1.5 flex flex-wrap gap-1.5">
                      {it.tags.map((t) => <span key={t} className="rounded-[3px] border border-rule bg-paper px-1.5 py-[1px] text-[11.5px] text-ink-3">{t}</span>)}
                    </dd></div>
                  )}
                  {it.threads && it.threads.length > 0 && (
                    <div><dt className="label">接着哪条线索</dt><dd className="mt-1.5 flex flex-wrap gap-1.5">
                      {it.threads.map((t) => (
                        <Link key={t} href={`/archive/#thread-${t}`}
                          className="inline-flex min-h-11 items-center rounded-[4px] border border-blue-wash-2 bg-blue-wash px-2.5 py-[2px] text-[12px] text-blue-text no-underline hover:underline sm:min-h-8 sm:px-2">{threadTitle(t)}</Link>
                      ))}
                    </dd></div>
                  )}
                </dl>
              </aside>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </article>
  );
}

export function ArsenalShelf({ items: seeded, shelves, threads }: { items: ArsenalItem[]; shelves: string[]; threads: Record<string, string> }) {
  const [live, setLive] = useState<ArsenalItem[]>([]);
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [tag, setTag] = useState("");
  const [thread, setThread] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const reduce = useReducedMotion();

  useEffect(() => {
    const m = location.hash.match(/^#kb-(.+)$/);
    if (m) setOpen(decodeURIComponent(m[1]));
  }, []);

  // 群友上架的那一批：取不到就只显示静态架，不打扰读者
  useEffect(() => {
    let alive = true;
    // 公开列表本身只含 shelved，pending/rejected/retired 后端就不给
    apiFetch<{ items?: ArsenalItem[] }>("/api/arsenal?limit=100")
      .then((d) => { if (alive) setLive(d.items ?? []); })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  // 同 id 以后端为准（它可能改过），其余按静态架
  const items = useMemo(() => {
    const byId = new Map(seeded.map((x) => [x.id, x]));
    for (const x of live) byId.set(x.id, { ...byId.get(x.id), ...x });
    return [...byId.values()].filter((x) => x.status !== "retired");
  }, [seeded, live]);

  const allTags = useMemo(() => {
    const c = new Map<string, number>();
    for (const it of items) for (const t of it.tags) c.set(t, (c.get(t) ?? 0) + 1);
    return [...c.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 18);
  }, [items]);

  const allThreads = useMemo(() => {
    const c = new Map<string, number>();
    for (const it of items) for (const t of it.threads ?? []) c.set(t, (c.get(t) ?? 0) + 1);
    return [...c.entries()].sort((a, b) => b[1] - a[1]);
  }, [items]);

  const list = useMemo(() => {
    const k = q.trim().toLowerCase();
    return items.filter((it) => {
      if (kind && it.kind !== kind) return false;
      if (tag && !it.tags.includes(tag)) return false;
      if (thread && !(it.threads ?? []).includes(thread)) return false;
      if (!k) return true;
      return (it.title + it.one_line + it.tags.join(" ") + it.for_whom).toLowerCase().includes(k);
    });
  }, [items, q, kind, tag, thread]);

  const grouped = useMemo(() => {
    const order = [...shelves, ...[...new Set(list.map((i) => i.kind))].filter((k) => !shelves.includes(k))];
    return order
      .map((k) => ({ kind: k, rows: list.filter((i) => i.kind === k).sort((a, b) => (a.collected_at < b.collected_at ? 1 : -1)) }))
      .filter((g) => g.rows.length);
  }, [list, shelves]);

  const filtering = !!(q || kind || tag || thread);
  const threadTitle = (id: string) => threads[id] ?? id;

  return (
    <div>
      {/* 找东西 */}
      <div className="border-y border-rule py-4">
        <div className="flex flex-wrap items-center gap-3">
          <label className="relative min-w-0 flex-1 sm:max-w-[320px]">
            <span className="sr-only">在架上找</span>
            <svg aria-hidden width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-3"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="在架上找：标题、一句话、标签"
              className="min-h-11 w-full rounded-[5px] border border-rule bg-paper py-2 pl-9 pr-3 font-sans text-[14px] text-ink outline-none transition-colors placeholder:text-ink-3/75 focus:border-blue-2 sm:min-h-0" />
          </label>
          <div className="flex flex-wrap gap-1.5">
            {["", ...shelves.filter((s) => items.some((i) => i.kind === s))].map((k) => (
              <button key={k || "all"} type="button" onClick={() => setKind(k)} aria-pressed={kind === k}
                className={`inline-flex min-h-11 items-center rounded-[5px] border px-2.5 py-1.5 font-sans text-[13px] font-medium transition-colors sm:min-h-0 ${kind === k ? "border-blue bg-blue text-paper" : "border-rule bg-paper text-ink-2 hover:bg-paper-2"}`}>
                {k || "全部"}
                <span className={`num ml-1.5 text-[11.5px] ${kind === k ? "text-paper/70" : "text-ink-3"}`}>{k ? items.filter((i) => i.kind === k).length : items.length}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1.5">
          <span className="label mr-1">标签</span>
          {allTags.map(([t, n]) => (
            <button key={t} type="button" onClick={() => setTag(tag === t ? "" : t)} aria-pressed={tag === t}
              className={`inline-flex min-h-11 items-center rounded-[3px] border px-2.5 py-[2px] font-sans text-[11.5px] transition-colors sm:min-h-8 sm:px-2 ${tag === t ? "border-amber-deep bg-amber-wash text-amber-text" : "border-rule text-ink-3 hover:bg-paper-2"}`}>
              {t}<span className="num ml-1 opacity-70">{n}</span>
            </button>
          ))}
        </div>

        {allThreads.length > 0 && (
          <div className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1.5">
            <span className="label mr-1">线索</span>
            {allThreads.map(([t, n]) => (
              <button key={t} type="button" onClick={() => setThread(thread === t ? "" : t)} aria-pressed={thread === t}
                className={`inline-flex min-h-11 items-center rounded-[3px] border px-2.5 py-[2px] font-sans text-[11.5px] transition-colors sm:min-h-8 sm:px-2 ${thread === t ? "border-blue bg-blue-wash text-blue-text" : "border-rule text-ink-3 hover:bg-paper-2"}`}>
                {threadTitle(t)}<span className="num ml-1 opacity-70">{n}</span>
              </button>
            ))}
          </div>
        )}

        {filtering && (
          <div className="mt-3 flex items-center gap-3 font-sans text-[12.5px] text-ink-3">
            <span className="num">找到 <b className="text-ink">{list.length}</b> 件</span>
            <button type="button" onClick={() => { setQ(""); setKind(""); setTag(""); setThread(""); }} className="text-blue-text hover:underline">全部看回来</button>
          </div>
        )}
      </div>

      {/* 分架 */}
      {grouped.length === 0 ? (
        <p className="py-14 text-center font-serif text-[18px] text-ink-3">架上没有对得上的。换个词试试。</p>
      ) : (
        <div className="mt-10 space-y-12">
          {grouped.map((g, gi) => (
            <motion.section key={g.kind}
              initial={reduce ? false : { opacity: 0, y: 10 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-50px" }}
              transition={{ duration: 0.45, delay: Math.min(gi, 5) * 0.05, ease: [0.16, 1, 0.3, 1] }}>
              <div className="flex items-baseline justify-between gap-4 border-b-2 border-blue pb-2">
                <h2 className="font-serif text-[22px] font-black text-ink">{g.kind}</h2>
                <span className="num font-sans text-[12.5px] text-ink-3">{g.rows.length} 件</span>
              </div>
              <div>
                {g.rows.map((it, i) => (
                  <Row key={it.id} it={it} i={i} open={open === it.id} threadTitle={threadTitle}
                    onToggle={() => { const next = open === it.id ? null : it.id; setOpen(next); if (next) history.replaceState(null, "", `#kb-${next}`); }} />
                ))}
              </div>
            </motion.section>
          ))}
        </div>
      )}
    </div>
  );
}
