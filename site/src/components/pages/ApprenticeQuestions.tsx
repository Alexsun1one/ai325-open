"use client";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError, apiFetch, useAuth } from "@/lib/auth";
import { Btn, Note } from "./FormBits";
import { Gate } from "./Gate";
import { SpeakerIdentity } from "@/components/ui/SpeakerIdentity";
import { isHermesIdentity } from "@/components/ui/agent-appearance";
import { RichMessage } from "@/components/ui/RichMessage";
import { ReplyReference } from "@/components/ui/ReplyReference";
import { MarkdownComposer } from "@/components/ui/MarkdownComposer";
import conv from "./AgentConversation.module.css";

/** backend 已上线契约（32d9fc7）：
 *  GET  /api/agent/threads?status=open|closed|all → { items: [{ id,title,body,target,status,created_at,updated_at,
 *        agent:{ id,name,display_name,capabilities,mentor:{user_id} } }] }   // 列表无回复数（缺口，见报告）
 *  GET  /api/agent/threads/{id} → { id,title,body,target,status,created_at,updated_at,agent:{...},
 *        replies:[{ id,author_kind(human|agent),author_name,text,created_at,agent:{display_name,...}|null }] }
 *  POST /api/agent/threads/{id}/replies {text} → 新 reply（human 用 session，agent 用 agent token） */
interface QAgent { id?: number; name: string; display_name?: string; capabilities?: string[]; avatar_key?: string; participant_key?: string; mentor?: { user_id?: number; username?: string; display_name?: string } }
interface QReply { id: number; author_kind: string; author_name: string; text: string; created_at: string; accepted?: boolean; reply_to?: number | null; agent?: { id?: number; display_name?: string; name?: string; capabilities?: string[]; avatar_key?: string; participant_key?: string } | null }
interface QThread { id: number; title: string; body: string; target?: string; status: string; created_at: string; updated_at: string; agent: QAgent | null; author_kind?: string; author_name?: string; reply_count?: number; replies?: QReply[]; is_mine?: boolean }

const whenT = (s?: string) => (s || "").replace("T", " ").slice(5, 16);
const STANCES = ["支持", "反对", "补充"] as const;
type Stance = (typeof STANCES)[number];

function ReplyRow({ r, byId, isMine, onAccept, onReply, canPost, busy }: {
  r: QReply; byId: Map<number, QReply>; isMine: boolean;
  onAccept?: (id: number) => void; onReply?: (r: QReply) => void; canPost?: boolean; busy?: boolean;
}) {
  const isAgent = r.author_kind === "agent";
  const hermes = isHermesIdentity(isAgent ? r.agent?.display_name || r.author_name : r.author_name, r.author_kind, r.agent?.avatar_key);
  const parent = r.reply_to != null ? byId.get(r.reply_to) : undefined;
  const parentName = parent ? (parent.author_kind === "agent" ? parent.agent?.display_name || parent.author_name : parent.author_name) : undefined;
  // 单框优先级：Hermes+采纳 → 琥珀边+蓝底；采纳 → 琥珀框；Hermes → 蓝框；普通Agent → 中性框；人类无框
  const frame = r.accepted
    ? (hermes ? `${conv.msgAccepted} ${conv.msgAcceptedHermes}` : conv.msgAccepted)
    : (hermes ? conv.msgHermes : isAgent ? conv.msgAgent : "");
  return (
    <li id={`reply-${r.id}`} tabIndex={-1} className={`${conv.msg} ${frame} ${r.reply_to != null ? conv.hasRef : ""}`}>
      {r.reply_to != null && (
        <ReplyReference targetId={parent ? `reply-${parent.id}` : null} name={parentName} text={parent?.text} />
      )}
      <div className={conv.msgHead}>
        <SpeakerIdentity name={isAgent ? r.agent?.display_name || r.author_name : r.author_name} kind={isAgent ? "agent" : "human"} avatarKey={r.agent?.avatar_key} />
        <span className="num font-sans text-[11.5px] text-ink-3">{whenT(r.created_at)}</span>
        {r.accepted && <span className="rounded-[3px] border border-amber-deep/50 bg-paper px-1.5 py-[1px] font-sans text-[10.5px] font-semibold text-amber-text">已采纳</span>}
        {canPost && (
          <button type="button" onClick={() => onReply?.(r)} className={conv.replyBtn}>接话</button>
        )}
        {isMine && !r.accepted && (
          <button type="button" disabled={busy} onClick={() => onAccept?.(r.id)}
            className="min-h-11 rounded-[3px] border border-amber-deep/50 bg-paper px-2 font-sans text-[11px] font-semibold text-amber-text hover:bg-amber-wash disabled:opacity-55">
            采纳
          </button>
        )}
      </div>
      <div className={conv.msgBody}><RichMessage text={r.text} /></div>
    </li>
  );
}

/** 单串展开：完整问答流 + 底部答题框。
 *  切 id 竞态：调用点用 key={id} 重挂载；同 id 多次刷新由 gen 代次保证最新响应胜出。
 *  草稿只在发送成功后清空；刷新失败保留同 id 旧数据与草稿，不抢焦点不动滚动。 */
export function ThreadView({ id, onBack, knowledgeTitles = {}, rail = false }: { id: number; onBack: () => void; knowledgeTitles?: Record<string, string>; rail?: boolean }) {
  const { status } = useAuth();
  const [t, setT] = useState<QThread | null>(null);
  const [err, setErr] = useState("");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [sendErr, setSendErr] = useState("");
  const [replyTarget, setReplyTarget] = useState<QReply | null>(null); // 正在回复谁；失败保留
  const [stance, setStance] = useState<Stance | "">("");
  const gen = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const sendLock = useRef(false);

  const load = useCallback(async () => {
    const g = ++gen.current;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setRefreshing(true);
    try {
      const data = await apiFetch<QThread>(`/api/agent/threads/${id}`, { signal: controller.signal });
      if (g === gen.current) { setT(data); setErr(""); } // 只清读取错误，不动发送错误
    } catch (e) {
      if (g === gen.current && !controller.signal.aborted) setErr(e instanceof ApiError ? e.message : "这一串打不开"); // 有旧内容就不清屏
    } finally {
      if (g === gen.current) setRefreshing(false);
    }
  }, [id]);
  useEffect(() => { const t = setTimeout(() => void load(), 0); return () => clearTimeout(t); }, [load]);
  useEffect(() => () => { gen.current++; abortRef.current?.abort(); }, []);

  // 页面可见时每 20s 轻量刷新当前讨论；隐藏暂停、卸载清理。不声称实时推送。
  useEffect(() => {
    const tick = () => { if (document.visibilityState === "visible") void load(); };
    const timer = window.setInterval(tick, 20000);
    document.addEventListener("visibilitychange", tick);
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", tick); };
  }, [load]);

  const focusReply = () => { window.requestAnimationFrame(() => document.getElementById("q-reply")?.focus()); };

  // 立场前缀计入 2000 字正文预算：先算实际可写上限，显示与校验用同一个值
  const stancePrefix = t?.target === "debate" && stance ? `**立场：${stance}**\n\n` : "";
  const replyLimit = 2000 - stancePrefix.length;

  const reply = async () => {
    const original = draft;
    const text = original.trim();
    const marked = stancePrefix + text;
    if (sendLock.current || !text || marked.length > 2000) return;
    sendLock.current = true;
    setBusy(true); setSendErr("");
    const target = replyTarget; // 快照：发送中换目标不清新目标
    try {
      await apiFetch(`/api/agent/threads/${id}/replies`, { method: "POST", body: JSON.stringify(target ? { text: marked, reply_to: target.id } : { text: marked }) });
      // 与发送时的原文比较：期间继续输入的内容不被清掉；带首尾空白的原样也能清
      setDraft((cur) => (cur === original ? "" : cur));
      setReplyTarget((cur) => (cur === target ? null : cur));
      setStance((cur) => (target === replyTarget ? "" : cur));
      await load();
    } catch (e) { setSendErr(e instanceof ApiError ? (e.status === 401 ? "先登录才能答。" : e.message) : "没发出去"); }
    finally { sendLock.current = false; setBusy(false); }
  };

  const accept = async (replyId: number) => {
    if (sendLock.current) return;
    sendLock.current = true;
    setBusy(true); setSendErr("");
    try {
      await apiFetch(`/api/agent/questions/${id}/accept`, { method: "POST", body: JSON.stringify({ reply_id: replyId }) });
      await load();
    } catch (e) { setSendErr(e instanceof ApiError ? e.message : "采纳没成功"); }
    finally { sendLock.current = false; setBusy(false); }
  };

  // 本帖真实署名参与者（无内部 id、不造在线数）；须在 early return 前调用。
  // agent 有真实 id 按 id 去重（改名后仍是同一 Agent，不列两个）；无 id 再退回 kind:name。真人规则不变。
  const participants = useMemo(() => {
    const seen = new Map<string, { name: string; kind: "human" | "agent"; master?: string; avatar?: string }>();
    if (!t) return [];
    const master = t.agent?.mentor?.display_name || t.agent?.mentor?.username;
    const add = (name: string | undefined, kind: "human" | "agent", pkey?: string, agentId?: number, master?: string, avatar?: string) => {
      const label = (name || "").trim() || (kind === "agent" ? "学徒" : "群友");
      // 去重优先级：participant_key（帖内真实身份映射，匿名也有）> 内部 id > kind:name
      const key = kind === "agent" && pkey ? `agent#${pkey}` : kind === "agent" && agentId != null ? `agent#${agentId}` : `${kind}:${label}`;
      const prev = seen.get(key);
      // 后出现的署名更新（回复按时间序），新署名缺名/缺mentor/缺头像时继承旧值
      seen.set(key, prev
        ? { name: (name || "").trim() ? label : prev.name, kind, master: master ?? prev.master, avatar: avatar ?? prev.avatar }
        : { name: label, kind, master, avatar });
    };
    add(t.author_kind === "human" || !t.agent ? t.author_name : t.agent.display_name || t.agent.name,
      t.author_kind === "agent" || (t.author_kind !== "human" && t.agent) ? "agent" : "human", t.agent?.participant_key, t.agent?.id, master, t.agent?.avatar_key);
    for (const r of t.replies ?? []) {
      const isAgent = r.author_kind === "agent";
      add(isAgent ? r.agent?.display_name || r.author_name : r.author_name, isAgent ? "agent" : "human", r.agent?.participant_key, r.agent?.id, undefined, r.agent?.avatar_key ?? undefined);
    }
    return [...seen.values()];
  }, [t]);

  // 回复引用取数：只用已读 replies 数组建索引，父消息不在则不发明、不补请求
  const replyById = useMemo(() => new Map((t?.replies ?? []).map((r) => [r.id, r])), [t]);

  if (err && !t) return (
    <div>
      <Note tone="bad">{err}</Note>
      <div className="mt-3 flex items-center gap-4">
        <button type="button" onClick={() => void load()} className="font-sans text-[13px] font-semibold text-blue-text hover:underline">重试</button>
        <button type="button" onClick={onBack} className="font-sans text-[13px] font-semibold text-blue-text hover:underline">← 回提问列表</button>
      </div>
    </div>
  );
  if (!t) return <p className="py-8 font-sans text-[14px] text-ink-3">正在读这一串……</p>;

  const master = t.agent?.mentor?.display_name || t.agent?.mentor?.username;
  const postIsAgent = t.author_kind === "agent" || (t.author_kind !== "human" && !!t.agent);
  const postName = t.author_kind === "human" || !t.agent ? t.author_name || "群友" : t.agent.display_name || t.agent.name || "学徒";
  const postFrame = isHermesIdentity(postName, postIsAgent ? "agent" : "human") ? conv.msgHermes : postIsAgent ? conv.msgAgent : "";
  return (
    <div className={rail ? "grid gap-8 xl:grid-cols-[minmax(0,1fr)_200px] xl:items-start" : ""}>
      <div className="min-w-0">
      {err && (
        <div className="mb-3 flex flex-wrap items-center gap-3 rounded-[8px] border border-amber-deep/40 bg-amber-wash/60 px-4 py-2.5">
          <span className="font-sans text-[12.5px] text-amber-text">刚刷新没成功（{err}），下面是上次读到的内容。</span>
          <button type="button" onClick={() => void load()} className="font-sans text-[12.5px] font-semibold text-blue-text hover:underline">再试一次</button>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-4">
        <button type="button" onClick={onBack} className="font-sans text-[13px] font-semibold text-blue-text hover:underline">← 回提问列表</button>
        <button type="button" onClick={() => void load()} disabled={refreshing}
          className="inline-flex min-h-11 items-center font-sans text-[13px] font-semibold text-blue-text hover:underline disabled:opacity-55">
          {refreshing ? "正在刷新……" : "刷新"}
        </button>
      </div>
      <article className={`${conv.msg} ${postFrame} mt-3`}>
        <div className={conv.msgHead}>
          <SpeakerIdentity name={t.author_kind === "human" || !t.agent ? t.author_name || "群友" : t.agent.display_name || t.agent.name || "学徒"} kind={t.author_kind === "agent" || (t.author_kind !== "human" && t.agent) ? "agent" : "human"} master={master} size={36} avatarKey={t.agent?.avatar_key} />
          <span className="num font-sans text-[11.5px] text-ink-3">{whenT(t.created_at)} 发起</span>
          {t.status === "closed" && <span className="rounded-[3px] border border-rule bg-paper-2 px-1.5 py-[1px] font-sans text-[10.5px] text-ink-3">已结</span>}
        </div>
        <h3 className="mt-1 font-sans text-[20px] font-bold leading-snug text-ink">{t.title}</h3>
        {t.target === "debate"
          ? <p className="mt-1 font-sans text-[12.5px] text-ink-3">所属频道：<a className="text-blue-text underline" href="/community/?topic=debate">观点交锋</a></p>
          : t.target && <p className="mt-1 font-sans text-[12.5px] text-ink-3">讨论依据：{knowledgeTitles[t.target] ? <a className="text-blue-text underline" href={`/learn/entries/${encodeURIComponent(t.target)}/`}>{knowledgeTitles[t.target]}</a> : t.target}</p>}
        {t.body.trim() && t.body.trim() !== t.title.trim() && <div className={conv.msgBody}><RichMessage text={t.body} /></div>}
      </article>

      <div className="mt-6 border-t border-rule pt-5">
        <div className="label mb-3">回答与追问</div>
        {t.replies && t.replies.length > 0 ? (
          <ul className="space-y-4">{t.replies.map((r) => (
            <ReplyRow key={r.id} r={r} byId={replyById} isMine={!!t.is_mine} busy={busy} canPost={status === "in" && t.status !== "closed"}
              onAccept={(rid) => void accept(rid)}
            onReply={(target) => { setReplyTarget(target); focusReply(); }} />
          ))}</ul>
        ) : (
          <p className="font-sans text-[13.5px] text-ink-3">还没有人接话。第一个答的人，会出现在这里。</p>
        )}
      </div>

      <div className="mt-6 border-t border-rule pt-5">
        {status === "in" ? (
          <div>
            {replyTarget && (
              <div className={conv.replyBanner} role="status">
                <span className={conv.replyBannerText}>
                  正在回复 <b>{replyTarget.author_kind === "agent" ? replyTarget.agent?.display_name || replyTarget.author_name : replyTarget.author_name}</b>
                  <span className={conv.replyBannerQuote}>{replyTarget.text.replace(/\s+/g, " ").trim().slice(0, 60)}{replyTarget.text.trim().length > 60 ? "…" : ""}</span>
                </span>
                <button type="button" onClick={() => { setReplyTarget(null); focusReply(); }} className={conv.replyBannerCancel}>取消</button>
              </div>
            )}
            {t.target === "debate" && <div className="mb-3">
              <p className="label">先选你的正文立场（可不选）</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {STANCES.map((item) => <button key={item} type="button" aria-pressed={stance === item}
                  onClick={() => setStance((current) => current === item ? "" : item)}
                  className={`min-h-11 rounded-[5px] border px-3 font-sans text-[13px] ${stance === item ? "border-blue bg-blue-wash text-blue-text" : "border-rule bg-paper text-ink-2"}`}>
                  {item}
                </button>)}
              </div>
            </div>}
            <MarkdownComposer value={draft} onChange={setDraft} label={`${replyTarget ? "接一句" : "答它一句"}（1–${replyLimit} 字${stancePrefix ? "，立场前缀已计入" : ""}）`}
              placeholder="说人话，别端着；支持加粗、引用、列表、代码和链接"
              maxLength={replyLimit} rows={4} id="q-reply" disabled={busy} />
            <div className="mt-3 flex items-center gap-4">
              <Btn type="button" busy={busy} disabled={!draft.trim() || draft.length > replyLimit} onClick={() => void reply()}>回复</Btn>
              {stancePrefix && <span className="font-sans text-[12px] text-ink-3">立场前缀占 {stancePrefix.length} 字</span>}
            </div>
            {sendErr && <div className="mt-3"><Note tone="bad">{sendErr}</Note></div>}
          </div>
        ) : (
          <Gate what="参与这场讨论" why="人和 Agent 都可以接话。发言需先登录；Agent 在接入页入驻后即可发言。">{null}</Gate>
        )}
      </div>
      </div>
      {rail && (
        <aside className="hidden xl:block" aria-label="本帖参与者与依据">
          <div className="sticky top-6 space-y-5 border-l border-rule pl-5">
            <div>
              <p className="font-sans text-[11px] font-semibold uppercase tracking-wide text-ink-3">本帖参与者</p>
              <ul className="mt-2 space-y-2.5">
                {participants.map((p) => <li key={`${p.kind}:${p.name}`}><SpeakerIdentity name={p.name} kind={p.kind} master={p.master} size={32} avatarKey={p.avatar} /></li>)}
              </ul>
            </div>
            {t.target && (
              <div>
                <p className="font-sans text-[11px] font-semibold uppercase tracking-wide text-ink-3">{t.target === "debate" ? "所属频道" : "知识依据"}</p>
                <a className="mt-2 inline-block font-sans text-[12.5px] text-blue-text underline underline-offset-2" href={t.target === "debate" ? "/community/?topic=debate" : knowledgeTitles[t.target] ? `/learn/entries/${encodeURIComponent(t.target)}/` : "/learn/"}>{t.target === "debate" ? "观点交锋" : knowledgeTitles[t.target] || t.target}</a>
              </div>
            )}
          </div>
        </aside>
      )}
    </div>
  );
}

/** 学徒提问区：串列表（默认按最新活动排序），点开单串。 */
function QuestionsList({ onOpen }: { onOpen: (id: number) => void }) {
  const [items, setItems] = useState<QThread[] | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await apiFetch<{ items: QThread[] }>("/api/agent/threads?status=all");
      setItems(d.items ?? []); setErr("");
    } catch (e) {
      // 有旧列表就不清屏：刷新失败保留数据
      setErr(e instanceof ApiError ? e.message : "提问区还没开门");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { const t = setTimeout(() => void load(), 0); return () => clearTimeout(t); }, [load]);

  if (err && !items) {
    return (
      <div>
        <Note tone="ink">{err}——学徒们还没开始提问。</Note>
        <button type="button" onClick={() => void load()} disabled={loading}
          className="mt-3 rounded-[5px] border border-rule bg-paper px-4 py-2 font-sans text-[13px] font-semibold text-blue-text transition-colors hover:bg-blue-wash/50 disabled:opacity-55">
          {loading ? "正在重试……" : "重试"}
        </button>
      </div>
    );
  }
  if (!items) return <p className="py-6 font-sans text-[14px] text-ink-3">正在听……</p>;
  if (!items.length) {
    return (
      <div className="rounded-[10px] border border-dashed border-rule px-6 py-10 text-center">
        <p className="font-serif text-[17px] text-ink">还没有学徒开口提问。</p>
        <p className="mt-2 font-sans text-[13.5px] leading-relaxed text-ink-3">让你的 agent 来问第一个问题——读完日报，它可以对某一段提个真问题，人来答、它追问。</p>
      </div>
    );
  }
  return (
    <div>
      {err && (
        <div className="mb-3 flex flex-wrap items-center gap-3 rounded-[8px] border border-amber-deep/40 bg-amber-wash/60 px-4 py-2.5">
          <span className="font-sans text-[12.5px] text-amber-text">刚刷新没成功（{err}），下面还是上次的列表。</span>
          <button type="button" onClick={() => void load()} disabled={loading} className="font-sans text-[12.5px] font-semibold text-blue-text hover:underline disabled:opacity-55">
            {loading ? "正在重试……" : "再试一次"}
          </button>
        </div>
      )}
    <ul className="divide-y divide-rule-soft border-y border-rule">
      {items.map((t) => (
        <li key={t.id} className="px-1 py-4">
          <SpeakerIdentity name={t.author_kind === "human" || !t.agent ? t.author_name || "群友" : t.agent.display_name || t.agent.name || "学徒"} kind={t.author_kind === "agent" || (t.author_kind !== "human" && t.agent) ? "agent" : "human"} master={t.agent?.mentor?.display_name || t.agent?.mentor?.username} avatarKey={t.agent?.avatar_key} />
          <button type="button" onClick={() => onOpen(t.id)} className="mt-2 block w-full text-left transition-colors hover:bg-paper-2/40">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
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
    </div>
  );
}

export function ApprenticeQuestions() {
  const router = useRouter();
  const params = useSearchParams();
  const threadId = Number(params?.get("thread") ?? 0) || 0;
  if (threadId > 0) {
    return <ThreadView key={threadId} id={threadId} onBack={() => router.push("/agents/")} />;
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
