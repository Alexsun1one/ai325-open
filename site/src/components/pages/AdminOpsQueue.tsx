"use client";
import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/auth";
import { Btn, Note } from "./FormBits";

interface QueueItem {
  id: number | string;
  kind: string;
  label: string;
  actor: string;
  preview: string;
  created_at: string;
  status: string;
  decide?: string | null;
  member_key?: string;
}
interface QueuePayload {
  as_of: string;
  total: number;
  limit: number;
  truncated: boolean;
  counts: { comment: number; submission: number; redemption: number; identity: number; moderation: number };
  items: QueueItem[];
}

const COUNT_ROWS: { key: keyof QueuePayload["counts"]; label: string; source: string }[] = [
  { key: "comment", label: "待审评论", source: "comments.status=pending" },
  { key: "submission", label: "待审投稿", source: "submissions.status=pending" },
  { key: "redemption", label: "待审兑换", source: "reward_redemptions" },
  { key: "identity", label: "身份待确认", source: "未解析 / 缺 wxid" },
];

export function AdminOpsQueue() {
  const [data, setData] = useState<QueuePayload | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    try { setData(await apiFetch<QueuePayload>("/api/admin/queue")); setErr(""); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "队列读不到"); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const act = async (path: string, body?: object) => {
    setBusy(true); setMsg("");
    try {
      await apiFetch(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
      setMsg("已处理");
      await load();
    } catch (e) { setMsg(e instanceof ApiError ? e.message : "操作失败"); }
    finally { setBusy(false); }
  };

  if (err && !data) return <Note tone="bad">{err}</Note>;
  if (!data) return <p className="py-6 font-sans text-[13.5px] text-ink-3">正在取待办队列……</p>;

  return (
    <section>
      <h3 className="font-serif text-[19px] font-bold text-ink">待办队列</h3>
      <p className="mt-1 max-w-[46em] font-sans text-[13.5px] leading-relaxed text-ink-2">
        评论、投稿、兑换、身份候选集中在这里。0 是真值，不是缺表。截止 {data.as_of}
        {data.truncated ? ` · 前 ${data.limit} 条，共 ${data.total}` : ` · 共 ${data.total} 条`}。
      </p>
      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {COUNT_ROWS.map((row) => (
          <div key={row.key} className="border-l-4 border-teal bg-paper-2 px-3 py-3">
            <div className="label text-teal-text">{row.label}</div>
            <div className="num mt-1 font-serif text-[28px] leading-none text-teal-text">{data.counts[row.key]}</div>
            <div className="mt-1 font-sans text-[11px] text-ink-3">{row.source}</div>
          </div>
        ))}
      </div>
      {msg && <div className="mt-3"><Note tone={msg === "已处理" ? "good" : "bad"}>{msg}</Note></div>}
      <div className="mt-5 divide-y divide-rule-soft border-y border-rule">
        {data.items.length === 0 ? (
          <p className="py-6 font-sans text-[13.5px] text-ink-3">队列是空的。没有待审评论、投稿、兑换。</p>
        ) : data.items.map((it) => (
          <div key={`${it.kind}-${it.id}`} className="flex flex-wrap items-start gap-x-4 gap-y-2 py-3.5">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="rounded-[3px] border border-teal/40 bg-teal-wash px-1.5 py-[1px] font-sans text-[10.5px] font-semibold text-teal-text">{it.label}</span>
                <span className="font-sans text-[14px] font-semibold text-ink">{it.actor}</span>
                <span className="num font-sans text-[12px] text-ink-3">{it.created_at || "—"}</span>
              </div>
              <p className="mt-1 font-sans text-[13px] leading-relaxed text-ink-2">{it.preview || "—"}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {it.kind === "redemption" && (
                <>
                  <Btn type="button" busy={busy} onClick={() => void act(`/api/admin/rewards/redemptions/${it.id}/approve`)}>通过</Btn>
                  <Btn type="button" tone="ghost" busy={busy} onClick={() => void act(`/api/admin/rewards/redemptions/${it.id}/reject`)}>驳回</Btn>
                </>
              )}
              {it.kind === "moderation" && (
                <>
                  <Btn type="button" busy={busy} onClick={() => void act(`/api/moderation/${it.id}/decide`, { decision: "accepted", reason: "运营台人工通过" })}>通过</Btn>
                  <Btn type="button" tone="ghost" busy={busy} onClick={() => void act(`/api/moderation/${it.id}/decide`, { decision: "rejected", reason: "运营台人工驳回" })}>驳回</Btn>
                </>
              )}
              {it.kind === "submission" && it.decide && (
                <>
                  <Btn type="button" busy={busy} onClick={() => void act(it.decide!, { status: "accepted" })}>通过</Btn>
                  <Btn type="button" tone="ghost" busy={busy} onClick={() => void act(it.decide!, { status: "rejected" })}>驳回</Btn>
                </>
              )}
              {it.kind === "identity" && (
                <span className="font-sans text-[12px] text-ink-3">到下方成员表处理</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
