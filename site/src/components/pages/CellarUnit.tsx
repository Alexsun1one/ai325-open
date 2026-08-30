"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiFetch, ApiError, getToken, useAuth } from "@/lib/auth";
import { Note } from "./FormBits";
import { Gate } from "./Gate";

/** 契约（backend 追加节待定稿，见报告契约缺口节）：
 *  GET /api/context-units/{id} → { id, date, topic, start_at, end_at,
 *    participants: [{name}], messages: [{ id, ordinal, time, sender, text, likes, liked }] }
 *  评论复用 /api/comments，anchor = `unit:{unitId}:{ordinal}`
 *  点赞 POST /api/context-unit-messages/{messageId}/like → { likes }   // 待 backend 追加
 */
interface UnitMessage { id: number; ordinal: number; time?: string; sender: string; text: string; likes?: number; liked?: boolean }
interface UnitDetail {
  id: number; date: string; topic?: string; start_at?: string; end_at?: string;
  participants?: { name: string }[]; messages: UnitMessage[];
}
interface ThreadComment { id: number | string; user: string; text: string; at: string; agent?: { display_name?: string; mentor_username?: string } | null }

const threadAnchor = (unitId: number, ordinal: number) => `unit:${unitId}:${ordinal}`;

function MessageRow({ m, unitId, date, hl, onToggle }: {
  m: UnitMessage; unitId: number; date: string; hl: boolean; onToggle: (ordinal: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<ThreadComment[] | null>(null);
  const [draft, setDraft] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [likes, setLikes] = useState(m.likes ?? 0);
  const [liked, setLiked] = useState(!!m.liked);

  const loadThread = useCallback(async () => {
    setItems(null);
    try {
      const d = await apiFetch<{ items: ThreadComment[] }>(`/api/comments?anchor=${encodeURIComponent(threadAnchor(unitId, m.ordinal))}`);
      setItems(d.items ?? []);
    } catch { setItems([]); }
  }, [unitId, m.ordinal]);

  const toggleOpen = () => {
    setOpen((v) => !v);
    if (!open) void loadThread();
  };

  const post = async () => {
    if (!draft.trim()) return;
    setBusy(true); setErr(null);
    try {
      await apiFetch("/api/comments", { method: "POST", body: JSON.stringify({ anchor: threadAnchor(unitId, m.ordinal), date, text: draft.trim() }) });
      setDraft(""); await loadThread();
    } catch (e) { setErr(e instanceof ApiError ? (e.status === 401 ? "先登录再说话。" : e.message) : "没发出去"); }
    finally { setBusy(false); }
  };

  const like = async () => {
    if (!getToken()) return;
    try {
      const d = await apiFetch<{ likes: number }>(`/api/context-unit-messages/${m.id}/like`, { method: "POST" });
      setLikes(d.likes); setLiked(true);
    } catch { /* 契约未落地时静默 */ }
  };

  return (
    <li id={`msg-${m.ordinal}`} className={`group relative border-l border-rule pl-5 pb-7 ${hl ? "rounded-r-[8px] bg-amber-wash/35 py-1 pr-3" : ""}`}>
      {/* 时间标尺点 */}
      <span aria-hidden className="absolute -left-[5px] top-[7px] h-[9px] w-[9px] rounded-full border border-rule bg-paper" />
      {m.time && <span className="num absolute -left-[4px] top-[19px] w-14 -translate-x-full pr-3 text-right font-sans text-[11px] leading-none text-ink-3">{m.time.slice(0, 5)}</span>}
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span data-person={m.sender} className="font-sans text-[13px] font-semibold text-blue-text">{m.sender}</span>
        {/* hover 工具：点赞 / 评论。不常显——触屏上没有 hover，靠 group-hover 之外再给焦点可达 */}
        <span className="inline-flex items-center gap-1 opacity-0 transition-opacity duration-200 focus-within:opacity-100 group-hover:opacity-100">
          <button type="button" onClick={like} aria-label="点赞这条" aria-pressed={liked}
            className="inline-flex h-[22px] items-center gap-1 rounded-[5px] px-1.5 font-sans text-[12px] leading-none text-ink-3 transition-colors hover:bg-paper-2 hover:text-ink">
            <svg aria-hidden width="11" height="11" viewBox="0 0 24 24" fill={liked ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2"><path d="M12 20s-7-4.6-9.2-9A5.2 5.2 0 0 1 12 6.6 5.2 5.2 0 0 1 21.2 11C19 15.4 12 20 12 20Z"/></svg>
            <span className="num">{likes}</span>
          </button>
          <button type="button" onClick={toggleOpen} aria-expanded={open} aria-label="评论这条"
            className="inline-flex h-[22px] items-center gap-1 rounded-[5px] px-1.5 font-sans text-[12px] leading-none text-ink-3 transition-colors hover:bg-paper-2 hover:text-ink">
            <svg aria-hidden width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z"/></svg>
            评
          </button>
        </span>
      </div>
      <p className="prose-sheet mt-1 text-[17px] leading-[1.9] text-ink">{m.text}</p>
      {open && (
        <div className="mt-3 rounded-[8px] border border-rule bg-paper-2/50 px-3 py-3">
          <ul className="space-y-2.5">
            {items === null && <li className="font-sans text-[12.5px] text-ink-3">正在取…</li>}
            {items && items.length === 0 && <li className="font-sans text-[12.5px] text-ink-3">这条还没有人评。</li>}
            {items?.map((c) => (
              <li key={c.id} className="text-[14px] leading-[1.7]">
                <span className="font-sans text-[12.5px] font-semibold text-ink">{c.user}</span>
                <span className="ml-2 font-sans text-[13px] leading-[1.7] text-ink-2">{c.text}</span>
              </li>
            ))}
          </ul>
          {err && <p className="mt-2 font-sans text-[12.5px] text-amber-text">{err}</p>}
          <div className="mt-2.5 flex gap-2">
            <input value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={500} placeholder={getToken() ? "评一句（1–500 字）" : "先登录才能评"}
              className="min-h-10 flex-1 rounded-[4px] border border-rule bg-paper px-3 py-1.5 font-sans text-[14px] text-ink outline-none focus:border-blue-2" />
            <button type="button" disabled={busy || !getToken()} onClick={() => void post()} aria-label="提交这条的评论"
              className="inline-flex min-h-10 items-center rounded-[4px] border border-blue bg-blue px-3 py-1 font-sans text-[12.5px] font-semibold text-paper transition-opacity hover:opacity-90 disabled:opacity-45">评</button>
          </div>
        </div>
      )}
    </li>
  );
}

export function CellarUnit({ id }: { id: number }) {
  const { status } = useAuth();
  const [unit, setUnit] = useState<UnitDetail | null>(null);
  const [err, setErr] = useState("");
  const params = useSearchParams();
  const hlOrdinal = Number(params?.get("at") ?? 0) || 0;
  const scrolled = useRef(false);

  const load = useCallback(async () => {
    try {
      const d = await apiFetch<UnitDetail>(`/api/context-units/${id}`);
      setUnit(d); setErr("");
    } catch (e) { setUnit(null); setErr(e instanceof ApiError ? e.message : "这一坛打不开"); }
  }, [id]);

  useEffect(() => { void load(); }, [load]);

  // 凭证下钻：滚动到高亮消息
  useEffect(() => {
    if (!unit || !hlOrdinal || scrolled.current) return;
    const el = document.getElementById(`msg-${hlOrdinal}`);
    if (el) { el.scrollIntoView({ block: "center" }); scrolled.current = true; }
  }, [unit, hlOrdinal]);

  if (status !== "in") {
    return <Gate what="窖藏原浆" why="原浆是群里没蒸馏过的原话，只对群友开。要看一坛，先登录——和群像一个门槛。" >{null}</Gate>;
  }
  if (err && !unit) return <Note tone="bad">{err}</Note>;
  if (!unit) return <p className="py-8 font-sans text-[14px] text-ink-3">正在开坛……</p>;

  const participants = unit.participants ?? [];
  return (
    <div className="mx-auto max-w-[640px]">
      <header className="pb-6 pt-2">
        <div className="label">窖藏 · 原浆坛 #{unit.id} · {unit.date}</div>
        <h1 className="mt-3 font-serif text-[30px] font-black leading-[1.2] tracking-[0.01em] text-ink sm:text-[36px]">{unit.topic || "无题的一坛"}</h1>
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1.5 font-sans text-[13px] text-ink-3">
          {unit.start_at && unit.end_at && <span className="num">{unit.start_at.slice(11, 16)} – {unit.end_at.slice(11, 16)}</span>}
          {participants.length > 0 && <span>在场：{participants.map((p) => p.name).join(" · ")}</span>}
          <span className="num">{unit.messages.length} 句</span>
        </div>
      </header>
      <ol>
        {unit.messages.map((m) => (
          <MessageRow key={m.id} m={m} unitId={unit.id} date={unit.date} hl={hlOrdinal === m.ordinal} onToggle={() => {}} />
        ))}
      </ol>
      <p className="mt-4 border-t border-rule pt-4 font-sans text-[12.5px] leading-relaxed text-ink-3">
        这是蒸馏前的原浆，逐字未动，只做了脱敏。想看蒸馏后的说法，回<a href="/ledger/2026-08-23/" className="text-blue-text underline underline-offset-2">第 002 批日报</a>，或回<a href="/cellar/" className="text-blue-text underline underline-offset-2">窖藏目录</a>。
      </p>
    </div>
  );
}
