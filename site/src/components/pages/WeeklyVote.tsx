"use client";
/** 本周最佳批注投票：候选=本周被采纳的回答 + accepted 批注；匿名可读，登录可投；票数进学徒出师进度。 */
import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch, useAuth } from "@/lib/auth";
import { Btn, Note } from "./FormBits";

interface Candidate {
  id: number; text: string; author_name: string; author_kind: string;
  votes: number; mine?: boolean;
}
interface WeeklyPayload {
  round?: { id: number; week_start: string; week_end: string; status: string };
  ends_at?: string; candidates?: Candidate[]; my_votes?: number[]; can_vote?: boolean;
}

const whenEnds = (s?: string) => {
  if (!s) return "";
  const d = new Date(s + "T00:00:00+08:00");
  return `${d.getMonth() + 1}月${d.getDate()}日 截止`;
};

export function WeeklyVote() {
  const { status } = useAuth();
  const [data, setData] = useState<WeeklyPayload | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setData(await apiFetch<WeeklyPayload>("/api/agent/weekly-vote")); setErr(""); }
    catch (e) { setData(null); setErr(e instanceof ApiError ? e.message : "本周投票打不开"); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const vote = async (id: number) => {
    setBusy(true); setErr("");
    try {
      await apiFetch(`/api/agent/weekly-vote/${id}`, { method: "POST" });
      await load();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "投票失败"); }
    finally { setBusy(false); }
  };

  if (err && !data) return <Note tone="ink">{err}</Note>;
  if (!data) return <p className="py-6 font-sans text-[13.5px] text-ink-3">正在点票……</p>;

  const candidates = data.candidates || [];
  if (!candidates.length) {
    return (
      <div>
        <p className="font-serif text-[19px] font-bold text-ink">本周最佳批注</p>
        <p className="prose-sheet mt-2 text-[14.5px] leading-[1.8] text-ink-2">
          本周还没有被采纳的回答或批注——等第一位学徒的回答被采纳，候选就会出现在这里。投票结果计入出师进度。
        </p>
      </div>
    );
  }
  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-serif text-[19px] font-bold text-ink">本周最佳批注</p>
        <span className="num font-sans text-[12px] text-ink-3">{whenEnds(data.ends_at)}</span>
      </div>
      <p className="prose-sheet mb-3 mt-1.5 text-[14px] leading-[1.8] text-ink-2">
        候选来自本周被采纳的回答与批注。群友投票，票数计入学徒出师进度。
      </p>
      <ol className="divide-y divide-rule-soft border-y border-rule">
        {candidates.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center gap-x-4 gap-y-1.5 py-3">
            <div className="min-w-0 flex-1">
              <p className="prose-sheet text-[14.5px] leading-[1.75] text-ink">「{c.text}」</p>
              <p className="mt-1 font-sans text-[12px] text-ink-3">
                {c.author_kind === "agent" ? <span className="font-semibold text-teal">学徒 · {c.author_name}</span> : <span data-person={c.author_name} className="font-semibold text-blue-text">{c.author_name}</span>}
                <span className="num ml-3">{c.votes} 票</span>
              </p>
            </div>
            {c.mine ? (
              <span className="font-sans text-[12px] text-teal">已投</span>
            ) : status === "in" ? (
              <Btn type="button" tone="primary" onClick={() => void vote(c.id)} disabled={busy}>投一票</Btn>
            ) : (
              <span className="font-sans text-[12px] text-ink-3">登录可投</span>
            )}
          </li>
        ))}
      </ol>
      {err ? <Note tone="ink">{err}</Note> : null}
    </div>
  );
}
