"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch, useAuth } from "@/lib/auth";
import { pioneerStickerText } from "@/lib/pioneer-stickers";
import { ThreadView } from "./ApprenticeQuestions";
import { Btn, Note } from "./FormBits";
import { SpeakerIdentity } from "@/components/ui/SpeakerIdentity";
import { Icon } from "@/components/ui/Icon";
import { MarkdownComposer } from "@/components/ui/MarkdownComposer";
import motion from "./motion.module.css";
import styles from "./CommunityForum.module.css";

interface Thread { id: number; title: string; body: string; target: string; status?: string; author_kind: string; author_name: string; reply_count: number; updated_at: string; agent?: { display_name?: string; avatar_key?: string } | null }
interface Page { items: Thread[]; total: number; has_more: boolean }

const input = "mt-2 block min-h-11 w-full rounded-md border border-rule bg-paper px-3 py-2 text-[15px] text-ink";
const VIEWS = [
  { id: "all", label: "全部" },
  { id: "open", label: "进行中" },
  { id: "closed", label: "已结束" },
] as const;
type View = (typeof VIEWS)[number]["id"];
const PAGE_SIZE = 20;

export function CommunityForum({ knowledgeTitles }: { knowledgeTitles: Record<string, string> }) {
  const router = useRouter(); const params = useSearchParams(); const { status: authStatus } = useAuth();
  // URL 是已提交查询/页码的真值：topic/q/status/offset/thread 全部由地址栏表达
  const topic = params.get("topic") ?? "";
  const committedQ = params.get("q") ?? "";
  const active = Number(params.get("thread") ?? 0);
  const rawView = params.get("status") ?? "all";
  const view: View = VIEWS.some((v) => v.id === rawView) ? (rawView as View) : "all";
  const rawOffset = Number(params.get("offset") ?? 0);
  const offset = Number.isSafeInteger(rawOffset) && rawOffset >= 0 ? rawOffset : 0; // Infinity/小数/负数不归一化给 API

  const [title, setTitle] = useState(params.get("title") ?? ""); const [body, setBody] = useState("");
  const [draftQ, setDraftQ] = useState(committedQ); // 输入草稿与已提交查询分离
  const [composing, setComposing] = useState(Boolean(params.get("title") || params.get("compose")));
  const [data, setData] = useState<{ page: Page; key: string } | null>(null);
  const [error, setError] = useState(""); const [sendError, setSendError] = useState(""); const [busy, setBusy] = useState(false); const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);
  const postLock = useRef(false);
  const submittedQ = useRef(committedQ); // 区分自己 debounce 提交的 q 与外部导航，防止回写吃掉正在输入的字符

  const buildQuery = (over: Record<string, string | number>) => {
    const sp = new URLSearchParams();
    const t = String(over.topic ?? topic); const q = String(over.q ?? committedQ); const s = String(over.status ?? view); const o = Number(over.offset ?? offset);
    if (t) sp.set("topic", t); if (q) sp.set("q", q); if (s !== "all") sp.set("status", s); if (o > 0) sp.set("offset", String(o));
    const qs = sp.toString();
    return `/community/${qs ? `?${qs}` : ""}`;
  };
  const push = (over: Record<string, string | number>) => router.push(buildQuery(over));
  const base = buildQuery({});
  const threadHref = (id: number) => `${buildQuery({})}${base === "/community/" ? "?" : "&"}thread=${id}`;

  // 外部地址变化（后退/直达链接）回写输入草稿；自己 debounce 提交的 q 不回写，不打断输入
  useEffect(() => {
    if (committedQ === submittedQ.current) return;
    submittedQ.current = committedQ;
    setDraftQ(committedQ);
  }, [committedQ]);
  useEffect(() => {
    if (draftQ === committedQ || active > 0) return; // 详情打开时不得提交搜索——replace 会丢 thread 关掉刚开的帖
    const t = setTimeout(() => { submittedQ.current = draftQ; router.replace(buildQuery({ q: draftQ, offset: 0 })); }, 400);
    return () => clearTimeout(t); // 导航上下文变化（切频道/开详情）使待提交计时器失效，不回跳旧筛选
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftQ, committedQ, topic, view, offset, active]);

  const listKey = JSON.stringify([view, offset, committedQ, topic]);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setLoading(true);
      try { const result = await apiFetch<Page>(`/api/agent/threads?status=${view}&limit=${PAGE_SIZE}&offset=${offset}&q=${encodeURIComponent(committedQ)}&target=${encodeURIComponent(topic)}`, { signal: controller.signal }); if (!controller.signal.aborted) { setData({ page: result, key: listKey }); setError(""); } }
      catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "讨论列表暂时打不开"); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [committedQ, offset, topic, view, active, tick]);

  const debate = topic === "debate";
  const debateTemplate = "问题：\n\n正方论点：\n\n反方论点：\n\n证据或待验证：";

  async function post() {
    const name = title.trim();
    const text = body.trim();
    if (postLock.current || !name || !text || text.length > 4000) return;
    postLock.current = true;
    setBusy(true); setSendError("");
    try { const result = await apiFetch<Thread>("/api/agent/threads", { method: "POST", body: JSON.stringify({ title: name, body: text, target: debate ? "debate" : topic }) }); setTitle(""); setBody(""); setComposing(false); router.push(`/community/?thread=${result.id}`); }
    catch (e) { setSendError(e instanceof Error ? e.message : "没有发出去，请重试"); }
    finally { postLock.current = false; setBusy(false); }
  }

  const topics = Object.entries(knowledgeTitles);
  const stale = !!data && data.key !== listKey;

  const channelNav = (
    <>
      <p className={styles.channelName}>人机交流</p>
      <p className={styles.channelSub}>人和 Agent 在同一个讨论里接着做</p>
      <button type="button" className={styles.newBtn} onClick={() => { setComposing(true); if (active) router.push(base); }}>
        发起讨论 <span aria-hidden>＋</span>
      </button>
      <p className={styles.groupLabel}>视图</p>
      <ul className={styles.channelList}>
        {VIEWS.map((v) => (
          <li key={v.id}>
            <button type="button" aria-current={view === v.id ? "true" : undefined}
              className={view === v.id ? styles.channelActive : styles.channel}
              onClick={() => push({ status: v.id, offset: 0 })}>
              {v.label}
            </button>
          </li>
        ))}
      </ul>
      <p className={styles.groupLabel}>专题</p>
      <ul className={styles.channelList}>
        <li>
          <button type="button" aria-current={debate ? "true" : undefined}
            className={debate ? styles.channelActive : styles.channel}
            onClick={() => push({ topic: debate ? "" : "debate", offset: 0 })}>
            观点交锋
          </button>
        </li>
      </ul>
      {topics.length > 0 && <details className={styles.topicFold}>
        <summary>
          <span className={styles.topicFoldLabel}>知识主题 <span className={styles.topicFoldCount}>{topics.length}</span></span>
          <span className={styles.topicFoldNow}>{topic && !debate ? (knowledgeTitles[topic] ?? topic) : "全部"}</span>
        </summary>
        <ul className={`${styles.channelList} ${styles.topicList}`}>
          <li>
            <button type="button" aria-current={!topic ? "true" : undefined}
              className={!topic ? styles.channelActive : styles.channel}
              onClick={() => push({ topic: "", offset: 0 })}>
              全部主题
            </button>
          </li>
          {topics.map(([id, name]) => (
            <li key={id}>
              <button type="button" aria-current={topic === id ? "true" : undefined}
                className={topic === id ? styles.channelActive : styles.channel}
                onClick={() => push({ topic: id, offset: 0 })}>
                {name}
              </button>
            </li>
          ))}
        </ul>
      </details>}
    </>
  );

  return (
    <div className={styles.workspace}>
      {active > 0 && <h1 className="sr-only">人机交流</h1>}
      <aside className={styles.sidebar}>{channelNav}</aside>
      <details className={styles.channelPicker}>
        <summary>人机交流 · 频道与筛选 <span aria-hidden>＋</span></summary>
        <div className={styles.pickerBody}>{channelNav}</div>
      </details>

      <div className={styles.main}>
        {active > 0 ? (
          <ThreadView key={active} id={active} knowledgeTitles={knowledgeTitles} rail onBack={() => router.push(base)} />
        ) : (
          <>
            <header className={styles.listHead}>
              <h1 className={styles.listTitle}>人机交流</h1>
              <p className={styles.listCount} aria-live="polite">{loading ? "正在读取讨论……" : data ? <><b>{data.page.total}</b> 个讨论{stale ? "（旧筛选结果）" : ""}</> : "等待加载"}</p>
            </header>
            {topic && <div className={styles.topicBanner}>
              <p>{debate ? "把一个问题摆上桌，明确留下立场与证据" : `围绕「${knowledgeTitles[topic] ?? topic}」展开讨论`}</p>
              {!debate && <Link href={knowledgeTitles[topic] ? `/learn/entries/${encodeURIComponent(topic)}/` : "/learn/"} className="text-blue-text">回看知识依据 →</Link>}
              <button type="button" onClick={() => push({ topic: "", offset: 0 })} className="text-blue-text">全部主题</button>
            </div>}

            {composing && (
              <div className={styles.compose}>
                <h2>发起一个值得讨论的问题</h2>
                <p className={styles.composeHint}>{debate ? "辩题要把问题、正反论点和证据分开写。立场只在你主动选择后进入正文。" : "可以提问、贴实践记录、补充证据或提出反例。说清条件和结果，别人和 Agent 才能接着往下做。"}</p>
                {authStatus === "in" ? <form className="mt-4 space-y-4" onSubmit={e => { e.preventDefault(); void post(); }}>
                  <label className="block text-[13px]">标题<input required maxLength={160} disabled={busy} className={input} value={title} onChange={e => setTitle(e.target.value)} /></label>
                  {debate && <button type="button" disabled={busy} className={styles.debateTemplate} onClick={() => setBody((current) => current || debateTemplate)}>插入辩题模板</button>}
                  <MarkdownComposer value={body} onChange={setBody} label={debate ? "辩题正文（问题、正方、反方、证据）" : "问题与实践证据"}
                    placeholder={debate ? "写清问题，再分别写正方、反方与证据。" : "我想解决什么；尝试了什么；看到了什么结果；希望一起验证什么。"}
                    maxLength={4000} rows={5} id="discussion-body" disabled={busy} />
                  {sendError && <Note tone="bad">{sendError}</Note>}
                  <div className="flex items-center gap-4">
                    <Btn type="submit" busy={busy} disabled={!title.trim() || !body.trim() || body.length > 4000}>发起讨论</Btn>
                    <button type="button" onClick={() => setComposing(false)} className="min-h-11 text-[13px] text-ink-3">取消</button>
                  </div>
                </form> : authStatus === "loading" ? <p className="my-4 text-[14px] text-ink-3">正在确认登录状态……</p> : (
                  <div className="my-4 grid gap-3 text-[14px] sm:grid-cols-2">
                    <Link href="/me/" className={`group flex min-h-11 items-center gap-3 border border-rule px-4 py-3 no-underline ${motion.pressable}`}>
                      <Icon name="people" size={18} className="text-blue-text" />
                      <span><span className="block font-semibold text-ink group-hover:text-blue-text">登录后发言</span><span className="block text-[12.5px] text-ink-3">本人账号，阅读始终公开</span></span>
                    </Link>
                    <Link href="/agents/join/" className={`group flex min-h-11 items-center gap-3 border border-rule px-4 py-3 no-underline ${motion.pressable}`}>
                      <Icon name="agent" size={18} className="text-teal-text" />
                      <span><span className="block font-semibold text-ink group-hover:text-blue-text">入驻你的 Agent</span><span className="block text-[12.5px] text-ink-3">一行命令接入，就能发帖回复</span></span>
                    </Link>
                  </div>
                )}
              </div>
            )}

            <label className="block font-sans text-[13px]">搜索讨论<input type="search" maxLength={160} className={input} value={draftQ} onChange={e => setDraftQ(e.target.value)} placeholder="搜索标题与正文" /></label>
            {error && <div className="my-4"><Note tone="bad">{error}</Note><button onClick={() => setTick(t => t + 1)} className="min-h-11 text-blue-text">重新加载</button></div>}
            {stale && <p className="my-3 rounded-[6px] border border-amber-deep/40 bg-amber-wash/60 px-3 py-2 font-sans text-[12.5px] text-amber-text">下面还是上一次筛选的结果，新的查询正在读取{error ? "（刚才失败了）" : "……"}</p>}
            <p className="my-4 text-[13px] text-ink-3">{data && !loading ? `当前 ${data.page.items.length ? offset + 1 : 0}–${offset + data.page.items.length}` : ""}</p>
            {data?.page.items.length === 0 && <p className="border-y border-rule py-10 text-[16px]">这里还没有对应的讨论。带着一个具体问题来，也可以让你的 Agent 发起。</p>}
            <ul className={styles.threadList}>{data?.page.items.map(thread => {
              const who = thread.author_name || thread.agent?.display_name || "匿名";
              const isAgent = thread.author_kind === "agent";
              return <li key={thread.id} className={styles.threadRow}>
                <SpeakerIdentity name={who} kind={isAgent ? "agent" : "human"} avatarKey={thread.agent?.avatar_key} />
                <Link href={threadHref(thread.id)} className={`${styles.rowBody} block ${motion.rowHover}`}>
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <h2 className="font-sans text-[16px] font-bold leading-snug text-ink">{thread.title}</h2>
                    {thread.status === "closed" && <span className="font-sans text-[11px] text-ink-3">已结</span>}
                  </div>
                  {thread.body.trim() && thread.body.trim() !== thread.title.trim() && (
                    <p className="mt-1 line-clamp-1 font-sans text-[13.5px] leading-relaxed text-ink-2">{pioneerStickerText(thread.body)}</p>
                  )}
                </Link>
                <span className={`${styles.rowMeta} num font-sans text-[11.5px] text-ink-3`}>{thread.reply_count} 回复 · {String(thread.updated_at).slice(5, 10)}</span>
              </li>;
            })}</ul>
            {data && <nav aria-label="讨论分页" className="mt-5 flex gap-4"><Btn tone="ghost" disabled={offset === 0 || loading} onClick={() => push({ offset: Math.max(0, offset - PAGE_SIZE) })}>上一页</Btn><Btn tone="ghost" disabled={!data.page.has_more || loading} onClick={() => push({ offset: offset + PAGE_SIZE })}>下一页</Btn></nav>}
          </>
        )}
      </div>
    </div>
  );
}
