"use client";

import { useEffect, useRef, useState } from "react";
import playground from "../../../content/playground.json";
import styles from "./PlaygroundSpotlight.module.css";

const scenes = [
  { name: "苦等中", line: "胡子又长了，按钮还没动。", speech: "别急，我就刷会儿 X。", action: "给他续杯 ☕" },
  { name: "准备按", line: "手指离按钮，只差一个 soon。", speech: "Soon™，懂的都懂。", action: "再戳一下他 👆" },
  { name: "封神了", line: "上一秒胡子拉碴，下一秒赛博义父。", speech: "额度降临。诸位，开工！", action: "谢谢义父 🙏" },
];

type Observation = { state: "loading" | "unknown" | "waiting" | "soon" | "reset"; source?: string; last?: string; next?: string };
const STATUS_URL = /^https:\/\/x\.com\/thsottiaux\/status\/\d+$/;
function readObservation(value: unknown): Observation {
  const empty: Observation = { state: "unknown" };
  if (!value || typeof value !== "object") return empty;
  const data = value as { health?: unknown; fetched_at?: unknown; source?: { handle?: unknown }; forecast?: { state?: unknown; reason?: unknown; source_url?: unknown }; posts?: unknown; reset_timeline?: unknown };
  const fetched = typeof data.fetched_at === "string" ? Date.parse(data.fetched_at) : NaN;
  const fresh = data.health === "ok" && data.source?.handle === "thsottiaux" && Number.isFinite(fetched) && fetched <= Date.now() && Date.now() - fetched <= 86400000;
  const posts = Array.isArray(data.posts) ? data.posts : [];
  const hasPost = (kind: string, url: unknown, fresh24: boolean) => posts.some((post: unknown) => {
    if (!post || typeof post !== "object") return false;
    const p = post as { kind?: unknown; url?: unknown; created_at?: unknown };
    const time = typeof p.created_at === "string" ? Date.parse(p.created_at) : NaN;
    return p.kind === kind && p.url === url && Number.isFinite(time) && time <= Date.now() && (!fresh24 || Date.now() - time <= 86400000);
  });
  // reset_timeline projection: historical last always kept; next only when fresh.
  const rt = data.reset_timeline as { fresh?: unknown; last_reset?: { reported_at?: unknown; source_url?: unknown } | null; next_reset?: { status?: unknown; window_start?: unknown; window_end?: unknown; time_basis?: unknown; timezone?: unknown; source_url?: unknown } | null } | undefined;
  const tl: { last?: string; next?: string } = {};
  const reported = rt && rt.last_reset ? Date.parse(String(rt.last_reset.reported_at)) : NaN;
  if (rt && rt.last_reset && Number.isFinite(reported) && reported <= Date.now() && typeof rt.last_reset.source_url === "string" && STATUS_URL.test(rt.last_reset.source_url)) {
    tl.last = `${new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(reported))}（${Intl.DateTimeFormat().resolvedOptions().timeZone || "本地"}·公告）`;
  }
  const nr = rt?.next_reset;
  const ws = Date.parse(String(nr?.window_start)), we = Date.parse(String(nr?.window_end));
  const windowValid = nr?.time_basis === "source_calendar" && nr?.timezone === "America/Los_Angeles" && Number.isFinite(ws) && Number.isFinite(we) && ws < we;
  const windowOpen = rt?.fresh === true && nr?.status === "announced" && windowValid && we > Date.now() && typeof nr?.source_url === "string" && STATUS_URL.test(nr.source_url) && hasPost("promise", nr.source_url, false);
  if (fresh && rt && rt.fresh !== false) {
    if (windowOpen) {
      const pacific = new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", timeZone: "America/Los_Angeles" });
      tl.next = `${pacific.format(new Date(ws))}–${pacific.format(new Date(we - 1))}（太平洋时间）`;
    } else if (windowValid) tl.next = "下次时间待确认";
    else if (nr?.status === "announced") tl.next = "已预告 · 哪天还没说";
    else if (nr?.status === "possible") tl.next = "有信号 · 还没定日子";
    else tl.next = "下次时间待确认";
  } else if (rt) tl.next = "下次时间待确认";
  if (!fresh) return { state: "unknown", ...tl };
  const state = data.forecast?.state;
  if (state !== "waiting" && state !== "soon" && state !== "reset") return { state: "unknown", ...tl };
  const source = data.forecast?.source_url;
  const validSource = typeof source === "string" && STATUS_URL.test(source);
  if (state === "waiting") {
    if (windowOpen) return { state: "soon", source: String(nr!.source_url), ...tl };
    return { state, ...tl };
  }
  const expected = state === "reset" ? "reset" : "promise";
  const reason = state === "reset" ? "PUBLIC_RESET_CLAIM_NOT_ACCOUNT_CONFIRMATION" : "EXPLICIT_FUTURE_PUBLIC_CLAIM";
  const strict = validSource && data.forecast?.reason === reason && hasPost(expected, source, true);
  if (!strict) {
    if (state === "soon" && windowOpen) return { state: "soon", source: String(nr!.source_url), ...tl };
    return { state: "unknown", ...tl };
  }
  return { state, ...(validSource ? { source } : {}), ...tl };
}

export function PlaygroundSpotlight() {
  const sectionRef = useRef<HTMLElement>(null);
  const [artReady, setArtReady] = useState(false);
  useEffect(() => {
    const section = sectionRef.current;
    if (!section) return;
    if (!("IntersectionObserver" in window)) { setArtReady(true); return; }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setArtReady(true);
        observer.disconnect();
      }
    }, { rootMargin: "300px" });
    observer.observe(section);
    return () => observer.disconnect();
  }, []);
  const [observation, setObservation] = useState<Observation>({ state: "loading" });
  const [demoScene, setDemoScene] = useState<number | null>(null);
  const [reaction, setReaction] = useState(false);
  useEffect(() => {
    let disposed = false;
    let busy = false;
    let request: AbortController | null = null;
    const refresh = async () => {
      if (busy || document.hidden) return;
      busy = true;
      request = new AbortController();
      const timeout = setTimeout(() => request?.abort(), 8000);
      try {
        const response = await fetch("/api/tibo/status", { cache: "no-store", signal: request.signal });
        if (!response.ok) throw new Error("Observation unavailable");
        const data: unknown = await response.json();
        if (!disposed) setObservation(readObservation(data));
      } catch {
        if (!disposed) setObservation(prev => ({ state: "unknown", last: prev.last, next: "下次时间待确认" }));
      } finally { clearTimeout(timeout); busy = false; }
    };
    const onVisible = () => { if (!document.hidden) void refresh(); };
    void refresh();
    const interval = setInterval(() => void refresh(), 60000);
    document.addEventListener("visibilitychange", onVisible);
    return () => { disposed = true; request?.abort(); clearInterval(interval); document.removeEventListener("visibilitychange", onVisible); };
  }, []);
  const liveScene = observation.state === "reset" ? 2 : observation.state === "soon" ? 1 : 0;
  const scene = demoScene ?? liveScene;
  const current = scenes[scene];
  const unknown = demoScene === null && (observation.state === "unknown" || observation.state === "loading");
  const status = { loading: "正在核对最新公告…", unknown: "暂时无法确认当前状态", waiting: "暂无新的有效重置预告", soon: "已公开预告 · 等待完成确认", reset: "本轮重置已公告完成" }[observation.state];
  return (
    <section ref={sectionRef} id="playground" className={styles.lab} aria-labelledby="playground-title" onFocusCapture={() => setArtReady(true)}>
      <div className={styles.heading}>
        <h2 id="playground-title">摸鱼实验室 <span>认真玩一下。</span></h2>
        <span className={styles.note}>社区趣味作品</span>
      </div>
      <div className={styles.stage}>
        <div className={styles.copy}>
          <p className={styles.eyebrow}>ai tibo <b>!</b></p>
          <h3>{playground.title}</h3>
          <div className={styles.observation} data-status={observation.state} role="status"><strong>{status}</strong>{observation.source && <a href={observation.source} target="_blank" rel="noopener noreferrer">核对原帖 ↗</a>}</div>
          {(observation.last || observation.next) && <p className={styles.tl}>上次 {observation.last ?? "—"} · 下次 {observation.next ?? "—"}</p>}
          <p className={styles.line} aria-live="polite">{unknown ? "先看原帖，再决定要不要叫义父。" : current.line}</p>
          <p className={styles.intro}>写代码写累了？来给他续杯、刮胡子，围观那个迟迟没按下去的红按钮。</p>
          <div className={styles.states} role="group" aria-label="切换漫画演示形态">
            {scenes.map((item, index) => <button key={item.name} type="button" aria-pressed={demoScene === index} onClick={() => { setDemoScene(index); setReaction(false); }}>{item.name}</button>)}
          </div>
          {demoScene !== null && <p className={styles.demo}>漫画试玩中 <button type="button" onClick={() => { setDemoScene(null); setReaction(false); }}>返回实时公告 ↗</button></p>}
          <a className={styles.enter} href={playground.url}>进入完整观测站 <span aria-hidden>↗</span></a>
          <p className={styles.disclaimer}>人物随公开公告更新；手动切换仅为漫画试玩。公告不代表你的账户额度。</p>
        </div>
        <div className={styles.comic}>
          <div key={scene} className={`${styles.illustration} ${artReady ? styles.artReady : ""} ${scene === 2 ? styles.god : ""}`} style={{ backgroundPosition: `50% ${scene * 50}%` }} role="img" aria-label={unknown ? "等待核验公开消息的漫画 Tibo" : `${current.name}：${current.line}`} />
          <p className={styles.speech} aria-live="polite">{reaction ? ["咖啡收下，按钮再说。", "别戳了，手已经在路上了。", "别拜了，快去写代码！"][scene] : unknown ? "我先看看他刚说了什么。" : current.speech}<small>本站配文 · {demoScene === null ? "形象跟随公告" : "漫画试玩"}</small></p>
          <button className={styles.react} type="button" onClick={() => setReaction(!reaction)}>{current.action}</button>
        </div>
      </div>
    </section>
  );
}
