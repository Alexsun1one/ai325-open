"use client";
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { pad3 } from "@/lib/shared";
import { API, api, token } from "@/lib/api";

const KEY = (date: string) => `xf-notes-${date}`;
/** where: local = 只在这台设备；cloud = 已存到账号下，群友能看到（除非设为「只给自己看」）。 */
interface Note { id: string; quote: string; note: string; section?: string; at: number; where?: "local" | "cloud"; visibility?: "public" | "private"; anchor?: string; syncing?: boolean; status?: string; reason?: string }

/** 形状照 backend 2026-08-23 10:56 报告：时间字段 at；mine 额外带 visibility / status / moderation。 */
interface CloudAnno {
  id: number | string; anchor?: string; quote: string; note?: string; section?: string;
  visibility?: "public" | "private"; at?: string; updated_at?: string;
  status?: "accepted" | "pending" | "rejected" | string;
  moderation?: { reason?: string; status?: string } | null;
  moderation_queue_id?: number | null;
}

function fromCloud(a: CloudAnno): Note {
  return {
    id: `c${a.id}`, quote: a.quote ?? "", note: a.note ?? "", section: a.section,
    at: a.at ? Date.parse(a.at) || Date.now() : Date.now(),
    where: "cloud", visibility: a.visibility ?? "public", anchor: a.anchor,
    status: a.status ?? "accepted", reason: a.moderation?.reason ?? "",
  };
}

/** 我的鉴定笔记：选中正文一段 →「记下」；右侧抽屉编辑器，按批保存在本机，可导出 Markdown。 */
export function Notebook({ date, issue, title }: { date: string; issue: number; title: string }) {
  const reduce = useReducedMotion();
  const [notes, setNotes] = useState<Note[]>([]);
  const [open, setOpen] = useState(false);
  const [sel, setSel] = useState<{ text: string; x: number; y: number; section?: string; anchor?: string } | null>(null);
  const [draft, setDraft] = useState("");
  const [signedIn, setSignedIn] = useState(false);
  const [cloudErr, setCloudErr] = useState("");
  const skip = useRef(false);

  // 本机的先出来，再去账号里取——取不到就当没有云，正文照读
  useEffect(() => {
    let local: Note[] = [];
    try { const raw = localStorage.getItem(KEY(date)); if (raw) local = JSON.parse(raw); } catch {}
    setNotes(local);
    const t = token();
    setSignedIn(!!t);
    if (!t) return;
    let alive = true;
    api<{ items?: CloudAnno[] } | CloudAnno[]>(`/api/annotations/mine?date=${date}`)
      .then((d) => {
        if (!alive) return;
        const cloud = (Array.isArray(d) ? d : d.items ?? []).map(fromCloud);
        // 云端与本机同一句话的，只留云端那一条
        const seen = new Set(cloud.map((c) => c.quote.replace(/\s+/g, "")));
        setNotes([...cloud, ...local.filter((n) => !seen.has(n.quote.replace(/\s+/g, "")))].sort((a, b) => b.at - a.at));
      })
      .catch(() => { if (alive) setCloudErr("云端笔记暂时取不到，先看这台设备上的。"); });
    return () => { alive = false; };
  }, [date]);

  /** 只把本机那部分写回 localStorage；云端的那份不落盘，免得两边打架。 */
  const persist = (n: Note[]) => {
    setNotes(n);
    try { localStorage.setItem(KEY(date), JSON.stringify(n.filter((x) => x.where !== "cloud"))); } catch {}
  };

  useEffect(() => {
    const onUp = () => {
      if (skip.current) { skip.current = false; return; }
      const s = window.getSelection(); const text = s?.toString().trim() ?? "";
      if (!s || s.isCollapsed || text.length < 4 || text.length > 600) { setSel(null); return; }
      const anchor = s.anchorNode?.parentElement; if (!anchor || !anchor.closest("main")) { setSel(null); return; }
      if (anchor.closest("textarea, input, button, [data-notebook]")) return;
      const r = s.getRangeAt(0).getBoundingClientRect();
      const section = anchor.closest("section")?.querySelector(".label")?.textContent ?? undefined;
      // 段落锚点由 ParagraphTools 打在 [data-anchor] 上，划线要靠它定位到具体哪一段
      const para = anchor.closest<HTMLElement>("[data-anchor]")?.dataset.anchor;
      setSel({ text, x: Math.min(Math.max(r.left + r.width / 2, 80), window.innerWidth - 80), y: r.top - 10, section, anchor: para });
    };
    const onDown = (e: MouseEvent) => { if ((e.target as HTMLElement).closest("[data-notepop]")) skip.current = true; else setSel(null); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); setSel(null); } };
    document.addEventListener("mouseup", onUp); document.addEventListener("mousedown", onDown); document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mouseup", onUp); document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, []);

  const add = async () => {
    if (!sel) return;
    const anchor = sel.anchor;
    const tmp: Note = { id: `${Date.now()}`, quote: sel.text, note: "", section: sel.section, at: Date.now(), where: signedIn ? "cloud" : "local", visibility: "public", anchor, syncing: signedIn };
    const next = [tmp, ...notes];
    persist(next);
    setSel(null); window.getSelection()?.removeAllRanges(); setOpen(true);
    if (!signedIn) return;
    try {
      const d = await api<{ annotation?: CloudAnno } & Partial<CloudAnno>>(`/api/annotations`, {
        method: "POST",
        body: JSON.stringify({ date, anchor, quote: tmp.quote, note: "", visibility: "public", kind: "highlight" }),
      });
      const saved = (d.annotation ?? d) as CloudAnno;
      setNotes((cur) => cur.map((n) => (n.id === tmp.id ? { ...fromCloud({ ...saved, quote: saved.quote ?? tmp.quote }), section: tmp.section } : n)));
    } catch {
      setNotes((cur) => cur.map((n) => (n.id === tmp.id ? { ...n, where: "local", syncing: false } : n)));
      setCloudErr("这条没能存到账号里，先留在这台设备上。");
    }
  };
  const addFree = () => { if (!draft.trim()) return; persist([{ id: `${Date.now()}`, quote: "", note: draft.trim(), at: Date.now() }, ...notes]); setDraft(""); };
  const update = (id: string, note: string) => persist(notes.map((n) => (n.id === id ? { ...n, note } : n)));
  /** 改批注 / 改可见性都走 PATCH；失败就把话说明白，不假装保存成功。 */
  const pushEdit = async (n: Note, patch: { note?: string; visibility?: "public" | "private" }) => {
    if (n.where !== "cloud") return;
    try {
      const d = await api<{ annotation?: CloudAnno } & Partial<CloudAnno>>(`/api/annotations/${String(n.id).replace(/^c/, "")}`, { method: "PATCH", body: JSON.stringify(patch) });
      const saved = (d.annotation ?? d) as CloudAnno;
      // 改了批注会重新过一遍审核，状态可能从 accepted 变回 pending——照实显示
      if (saved && (saved.status || saved.visibility)) {
        setNotes((cur) => cur.map((x) => (x.id === n.id ? { ...x, status: saved.status ?? x.status, visibility: saved.visibility ?? x.visibility, reason: saved.moderation?.reason ?? "" } : x)));
      }
      setCloudErr("");
    } catch { setCloudErr("这条改动没同步上去，刷新后可能还是旧的。"); }
  };
  const toggleVis = (id: string) => {
    const n = notes.find((x) => x.id === id); if (!n) return;
    const v = n.visibility === "private" ? "public" : "private";
    persist(notes.map((x) => (x.id === id ? { ...x, visibility: v } : x)));
    void pushEdit(n, { visibility: v });
  };
  const remove = async (id: string) => {
    const n = notes.find((x) => x.id === id);
    persist(notes.filter((x) => x.id !== id));
    if (n?.where === "cloud") {
      try { await api(`/api/annotations/${String(n.id).replace(/^c/, "")}`, { method: "DELETE" }); }
      catch { setCloudErr("这条在云端没删掉，刷新后可能还在。"); }
    }
  };
  const save = (md: string) => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([md], { type: "text/markdown" }));
    a.download = `鉴定笔记-${date}.md`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  };
  const localMd = () => [`# 我的鉴定笔记 · 先锋队台账 第 ${pad3(issue)} 批 · ${title}`, "", ...notes.flatMap((n) => [n.quote ? `> ${n.quote}${n.section ? `  \n> —— ${n.section}` : ""}` : "", n.note ? n.note : "", ""])].join("\n");
  /** 登录了就要服务端那份（跨设备齐全）；要不到就用这台设备上看得见的凑。 */
  const exportMd = async () => {
    if (signedIn) {
      try {
        const r = await fetch(`${API}/api/annotations/mine/export.md?date=${date}`, { headers: { Authorization: `Bearer ${token()}` } });
        if (r.ok) { save(await r.text()); return; }
      } catch {}
      setCloudErr("服务器那份导不出来，先给你这台设备上看得见的。");
    }
    save(localMd());
  };

  return (
    <>
      {/* 选中后的「记下」 */}
      <AnimatePresence>
        {sel && (
          <motion.button
            data-notepop type="button" onClick={add}
            initial={reduce ? false : { opacity: 0, y: 4, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={reduce ? { opacity: 0 } : { opacity: 0, y: 4, scale: 0.96 }} transition={reduce ? { duration: 0 } : { duration: 0.18 }}
            className="note-pop fixed z-50 inline-flex min-h-11 -translate-x-1/2 -translate-y-full items-center rounded-full border border-blue bg-paper px-4 py-1.5 font-sans text-[13px] font-semibold text-blue-text"
            style={{ left: sel.x, top: sel.y }}
          >
            记下这段 ✎{!signedIn && <span className="ml-1.5 font-normal text-ink-3">· 只存这台设备</span>}
          </motion.button>
        )}
      </AnimatePresence>

      {/* 抽屉开关：一滴琥珀（gooey：数字徽从液滴里冒出来） */}
      <div data-notebook className="no-print fixed bottom-4 left-4 z-40" style={{ filter: "url(#xf-goo)" }}>
        <svg width="0" height="0" className="absolute" aria-hidden><defs><filter id="xf-goo"><feGaussianBlur in="SourceGraphic" stdDeviation="4" result="b" /><feColorMatrix in="b" mode="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 20 -9" result="g" /><feComposite in="SourceGraphic" in2="g" operator="atop" /></filter></defs></svg>
        <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
          className="relative inline-flex min-h-[44px] items-center gap-2 rounded-full bg-amber-deep px-4 py-2.5 font-sans text-[12.5px] font-semibold text-paper transition-colors hover:bg-amber active:bg-amber-deep">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" aria-hidden><path d="M4 4h12l4 4v12H4z"/><path d="M8 4v6h8V4M8 20v-6h8v6"/></svg>
          鉴定笔记
        </button>
        <AnimatePresence>
          {notes.length > 0 && (
            <motion.span key="n" initial={reduce ? false : { scale: 0, x: -14, y: 6 }} animate={{ scale: 1, x: 0, y: 0 }} exit={reduce ? { opacity: 0 } : { scale: 0, x: -14, y: 6 }} transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 260, damping: 18 }}
              className="num absolute -right-2 -top-2 flex h-6 min-w-6 items-center justify-center rounded-full bg-amber-deep px-1.5 text-[11px] font-bold text-paper">{notes.length}</motion.span>
          )}
        </AnimatePresence>
      </div>

      <AnimatePresence>
        {open && (
          <motion.aside data-notebook initial={reduce ? false : { x: 24, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={reduce ? { opacity: 0 } : { x: 24, opacity: 0 }} transition={reduce ? { duration: 0 } : { duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
            className="no-print fixed bottom-0 right-0 top-[var(--nav-h)] z-40 flex w-full max-w-[420px] flex-col border-l border-rule bg-paper shadow-[var(--shadow-pop)]" role="dialog" aria-modal="false" aria-label="我的鉴定笔记">
            <div className="flex items-center justify-between border-b border-rule px-5 py-3">
              <div>
                <div className="font-serif text-[16px] font-bold text-ink">我的鉴定笔记</div>
                <div className="num font-sans text-[12px] text-ink-3">第 {pad3(issue)} 批 · {signedIn ? "存在你账号里，换设备也在" : "只存这台设备"}</div>
              </div>
              <div className="flex items-center gap-2 font-sans text-[12.5px]">
                <button type="button" onClick={() => void exportMd()} disabled={!notes.length} className="inline-flex min-h-11 items-center rounded-md border border-rule px-3 py-1 text-ink-2 hover:border-blue-2 disabled:opacity-40 sm:min-h-0">导出 .md</button>
                <button type="button" onClick={() => setOpen(false)} className="rounded-md px-2 py-1 text-ink-3 hover:text-ink" aria-label="关闭"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M6 6l12 12M18 6L6 18"/></svg></button>
              </div>
            </div>
            {!signedIn && (
              <p className="border-b border-rule bg-blue-wash/60 px-5 py-2.5 font-sans text-[12.5px] leading-relaxed text-ink-2">
                现在写的东西<b>只留在这台设备上</b>。登录之后会永久保存，划过的句子还会对群友可见——群友凭邀请码在<a href="/members/" className="text-blue-text underline underline-offset-2">群像</a>页进门。
              </p>
            )}
            {cloudErr && (
              <p className="border-b border-rule bg-amber-wash px-5 py-2.5 font-sans text-[12.5px] leading-relaxed text-amber-text">{cloudErr}</p>
            )}
            <div className="border-b border-rule px-5 py-3">
              <textarea value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="写一条自己的鉴定：这一锅里什么对你最有用？" rows={3}
                className="hand w-full resize-none rounded-[8px] border border-rule bg-paper-2/60 px-3 py-2 text-[16px] leading-[1.7] text-ink outline-none placeholder:text-ink-3 focus:border-blue-2" />
              <div className="mt-2 flex items-center justify-between">
                <span className="font-sans text-[12px] text-ink-3">也可以在正文选中一段，点「记下这段」</span>
                <button type="button" onClick={addFree} disabled={!draft.trim()} className="rounded-md border border-blue bg-blue-wash px-3 py-1 font-sans text-[12.5px] font-semibold text-blue-text disabled:opacity-40">记下</button>
              </div>
            </div>
            <ul className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
              {notes.length === 0 && <li className="font-sans text-[13px] leading-relaxed text-ink-3">还没有笔记。读到让你停一下的句子，选中它——它会和你的批注一起留在这里。划过的句子会在正文里显出一道琥珀线，别人也看得到是谁划的。</li>}
              {notes.map((n) => (
                <li key={n.id} className="rounded-[10px] border border-rule bg-paper-2/50 px-4 py-3">
                  {n.quote && <blockquote className="prose-sheet border-l border-amber pl-3 text-[14.5px] leading-[1.75] text-ink-2">{n.quote}{n.section && <span className="ml-2 font-sans text-[11.5px] text-ink-3">· {n.section}</span>}</blockquote>}
                  <textarea value={n.note} onChange={(e) => update(n.id, e.target.value)} onBlur={() => void pushEdit(n, { note: n.note })} placeholder="你的批注…" rows={2}
                    className="hand mt-2 w-full resize-none bg-transparent text-[15.5px] leading-[1.7] text-ink outline-none placeholder:text-ink-3" />
                  {n.status === "rejected" && n.reason && (
                    <p className="mt-1.5 rounded-[6px] bg-cinnabar-wash/60 px-2.5 py-1.5 font-sans text-[12px] leading-relaxed text-cinnabar-text">{n.reason}</p>
                  )}
                  <div className="mt-1 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 font-sans text-[11.5px] text-ink-3">
                    <span className="num">{new Date(n.at).toLocaleString("zh-CN", { hour12: false })}</span>
                    <span className="flex items-center gap-3">
                      {n.where === "cloud" && n.status === "pending" && (
                        <span className="rounded-[3px] border border-amber-deep/45 bg-amber-wash px-1.5 py-[1px] font-semibold text-amber-text" title="批注要过一遍审核，通过之前群友看不到；划线本身已经生效">批注审核中</span>
                      )}
                      {n.where === "cloud" && n.status === "rejected" && (
                        <span className="rounded-[3px] border border-cinnabar/45 bg-cinnabar-wash px-1.5 py-[1px] font-semibold text-cinnabar-text" title={n.reason || "没通过审核"}>批注没通过</span>
                      )}
                      {n.where === "cloud" ? (
                        <button type="button" onClick={() => toggleVis(n.id)}
                          className={`inline-flex min-h-11 items-center rounded-[3px] border px-1.5 py-[1px] font-semibold sm:min-h-0 ${n.visibility === "private" ? "border-rule bg-paper-2 text-ink-3" : "border-amber-deep/45 bg-amber-wash text-amber-text"}`}
                          title={n.visibility === "private" ? "现在只有你看得见，点一下让群友也能看到" : "现在群友能看到，点一下改成只给自己看"}>
                          {n.visibility === "private" ? "只给自己看" : "群友可见"}
                        </button>
                      ) : (
                        <span className="rounded-[3px] border border-rule bg-paper-2 px-1.5 py-[1px]">只在这台设备</span>
                      )}
                      <button type="button" onClick={() => void remove(n.id)} className="inline-flex min-h-11 items-center hover:text-cinnabar-text sm:min-h-0">删除</button>
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  );
}
