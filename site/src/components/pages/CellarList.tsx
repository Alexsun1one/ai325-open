"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { apiFetch, ApiError, checkAuth, useAuth } from "@/lib/auth";
import { Note } from "./FormBits";

export type UnitParticipant = string | { name?: string | null };

/** 语境块摘要：字段名与 `/api/context-units` 最终契约保持一致。 */
export interface UnitSummary {
  id: string;
  date: string;
  version?: number;
  status?: string;
  visibility?: string;
  title?: string | null;
  summary?: string | null;
  start_at?: string | null;
  end_at?: string | null;
  participants?: UnitParticipant[] | null;
  message_count?: number | null;
  has_gap?: boolean;
  evidence_count?: number | null;
  detail_url?: string;
}

interface UnitListResponse {
  items?: UnitSummary[];
  next_cursor?: string | null;
  count?: number;
  selected_date?: string | null; // latest=true 服务端选定的真实日期；date 请求回显
}

const PAGE_LIMIT = 100;

export function participantName(value: UnitParticipant): string {
  return typeof value === "string" ? value.trim() : value.name?.trim() ?? "群友";
}

export function clock(value?: string | null): string {
  if (!value) return "";
  const match = value.match(/T(\d{2}:\d{2})/);
  return match?.[1] ?? value.slice(0, 5);
}

function timeRange(unit: UnitSummary): string {
  const start = clock(unit.start_at);
  const end = clock(unit.end_at);
  if (!start) return "时间未标注";
  return end && end !== start ? `${start} – ${end}` : start;
}

function queryFor(date: string, cursor?: string | null) {
  const query = new URLSearchParams({ date, limit: String(PAGE_LIMIT) });
  if (cursor) query.set("cursor", cursor);
  return `/api/context-units?${query.toString()}`;
}

/** 裸页 latest 直取：服务端选最新可见日，不再先等 dates 日历。 */
function latestUrl() {
  return `/api/context-units?latest=true&limit=${PAGE_LIMIT}`;
}

interface DateItem { date: string; count: number }

/** 窖藏目录：按 API 游标装一页一页的坛子，不把当前页数量冒充总数。
 *  date 缺省时裸页 latest 直取（服务端选最新可见日），日历独立并行。
 *  账号隔离外层：验票完成才挂列表——匿名先发再登录不留旧权限摘要；
 *  登录/登出/换账号按 key 整体重挂真实重取；验票失败按匿名内容显示并如实报 netErr。 */
export function CellarList({ date }: { date?: string }) {
  const { status, user, netErr } = useAuth();
  if (status === "loading") return <p className="py-8 font-sans text-[14px] text-ink-3">正在验票……</p>;
  // netErr=验票失败但 token 仍带 Bearer——不能假装匿名继续取列表；显式重试验票
  if (netErr) {
    return (
      <Note tone="bad">验票没成功：{netErr} <button type="button" onClick={() => void checkAuth(true)} className="inline-flex min-h-11 items-center px-3 font-semibold text-blue-text underline underline-offset-2">重试</button></Note>
    );
  }
  // 身份前缀防撞：合法用户名 anon 不与匿名键撞（in:username:role / anon）
  const accountKey = status === "in" && user ? `in:${user.username}:${user.role ?? ""}` : "anon";
  return <ListBody key={accountKey} date={date} />;
}

function ListBody({ date }: { date?: string }) {
  const [items, setItems] = useState<UnitSummary[] | null>(null);
  const [dates, setDates] = useState<DateItem[] | null>(null);
  const [datesErr, setDatesErr] = useState("");
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const [moreErr, setMoreErr] = useState("");
  const [loadingMore, setLoadingMore] = useState(false);
  const [datesNonce, setDatesNonce] = useState(0);   // dates 重试
  const [itemsNonce, setItemsNonce] = useState(0);   // 列表重试
  const [selectedDate, setSelectedDate] = useState<string | null>(null); // latest 回包选定的真实日
  const aliveAll = useRef(true);
  const listSeq = useRef(0);
  const listCtl = useRef<AbortController | null>(null);
  const moreBusyRef = useRef(false);               // 同步闸：连点同 tick 内也拦
  const moreCtl = useRef<AbortController | null>(null);

  // 显式 date 走原路径；裸页 resolved 自 latest 回包（不再等 dates）
  const activeDate = date ?? selectedDate;
  const reqKey = date ?? "__latest__";

  useEffect(() => {
    aliveAll.current = true;
    return () => { aliveAll.current = false; listCtl.current?.abort(); moreCtl.current?.abort(); };
  }, []); // StrictMode 重挂先复位

  // 日历：独立并行请求，失败显式报错可重试——不再置 null 假装还在加载
  useEffect(() => {
    let alive = true;
    const c = new AbortController();
    const t = window.setTimeout(() => {
      if (!alive) return;
      setDatesErr("");
      apiFetch<{ items: DateItem[] }>("/api/context-units/dates", { signal: c.signal })
        .then((d) => { if (alive && !c.signal.aborted) setDates(d.items ?? []); })
        .catch((e) => {
          if (c.signal.aborted || (e instanceof DOMException && e.name === "AbortError")) return;
          if (alive) setDatesErr(e instanceof ApiError ? e.message : "开窖日历没取到，请再试一次。");
        });
    }, 0);
    return () => { alive = false; window.clearTimeout(t); c.abort(); };
  }, [datesNonce]);

  // 列表：只依赖请求输入（显式date 或 latest），不因 selected_date 回包再发；
  // 换请求作废在途（seq+abort）并掐死上一请求的 loadMore——晚回包不串日
  useEffect(() => {
    const s = ++listSeq.current;
    listCtl.current?.abort();
    moreCtl.current?.abort();
    moreBusyRef.current = false; // 上一请求的在途 loadMore 作废：重置闸，其 finally 按 controller 身份跳过释放
    const c = new AbortController(); listCtl.current = c;
    let alive = true;
    const t = window.setTimeout(() => {
      if (!alive) return;
      setItems(null); setErr(""); setMoreErr(""); setNextCursor(null); setLoadingMore(false); setSelectedDate(null);
      apiFetch<UnitListResponse>(reqKey === "__latest__" ? latestUrl() : queryFor(reqKey), { signal: c.signal })
        .then((data) => {
          if (c.signal.aborted || s !== listSeq.current || !alive) return;
          setItems(data.items ?? []);
          setNextCursor(data.next_cursor ?? null);
          setSelectedDate(data.selected_date ?? null);
        })
        .catch((error) => {
          if (c.signal.aborted || (error instanceof DOMException && error.name === "AbortError")) return;
          if (s !== listSeq.current || !alive) return;
          setItems(null);
          setErr(error instanceof ApiError ? error.message : "这一天的原浆还没装坛");
        });
    }, 0);
    return () => { alive = false; window.clearTimeout(t); c.abort(); };
  }, [reqKey, itemsNonce]);

  const loadMore = async () => {
    if (!nextCursor || !activeDate || moreBusyRef.current) return;
    moreBusyRef.current = true;
    const s = listSeq.current; // 捕获当前日期代——换日后旧回包/旧finally一律无权写状态
    setLoadingMore(true);
    setMoreErr("");
    const c = new AbortController(); moreCtl.current = c;
    try {
      const data = await apiFetch<UnitListResponse>(queryFor(activeDate, nextCursor), { signal: c.signal });
      if (c.signal.aborted || s !== listSeq.current || !aliveAll.current) return;
      setItems((current) => {
        const seen = new Set((current ?? []).map((u) => u.id));
        return [...(current ?? []), ...(data.items ?? []).filter((u) => !seen.has(u.id))];
      });
      setNextCursor(data.next_cursor ?? null);
    } catch (error) {
      if (c.signal.aborted || (error instanceof DOMException && error.name === "AbortError")) return;
      if (s === listSeq.current && aliveAll.current) setMoreErr(error instanceof ApiError ? error.message : "下一页原浆没取到，请再试一次。");
    } finally {
      if (c === moreCtl.current) { // 仅当前一代可解锁——旧 finally 不得释放新请求的门
        moreBusyRef.current = false;
        if (aliveAll.current) setLoadingMore(false);
      }
    }
  };

  // 日历错误/重试在所有分支都可见（空态/错误态不吞）
  const datesBar = datesErr ? (
    <div className="mb-3">
      <Note tone="bad">{datesErr} <button type="button" onClick={() => setDatesNonce((n) => n + 1)} className="inline-flex min-h-11 items-center px-3 font-semibold text-blue-text underline underline-offset-2">重试</button></Note>
    </div>
  ) : null;

  if (err && !items) {
    return (
      <div>
        {datesBar}
        <Note tone="bad">{err} <button type="button" onClick={() => setItemsNonce((n) => n + 1)} className="inline-flex min-h-11 items-center px-3 font-semibold text-blue-text underline underline-offset-2">重试</button></Note>
      </div>
    );
  }
  if (!items) return <p className="py-8 font-sans text-[14px] text-ink-3">正在开窖……</p>;
  if (items.length === 0 && !date) {
    // latest 空态：服务端判定无任何可见坛子
    return <div>{datesBar}<Note tone="ink">还没有装过坛的日子——下钻日报的「凭证」就能看到单块原浆。</Note></div>;
  }
  if (items && !items.length) {
    const idx = (dates ?? []).findIndex((d) => d.date === activeDate);
    const prev = idx > 0 ? dates![idx - 1] : null;
    const next = idx >= 0 && idx < (dates?.length ?? 0) - 1 ? dates![idx + 1] : null;
    return (
      <div>
        {datesBar}
      <div className="rounded-[10px] border border-dashed border-rule px-6 py-10 text-center">
        <p className="font-serif text-[17px] text-ink">{activeDate} 这天还没装坛。</p>
        <div className="mt-4 flex flex-wrap justify-center gap-3 font-sans text-[13px]">
          {next && <Link prefetch={false} href={`/cellar/?date=${next.date}`} className="font-semibold text-blue-text no-underline hover:underline">看后一天（{next.date}，{next.count} 块）→</Link>}
          {prev && <Link prefetch={false} href={`/cellar/?date=${prev.date}`} className="font-semibold text-blue-text no-underline hover:underline">← 看前一天（{prev.date}，{prev.count} 块）</Link>}
          {!prev && !next && <span className="text-ink-3">还没有装过坛的日子——下钻日报的「凭证」就能看到单块原浆。</span>}
        </div>
      </div>
      </div>
    );
  }

  return (
    <div>
      {datesBar}
      <div className="mb-3 flex flex-wrap gap-2 font-sans text-[12px]">
        {(dates ?? []).map((d) => {
          const active = d.date === activeDate;
          return (
            <Link key={d.date} prefetch={false} href={`/cellar/?date=${d.date}`}
              className={`rounded-[4px] border px-2.5 py-1 no-underline transition-colors ${
                active ? "border-amber-deep/60 bg-amber-wash font-semibold text-amber-text" : "border-rule text-ink-3 hover:border-blue-wash-2 hover:text-blue-text"
              }`}>
              {d.date.slice(5)}<span className="num ml-1 opacity-70">·{d.count}</span>
            </Link>
          );
        })}
      </div>
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 font-sans text-[12.5px] text-ink-3">
        <span><span className="num font-semibold text-amber-text">{items.length}</span> 块已显示{nextCursor ? " · 还有后续坛子" : ""}</span>
        <span className="num">按时间顺序 · {activeDate}</span>
      </div>
      <div className="divide-y divide-rule-soft border-y border-rule">
        {items.map((unit) => {
          const people = (unit.participants ?? []).map(participantName).filter(Boolean);
          const title = unit.title?.trim() || "无题的一坛";
          return (
            <Link
              key={unit.id}
              prefetch={false}
              href={`/cellar/?unit=${encodeURIComponent(unit.id)}`}
              className="group block px-1 py-5 no-underline transition-colors hover:bg-paper-2/40 focus-visible:bg-paper-2/40"
            >
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="num font-sans text-[12px] font-semibold tracking-[0.03em] text-blue-text">{unit.id}</span>
                <span className="num font-sans text-[12px] text-ink-3">{timeRange(unit)}</span>
                {unit.has_gap && <span className="rounded-[3px] bg-amber-wash px-1.5 py-[2px] font-sans text-[11px] font-medium text-amber-text">数据有缺口</span>}
              </div>
              <h3 className="mt-2 break-words font-serif text-[19px] font-bold leading-snug text-ink transition-colors group-hover:text-blue-text [overflow-wrap:anywhere]">{title}</h3>
              {unit.summary && <p className="prose-sheet mt-1.5 line-clamp-2 text-[15px] leading-[1.75] text-ink-2">{unit.summary}</p>}
              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 font-sans text-[12.5px] text-ink-3">
                {typeof unit.message_count === "number" && <span className="num">{unit.message_count} 句原话</span>}
                {typeof unit.evidence_count === "number" && unit.evidence_count > 0 && <span className="num">{unit.evidence_count} 条凭证</span>}
                {people.length > 0 && (
                  <span className="flex flex-wrap gap-x-1.5 gap-y-1">
                    {people.slice(0, 8).map((name, index) => (
                      <span key={`${name}-${index}`} data-person={name} className="rounded-[3px] bg-blue-wash px-1.5 py-[2px] font-sans text-[11.5px] text-blue-text">{name}</span>
                    ))}
                    {people.length > 8 && <span className="num">等 {people.length} 人</span>}
                  </span>
                )}
              </div>
            </Link>
          );
        })}
      </div>
      {nextCursor && (
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => void loadMore()}
            disabled={loadingMore}
            className="inline-flex min-h-11 items-center rounded-[5px] border border-rule bg-paper-2 px-4 py-2 font-sans text-[13px] font-semibold text-ink-2 transition-colors hover:border-blue-2 hover:text-blue-text disabled:cursor-wait disabled:opacity-60"
          >
            {loadingMore ? "继续开窖中…" : "继续开窖"}
          </button>
          <span className="font-sans text-[12px] text-ink-3">下一页仍按服务端游标接续，不重复坛子。</span>
        </div>
      )}
      {moreErr && <div className="mt-3"><Note tone="bad">{moreErr}</Note></div>}
    </div>
  );
}
