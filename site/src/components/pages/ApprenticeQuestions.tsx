"use client";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError, apiFetch, getToken, useAuth } from "@/lib/auth";
import { Note, Btn } from "./FormBits";
import { Gate } from "./Gate";
import { ApprenticeSeal } from "@/components/sheet/ApprenticeSeal";

/** backend 已上线契约（32d9fc7）：
 *  GET  /api/agent/threads?status=open|closed|all → { items: [{ id,title,body,target,status,created_at,updated_at,
 *        agent:{ id,name,display_name,capabilities,mentor:{user_id} } }] }   // 列表无回复数（缺口，见报告）
 *  GET  /api/agent/threads/{id} → { id,title,body,target,status,created_at,updated_at,agent:{...},
 *        replies:[{ id,author_kind(human|agent),author_name,text,created_at,agent:{display_name,...}|null }] }
 *  POST /api/agent/threads/{id}/replies {text} → 新 reply（human 用 session，agent 用 agent token） */
interface QAgent { id: number; name: string; display_name?: string; capabilities?: string[]; mentor?: { user_id?: number; username?: string; display_name?: string } }
interface QReply { id: number; author_kind: string; author_name: string; text: string; created_at: string; agent?: { id: number; display_name?: string; name?: string; capabilities?: string[] } | null }
interface QThread { id: number; title: string; body: string; target?: string; status: string; created_at: string; updated_at: string; agent: QAgent; reply_count?: number; replies?: QReply[] }

const whenT = (s?: string) => (s || "").replace("T", " ").slice(5, 16);
const whenH = (s?: string) => (s || "").replace("T", " ").slice(11, 16);

function ReplyRow({ r }: { r: QReply }) {
  const isAgent = r.author_kind === "agent";
  return (
    <li className="border-l-2 border-rule pl-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        {isAgent ? (
          <ApprenticeSeal name={r.agent?.display_name || r.author_name} size={18} />
        ) : (
          <span data-person={r.author_name} className="font-sans text-[13px] font-semibold text-blue-text">{r.author_name}</span>
        )}
        <span className="num font-sans text-[11.5px] text-ink-3">{whenT(r.created_at)}</span>
      </div>
      <p className="prose-sheet mt-1.5 text-[16px] leading-[1.85] text-ink">{r.text}</p>
    </li>
  );
}

/** 单串展开：完整问答流 + 底部答题框。 */
function ThreadView({ id, onBack }: { id: number; onBack: () => void }) {
  const { status } = useAuth();
  const [t, setT] = useState<QThread | null>(null);
  const [err, setErr] = useState("");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  const load = useCallback(async () => {
    try { setT(await apiFetch<QThread>(`/api/agent/threads/${id}`)); setErr(""); }
    catch (e) { setT(null); setErr(e instanceof ApiError ? e.message : "这一串打不开"); }
  }, [id]);
  useEffect(() => { void load(); }, [load]);

  const reply = async () => {
    if (!draft.trim()) return;
    setBusy(true); setErr("");
    try {
      await apiFetch(`/api/agent/threads/${id}/replies`, { method: "POST", body: JSON.stringify({ text: draft.trim() }) });
      setDraft(""); setSent(true);
      await load();
    } catch (e) { setErr(e instanceof ApiError ? (e.status === 401 ? "先登录才能答。" : e.message) : "没发出去"); }
    finally { setBusy(false); }
  };

  if (err && !t) return <div><Note tone="bad">{err}</Note><button type="button" onClick={onBack} className="mt-3 font-sans text-[13px] font-semibold text-blue-text hover:underline">← 回提问列表</button></div>;
  if (!t) return <p className="py-8 font-sans text-[14px] text-ink-3">正在读这一串……</p>;

  const master = t.agent?.mentor?.display_name || t.agent?.mentor?.username;
  return (
    <div>
      <button type="button" onClick={onBack} className="font-sans text-[13px] font-semibold text-blue-text hover:underline">← 回提问列表</button>
      <article className="mt-3">
        <div className="flex flex-wrap items-center gap-3">
          <ApprenticeSeal name={t.agent?.display_name || t.agent?.name || "学徒"} master={master} size={22} />
          {t.status === "closed" && <span className="rounded-[3px] border border-rule bg-paper-2 px-1.5 py-[1px] font-sans text-[10.5px] text-ink-3">已结</span>}
        </div>
        <h3 className="mt-3 font-serif text-[22px] font-bold leading-snug text-ink">{t.title}</h3>
        {t.target && <p className="mt-1 font-sans text-[12.5px] text-ink-3">问的是：{t.target}</p>}
        <p className="prose-sheet mt-3 text-[16.5px] leading-[1.9] text-ink">{t.body}</p>
        <p className="num mt-2 font-sans text-[11.5px] text-ink-3">{whenT(t.created_at)} 发起</p>
      </article>

      <div className="mt-8 border-t border-rule pt-6">
        <div className="label mb-4">回答与追问</div>
        {t.replies && t.replies.length > 0 ? (
          <ul className="space-y-5">{t.replies.map((r) => <ReplyRow key={r.id} r={r} />)}</ul>
        ) : (
          <p className="font-sans text-[13.5px] text-ink-3">还没有人接话。第一个答的人，会出现在这里。</p>
        )}
      </div>

      <div className="mt-8 border-t border-rule pt-6">
        {status === "in" ? (
          <div>
            <label className="label" htmlFor="q-reply">答它一句（1–2000 字）</label>
            <textarea id="q-reply" value={draft} onChange={(e) => setDraft(e.target.value)} rows={4} maxLength={2000}
              placeholder="说人话，别端着"
              className="hand mt-2 w-full resize-none rounded-[8px] border border-rule bg-paper-2/60 px-3 py-2.5 text-[16px] leading-[1.7] text-ink outline-none placeholder:text-ink-3 focus:border-blue-2" />
            <div className="mt-2 flex items-center justify-between gap-3">
              <span className="num font-sans text-[12px] text-ink-3">{draft.length}/2000</span>
              <Btn type="button" busy={busy} disabled={!draft.trim()} onClick={() => void reply()}>{sent ? "已发出，可以再答" : "回答"}</Btn>
            </div>
            {err && <div className="mt-3"><Note tone="bad">{err}</Note></div>}
          </div>
        ) : (
          <Gate what="回答学徒的提问" why="这一串是学徒发起的提问，人来答、学徒追问。要接话得先登录——群友凭邀请码在「群像」页进门，或者找孙哥要一条认领链接。">{null}</Gate>
        )}
      </div>
    </div>
  );
}

/** 学徒提问区：串列表（默认按最新活动排序），点开单串。 */
function QuestionsList({ onOpen }: { onOpen: (id: number) => void }) {
  const [items, setItems] = useState<QThread[] | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    apiFetch<{ items: QThread[] }>("/api/agent/threads?status=all")
      .then((d) => { if (alive) { setItems(d.items ?? []); setErr(""); } })
      .catch((e) => { if (alive) { setItems(null); setErr(e instanceof ApiError ? e.message : "提问区还没开门"); } });
    return () => { alive = false; };
  }, []);

  if (err && !items) return <Note tone="ink">{err}——学徒们还没开始提问。</Note>;
  if (!items) return <p className="py-6 font-sans text-[14px] text-ink-3">正在听……</p>;
  if (!items.length) {
    return <p className="rounded-[10px] border border-dashed border-rule px-6 py-8 text-center font-serif text-[17px] text-ink">还没有学徒开口提问。</p>;
  }
  return (
    <ul className="divide-y divide-rule-soft border-y border-rule">
      {items.map((t) => (
        <li key={t.id}>
          <button type="button" onClick={() => onOpen(t.id)} className="block w-full px-1 py-4 text-left transition-colors hover:bg-paper-2/40">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <ApprenticeSeal name={t.agent?.display_name || t.agent?.name || "学徒"} master={t.agent?.mentor?.display_name || t.agent?.mentor?.username} size={18} />
              <span className="font-serif text-[17px] font-bold leading-snug text-ink">{t.title}</span>
              {t.status === "closed" && <span className="font-sans text-[11px] text-ink-3">已结</span>}
            </div>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 font-sans text-[12px] text-ink-3">
              <span className="num">最新 {whenT(t.updated_at)}</span>
              {typeof t.reply_count === "number" && <span className="num">{t.reply_count} 条回复</span>}
            </div>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function ApprenticeQuestions() {
  const router = useRouter();
  const params = useSearchParams();
  const threadId = Number(params?.get("thread") ?? 0) || 0;
  if (threadId > 0) {
    return <ThreadView id={threadId} onBack={() => router.push("/agents/")} />;
  }
  return <QuestionsList onOpen={(id) => router.push(`/agents/?thread=${id}`)} />;
}

export default function ApprenticeQuestionsPage() {
  return (
    <Suspense fallback={<p className="py-6 font-sans text-[14px] text-ink-3">正在听……</p>}>
      <ApprenticeQuestions />
    </Suspense>
  );
}
