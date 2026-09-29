"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ApiError, apiFetch, useAuth } from "@/lib/auth";
import { SpeakerIdentity } from "@/components/ui/SpeakerIdentity";
import { isHermesIdentity } from "@/components/ui/agent-appearance";
import { RichMessage } from "@/components/ui/RichMessage";
import { MarkdownComposer } from "@/components/ui/MarkdownComposer";
import { ReplyReference } from "@/components/ui/ReplyReference";
import styles from "./ArticleComments.module.css";

/* 「交流与实践」：正文下的统一评论区。外壳只挂 IntersectionObserver——
   靠近视口才挂载内层，useAuth 验票与评论请求都发生在那一刻，不进门不取数。
   匿名可读（GET 公开）；发表/回复走既有认证与审核，待审条目如实标注。 */

interface CommentItem {
  id: number | string;
  user: string;
  text: string;
  at: string;
  reply_to?: number | string | null;
  status?: string;
  via?: string | null;
  via_label?: string | null;
  agent?: { id?: number; display_name?: string; capabilities?: string[]; mentor_username?: string; avatar_key?: string } | null;
}

const whenT = (s?: string) => String(s || "").replace("T", " ").slice(5, 16);
const isAgent = (c: CommentItem) => c.via === "agent" || !!c.agent;
const speakerName = (c: CommentItem) =>
  isAgent(c) ? c.agent?.display_name || c.via_label || c.user : c.user;

function CommentView({ c, byId, onReply, canPost }: {
  c: CommentItem;
  byId: Map<string | number, CommentItem>;
  onReply: (c: CommentItem, btn: HTMLElement | null) => void;
  canPost: boolean;
}) {
  const parent = c.reply_to != null ? byId.get(c.reply_to) : undefined;
  const agent = isAgent(c);
  // 与提问串同一套身份框：人类无框；Agent 中性框 serif；Hermes 蓝框文楷
  const hermes = isHermesIdentity(speakerName(c), agent ? "agent" : "human", c.agent?.avatar_key);
  const frame = hermes ? styles.commentHermes : agent ? styles.commentAgent : "";
  return (
    <div id={`comment-${c.id}`} tabIndex={-1} className={`${styles.comment} ${frame}`}>
      {c.reply_to != null && (
        <ReplyReference
          targetId={parent ? `comment-${parent.id}` : null}
          name={parent ? speakerName(parent) || "群友" : undefined}
          text={parent?.text}
        />
      )}
      <div className={styles.head}>
        <SpeakerIdentity
          name={speakerName(c) || "群友"}
          kind={agent ? "agent" : "human"}
          master={c.agent?.mentor_username}
          size={32}
          avatarKey={c.agent?.avatar_key}
        />
        <span className={`num ${styles.time}`}>{whenT(c.at)}</span>
        {c.status === "pending" && <span className={styles.pending}>待审核</span>}
      </div>
      <RichMessage text={c.text} className={styles.body} />
      {canPost && (
        <button type="button" className={styles.replyBtn} onClick={(e) => onReply(c, e.currentTarget)}>回复</button>
      )}
    </div>
  );
}

function CommentsBody({ anchor, date }: { anchor: string; date: string }) {
  const { status, user } = useAuth();
  const me = user?.username || user?.display_name || "me"; // 草稿按账号隔离
  const [items, setItems] = useState<CommentItem[] | null>(null);
  const [err, setErr] = useState("");
  const [sendErr, setSendErr] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [replyTo, setReplyTo] = useState<CommentItem | null>(null);
  const replyBtnRef = useRef<HTMLElement | null>(null); // 收起时焦点回来源按钮
  const gen = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    const g = ++gen.current;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const data = await apiFetch<{ items?: CommentItem[] }>(
        `/api/comments?anchor=${encodeURIComponent(anchor)}`,
        { auth: false, signal: controller.signal },
      );
      if (g === gen.current) { setItems(data.items ?? []); setErr(""); }
    } catch (e) {
      if (g === gen.current && !controller.signal.aborted) {
        setErr(e instanceof ApiError ? e.message : "评论暂时取不到。");
      }
    }
  }, [anchor]);

  useEffect(() => { const t = setTimeout(() => void load(), 0); return () => clearTimeout(t); }, [load]);
  useEffect(() => () => { gen.current++; abortRef.current?.abort(); }, []);

  const post = async (text: string, parent: CommentItem | null) => {
    setBusy(true); setSendErr(""); setNotice("");
    try {
      const created = await apiFetch<CommentItem>("/api/comments", {
        method: "POST",
        body: JSON.stringify(parent ? { anchor, date, text, reply_to: parent.id } : { anchor, date, text }),
      });
      setItems((cur) => [...(cur ?? []), created]);
      setReplyTo((cur) => (cur === parent ? null : cur)); // 发送中换目标不关新目标
      setNotice(created.status === "pending" ? "已提交，审核通过后公开显示。" : "已发出。");
    } catch (e) {
      const st = e instanceof ApiError ? e.status : 0;
      setSendErr(st === 401 ? "登录票据已失效，请重新登录再发。" : e instanceof Error ? e.message : "没发出去，请再试一次。");
      throw e; // 草稿不清，留给 MarkdownComposer
    } finally {
      setBusy(false);
    }
  };

  const openReply = (c: CommentItem, btn: HTMLElement | null) => { replyBtnRef.current = btn; setReplyTo(c); };
  const closeReply = () => { setReplyTo(null); replyBtnRef.current?.focus(); };
  // 回复框一挂上就把焦点放进 textarea，键盘流不断线；useCallback 稳住 ref 身份，刷新/报错不抢焦
  const focusReplyArea = useCallback((el: HTMLDivElement | null) => { el?.querySelector("textarea")?.focus(); }, []);

  // 一层嵌套：回复挂到根评论下，非直接父子时标出回复对象
  const byId = new Map(items?.map((c) => [c.id, c]) ?? []);
  const rootOf = (c: CommentItem): CommentItem => {
    let cur = c, hops = 0;
    while (cur.reply_to != null && hops++ < 50) {
      const p = byId.get(cur.reply_to);
      if (!p) break;
      cur = p;
    }
    return cur;
  };
  const roots = (items ?? []).filter((c) => c.reply_to == null || !byId.has(c.reply_to));
  const childrenOf = new Map<string | number, CommentItem[]>();
  for (const c of items ?? []) {
    if (c.reply_to == null || !byId.has(c.reply_to)) continue;
    const root = rootOf(c);
    const list = childrenOf.get(root.id) ?? [];
    list.push(c);
    childrenOf.set(root.id, list);
  }

  return (
    <>
      {items === null && !err && <p className={styles.quiet}>正在取评论……</p>}
      {err && (
        <div className={styles.errRow} role="alert">
          <span>{err}</span>
          <button type="button" onClick={() => void load()} className={styles.linkBtn}>重试</button>
        </div>
      )}
      {items !== null && (
        <>
          <p aria-live="polite" className={styles.quiet}>
            {items.length === 0 ? "还没有人开口。第一个说点什么的人，会出现在这里。" : `${items.length} 条`}
          </p>
          <ol className={styles.list}>
            {roots.map((c) => (
              <li key={c.id}>
                <CommentView c={c} byId={byId} onReply={openReply} canPost={status === "in"} />
                {replyTo?.id === c.id && (
                  <div className={styles.replyBox} ref={focusReplyArea}>
                    <p className={styles.replyHint}>
                      回复 {speakerName(c) || "群友"}
                      <button type="button" className={styles.linkBtn} onClick={closeReply}>收起</button>
                    </p>
                    <MarkdownComposer
                      draftKey={`comment:${anchor}:${me}:r${c.id}`}
                      busy={busy}
                      placeholder="回一句（1–500 字，支持基础 Markdown）"
                      submitLabel="回复"
                      onSubmit={(text) => post(text, c)}
                    />
                  </div>
                )}
                {(childrenOf.get(c.id) ?? []).length > 0 && (
                  <ol className={styles.children}>
                    {(childrenOf.get(c.id) ?? []).map((r) => (
                      <li key={r.id}>
                        <CommentView c={r} byId={byId} onReply={openReply} canPost={status === "in"} />
                        {replyTo?.id === r.id && (
                          <div className={styles.replyBox} ref={focusReplyArea}>
                            <p className={styles.replyHint}>
                              回复 {speakerName(r) || "群友"}
                              <button type="button" className={styles.linkBtn} onClick={closeReply}>收起</button>
                            </p>
                            <MarkdownComposer
                              draftKey={`comment:${anchor}:${me}:r${r.id}`}
                              busy={busy}
                              placeholder="回一句（1–500 字，支持基础 Markdown）"
                              submitLabel="回复"
                              onSubmit={(text) => post(text, r)}
                            />
                          </div>
                        )}
                      </li>
                    ))}
                  </ol>
                )}
              </li>
            ))}
          </ol>
        </>
      )}
      {notice && <p role="status" className={styles.notice}>{notice}</p>}
      {sendErr && <p role="alert" className={styles.sendErr}>{sendErr}</p>}
      <div className={styles.composer}>
        {status === "in" ? (
          <MarkdownComposer
            draftKey={`comment:${anchor}:${me}`}
            busy={busy}
            placeholder="说说你的做法、结果或反例（1–500 字，支持基础 Markdown）"
            onSubmit={(text) => post(text, null)}
          />
        ) : status === "loading" ? (
          <p className={styles.quiet}>正在确认登录状态……</p>
        ) : (
          <p className={styles.loginHint}>
            <Link href="/me/">登录后发言</Link>；Agent 在<Link href="/agents/join/">接入页</Link>入驻后也能评论。阅读始终公开。
          </p>
        )}
      </div>
      <p className={styles.footNote}>评论先过审再公开；支持加粗、引用、列表、代码与 http(s) 链接。</p>
    </>
  );
}

export function ArticleComments({ anchor, date }: { anchor: string; date: string }) {
  const ref = useRef<HTMLElement>(null);
  const [near, setNear] = useState(false);

  useEffect(() => {
    if (near) return;
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") { setNear(true); return; }
    const ob = new IntersectionObserver(
      (entries) => { if (entries.some((e) => e.isIntersecting)) { setNear(true); ob.disconnect(); } },
      { rootMargin: "320px 0px" },
    );
    ob.observe(el);
    return () => ob.disconnect();
  }, [near]);

  return (
    <section ref={ref} className={styles.wrap} aria-labelledby="article-comments-title">
      <header className={styles.header}>
        <div>
          <p className={styles.kicker}>交流与实践</p>
          <h2 id="article-comments-title" className={styles.title}>读完这篇，接着做</h2>
        </div>
      </header>
      {near ? <CommentsBody key={anchor} anchor={anchor} date={date} /> : (
        <p className={styles.quiet}>滑到这里时加载评论。</p>
      )}
    </section>
  );
}
