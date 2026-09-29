"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/auth";
import { SpeakerIdentity } from "@/components/ui/SpeakerIdentity";
import {
  gardenApi, newClientId,
  type Crop, type GardenEventPage, type GardenResponse, type NeighborPage, type Plot,
} from "@/lib/garden";
import styles from "./GardenView.module.css";

// 「我的护法与图鉴」懒挂载：首次展开 details 才加载/发请求，之后常驻保状态（Claude 组件，GARDEN-COMPANION 契约）
const GardenCompanion = dynamic(() => import("./GardenCompanion").then((m) => m.default), { ssr: false });
// 「成果木牌」懒挂载：mine/visit 共用，key=garden.id 随园切换 remount 隔离（pW 组件，GARDEN-MARKS 契约）
const GardenMarks = dynamic(() => import("./GardenMarks").then((m) => m.default), { ssr: false });

/* Design Contract（≤10 行）· POLISH R1
   屏职：登录群友的像素小菜园——看地块、选种播种、收菜、串门摘一点。
   首屏秩序：窄横幅 → 选种横条 → 地块（桌面 4 连排 / 手机 2×2，4:3）→ 情境提示行。
   空地去土纹，留浅垄虚线种植位；收成弱化为一行数字；提示不再 sticky 遮内容。
   层级：园景地块（主）＞操作侧栏（收成/种子/院门/串门/动态）＞手机底部情境条。
   必备态：未开通/空/生长中（服务器校时倒计时）/成熟/被摘/pending 禁重/失败/空邻居。
   禁：卡片墙、整幅插图冒充实时地图、假邻居、localStorage 存状态、写死规则数、工程黑话。 */

const REFRESH_MS = 30_000;

const fmt = (s?: string | null) => (s || "").replace("T", " ").slice(5, 16);
const fmtDur = (s: number) =>
  s < 90 ? `${Math.max(1, Math.round(s))} 秒` : s < 3300 ? `约 ${Math.round(s / 60)} 分钟` : s < 5400 ? "约 1 小时" : `约 ${(s / 3600).toFixed(1).replace(/\.0$/, "")} 小时`;
/** 剩余时间：ms<=0 由调用方另行处理 */
const fmtLeft = (ms: number) =>
  ms < 60_000 ? "不到 1 分钟" : ms < 3600_000 ? `约 ${Math.ceil(ms / 60_000)} 分钟` : `约 ${(ms / 3_600_000).toFixed(1).replace(/\.0$/, "")} 小时`;
const fmtClock = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(+d) ? "" : `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};
const errText = (e: unknown, fb: string) => (e instanceof ApiError ? e.message : fb);
const cropOf = (r: GardenResponse, id: string | null) => r.rules.crops.find((c) => c.id === id) ?? null;

function cropKind(c?: Crop | null): "radish" | "cabbage" | "pumpkin" | "sprout" {
  const s = `${c?.id ?? ""} ${c?.name ?? ""}`;
  if (/radish|luobo|carrot|萝卜/i.test(s)) return "radish";
  if (/cabbage|baicai|lettuce|白菜|青菜/i.test(s)) return "cabbage";
  if (/pumpkin|nangua|南瓜/i.test(s)) return "pumpkin";
  return "sprout";
}

/** 种子/作物小图标：自绘 SVG，不引图标库。 */
function CropIcon({ crop }: { crop?: Crop | null }) {
  const k = cropKind(crop);
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden className={styles.seedIco}>
      {k === "radish" && (<>
        <path d="M12 10C11 7 9 5.5 6.5 5M12 10c.2-3.2 1-5.6 3-7M12 10c1.2-2.6 3.2-3.6 5.5-3.5" stroke="#3f7a34" strokeWidth="1.8" fill="none" strokeLinecap="round" />
        <circle cx="12" cy="15.4" r="5.6" fill="#c0392b" /><path d="M10.8 20.4 12 23l1.2-2.6z" fill="#a93226" />
        <circle cx="10.2" cy="13.6" r="1.4" fill="#e89080" />
      </>)}
      {k === "cabbage" && (<>
        <circle cx="12" cy="13.5" r="7" fill="#5da24a" />
        <path d="M12 6.8v13.4M5.8 11c1.9 2 3.9 3 6.2 3s4.3-1 6.2-3M7 16.4c1.5 1.3 3.2 2 5 2s3.5-.7 5-2" stroke="#3f7a34" strokeWidth="1.4" fill="none" strokeLinecap="round" />
      </>)}
      {k === "pumpkin" && (<>
        <ellipse cx="12" cy="14.5" rx="8.2" ry="6.4" fill="#d98a2b" />
        <path d="M9 8.6c-1.2 3.4-1.2 8.3 0 11.8M15 8.6c1.2 3.4 1.2 8.3 0 11.8M12 8.2v12.6" stroke="#b06d1d" strokeWidth="1.3" fill="none" />
        <path d="M12 8.4c-.4-2 .4-3.4 2-4.2" stroke="#3f7a34" strokeWidth="1.8" fill="none" strokeLinecap="round" />
      </>)}
      {k === "sprout" && (<>
        <path d="M12 21v-9" stroke="#3f7a34" strokeWidth="1.8" strokeLinecap="round" />
        <path d="M12 13c0-3.2-2.6-5.4-6.2-5.4 0 3.2 2.6 5.4 6.2 5.4zM12 11c0-3.2 2.6-5.4 6.2-5.4 0 3.2-2.6 5.4-6.2 5.4z" fill="#5da24a" />
      </>)}
    </svg>
  );
}

function Head({ kicker, title, sub, extra }: { kicker: string; title: string; sub?: string; extra?: React.ReactNode }) {
  return (
    <header className={styles.head}>
      <div>
        <p className={styles.kicker}>{kicker}</p>
        <h2 className={styles.h2}>{title}</h2>
        {sub && <p className={styles.sub}>{sub}</p>}
      </div>
      {extra}
    </header>
  );
}

function State({ text, onRetry }: { text: string; onRetry?: () => void }) {
  return <div className={styles.state}>{text}{onRetry && <button type="button" onClick={onRetry}>重试</button>}</div>;
}

const EV_TEXT: Record<string, (e: { amount: number; crop_name: string | null }) => string> = {
  plant: (e) => `种下了 ${e.crop_name ?? "种子"}`,
  harvest: (e) => `收了 ${e.amount} 个 ${e.crop_name ?? "菜"}`,
  steal: (e) => `摘走 ${e.amount} 个 ${e.crop_name ?? "菜"}`,
  visibility: () => "动了院门",
};

/** 院里/邻家动态：真实事件，没有就不渲染。 */
function EventList({ ev, err, onRetry }: { ev: GardenEventPage | null; err: string; onRetry: () => void }) {
  if (err) return <p className={styles.notice}>{err}。<button type="button" onClick={onRetry}>重试</button></p>;
  if (ev === null) return <State text="正在读动态……" />;
  if (!ev.items.length) return <p className={styles.hint}>还没有动静。</p>;
  return (
    <div>
      {ev.items.map((e) => (
        <div key={e.id} className={styles.evRow}>
          <SpeakerIdentity name={e.actor.name} size={32} /> {(EV_TEXT[e.kind] ?? (() => "动了动"))(e)} <span className={styles.evTime}>{fmt(e.created_at)}</span>
        </div>
      ))}
      {ev.items.length < ev.total && <p className={styles.hint}>共 {ev.total} 条，这里只列最近 {ev.items.length} 条。</p>}
    </div>
  );
}

/** 单块地：真实 DOM 按钮，状态由服务端响应驱动；sprite 只作内景插画。 */
function PlotTile({
  p, crop, visiting, stealAmount, serverNow, busyThis, seedName, onPlant, onHarvest, onSteal,
}: {
  p: Plot; crop: Crop | null; visiting: boolean; stealAmount: number; serverNow: number;
  busyThis: boolean; seedName: string;
  onPlant: (p: Plot) => void; onHarvest: (p: Plot) => void; onSteal: (p: Plot) => void;
}) {
  const left = p.ripe_at && Number.isFinite(serverNow) ? Date.parse(p.ripe_at) - serverNow : null;
  let cls = styles.plot; let foot: React.ReactNode; let label: string; let act: (() => void) | undefined;
  if (p.state === "empty") {
    cls += ` ${styles.plotEmpty}`;
    if (visiting) { foot = <span>空地</span>; label = `${p.id} 号地，空地`; }
    else {
      foot = <><span>空地</span><span className={styles.go}>{seedName ? `种 ${seedName}` : "先选种子"}</span></>;
      label = `${p.id} 号地，空地${seedName ? `，按下种下 ${seedName}` : "，先到下面挑个种子"}`;
      act = () => onPlant(p);
    }
  } else if (p.state === "growing") {
    cls += ` ${styles.plotGrowing}`;
    const soon = left !== null && left <= 0;
    foot = left === null
      ? <span>生长中</span>
      : <><span>{soon ? "马上就熟" : `还差 ${fmtLeft(left)}`}</span><small>{!soon && p.ripe_at ? `约 ${fmtClock(p.ripe_at)} 熟` : ""}</small></>;
    label = `${p.id} 号地，${crop?.name ?? "菜"}，生长中${left === null ? "" : soon ? "，马上就熟" : `，还差${fmtLeft(left)}`}`;
  } else {
    cls += ` ${styles.plotRipe}`;
    if (visiting) {
      if (p.can_steal) {
        foot = <><span>熟了</span><span className={styles.steal}>摘一点 · 至多 {stealAmount}</span></>;
        label = `${p.id} 号地，${crop?.name ?? "菜"}熟了，按下摘一点`; act = () => onSteal(p);
      } else { foot = <><span>熟了</span><small>这块摘不了</small></>; label = `${p.id} 号地，${crop?.name ?? "菜"}熟了，摘不了`; }
    } else {
      foot = <><span>熟了</span><span className={styles.go}>{busyThis ? "收菜中…" : "点我收获"}</span></>;
      label = `${p.id} 号地，${crop?.name ?? "菜"}熟了，按下收获`; act = () => onHarvest(p);
    }
  }
  return (
    <li>
      <button type="button" id={`garden-plot-${p.id}`} className={cls} disabled={!act || busyThis} aria-label={label}
        onClick={act ? () => act() : undefined}>
        <span className={styles.plotArt} aria-hidden />
        <span className={styles.plotNum} aria-hidden>{p.id}</span>
        <span className={styles.plotTop}>
          {crop && <span className={styles.chip}><CropIcon crop={crop} />{crop.name}</span>}
          {p.stolen > 0 && <span className={`${styles.chip} ${styles.chipCin}`}>被摘走 {p.stolen}</span>}
          {p.state === "ripe" && !visiting && <span className={`${styles.chip} ${styles.chipAmber}`}>熟了</span>}
        </span>
        <span className={styles.plotFoot}>{foot}</span>
      </button>
      {!visiting && p.state === "ripe" && (p.stolen > 0 || p.protected_yield > 0) && (
        <p className={styles.hint}>产 {p.yield} · 保底 {p.protected_yield}{p.stolen > 0 ? ` · 已被摘 ${p.stolen}` : ""}</p>
      )}
    </li>
  );
}

export default function GardenView() {
  const [mine, setMine] = useState<GardenResponse | null>(null);      // null=未取到；garden=null=未开通
  const [visit, setVisit] = useState<GardenResponse | null>(null);    // 串门中的家园
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState("");
  const [seed, setSeed] = useState("");
  const [nudge, setNudge] = useState(false);
  const [nb, setNb] = useState<NeighborPage | null>(null);
  const [nbErr, setNbErr] = useState("");
  const [nbMore, setNbMore] = useState(false);
  const [ev, setEv] = useState<GardenEventPage | null>(null);
  const [evErr, setEvErr] = useState("");
  const [compOpen, setCompOpen] = useState(false);          // 首次展开后不再卸载
  const [rev, setRev] = useState(0);                        // 护法/图鉴刷新钥匙：仅本人 开通/种/收 成功才换

  const seq = useRef(0); const vseq = useRef(0); const nbSeq = useRef(0); const evSeq = useRef(0);
  const navSeq = useRef(0);                                              // 用户导航代际：仅 goVisit/back 递增，poll 不碰
  const visitId = useRef<string | null>(null);
  const cids = useRef<Record<string, string>>({});                   // 每个操作意图一个幂等 id，成功才换
  const seedBox = useRef<HTMLFieldSetElement>(null);

  /* ---------- 取数 ---------- */
  const loadEvents = useCallback(async (gid: string | undefined) => {
    if (!gid) return;
    const s = ++evSeq.current;
    try { const d = await gardenApi.events(gid, 0, 12); if (s === evSeq.current) { setEv(d); setEvErr(""); } }
    catch (e) { if (s === evSeq.current) setEvErr(errText(e, "动态暂时没取到")); }
  }, []);

  const loadMine = useCallback(async () => {
    const s = ++seq.current;
    try {
      const d = await gardenApi.mine();
      if (s !== seq.current) return;
      setMine(d); setErr("");
      setSeed((cur) => cur || d.rules.crops[0]?.id || "");
      // 串门期间不回写：旧响应也不能把我家动态盖到邻家上
      if (d.garden && visitId.current === null) void loadEvents(d.garden.id);
    } catch (e) { if (s === seq.current) setErr(errText(e, "家园暂时读不到")); }
  }, [loadEvents]);

  const loadVisit = useCallback(async (id: string) => {
    const s = ++vseq.current;
    try {
      const d = await gardenApi.visit(id);
      if (s !== vseq.current) return;
      setVisit(d); setErr("");
      if (d.garden && visitId.current === id) void loadEvents(d.garden.id);
    } catch (e) { if (s === vseq.current) setErr(errText(e, "这家暂时进不去")); }
  }, [loadEvents]);

  const loadNeighbors = useCallback(async (offset = 0, append = false) => {
    const s = ++nbSeq.current;
    try {
      const d = await gardenApi.neighbors(offset, 12);
      if (s !== nbSeq.current) return;
      setNb((prev) => (append && prev ? { ...d, items: [...prev.items, ...d.items] } : d));
      setNbErr("");
    } catch (e) { if (s === nbSeq.current) setNbErr(errText(e, "邻居列表暂时没取到")); }
  }, []);

  const refreshActive = useCallback(() => {
    if (document.hidden) return;
    const vid = visitId.current;
    if (vid) void loadVisit(vid); else void loadMine();
  }, [loadMine, loadVisit]);

  // 只在挂载期间取数；30s 一次（服务器校时），tab 后台停止，回前台立即补一次
  useEffect(() => {
    const boot = setTimeout(() => void loadMine(), 0);
    const t = setInterval(refreshActive, REFRESH_MS);
    const onVis = () => { if (!document.hidden) refreshActive(); };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      clearTimeout(boot); clearInterval(t); document.removeEventListener("visibilitychange", onVis);
      seq.current += 1; vseq.current += 1; nbSeq.current += 1; evSeq.current += 1; navSeq.current += 1;
    };
  }, [loadMine, refreshActive]);

  const myGid = mine?.garden?.id ?? null;
  useEffect(() => { const t = setTimeout(() => { if (myGid) void loadNeighbors(); }, 0); return () => clearTimeout(t); }, [myGid, loadNeighbors]);

  /* ---------- 动作 ---------- */
  const open = async () => {
    if (busy) return;
    setBusy("open"); setErr(""); setMsg("");
    try {
      const d = await gardenApi.create(cids.current["open"] ??= newClientId());
      seq.current += 1;
      setMine(d); delete cids.current["open"]; setRev((r) => r + 1);
      setMsg("小院开好了。挑个种子，点一块空地种下。");
      if (d.garden && visitId.current === null) void loadEvents(d.garden.id);
    } catch (e) {
      setErr(errText(e, "开通没成功，再试一次。"));
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) delete cids.current["open"];
    } finally { setBusy(""); }
  };

  const plant = async (p: Plot) => {
    const g = mine?.garden;
    if (busy || !g) return;
    const cropId = seed || mine?.rules.crops[0]?.id || "";
    if (!cropId) { setNudge(true); setTimeout(() => setNudge(false), 3200); seedBox.current?.scrollIntoView({ block: "center", behavior: "smooth" }); return; }
    setBusy(`p${p.id}`); setErr(""); setMsg("");
    const k = `plant:${p.id}:${cropId}`;   // 意图=地+种子；换种子即新意图新 key
    try {
      const d = await gardenApi.plant(p.id, cropId, (cids.current[k] ??= newClientId()));
      seq.current += 1;                    // 让在途旧 poll 失效，免得响应倒退成熟状态
      setMine(d); delete cids.current[k]; setRev((r) => r + 1);
      const c = cropOf(d, cropId);
      setMsg(`${p.id} 号地种下了 ${c?.name ?? "种子"}，${fmtDur(c?.duration_seconds ?? 0)} 后熟。`);
      if (visitId.current === null) void loadEvents(d.garden?.id);
    } catch (e) {
      setErr(errText(e, "没种上，再点一次试试。"));
      // 4xx=服务端明确拒绝：意图作废允许新动作；0/5xx=可能已落库，保留 key 等重试回放
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) delete cids.current[k];
      if (e instanceof ApiError && (e.status === 409 || e.status === 400)) void loadMine();
    } finally { setBusy(""); }
  };

  const harvest = async (p: Plot) => {
    if (busy || !mine?.garden || !p.cycle_id) return;
    setBusy(`h${p.id}`); setErr(""); setMsg("");
    const k = `harvest:${p.id}:${p.cycle_id}`;
    try {
      const d = await gardenApi.harvest(p.id, p.cycle_id, (cids.current[k] ??= newClientId()));
      seq.current += 1;
      setMine(d); delete cids.current[k]; setRev((r) => r + 1);
      setMsg(`${p.id} 号地收了 ${d.action.amount} 个 ${cropOf(d, p.crop_id)?.name ?? "菜"}。`);
      if (visitId.current === null) void loadEvents(d.garden?.id);
    } catch (e) {
      setErr(errText(e, "没收成，再点一次试试。"));
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) delete cids.current[k];
      if (e instanceof ApiError && (e.status === 409 || e.status === 400)) void loadMine();
    } finally { setBusy(""); }
  };

  const toggleGate = async () => {
    const g = mine?.garden;
    if (!g || busy) return;
    const next = g.visibility === "members" ? "private" : "members";
    setBusy("vis"); setErr(""); setMsg("");
    try {
      const d = await gardenApi.setVisibility(next, (cids.current["vis"] ??= newClientId()));
      seq.current += 1;
      setMine(d); delete cids.current["vis"];
      setMsg(next === "members" ? "院门开了——群友能来串门摘菜了。" : "院门关上了，只有你能看。");
    } catch (e) {
      setErr(errText(e, "院门没动成，再试一次。"));
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) delete cids.current["vis"];
    } finally { setBusy(""); }
  };

  const goVisit = async (id: string) => {
    if (busy) return;
    const n = ++navSeq.current;            // 用户导航代际
    const s = ++vseq.current;              // 未返回的旧访客请求不许回写跳邻家
    setBusy("go"); setErr(""); setMsg("");
    try {
      const d = await gardenApi.visit(id);
      if (n !== navSeq.current || s !== vseq.current) return;
      if (!d.garden) { setErr("这座家园没开门。"); return; }
      visitId.current = id; setVisit(d);
      setEv(null); setEvErr("");
      void loadEvents(d.garden.id);
    } catch (e) { if (n === navSeq.current && s === vseq.current) setErr(errText(e, "这家暂时进不去")); } finally { setBusy(""); }
  };

  const back = () => {
    navSeq.current += 1;                   // 在途 steal/visit 成功也只清 client_id，不 restore
    vseq.current += 1; evSeq.current += 1; // 在途访客请求/动态一律作废
    setVisit(null); visitId.current = null; setErr(""); setMsg("");
    setEv(null); setEvErr("");
    void loadMine(); void loadNeighbors();
  };

  const steal = async (p: Plot) => {
    const g = visit?.garden;
    if (!g || busy || !p.cycle_id) return;
    setBusy(`s${p.id}`); setErr(""); setMsg("");
    const k = `steal:${g.id}:${p.id}:${p.cycle_id}`;
    const n = navSeq.current;              // 导航代际快照：await 期间用户 back/换家则判过时
    try {
      const d = await gardenApi.steal(g.id, p.id, p.cycle_id, (cids.current[k] ??= newClientId()));
      delete cids.current[k];              // 菜已真实入账，无论视图是否还在邻家都清 key
      if (n !== navSeq.current) {          // 已离开：提示入账但不 restore visit
        setMsg(`摘到 ${d.action.amount} 个，放进你的库房了。`);
        return;
      }
      vseq.current += 1;                   // 在途旧访客 poll 作废
      if (d.garden && d.garden.is_mine) {
        // 主人中途关了院门：回执退回的是我自己的园子，跟着回本院
        seq.current += 1;
        setVisit(null); visitId.current = null; setMine(d);
        setMsg(`摘到 ${d.action.amount} 个，放进你的库房了；他家院门刚关上。`);
        void loadEvents(d.garden.id);
      } else {
        setVisit(d);
        setMsg(`摘到 ${d.action.amount} 个，放进你的库房了。`);
        void loadEvents(g.id);
      }
    } catch (e) {
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) delete cids.current[k];
      if (n !== navSeq.current) return;    // 过时失败不覆盖当前视图的错误提示
      setErr(errText(e, "没摘到。"));
      if (e instanceof ApiError && (e.status === 409 || e.status === 400)) { const vid = visitId.current; if (vid) void loadVisit(vid); }
    } finally { setBusy(""); }
  };

  /* ---------- 渲染 ---------- */
  if (mine === null && !err) return <State text="正在看家园……" />;
  if (mine === null) return <State text={err} onRetry={() => void loadMine()} />;

  const rules = visit?.rules ?? mine.rules;

  /* 未开通：只有开通按钮 */
  if (!visit && !mine.garden) {
    return (
      <div className={styles.garden}>
        <Head kicker="家园" title="你的小院" sub="一块自己的菜地：种下去，等它熟，顺手还能去邻居家摘一点。" />
        {err && <p role="alert" className={styles.err}>{err}</p>}
        <div className={styles.hero}>
          <div className={styles.heroCopy}>
            <p>给你留了 {rules.plot_count} 块地。挑个种子点空地就种上；熟了来点一下就收进库房。</p>
            <p>院门默认关着，只有你能看；想让群友来串门摘菜，随时可以自己开。</p>
            <div className={styles.acts}>
              <button type="button" className={styles.primary} disabled={!!busy} onClick={() => void open()}>{busy === "open" ? "正在开园……" : "开通我的小院"}</button>
            </div>
            <p className={styles.hint}>收的只是地里的菜，图个乐——不是积分，也不能兑换。</p>
          </div>
          <figure className={styles.heroImg}>
            <img src="/brand/garden/cozy-homestead-v1.webp" alt="一座像素风小院：木屋、菜床、灯笼，还有一台小机器人。" width={1254} height={1254} loading="lazy" decoding="async" />
          </figure>
        </div>
      </div>
    );
  }

  const view = visit ?? mine;
  const garden = view.garden;
  if (!garden) return <State text="这座家园暂时看不了。" onRetry={visit ? back : () => void loadMine()} />;
  const visiting = !!visit;
  // 倒计时以最近一次响应的 server_now 为基准；≤30s 一刷即任务书允许的最大更新频率
  const t = Date.parse(view.server_now);
  const ripeCount = garden.plots.filter((p) => p.state === "ripe").length;
  const hasEmpty = garden.plots.some((p) => p.state === "empty");
  const nextRipe = garden.plots.filter((p) => p.state === "growing" && p.ripe_at).flatMap((p) => (p.ripe_at ? [Date.parse(p.ripe_at)] : [])).filter(Number.isFinite).sort((a, b) => a - b)[0];
  const seedCrop = cropOf(view, seed);
  const firstRipe = garden.plots.find((p) => p.state === "ripe");

  return (
    <div className={styles.garden}>
      <Head
        kicker="家园"
        title={visiting ? `${garden.owner.name} 的家园` : "我的小院"}
        sub={visiting ? "来看看，熟地可以顺手摘一点。" : "种地、收菜、串门。全部种收都以服务器时间为准。"}
        extra={visiting ? <button type="button" className={styles.ghost} onClick={back}>← 回我的小院</button> : undefined}
      />
      {err && <p role="alert" className={styles.err}>{err}<button type="button" className={styles.textBtn} onClick={refreshActive}>刷新</button></p>}
      {msg && <p role="status" className={styles.ok}>{msg}</p>}

      <div className={styles.layout}>
        <section className={styles.scene} aria-label={visiting ? `${garden.owner.name} 的地` : "我的地"}>
          {visiting && (
            <div className={styles.visitBar}>
              <span className={styles.visitWho}><SpeakerIdentity name={garden.owner.name} size={32} /> 的家园</span>
              <span>总收成 {garden.harvest_total} · 熟了 {ripeCount} 块</span>
            </div>
          )}
          {!visiting && (
            <figure className={styles.banner}>
              <img src="/brand/garden/cozy-homestead-v1.webp" alt="" width={1254} height={1254} loading="lazy" decoding="async" />
            </figure>
          )}
          {!visiting && (
            <fieldset className={`${styles.seedStrip} ${nudge ? styles.nudge : ""}`} ref={seedBox}>
              <legend className="sr-only">选种子</legend>
              <span className={styles.seedCap}>种子</span>
              {rules.crops.map((c) => (
                <label key={c.id} className={styles.seedChip}>
                  <input type="radio" name="garden-seed" className={styles.seedInput} value={c.id}
                    checked={seed === c.id} onChange={() => setSeed(c.id)} />
                  <CropIcon crop={c} />
                  <span className={styles.seedName}>{c.name}<small>{fmtDur(c.duration_seconds)} · 收 {c.yield}</small></span>
                  {seed === c.id && <span className={styles.seedCheck}>已选</span>}
                </label>
              ))}
            </fieldset>
          )}
          {garden.plots.length === 0 ? <State text="地还没翻出来，等会儿再来。" /> : (
            <ul className={styles.plotGrid}>
              {garden.plots.map((p) => (
                <PlotTile key={p.id} p={p} crop={cropOf(view, p.crop_id)} visiting={visiting}
                  stealAmount={rules.steal_amount} serverNow={t} seedName={seedCrop?.name ?? ""}
                  busyThis={busy === `p${p.id}` || busy === `h${p.id}` || busy === `s${p.id}`}
                  onPlant={(x) => void plant(x)} onHarvest={(x) => void harvest(x)} onSteal={(x) => void steal(x)} />
              ))}
            </ul>
          )}
          {!visiting && (
            <p className={styles.sceneHint} aria-live="polite">
              {busy ? "正在处理……"
                : ripeCount > 0 ? <>{ripeCount} 块地熟了<button type="button" onClick={() => { const el = firstRipe && document.getElementById(`garden-plot-${firstRipe.id}`); el?.scrollIntoView({ block: "center" }); el?.focus(); }}>去收 →</button></>
                : hasEmpty ? (seedCrop ? `已选 ${seedCrop.name} · 点一块空地种下` : "先在上方挑个种子")
                : nextRipe ? `地都种上了，最近一茬 ${fmtLeft(nextRipe - t)}后熟` : "地都种上了"}
            </p>
          )}
          {/* 成果木牌：mine/visit 都挂，gardenId+isMine 变化即 remount；不传 revisionKey（不随 poll/种收刷新） */}
          <GardenMarks key={`${visiting ? "v" : "m"}:${garden.id}`} gardenId={garden.id} isMine={!visiting} />
        </section>

        <aside className={styles.ops}>
          <section className={styles.opsBlock}>
            <h3 className={styles.opsTitle}>{visiting ? "他家收成" : "收成"}</h3>
            <p className={styles.harvestNum}>{garden.harvest_total}</p>
            {!visiting && <p className={styles.hint}>收的是菜，图个乐——不是积分，也不能兑换。</p>}
          </section>

          {!visiting && garden && (
            <section className={styles.opsBlock}>
              <h3 className={styles.opsTitle}>院门</h3>
              <div className={styles.switchRow}>
                <span className={styles.switchLabel}>{garden.visibility === "members" ? "开着：群友能来串门" : "关着：只有自己能看"}</span>
                <button type="button" role="switch" aria-checked={garden.visibility === "members"} className={styles.switch}
                  disabled={busy === "vis"} onClick={() => void toggleGate()} aria-label="让群友来串门摘菜" />
              </div>
              <p className={styles.hint}>
                开着的时候，群友能进你的院子，每茬菜每人最多顺手摘 {rules.steal_amount} 个；你的保底收成谁都摘不动。
              </p>
            </section>
          )}

          {!visiting && (
            <section className={styles.opsBlock}>
              <details className={styles.details}
                onToggle={(e) => { if (e.currentTarget.open) setCompOpen(true); }}>
                <summary>我的护法与图鉴</summary>
                <div className={styles.detailsBody}>
                  {compOpen && <GardenCompanion revisionKey={String(rev)} />}
                </div>
              </details>
            </section>
          )}

          {!visiting && (
            <section className={styles.opsBlock}>
              <h3 className={styles.opsTitle}>去串门</h3>
              {nbErr ? <p className={styles.notice}>{nbErr}。<button type="button" onClick={() => void loadNeighbors()}>重试</button></p>
                : nb === null ? <State text="正在找邻居……" />
                : !nb.items.length ? <p className={styles.hint}>还没有开着门的家园。在群里喊一声——开了小院、打开院门，就能互相摘菜了。</p>
                : (
                  <>
                    <ul className={styles.rows}>
                      {nb.items.map((n) => (
                        <li key={n.id} className={styles.nbRow}>
                          <span className={styles.nbName}><SpeakerIdentity name={n.owner.name} size={32} />{n.ripe_count > 0 && <span className={styles.ripeTag}>熟了 {n.ripe_count} 块</span>}</span>
                          <span className={styles.rowMeta}>总收 {n.harvest_total}</span>
                          <button type="button" className={styles.textBtn} disabled={busy === "go"} onClick={() => void goVisit(n.id)}>去串门 →</button>
                        </li>
                      ))}
                    </ul>
                    {nb.items.length < nb.total && (
                      <div className={styles.blockTight}>
                        <button type="button" className={styles.textBtn} disabled={nbMore}
                          onClick={() => { setNbMore(true); void loadNeighbors(nb.items.length, true).finally(() => setNbMore(false)); }}>
                          {nbMore ? "加载中…" : `再看几家（还有 ${nb.total - nb.items.length} 家）`}
                        </button>
                      </div>
                    )}
                    <p className={styles.hint}>共 {nb.total} 家开着门{nb.items.length < nb.total ? `，已显示前 ${nb.items.length} 家` : ""}。</p>
                  </>
                )}
            </section>
          )}

          {visiting && (
            <section className={styles.opsBlock}>
              <h3 className={styles.opsTitle}>摘菜规矩</h3>
              <p className={styles.opsSub}>每块熟地最多摘 {rules.steal_amount} 个，一茬只能摘一次；主人的保底收成摘不动。</p>
            </section>
          )}

          <section className={styles.opsBlock}>
            <h3 className={styles.opsTitle}>{visiting ? "这家最近" : "院里最近"}</h3>
            <EventList ev={ev} err={evErr} onRetry={() => void loadEvents(garden.id)} />
          </section>
        </aside>
      </div>
    </div>
  );
}
