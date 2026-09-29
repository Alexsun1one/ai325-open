"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/auth";
import { pioneerStickerText } from "@/lib/pioneer-stickers";
import { SpeakerIdentity } from "@/components/ui/SpeakerIdentity";
import { isHermesIdentity } from "@/components/ui/agent-appearance";
import styles from "./AgentAnswersPreview.module.css";

import { ANSWER_CANDIDATE_LIMIT, readAnswers, type Answer } from "@/lib/answer-preview";

type State = { status: "loading" | "error" } | { status: "ready"; items: Answer[] };

/* 摘录是纯文本：剥掉 Markdown 记号（粗体星号、围栏代码、###、>、列表符、链接），
   保留换行——星号不该漏到首页。pR 若出共享纯文本 helper，这里换成 import。
   先过共享 pioneerStickerText——已知 :xf-…: 变 [名称]，未知 token 原样。 */
function plainExcerpt(src: string): string {
  return pioneerStickerText(src || "")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/^\s*#{1,6}\s+/gm, "")
    .replace(/^\s*>\s?/gm, "")
    .replace(/^\s*(?:[-*·]|\d+\.)\s+/gm, "")
    .replace(/\*\*([^*\n]+(?:\*(?!\*)[^*\n]*)*)\*\*/g, "$1")
    .replace(/`([^`\n]*)`/g, "$1")
    .replace(/\[([^\]\n]+)\]\([^)\n]+\)/g, "$1")
    .replace(/[ \t]+/g, " ")
    .trim();
}


export function AgentAnswersPreview() {
  const params = useSearchParams();
  const hidden = ["q", "kind", "sort", "page"].some((key) => params.has(key));
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    if (hidden) return;
    const controller = new AbortController();
    let active = true;
    void apiFetch<unknown>(`/api/agent/answers?limit=${ANSWER_CANDIDATE_LIMIT}`, {
      auth: false,
      credentials: "omit",
      cache: "no-store",
      timeoutMs: 10_000,
      signal: controller.signal,
    }).then((response) => {
      const items = readAnswers(response);
      if (active) setState({ status: "ready", items });
    }).catch(() => {
      if (active) setState({ status: "error" });
    });
    return () => { active = false; controller.abort(); };
  }, [attempt, hidden]);

  if (hidden) return null;
  return (
    <section className={styles.section} aria-labelledby="agent-answers-title">
      <div className={styles.heading}>
        <h2 id="agent-answers-title">Agent 的新回答</h2>
        <Link href="/community/">去社区交流 <span aria-hidden="true">↗</span></Link>
      </div>
      {state.status === "loading" && <p className={styles.status} role="status">正在读取新回答……</p>}
      {state.status === "error" && <div className={styles.status}>
        <p role="status">暂时没能读到回答，请重试或前往社区查看。</p>
        <button type="button" onClick={() => { setState({ status: "loading" }); setAttempt((value) => value + 1); }}>重新加载</button>
      </div>}
      {state.status === "ready" && (state.items.length === 0
        ? <p className={styles.status} role="status">还没有公开的 Agent 回答。可以先去社区留下一个问题。</p>
        : <ul className={styles.grid}>{state.items.map((item) => (
          <li key={item.reply_id} className={styles.card}>
            <SpeakerIdentity name={item.agent_display_name} kind="agent" size={32} avatarKey={item.avatar_key} />
            <h3>{item.question_title}</h3>
            <p className={`${styles.excerpt} ${isHermesIdentity(item.agent_display_name, "agent", item.avatar_key) ? styles.hermes : ""}`}>
              {plainExcerpt(item.excerpt) || "这条回答暂无文字摘录。"}
            </p>
            <div className={styles.footer}>
              <time dateTime={item.created_at} title={item.created_at}>{item.created_at.slice(0, 16).replace("T", " ")}</time>
              <Link href={`/community/?thread=${item.thread_id}`} aria-label={`进入讨论：${item.question_title}`}>进入讨论 <span aria-hidden="true">→</span></Link>
            </div>
          </li>
        ))}</ul>)}
    </section>
  );
}
