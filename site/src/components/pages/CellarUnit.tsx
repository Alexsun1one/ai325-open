"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiFetch, ApiError, getToken, useAuth } from "@/lib/auth";
import { Note } from "./FormBits";
import { Gate } from "./Gate";
import { SpeakerIdentity } from "@/components/ui/SpeakerIdentity";
import { RichMessage } from "@/components/ui/RichMessage";
import { clock, participantName, type UnitParticipant, type UnitSummary } from "./CellarList";

interface UnitMessage {
  id: number | null;
  ordinal: number;
  time?: string | null;
  at?: string | null;
  sender?: string | null;
  sender_name?: string | null;
  text: string;
  likes?: number;
  liked?: boolean;
  comment_anchor?: string | null;
}

interface UnitDetail extends UnitSummary {
  locked?: boolean;
  messages?: UnitMessage[] | null;
}

interface ThreadComment {
  id: number | string;
  user?: string;
  text: string;
  at?: string;
  status?: string;
  reply_to?: number | string | null;
  via?: string | null;
  via_label?: string | null;
  agent?: { display_name?: string; mentor_username?: string; avatar_key?: string } | null;
}

interface LikeResponse {
  likes: number;
  liked?: boolean;
}

function unitAnchor(unitId: string, ordinal: number) {
  return `atom:${unitId}:${ordinal}`;
}

function messageId(unitId: string, ordinal: number) {
  return `cellar-message-${unitId}-${ordinal}`;
}

function parseOrdinal(raw: string | null) {
  if (!raw || !/^[1-9]\d*$/.test(raw)) return null;
  const value = Number(raw);
  return Number.isSafeInteger(value) ? value : null;
}

function messageSender(message: UnitMessage) {
  return message.sender?.trim() || message.sender_name?.trim() || "群友";
}

function messageTime(message: UnitMessage) {
  return clock(message.time ?? message.at);
}

function UnitHeader({ unit }: { unit: UnitDetail }) {
  const people = (unit.participants ?? []).map((person: UnitParticipant) => participantName(person)).filter(Boolean);
  const title = unit.title?.trim() || "无题的一坛";
  const start = clock(unit.start_at);
  const end = clock(unit.end_at);
  return (
    <header className="border-b border-rule pb-7">
      <a href="/cellar/" className="inline-flex min-h-11 items-center gap-1.5 font-sans text-[13px] font-semibold text-blue-text no-underline hover:underline sm:min-h-0">
        <svg aria-hidden width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M15 6l-6 6 6 6" /></svg>
        回原浆目录
      </a>
      <div className="mt-5 flex flex-wrap items-start justify-between gap-5">
        <div className="min-w-0">
          <div className="label">窖藏 · 原浆坛</div>
          <h1 className="mt-2 font-serif text-[30px] font-black leading-[1.2] tracking-[0.01em] text-ink sm:text-[38px]">{title}</h1>
        </div>
        <div className="shrink-0 rotate-[-2deg] border border-blue px-3 py-2 text-right text-blue-text">
          <div className="label text-[10px]">窖藏编号</div>
          <div className="num mt-0.5 text-[12px] font-semibold tracking-[0.04em]">{unit.id}</div>
        </div>
      </div>
      <p className="prose-sheet mt-4 max-w-[42em] text-[16px] leading-[1.85] text-ink-2">{unit.summary || "这一坛没有另外的摘要，登录后可读逐字原浆。"}</p>
      <dl className="mt-5 grid grid-cols-2 gap-x-5 gap-y-3 border-t border-rule pt-4 font-sans text-[12.5px] sm:grid-cols-4">
        <div><dt className="label">日期</dt><dd className="num mt-0.5 text-ink">{unit.date}</dd></div>
        <div><dt className="label">时间</dt><dd className="num mt-0.5 text-ink">{start ? `${start}${end && end !== start ? ` – ${end}` : ""}` : "—"}</dd></div>
        <div><dt className="label">原话</dt><dd className="num mt-0.5 text-ink">{typeof unit.message_count === "number" ? unit.message_count : "—"} 句</dd></div>
        <div><dt className="label">在场</dt><dd className="mt-0.5 text-ink">{people.length || "—"} 人</dd></div>
      </dl>
      {people.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {people.map((name, index) => <span key={`${name}-${index}`} data-person={name} className="rounded-[3px] bg-blue-wash px-1.5 py-[2px] font-sans text-[11.5px] text-blue-text">{name}</span>)}
        </div>
      )}
      {unit.has_gap && <div className="mt-5"><Note tone="ink">这一坛的原始时段有缺口，时间线照现有记录呈现，不把缺口补成连续聊天。</Note></div>}
    </header>
  );
}

function MessageRow({ message, unitId, date, highlighted }: { message: UnitMessage; unitId: string; date: string; highlighted: boolean }) {
  const [open, setOpen] = useState(false);
  const [comments, setComments] = useState<ThreadComment[] | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [likeBusy, setLikeBusy] = useState(false);
  const [likes, setLikes] = useState(message.likes ?? 0);
  const [liked, setLiked] = useState(Boolean(message.liked));
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const expectedAnchor = unitAnchor(unitId, message.ordinal);
  const anchor = message.comment_anchor === expectedAnchor ? message.comment_anchor : expectedAnchor;
  const sender = messageSender(message);
  const time = messageTime(message);

  const loadComments = useCallback(async () => {
    setComments(null);
    setError("");
    try {
      const data = await apiFetch<{ items?: ThreadComment[] }>(`/api/comments?anchor=${encodeURIComponent(anchor)}`);
      setComments(data.items ?? []);
    } catch (cause) {
      setComments([]);
      setError(cause instanceof ApiError ? cause.message : "评论暂时取不到，请再试一次。");
    }
  }, [anchor]);

  const toggleComments = () => {
    const next = !open;
    setOpen(next);
    if (next && comments === null) void loadComments();
  };

  const like = async () => {
    if (liked || likeBusy) return;
    if (!getToken()) {
      setError("登录票据已失效，请重新登录后再赞。");
      return;
    }
    if (message.id == null) {
      setError("这条原浆暂时没有可用的消息凭证。");
      return;
    }
    setLikeBusy(true);
    setError("");
    try {
      const data = await apiFetch<LikeResponse>(`/api/context-unit-messages/${message.id}/like`, { method: "POST" });
      setLikes(data.likes);
      setLiked(data.liked ?? true);
      setNotice("已赞");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "没赞上，请再试一次。");
    } finally {
      setLikeBusy(false);
    }
  };

  const postComment = async () => {
    const text = draft.trim();
    if (!text || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const created = await apiFetch<ThreadComment & { moderation_queue_id?: number | string }>("/api/comments", {
        method: "POST",
        body: JSON.stringify({ anchor, date, text, reply_to: null }),
      });
      setDraft("");
      setComments((current) => [...(current ?? []), created]);
      setNotice(created.status === "pending" ? "已提交，审核后会显示。" : "评论已发出。");
    } catch (cause) {
      setError(cause instanceof ApiError ? (cause.status === 401 ? "先登录再说话。" : cause.message) : "没发出去，请再试一次。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <li
      id={messageId(unitId, message.ordinal)}
      data-ordinal={message.ordinal}
      aria-current={highlighted ? "location" : undefined}
      className={`group relative ml-16 border-l border-rule pb-8 pl-5 sm:ml-20 sm:pl-6 ${highlighted ? "rounded-r-[8px] bg-amber-wash/55 py-2 pr-3" : ""}`}
    >
      <span aria-hidden className="absolute -left-[5px] top-[8px] h-[9px] w-[9px] rounded-full border border-rule bg-paper" />
      {time && <time dateTime={message.time ?? message.at ?? undefined} className="num absolute -left-[4.25rem] top-[5px] w-14 text-right font-sans text-[11px] leading-none text-ink-3 sm:-left-[5.25rem]">{time}</time>}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <SpeakerIdentity name={sender} />
        <span className="num font-sans text-[11.5px] text-ink-3">第 {message.ordinal} 条</span>
        <div className="ml-auto flex items-center gap-1 font-sans text-[12px] text-ink-3">
          <button
            type="button"
            onClick={() => void like()}
            disabled={liked || likeBusy}
            aria-label={liked ? "已点赞这条原浆" : "点赞这条原浆"}
            aria-pressed={liked}
            className="inline-flex min-h-9 items-center gap-1 rounded-[5px] px-1.5 transition-colors hover:bg-paper-2 hover:text-ink disabled:cursor-default disabled:opacity-75"
          >
            <svg aria-hidden width="13" height="13" viewBox="0 0 24 24" fill={liked ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2"><path d="M12 20s-7-4.6-9.2-9A5.2 5.2 0 0 1 12 6.6 5.2 5.2 0 0 1 21.2 11C19 15.4 12 20 12 20Z" /></svg>
            <span className="num">{likes}</span>
          </button>
          <button
            type="button"
            onClick={toggleComments}
            aria-expanded={open}
            aria-controls={`${messageId(unitId, message.ordinal)}-comments`}
            aria-label={`评论第 ${message.ordinal} 条原浆`}
            className="inline-flex min-h-9 items-center gap-1 rounded-[5px] px-1.5 transition-colors hover:bg-paper-2 hover:text-ink"
          >
            <svg aria-hidden width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z" /></svg>
            评
          </button>
        </div>
      </div>
      <p className="prose-sheet mt-2 whitespace-pre-wrap text-[17px] leading-[1.9] text-ink">{message.text}</p>
      {highlighted && <span className="mt-1 inline-flex rounded-[3px] bg-amber-wash px-1.5 py-[2px] font-sans text-[11px] font-semibold text-amber-text">凭证定位 · 第 {message.ordinal} 条</span>}
      {(notice || error) && <p role={error ? "alert" : "status"} className={`mt-2 font-sans text-[12px] ${error ? "text-cinnabar-text" : "text-teal-text"}`}>{error || notice}</p>}
      {open && (
        <div id={`${messageId(unitId, message.ordinal)}-comments`} className="mt-4 rounded-[8px] border border-rule bg-paper-2/55 px-3.5 py-3.5">
          <div className="flex items-baseline justify-between gap-3">
            <h3 className="label">这条的评论</h3>
            <span className="num font-sans text-[11px] text-ink-3">{anchor}</span>
          </div>
          <ul className="mt-2.5 space-y-2.5">
            {comments === null && <li className="font-sans text-[12.5px] text-ink-3">正在取评论…</li>}
            {comments?.length === 0 && !error && <li className="font-sans text-[12.5px] text-ink-3">这条还没有人评。</li>}
            {comments?.map((comment) => (
              <li key={comment.id} className="text-[14px] leading-[1.7]">
                <SpeakerIdentity name={comment.via === "agent" || comment.agent ? comment.agent?.display_name || comment.via_label || comment.user || "学徒" : comment.user || "群友"} kind={comment.via === "agent" || comment.agent ? "agent" : "human"} master={comment.agent?.mentor_username} avatarKey={comment.agent?.avatar_key} />
                <RichMessage text={comment.text} className="mt-1.5 text-ink-2" />
                {comment.status === "pending" && <span className="ml-2 font-sans text-[11px] text-amber-text">待审核</span>}
              </li>
            ))}
          </ul>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row">
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => { if ((event.metaKey || event.ctrlKey) && event.key === "Enter") void postComment(); }}
              maxLength={500}
              placeholder="评一句（1–500 字）"
              aria-label={`评论第 ${message.ordinal} 条原浆`}
              className="min-h-11 min-w-0 flex-1 rounded-[4px] border border-rule bg-paper px-3 py-1.5 font-sans text-[14px] text-ink outline-none focus:border-blue-2"
            />
            <button
              type="button"
              disabled={busy || !draft.trim()}
              onClick={() => void postComment()}
              className="inline-flex min-h-11 items-center justify-center rounded-[4px] border border-blue bg-blue px-4 py-1 font-sans text-[12.5px] font-semibold text-paper transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
            >
              {busy ? "发出中…" : "评"}
            </button>
          </div>
          <p className="mt-2 font-sans text-[11.5px] leading-relaxed text-ink-3">评论会挂在 {anchor} 下；⌘/Ctrl + Enter 可提交。</p>
        </div>
      )}
    </li>
  );
}

function UnitTranscript({ detail, highlightOrdinal }: { detail: UnitDetail; highlightOrdinal: number | null }) {
  const unitId = detail.id;
  const date = detail.date;
  const messages = useMemo(() => (detail.messages ?? []).slice().sort((a, b) => a.ordinal - b.ordinal), [detail.messages]);

  useEffect(() => {
    if (!messages.length || !highlightOrdinal) return;
    const target = document.getElementById(messageId(unitId, highlightOrdinal));
    if (!target) return;
    target.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [messages, unitId, highlightOrdinal]);

  if (detail.locked || !Array.isArray(detail.messages)) return <Note tone="bad">登录票据没有打开逐字层，请退出后重新登录。</Note>;
  if (!messages.length) return <Note tone="ink">这一坛目前没有可展示的逐字记录。</Note>;

  const missing = highlightOrdinal != null && !messages.some((message) => message.ordinal === highlightOrdinal);
  return (
    <div>
      <div className="mb-5 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-y border-rule py-3 font-sans text-[12.5px] text-ink-3">
        <span>登录可见 · 逐字层已开</span>
        <span className="num">{messages.length} 条 · 按时间顺序</span>
      </div>
      {missing && <div className="mb-4"><Note tone="ink">凭证要定位的第 {highlightOrdinal} 条不在这一坛，先展示完整时间线。</Note></div>}
      <ol aria-label={`${unitId} 逐字原浆`}>
        {messages.map((message) => (
          <MessageRow key={`${message.id ?? "message"}-${message.ordinal}`} message={message} unitId={unitId} date={date} highlighted={highlightOrdinal === message.ordinal} />
        ))}
      </ol>
      <p className="mt-2 border-t border-rule pt-4 font-sans text-[12px] leading-relaxed text-ink-3">原文只在登录后的成员层展示；页面上的人名已按公开规则脱敏，评论和点赞也只作用于这条原浆。</p>
    </div>
  );
}

export function CellarUnit({ id }: { id: string }) {
  const { status, user } = useAuth();
  // 账号维度 remount：登录/登出/换账号整棵重来，前人私密正文不残留
  const accountKey = status === "in" && user ? user.username : status === "out" ? "anon" : null;
  if (accountKey === null) return <p className="py-8 font-sans text-[14px] text-ink-3">正在验票……</p>;
  return <UnitBody key={`${accountKey}:${id}`} id={id} />;
}

function UnitBody({ id }: { id: string }) {
  const params = useSearchParams();
  const highlightOrdinal = parseOrdinal(params?.get("at") ?? null);
  const [unit, setUnit] = useState<UnitDetail | null>(null);
  const [error, setError] = useState("");
  const [nonce, setNonce] = useState(0); // 显式重试

  // 单次取 detail：匿名拿摘要层、登录拿逐字层；登录态变化由外层 key remount 重新取，不复用前人响应
  useEffect(() => {
    let alive = true;
    const c = new AbortController();
    apiFetch<UnitDetail>(`/api/context-units/${encodeURIComponent(id)}`, { signal: c.signal })
      .then((data) => { if (alive && !c.signal.aborted) setUnit(data); })
      .catch((cause) => {
        if (c.signal.aborted || (cause instanceof DOMException && cause.name === "AbortError")) return;
        if (alive) setError(cause instanceof ApiError ? cause.message : "这一坛打不开，请再试一次。");
      });
    return () => { alive = false; c.abort(); };
  }, [id, nonce]);

  if (error) {
    return <Note tone="bad">{error} <button type="button" onClick={() => { setError(""); setUnit(null); setNonce((n) => n + 1); }} className="inline-flex min-h-11 items-center px-3 font-semibold text-blue-text underline underline-offset-2">重试</button></Note>;
  }
  if (!unit) return <p className="py-8 font-sans text-[14px] text-ink-3">正在开坛……</p>;

  return (
    <div className="mx-auto max-w-[760px]">
      <UnitHeader unit={unit} />
      <section className="pt-8" aria-labelledby="cellar-transcript-heading">
        <div className="mb-5 flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <div className="label">原浆逐字层</div>
            <h2 id="cellar-transcript-heading" className="mt-1 font-serif text-[23px] font-bold leading-snug text-ink">下窖读原话</h2>
          </div>
          <span className="font-sans text-[12px] text-ink-3">未登录只见上面的块摘要</span>
        </div>
        <Gate what="窖藏原浆" why="原浆是群里还没蒸馏过的原话，只对群友开。登录后可以沿时间标尺逐条阅读、点赞和评论。">
          <UnitTranscript detail={unit} highlightOrdinal={highlightOrdinal} />
        </Gate>
      </section>
    </div>
  );
}
