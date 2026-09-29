"use client";
/* 公开互动行（CONTENT-ENGAGEMENT R1）：阅读/赞/评论计数 + 点赞 + 分享复制。
 * 公共 GET 匿名可读；「阅读」按服务端 visible_ms 可见停留后记一次、
 * 每浏览器每北京日去重（localStorage 不可写则不记，避免重刷变新 ID）；
 * 点赞仅真人 session，busyRef 同步锁；0/5xx 锁内重取真值不装成功；
 * open 式 POST 响应只合 views，不盖在途点赞；账号:条目 key remount。 */
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, useAuth } from "@/lib/auth";
import { engagementApi, shanghaiDay, visitorId, type EngagementKind, type PublicStats } from "@/lib/content-engagement";
import { Icon } from "@/components/ui/Icon";
import styles from "./ContentEngagement.module.css";

export function ContentEngagement(props: { kind: EngagementKind; resourceId: string; commentHref?: string }) {
  const { status, user } = useAuth();
  if (status === "loading") return <div className={styles.bar} aria-hidden="true" />;
  // key=账号:条目：换账号/换条目整棵重挂载，liked/stats/在途不跨边界
  return <Inner key={`${user?.username ?? "anon"}:${props.kind}:${props.resourceId}`} {...props} authed={status === "in" && !!user} />;
}

function Inner({ kind, resourceId, commentHref, authed }: {
  kind: EngagementKind; resourceId: string; commentHref?: string; authed: boolean;
}) {
  const [stats, setStats] = useState<PublicStats | null>(null);
  const [liked, setLiked] = useState<boolean | null>(null); // 登录者未取到前不显示假 false
  const [loadErr, setLoadErr] = useState("");
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [unconfirmed, setUnconfirmed] = useState(false);
  const [rechecking, setRechecking] = useState(false);
  const [shareMsg, setShareMsg] = useState("");
  const [needLogin, setNeedLogin] = useState(false); // 匿名点赞提示与读取失败分开——登录修不了网络
  const alive = useRef(true);
  const seq = useRef(0);
  const ctl = useRef<AbortController | null>(null);
  const viewFired = useRef(false);

  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []); // StrictMode 复位

  // 公共计数 + 登录者本人点赞态；stats+mine 全成功才解除未知——
  // mine 失败时 liked 置 null 禁用，旧值不当真值，只留重试可达
  const load = useCallback(async () => {
    const s = ++seq.current;
    ctl.current?.abort();
    const c = new AbortController(); ctl.current = c;
    try {
      const st = await engagementApi.stats(kind, resourceId, c.signal);
      if (s !== seq.current || !alive.current) return;
      // visible_ms 必须是服务端给的有效正数——无效按读取失败，不记 view 不用客户端默认
      if (!Number.isFinite(st.view_policy?.visible_ms) || st.view_policy.visible_ms <= 0) throw new Error("view_policy invalid");
      setStats(st);
      if (authed) {
        const mine = await engagementApi.myLike(kind, resourceId, c.signal);
        if (s !== seq.current || !alive.current) return;
        setLiked(mine.liked);
      }
      setLoadErr(""); setRechecking(false); setUnconfirmed(false);
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      if (s === seq.current && alive.current) {
        setLoadErr(e instanceof ApiError ? e.message : "计数暂时没取到");
        setRechecking(false);
        if (authed) setLiked(null);
      }
    }
  }, [kind, resourceId, authed]);

  useEffect(() => {
    const t = window.setTimeout(() => void load(), 0);
    return () => { window.clearTimeout(t); seq.current += 1; ctl.current?.abort(); };
  }, [load]);

  // 「阅读」：持续监听可见性；visible 才排 visible_ms，hidden 取消未到的记录；
  // fire 复核可见+活着+本地当日未记+visitor 可持久化；响应只合 views
  useEffect(() => {
    if (!stats || viewFired.current) return;
    const dayKey = `xce-viewed:${kind}:${resourceId}`;
    let timer = 0;
    const fire = () => {
      if (viewFired.current || !alive.current || document.visibilityState !== "visible") return;
      try { if (window.localStorage.getItem(dayKey) === shanghaiDay()) { viewFired.current = true; return; } } catch {}
      const vid = visitorId();
      if (!vid) { viewFired.current = true; return; } // 写不进 localStorage 就不计
      viewFired.current = true;
      void engagementApi.view(kind, resourceId, vid).then((r) => {
        if (!alive.current) return;
        setStats((p) => p ? { ...p, views: r.views } : p); // 只合 views，点赞真值不回头盖
        try { window.localStorage.setItem(dayKey, shanghaiDay()); } catch {}
      }).catch(() => { viewFired.current = false; /* 失败下次访问再试 */ });
    };
    const onVis = () => {
      window.clearTimeout(timer);
      if (document.visibilityState === "visible" && !viewFired.current) {
        timer = window.setTimeout(fire, stats.view_policy.visible_ms); // 已在 load 校验为正有限数，不夹客户端默认
      }
    };
    document.addEventListener("visibilitychange", onVis);
    onVis();
    return () => { window.clearTimeout(timer); document.removeEventListener("visibilitychange", onVis); };
  }, [stats, kind, resourceId]);

  const like = async () => {
    if (busyRef.current) return;
    if (!authed) { setNeedLogin(true); return; }
    busyRef.current = true; setBusy(true); setUnconfirmed(false);
    seq.current += 1; ctl.current?.abort(); // 作废在途 GET，旧响应不盖新赞
    try {
      const r = await engagementApi.setLike(kind, resourceId, !liked);
      if (alive.current) { setLiked(r.liked); setStats(r.stats); }
    } catch (e) {
      if (alive.current) {
        if (e instanceof ApiError && e.status >= 400 && e.status < 500) setLoadErr(e.message);
        else { setUnconfirmed(true); setRechecking(true); await load(); } // 没确认→锁内重取真值
      }
    } finally {
      busyRef.current = false;
      if (alive.current) setBusy(false);
    }
  };

  const share = async () => {
    const url = `${window.location.origin}${window.location.pathname}`;
    try {
      await navigator.clipboard.writeText(url);
      if (alive.current) { setShareMsg("链接已复制"); window.setTimeout(() => alive.current && setShareMsg(""), 2000); }
    } catch {
      if (alive.current) setShareMsg("复制没成功——请手动复制地址栏。");
    }
  };

  return (
    <div className={styles.bar}>
      <span className={styles.stat} title="每浏览器每天只记一次，不是独立人数">
        <Icon name="book" size={15} aria-hidden />阅读 {stats ? stats.views : "…"}
      </span>
      <button type="button" className={`${styles.act} ${liked ? styles.on : ""}`}
        disabled={busy || (authed && liked === null)} aria-pressed={!!liked}
        onClick={() => void like()}>
        <Icon name="spark" size={15} aria-hidden />{busy ? "处理中…" : liked ? `已赞 ${stats ? stats.likes : "…"} · 取消` : `赞 ${stats ? stats.likes : "…"}`}
      </button>
      {commentHref
        ? <a className={styles.stat} href={commentHref}><Icon name="chat" size={15} aria-hidden />评论 {stats ? stats.comments : "…"}</a>
        : <span className={styles.stat}><Icon name="chat" size={15} aria-hidden />评论 {stats ? stats.comments : "…"}</span>}
      <button type="button" className={styles.act} onClick={() => void share()}>
        <Icon name="external" size={15} aria-hidden />分享
      </button>
      {shareMsg && <span className={styles.note}>{shareMsg}</span>}
      <span className={styles.note}>阅读数按每浏览器每天去重，不是独立人数 · 从功能上线起累计</span>
      {unconfirmed && <span className={styles.note}>上一步结果没确认{rechecking ? "——正在重新核对……" : "，重试也没取到，稍后再点。"}</span>}
      {needLogin && !authed && <span className={styles.note}>登录后才能点赞 <Link href="/me/" className={styles.act}>去登录</Link></span>}
      {loadErr && <span className={styles.err}>{loadErr} <button type="button" className={styles.act} disabled={busy} onClick={() => void load()}>重试</button></span>}
    </div>
  );
}
