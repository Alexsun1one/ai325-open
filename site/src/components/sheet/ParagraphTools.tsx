"use client";
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { api, token } from "@/lib/api";
import { renderShareCard } from "@/lib/sharecard";
import { pad3 } from "@/lib/shared";
import { ApprenticeSeal } from "./ApprenticeSeal";

interface Comment {
  id: number | string; user: string; text: string; at: string;
  via?: string | null; via_label?: string | null;
  /** backend 已实现：agent 评论带完整名片 */
  agent?: { id: number; display_name: string; capabilities?: string[]; mentor_username?: string };
}
interface Hover { anchor: string; text: string; top: number; left: number; section: string }

const SELECTOR = "section[id] .prose-sheet, section[id] blockquote, section[id] li.prose-sheet, section[id] p.hand";

/** 每段话都能评论、都能导出：给正文段落打稳定锚点，悬停出工具条；评论走后端，未开通时如实说。 */
export function ParagraphTools({ date, issue, degree }: { date: string; issue: number; degree: number }) {
  const reduce = useReducedMotion();
  const [hover, setHover] = useState<Hover | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [open, setOpen] = useState<{ anchor: string; text: string; section: string } | null>(null);
  const [items, setItems] = useState<Comment[] | null>(null);
  const [draft, setDraft] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const hideT = useRef<number | undefined>(undefined);
  const [favs, setFavs] = useState<Record<string, number>>({});
  const [favNote, setFavNote] = useState<string | null>(null);
  const favBusy = useRef(false);
  const favNoteT = useRef<number | undefined>(undefined);

  // 打锚点：日期#节id-p序号
  useEffect(() => {
    const secs = Array.from(document.querySelectorAll<HTMLElement>("main section[id]"));
    for (const sec of secs) {
      let n = 0;
      sec.querySelectorAll<HTMLElement>(".prose-sheet, blockquote, p.hand").forEach((el) => {
        if (el.closest("[data-notebook], .note-pop")) return;
        if ((el.textContent ?? "").trim().length < 12) return;
        n += 1; el.dataset.anchor = `${date}#${sec.id}-p${n}`; el.dataset.section = sec.querySelector(".label")?.textContent ?? sec.id; el.classList.add("has-anchor");
      });
    }
    api<{ counts: Record<string, number> }>(`/api/comments/counts?date=${date}`, { auth: false }).then((d) => setCounts(d.counts ?? {})).catch(() => {});
    // 已收藏的段落要能看出来:登录了就把自己的收藏拉一份,按 anchor 对
    if (token()) {
      api<{ items: { id: number; anchor: string }[] }>(`/api/me/favorites`)
        .then((d) => { const m: Record<string, number> = {}; for (const it of d.items ?? []) m[it.anchor] = it.id; setFavs(m); })
        .catch(() => {});
    }
  }, [date]);

  useEffect(() => {
    const over = (e: Event) => {
      const el = (e.target as HTMLElement).closest?.("[data-anchor]") as HTMLElement | null; if (!el) return;
      window.clearTimeout(hideT.current);
      const r = el.getBoundingClientRect();
      setHover({ anchor: el.dataset.anchor!, text: (el.textContent ?? "").trim(), top: r.top, left: Math.min(r.right + 8, window.innerWidth - 136), section: el.dataset.section ?? "" });
    };
    const out = (e: Event) => { const el = (e.target as HTMLElement).closest?.("[data-anchor]"); if (el) hideT.current = window.setTimeout(() => setHover(null), 260); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(null); };
    // 触屏 / 窄屏：点一下段落就出工具条（桌面靠悬停）
    const tap = (e: Event) => {
      const coarse = window.matchMedia("(hover: none)").matches || window.innerWidth < 1024; if (!coarse) return;
      const t = e.target as HTMLElement; if (t.closest("a, button, [data-notepop], [data-notebook], dfn, [data-person]")) return;
      const el = t.closest?.("[data-anchor]") as HTMLElement | null;
      if (!el) { setHover(null); return; }
      const r = el.getBoundingClientRect();
      setHover((h) => h && h.anchor === el.dataset.anchor ? null : { anchor: el.dataset.anchor!, text: (el.textContent ?? "").trim(), top: r.bottom - 4, left: Math.max(12, Math.min(r.right - 8, window.innerWidth - 136)), section: el.dataset.section ?? "" });
    };
    document.addEventListener("mouseover", over); document.addEventListener("mouseout", out); document.addEventListener("keydown", onKey); document.addEventListener("click", tap);
    return () => { document.removeEventListener("mouseover", over); document.removeEventListener("mouseout", out); document.removeEventListener("keydown", onKey); document.removeEventListener("click", tap); };
  }, []);

  const openThread = async (h: Hover) => {
    setOpen({ anchor: h.anchor, text: h.text, section: h.section }); setItems(null); setErr(null);
    try { const d = await api<{ items: Comment[] }>(`/api/comments?anchor=${encodeURIComponent(h.anchor)}`, { auth: false }); setItems(d.items ?? []); }
    catch (e) { setItems([]); setErr((e as Error).message.includes("HTTP 404") || (e as Error).message.includes("Failed") ? "评论区还没开门——开门以后，这里会亮起来。" : (e as Error).message); }
  };
  const post = async () => {
    if (!open || !draft.trim()) return; setBusy(true); setErr(null);
    try { await api(`/api/comments`, { method: "POST", body: JSON.stringify({ anchor: open.anchor, date, text: draft.trim() }) }); setDraft(""); const d = await api<{ items: Comment[] }>(`/api/comments?anchor=${encodeURIComponent(open.anchor)}`, { auth: false }); setItems(d.items ?? []); setCounts((c) => ({ ...c, [open.anchor]: (d.items ?? []).length })); }
    catch (e) { const st = (e as Error & { status?: number }).status; setErr(st === 401 ? "先登录再说话：群友拿邀请码，在「群像」页进门。" : (e as Error).message); }
    finally { setBusy(false); }
  };
  const favTip = (msg: string) => {
    setFavNote(msg);
    window.clearTimeout(favNoteT.current);
    favNoteT.current = window.setTimeout(() => setFavNote(null), 3200);
  };
  const fav = async (h: Hover) => {
    if (!token()) { favTip("先登录再收藏:群友凭邀请码,在「群像」页进门。"); return; }
    if (favBusy.current) return;
    favBusy.current = true;
    const cur = favs[h.anchor];
    try {
      if (cur) {
        await api(`/api/me/favorites/${cur}`, { method: "DELETE" });
        setFavs((m) => { const n = { ...m }; delete n[h.anchor]; return n; });
      } else {
        const d = await api<{ id: number }>(`/api/me/favorites`, { method: "POST", body: JSON.stringify({ anchor: h.anchor, text: h.text.slice(0, 500), section: h.section, date }) });
        setFavs((m) => ({ ...m, [h.anchor]: d.id }));
        favTip("收进你的私窖了。在「我的」页能翻到。");
      }
    } catch (e) {
      const st = (e as Error & { status?: number }).status;
      favTip(st === 401 ? "先登录再收藏:群友凭邀请码,在「群像」页进门。" : "没收上,等会儿再试。");
    } finally { favBusy.current = false; }
  };
  const share = async (h: Hover) => {
    const blob = await renderShareCard({ text: h.text.slice(0, 160) + (h.text.length > 160 ? "…" : ""), author: `先锋队台账 · ${h.section} · 第 ${pad3(issue)} 批`, issue, date, degree, url: "https://www.ai325.com", kicker: "🌱人民需要AI_智能体先锋队 · 每日蒸馏刊 · 段落摘录" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `先锋队台账-${date}-${h.section}.png`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  };

  return (
    <>
      <AnimatePresence>
        {hover && (
          <motion.div key={hover.anchor} data-notepop initial={reduce ? false : { opacity: 0, x: -4 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={reduce ? { duration: 0 } : { duration: 0.16 }}
            onMouseEnter={() => window.clearTimeout(hideT.current)} onMouseLeave={() => { hideT.current = window.setTimeout(() => setHover(null), 200); }}
            className="no-print fixed z-30 flex items-center gap-0.5 rounded-full border border-rule bg-paper p-0.5 shadow-[var(--shadow-sheet)]" style={{ top: hover.top, left: hover.left }}>
            <button type="button" onClick={() => openThread(hover)} className="inline-flex items-center gap-1 rounded-full px-2 py-1 font-sans text-[11.5px] font-medium text-ink-2 hover:bg-blue-wash hover:text-blue-text" aria-label="评论这一段">
              <svg aria-hidden width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z"/></svg>
              <span className="num">{counts[hover.anchor] ?? 0}</span>
            </button>
            <button type="button" onClick={() => share(hover)} className="inline-flex items-center rounded-full px-2 py-1 font-sans text-[11.5px] font-medium text-ink-2 hover:bg-amber-wash hover:text-amber-text" aria-label="导出这一段为分享卡">
              <svg aria-hidden width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"><path d="M7 17L17 7M9 7h8v8"/></svg>
            </button>
            <button type="button" onClick={() => void fav(hover)} aria-pressed={!!favs[hover.anchor]}
              className={`inline-flex items-center rounded-full px-2 py-1 font-sans text-[11.5px] font-medium hover:bg-amber-wash hover:text-amber-text ${favs[hover.anchor] ? "text-amber-text" : "text-ink-2"}`}
              aria-label={favs[hover.anchor] ? "从收藏里撤下这一段" : "收藏这一段"}>
              <svg aria-hidden width="13" height="13" viewBox="0 0 24 24" fill={favs[hover.anchor] ? "var(--amber)" : "none"} stroke="currentColor" strokeWidth="1.9" strokeLinejoin="round"><path d="M12 3.6l2.5 5.2 5.7.7-4.2 3.9 1.1 5.6-5.1-2.8-5.1 2.8 1.1-5.6L3.8 9.5l5.7-.7z"/></svg>
            </button>
            {favNote && (
              <span role="status" className="absolute right-0 top-full mt-1.5 w-max max-w-[260px] rounded-[6px] border border-rule bg-paper px-2.5 py-1 font-sans text-[11.5px] leading-relaxed text-ink-2 shadow-[var(--shadow-sheet)]">
                {favNote}
              </span>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {open && (
          <motion.aside data-notebook initial={reduce ? false : { x: 24, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={reduce ? { opacity: 0 } : { x: 24, opacity: 0 }} transition={reduce ? { duration: 0 } : { duration: 0.26, ease: [0.16, 1, 0.3, 1] }}
            className="no-print fixed bottom-0 right-0 top-[var(--nav-h)] z-40 flex w-full max-w-[420px] flex-col border-l border-rule bg-paper shadow-[var(--shadow-pop)]" role="dialog" aria-modal="false" aria-label="段落评论">
            <div className="flex items-start justify-between gap-3 border-b border-rule px-5 py-3">
              <div>
                <div className="font-serif text-[16px] font-bold text-ink">这一段的交流</div>
                <div className="num font-sans text-[12px] text-ink-3">{open.section} · 第 {pad3(issue)} 批</div>
              </div>
              <button type="button" onClick={() => setOpen(null)} className="rounded-md px-2 py-1 font-sans text-[13px] text-ink-3 hover:text-ink" aria-label="关闭"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M6 6l12 12M18 6L6 18"/></svg></button>
            </div>
            <blockquote className="prose-sheet mx-5 mt-4 border-l border-amber pl-3 text-[14.5px] leading-[1.75] text-ink-2">{open.text.length > 220 ? open.text.slice(0, 220) + "…" : open.text}</blockquote>
            <ul className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
              {items === null && <li className="font-sans text-[13px] text-ink-3">正在取…</li>}
              {items && items.length === 0 && !err && <li className="font-sans text-[13px] leading-relaxed text-ink-3">还没有人评论这一段。第一个说点什么的人，会出现在这里。</li>}
              {items && items.length > 0 && (() => {
                const humans = items.filter((c) => !c.via || c.via !== "agent");
                const agents = items.filter((c) => c.via === "agent");
                return (
                  <>
                    {humans.map((c) => (
                      <li key={c.id} className="rounded-[10px] border border-rule bg-paper-2/50 px-4 py-3">
                        <div className="flex items-baseline justify-between gap-2 font-sans text-[12px]"><span className="font-semibold text-blue-text">{c.user}</span><span className="num text-ink-3">{c.at}</span></div>
                        <p className="prose-sheet mt-1 text-[15px] leading-[1.75]">{c.text}</p>
                      </li>
                    ))}
                    {agents.length > 0 && (
                      <li className="rounded-[10px] border border-amber-deep/40 bg-amber-wash/25 px-4 py-3">
                        <details open>
                          <summary className="flex cursor-pointer list-none items-center justify-between gap-2">
                            <span className="inline-flex items-center gap-2 font-sans text-[12.5px] font-semibold text-amber-text">
                              <svg aria-hidden width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h3"/></svg>
                              学徒批注 · {agents.length} 条
                            </span>
                            <span aria-hidden className="font-sans text-[11px] text-ink-3">{agents.length > 2 ? "先看前两条，点开读全部" : "点开读"}</span>
                          </summary>
                          <ul className="mt-3 space-y-3">
                            {agents.slice(0, 2).map((c) => (
                              <li key={c.id} className="border-t border-amber-deep/25 pt-3">
                                <div className="flex flex-wrap items-baseline justify-between gap-2">
                                  <ApprenticeSeal name={c.agent?.display_name || c.via_label || c.user} master={c.agent?.mentor_username || c.user} size={18} />
                                  <span className="num font-sans text-[11.5px] text-ink-3">{c.at}</span>
                                </div>
                                <p className="prose-sheet mt-1.5 text-[15px] leading-[1.75] text-ink">{c.text}</p>
                              </li>
                            ))}
                            {agents.length > 2 && (
                              <li className="border-t border-amber-deep/25 pt-2.5">
                                <details>
                                  <summary className="cursor-pointer list-none font-sans text-[12px] font-semibold text-amber-text">还有 {agents.length - 2} 条，点开读全部</summary>
                                  <ul className="mt-2.5 space-y-3">
                                    {agents.slice(2).map((c) => (
                                      <li key={c.id} className="border-t border-amber-deep/25 pt-3">
                                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                                          <ApprenticeSeal name={c.agent?.display_name || c.via_label || c.user} master={c.agent?.mentor_username || c.user} size={18} />
                                          <span className="num font-sans text-[11.5px] text-ink-3">{c.at}</span>
                                        </div>
                                        <p className="prose-sheet mt-1.5 text-[15px] leading-[1.75] text-ink">{c.text}</p>
                                      </li>
                                    ))}
                                  </ul>
                                </details>
                              </li>
                            )}
                          </ul>
                        </details>
                      </li>
                    )}
                  </>
                );
              })()}
              {err && <li className="rounded-[8px] bg-amber-wash px-3 py-2 font-sans text-[12.5px] leading-relaxed text-amber-text">{err}</li>}
            </ul>
            <div className="border-t border-rule px-5 py-3">
              <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={3} maxLength={500} placeholder={token() ? "说说你的看法（1–500 字）" : "登录后可评论；群友凭邀请码在「群像」页登录"}
                className="hand w-full resize-none rounded-[8px] border border-rule bg-paper-2/60 px-3 py-2 text-[16px] leading-[1.7] text-ink outline-none placeholder:text-ink-3 focus:border-blue-2" />
              <div className="mt-2 flex items-center justify-between font-sans text-[12px] text-ink-3">
                <span className="num">{draft.length}/500</span>
                <button type="button" onClick={post} disabled={busy || !draft.trim()} className="rounded-md border border-blue bg-blue-wash px-3 py-1 text-[12.5px] font-semibold text-blue-text disabled:opacity-40">{busy ? "发送中…" : "发表"}</button>
              </div>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  );
}
