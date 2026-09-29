"use client";
/* 详情页正文上方的阅读足迹工具条（READING-GROWTH R1）。
 * 匿名只见登录提示、不发任何私有请求；登录后 GET 记录，
 * 页面可见 3 秒后记一次「打开」（每挂载最多一次，hidden 取消未到的记录）。
 * 外层按 账号:kind:id key remount——openFired/rec 不跨账号与条目；
 * GET/open/patch 全走 alive+seq 守卫，PATCH 发起即作废在途 GET。 */
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, useAuth } from "@/lib/auth";
import { readingGrowthApi, type ReadingKind, type ReadingRecord } from "@/lib/reading-growth";
import styles from "./ReadingActions.module.css";

export function ReadingActions(props: { kind: ReadingKind; resourceId: string }) {
  const { status, user } = useAuth();
  if (status === "loading") return <div className={styles.bar} aria-hidden="true" />;
  if (status !== "in" || !user) {
    return (
      <div className={styles.bar}>
        <span className={styles.note}>收藏这篇、读完这篇是私人足迹——</span>
        <Link href="/me/?view=reading" className={styles.act}>登录后可见</Link>
      </div>
    );
  }
  // key=账号:条目：换账号/换条目整棵重挂载，openFired/rec/在途全部不跨边界
  return <Actions key={`${user.username}:${props.kind}:${props.resourceId}`} {...props} />;
}

function Actions({ kind, resourceId }: { kind: ReadingKind; resourceId: string }) {
  const [rec, setRec] = useState<ReadingRecord | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loadErr, setLoadErr] = useState("");
  const [busy, setBusy] = useState<"saved" | "finished" | "">("");
  const [unconfirmed, setUnconfirmed] = useState(false);
  const [rechecking, setRechecking] = useState(false); // 未确认后重取中——未取到前不宣称已核对
  const alive = useRef(true);
  const seq = useRef(0);
  const ctl = useRef<AbortController | null>(null);
  const openFired = useRef(false);
  const busyRef = useRef(false); // 同步闸：连点在同一事件循环就拦下

  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []); // StrictMode 重挂先复位

  const load = useCallback(async () => {
    const s = ++seq.current;
    ctl.current?.abort();
    const c = new AbortController(); ctl.current = c;
    try {
      const { item } = await readingGrowthApi.get(kind, resourceId, c.signal);
      if (s !== seq.current || !alive.current) return;
      setRec(item); setLoaded(true); setLoadErr(""); setRechecking(false); setUnconfirmed(false);
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      if (s === seq.current && alive.current) { setLoadErr("阅读足迹暂时没取到"); setRechecking(false); }
    }
  }, [kind, resourceId]);

  useEffect(() => {
    const t = window.setTimeout(() => void load(), 0);
    return () => { window.clearTimeout(t); seq.current += 1; ctl.current?.abort(); };
  }, [load]);

  // 「打开」：持续监听可见性；visible 才排 3 秒，hidden 立即取消未到的记录；
  // fire 时再核 visible+alive——hide 期间绝不写
  useEffect(() => {
    let timer = 0;
    const fire = () => {
      if (openFired.current || !alive.current || document.visibilityState !== "visible") return;
      openFired.current = true;
      // open 只负责记一次「打开」——响应不落状态，按钮真值只来自 GET/PATCH（迟到 open 永不可能盖在途 PATCH）
      void readingGrowthApi.open(kind, resourceId).catch(() => { /* 打开记录失败不打扰阅读 */ });
    };
    const onVis = () => {
      window.clearTimeout(timer);
      if (document.visibilityState === "visible" && !openFired.current) {
        timer = window.setTimeout(fire, 3000);
      }
    };
    document.addEventListener("visibilitychange", onVis);
    onVis(); // 初始可见性也走同一条路径
    return () => { window.clearTimeout(timer); document.removeEventListener("visibilitychange", onVis); };
  }, [kind, resourceId]);

  const patch = async (field: "saved" | "finished", v: boolean) => {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(field); setUnconfirmed(false);
    seq.current += 1;      // 作废在途 GET——旧 GET 不得盖 PATCH 的新状态
    ctl.current?.abort();
    try {
      const { item } = await readingGrowthApi.patch(kind, resourceId, { [field]: v });
      if (alive.current) setRec(item);
    } catch (e) {
      if (alive.current) {
        if (e instanceof ApiError && e.status >= 400 && e.status < 500) setLoadErr(e.message);
        else {
          // 0/5xx：结果没确认→await 重取真值；busyRef 全程保持，防第二次 PATCH 被重查旧结果盖
          setUnconfirmed(true); setRechecking(true);
          await load();
        }
      }
    } finally {
      busyRef.current = false;
      if (alive.current) setBusy("");
    }
  };

  return (
    <div className={styles.bar}>
      <button type="button" className={`${styles.act} ${rec?.saved ? styles.on : ""}`} disabled={!!busy || !loaded}
        onClick={() => void patch("saved", !rec?.saved)}>
        {busy === "saved" ? "处理中…" : rec?.saved ? "已收藏 · 取消" : "收藏这篇"}
      </button>
      <button type="button" className={`${styles.act} ${rec?.finished ? styles.on : ""}`} disabled={!!busy || !loaded}
        onClick={() => void patch("finished", !rec?.finished)}>
        {busy === "finished" ? "处理中…" : rec?.finished ? "已读完这篇 · 取消" : "读完这篇"}
      </button>
      <Link href="/me/?view=reading" className={styles.act}>我的阅读 →</Link>
      <span className={styles.note}>
        {!loaded && !loadErr ? "正在读足迹…… · " : ""}足迹只你可见 · 在本页停留片刻自动记下「打开」 · 「读完」指这篇导读，不是整本原书
      </span>
      {unconfirmed && (
        <span className={styles.note}>
          上一步结果没确认{rechecking ? "——正在重新核对……" : "，重试也没取到，稍后再点。"}
        </span>
      )}
      {loadErr && <span className={styles.err}>{loadErr} <button type="button" className={styles.act} disabled={!!busy} onClick={() => void load()}>重试</button></span>}
    </div>
  );
}
