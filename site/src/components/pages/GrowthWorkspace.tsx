"use client";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, useAuth } from "@/lib/auth";
import { practiceApi, type Challenge, type Practice, type PracticeStatus, type Reply, type Submission } from "@/lib/practice";
import { parsePracticeIndex, practiceIndexFor, type PracticeIndexEntry } from "@/lib/reading-practice";
import { SpeakerIdentity } from "@/components/ui/SpeakerIdentity";
import { RichMessage } from "@/components/ui/RichMessage";
import { MarkdownComposer } from "@/components/ui/MarkdownComposer";
import styles from "./GrowthWorkspace.module.css";

/** 「我的成长」实践工作区：概览 / 我的实践 / 共练。
 *  路由 ?view=&p=&c=&s= 全由 URL 驱动，push 保留后退；模块只在选中视图挂载时才取数。
 *  编辑失败保稿；409 不覆盖；同一按钮防重；草稿只留内存且按账号隔离。 */

const fmt = (s?: string) => (s || "").replace("T", " ").slice(5, 16);
const STATUS_LABEL: Record<PracticeStatus, string> = { active: "进行中", completed: "已完成", archived: "已归档" };
const STATUS_BADGE: Record<PracticeStatus, string> = { active: styles.badge, completed: styles.badgeDone, archived: styles.badgeArch };

/** 未保存草稿只留内存，key 带账号——换账号看不到旧草稿。 */
const drafts = new Map<string, Record<string, string>>();
const draftKey = (user: string, id: string) => `${user}:${id}`;
function saveDraft(user: string, id: string, v: Record<string, string>) {
  if (drafts.size > 30) drafts.delete(drafts.keys().next().value as string);
  drafts.set(draftKey(user, id), v);
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

function errText(e: unknown, fallback: string) {
  return e instanceof ApiError ? e.message : fallback;
}

/* ---------- 创建小目标表单（概览空态与我的实践共用；可接阅读预填） ---------- */
function CreateForm({ onCreated, compact = false, prefill = null, onBusy }: {
  onCreated: (p: Practice) => void; compact?: boolean; prefill?: PracticeIndexEntry | null;
  onBusy?: (busy: boolean) => void;
}) {
  const [title, setTitle] = useState(""); const [outcome, setOutcome] = useState(""); const [step, setStep] = useState("");
  const [src, setSrc] = useState<{ url: string; title: string } | null>(null);
  const [busy, setBusy] = useState(false); const [err, setErr] = useState("");
  const [unconfirmed, setUnconfirmed] = useState(false);
  const [existed, setExisted] = useState<Practice | null>(null);
  const busyRef = useRef(false);   // 同步闸：state 有一帧延迟，连点在同一事件循环就拦下
  // pending = 已发出但结果未确认的创建意图：client_id 与请求体绑定——同 key 绝不发不同 body
  const pending = useRef<{ client_id: string; bodyKey: string } | null>(null);
  // auto 记录哪些字段是预填写的：下一轮预填可盖它们，但用户手写的字永不覆盖
  const auto = useRef<Set<string>>(new Set());
  useEffect(() => {
    const t = window.setTimeout(() => {
      if (!prefill) { setSrc(null); return; } // 预填撤销/换源/未知 id：清旧来源，手写稿保留——不带旧来源创建
      const fill = (key: string, value: string, set: (fn: (v: string) => string) => void) => {
        set((v) => ((!v || auto.current.has(key)) && value) ? (auto.current.add(key), value) : v);
      };
      fill("title", prefill.title, setTitle);
      fill("outcome", prefill.outcome, setOutcome);
      fill("step", prefill.next_step, setStep);
      setSrc({ url: prefill.source_url, title: prefill.source_title });
    }, 0);
    return () => window.clearTimeout(t);
  }, [prefill]);

  const newClientId = () => (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function")
    ? crypto.randomUUID()
    : `ci_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 12)}`;
  // 与后端 _text 规范化对齐：单行剥全部控制/隐形符；多行 \r\n→\n 后剥行内控制符（保 \n）
  const normSingle = (v: string) => v.replace(/[\x00-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2060\ufeff]/g, "").trim();
  const normMulti = (v: string) => v.replace(/\r\n/g, "\n").replace(/\r/g, "\n").replace(/[\x00-\x09\x0b-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2060\ufeff]/g, "").trim();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busyRef.current) return; // 双击/连点：同步闸先拦，不等 state 那一帧
    busyRef.current = true; setBusy(true); onBusy?.(true);
    setErr(""); setExisted(null); setUnconfirmed(false);
    const body = {
      title: title.trim(), outcome: outcome.trim(),
      ...(step.trim() ? { next_step: step.trim() } : {}),
      ...(src ? { source_url: src.url, source_title: src.title } : {}),
    };
    const bodyKey = JSON.stringify(body);
    if (!pending.current || pending.current.bodyKey !== bodyKey) {
      pending.current = { client_id: newClientId(), bodyKey }; // 字段变了=新意图：新 key，同 key 绝不发不同 body
    }
    try {
      const p = await practiceApi.create({ ...body, client_id: pending.current.client_id });
      // 同来源已有 active 时后端幂等返回既存：字段对得上才算这次真建了，
      // 对不上就诚实提示打开现有——不宣称新建，也不清用户未确认的稿
      const mine = p.title === normSingle(title) && p.outcome === normMulti(outcome)
        && (normMulti(step) ? p.next_step === normMulti(step) : !p.next_step);
      pending.current = null; // 有定论（新建成功或命中既有）：本次意图结束
      if (src && p.status === "active" && !mine) { setExisted(p); return; }
      onCreated(p);
    } catch (e2) {
      if (e2 instanceof ApiError && e2.status >= 400 && e2.status < 500) {
        pending.current = null; // 4xx 确定拒绝：下次点击是新意图换新 key
        setErr(e2.message);
      } else {
        setUnconfirmed(true); // 0/5xx：结果没确认，pending 保留——字段不动再点是同票重试
      }
    } finally { busyRef.current = false; setBusy(false); onBusy?.(false); }
  };
  return (
    <form onSubmit={submit} className={styles.detail}>
      {!compact && <h3>开始一个小目标</h3>}
      {src && <p className={styles.notice}>来源：<Link href={src.url} className={styles.textBtn}>《{src.title}》精读</Link>——已按它预填，改完点「创建并开始」才真的建。</p>}
      {existed && (
        <p className={styles.notice}>
          这条来源已经有进行中的练习：「{existed.title}」——你刚写的内容没有被当成新目标创建，也还在下面。
          <button type="button" className={styles.textBtn} onClick={() => onCreated(existed)}>打开已有练习 →</button>
        </p>
      )}
      <label className={styles.fieldLabel}>想做成什么（1–120 字）
        <input className={styles.input} required maxLength={120} value={title} disabled={busy} onChange={(e) => { auto.current.delete("title"); setTitle(e.target.value); }} placeholder="例：用 AI 把每周会议纪要整理成一条精读" /></label>
      <label className={styles.fieldLabel}>做到什么算完成（1–1000 字）
        <textarea className={styles.area} required maxLength={1000} rows={2} value={outcome} disabled={busy} onChange={(e) => { auto.current.delete("outcome"); setOutcome(e.target.value); }} placeholder="例：跑通一次完整流程，产出一篇可回看的整理稿" /></label>
      <label className={styles.fieldLabel}>下一步（可选）
        <input className={styles.input} maxLength={1000} value={step} disabled={busy} onChange={(e) => { auto.current.delete("step"); setStep(e.target.value); }} placeholder="例：先找一份真实会议录音转写" /></label>
      {err && <p className={styles.err}>{err}</p>}
      {unconfirmed && (
        <p className={styles.notice}>
          这次创建的结果没确认——可能已经建好，也可能没有。字段不动再点一次会用同一张票据重试，不会重复建；
          改了内容再点则算新目标。拿不准就先到列表里看一眼。
        </p>
      )}
      <div className={styles.acts}><button type="submit" className={styles.primary} disabled={busy}>{busy ? "创建中…" : "创建并开始"}</button></div>
      <p className={styles.hint}>创建的是私人草稿，只有你自己可见；要不要公开由你之后明确提交。</p>
    </form>
  );
}

/* ---------- 概览 ---------- */
function Overview({ go }: { go: (q: Record<string, string>) => void }) {
  const [active, setActive] = useState<Practice[] | null>(null);
  const [done, setDone] = useState<Practice[] | null>(null);
  const [chs, setChs] = useState<Challenge[] | null>(null);
  const [errs, setErrs] = useState<{ mine?: string; chs?: string }>({});
  const [joining, setJoining] = useState("");
  const seq = useRef(0);

  const load = useCallback(async () => {
    const s = ++seq.current;
    const [a, c, d] = await Promise.allSettled([
      practiceApi.listMine("active", 0, 1),
      practiceApi.challenges(),
      practiceApi.listMine("completed", 0, 5),
    ]);
    if (s !== seq.current) return;
    if (a.status === "fulfilled") setActive(a.value.items); else setErrs((p) => ({ ...p, mine: "实践列表暂时没取到" }));
    if (c.status === "fulfilled") setChs(c.value.items); else setErrs((p) => ({ ...p, chs: "共练列表暂时没取到" }));
    if (d.status === "fulfilled") setDone(d.value.items);
    if (a.status === "fulfilled" && c.status === "fulfilled") setErrs({});
  }, []);
  useEffect(() => { const t = setTimeout(() => void load(), 0); return () => { clearTimeout(t); seq.current += 1; }; }, [load]);

  const join = async (c: Challenge) => {
    if (joining) return;
    setJoining(c.id);
    try { const p = await practiceApi.join(c.id); go({ view: "mine", p: p.id }); }
    catch (e) { setErrs((x) => ({ ...x, chs: errText(e, "参加没成功，等会儿再试。") })); }
    finally { setJoining(""); }
  };

  const cur = active?.[0];
  return (
    <div>
      <Head kicker="概览" title="继续眼前的一件事" sub="私人实践只有你自己可见；提交到共练后其他已登录群友才看得到那一份快照。" />
      {errs.mine ? <p className={styles.notice}>{errs.mine}。<button type="button" onClick={() => void load()}>重试</button></p> : null}
      {active === null && !errs.mine ? <State text="正在读你的实践……" /> : cur ? (
        <div className={styles.continue}>
          <h3>{cur.title}</h3>
          <p className={styles.next}>{cur.next_step ? <>下一步：{cur.next_step}</> : <>目标：{cur.outcome}</>}</p>
          <div className={styles.acts}>
            <button type="button" className={styles.primary} onClick={() => go({ view: "mine", p: cur.id })}>继续这件事 →</button>
            <button type="button" className={styles.ghost} onClick={() => go({ view: "mine" })}>换一件</button>
          </div>
        </div>
      ) : (
        <CreateForm compact onCreated={(p) => go({ view: "mine", p: p.id })} />
      )}

      <div className={styles.block}>
        <Head kicker="一起练" title="进行中的共练" sub="参加会建一份关联的私人实践；只有你明确提交的成果才会对群友可见。" />
        {errs.chs ? <p className={styles.notice}>{errs.chs}。<button type="button" onClick={() => void load()}>重试</button></p>
          : chs === null ? <State text="正在读共练……" />
          : !chs.length ? <State text="现在没有进行中的共练。" />
          : (
            <ul className={styles.rows}>
              {chs.map((c) => (
                <li key={c.id}>
                  <button type="button" className={styles.row} onClick={() => go({ view: "challenges", c: c.id })}>
                    <span className={styles.rowTitle}>{c.title}{c.status === "closed" && <span className={`${styles.badge} ${styles.badgeClosed}`} style={{ marginLeft: ".4rem" }}>已结束</span>}</span>
                    <span className={styles.rowMeta}>{c.submission_count} 份成果</span>
                  </button>
                  {c.status === "open" && (
                    <div className={styles.blockTight}>
                      {c.my_practice_id
                        ? <button type="button" className={styles.textBtn} onClick={() => go({ view: "mine", p: c.my_practice_id as string })}>你已参加，继续你的实践 →</button>
                        : <button type="button" className={styles.textBtn} disabled={!!joining} onClick={() => void join(c)}>{joining === c.id ? "参加中…" : "参加这项共练 →"}</button>}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
      </div>

      {done && done.length > 0 && (
        <div className={styles.block}>
          <Head kicker="最近完成" title="做成了的事" sub="" extra={
            <button type="button" className={styles.textBtn} onClick={() => go({ view: "mine", status: "completed" })}>全部 →</button>} />
          <ul className={styles.rows}>
            {done.map((p) => (
              <li key={p.id}><button type="button" className={styles.row} onClick={() => go({ view: "mine", p: p.id, status: "completed" })}>
                <span className={styles.rowTitle}>{p.title}</span><span className={styles.rowMeta}>{fmt(p.updated_at)}</span>
              </button></li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/* ---------- 我的实践：列表 ---------- */
function MineList({ go, status, reading }: { go: (q: Record<string, string>) => void; status: string; reading: string | null }) {
  const [page, setPage] = useState<{ items: Practice[]; total: number } | null>(null);
  const [err, setErr] = useState("");
  const [creating, setCreating] = useState(false);
  const [createBusy, setCreateBusy] = useState(false); // 创建在途：禁收起/来源切换，防在写新字被在途响应跳走
  const [more, setMore] = useState(false);
  const seq = useRef(0);
  // 阅读来源预填：?reading=<id> → 静态索引白名单查条目；seq/Abort 守快速换 id 与卸载
  const [srcState, setSrcState] = useState<"idle" | "loading" | "ready" | "err" | "unknown">("idle");
  const [prefill, setPrefill] = useState<PracticeIndexEntry | null>(null);
  const srcSeq = useRef(0); const srcCtl = useRef<AbortController | null>(null);

  const loadIndex = useCallback(async (id: string) => {
    const s = ++srcSeq.current;
    srcCtl.current?.abort();
    const c = new AbortController(); srcCtl.current = c;
    setSrcState("loading"); setPrefill(null);
    try {
      const res = await fetch("/readings/practice-index.json", { signal: c.signal, cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const idx = parsePracticeIndex(await res.json());
      if (!idx) throw new Error("索引格式不对");
      if (s !== srcSeq.current) return; // 过期响应作废
      const e = practiceIndexFor(idx, id);
      if (!e) { setSrcState("unknown"); return; }
      setPrefill(e); setSrcState("ready"); setCreating(true);
    } catch (e2) {
      if (e2 instanceof DOMException && e2.name === "AbortError") return;
      if (s === srcSeq.current) setSrcState("err");
    }
  }, []);
  useEffect(() => {
    const t = window.setTimeout(() => {
      if (!reading) { setSrcState("idle"); setPrefill(null); return; }
      void loadIndex(reading);
    }, 0);
    return () => { window.clearTimeout(t); srcSeq.current += 1; srcCtl.current?.abort(); };
  }, [reading, loadIndex]);

  const load = useCallback(async (offset = 0, append = false) => {
    const s = ++seq.current;
    try {
      const d = await practiceApi.listMine(status as PracticeStatus | "all", offset, 20);
      if (s !== seq.current) return;
      setPage((prev) => append && prev ? { items: [...prev.items, ...d.items], total: d.total } : d);
      setErr("");
    } catch (e) { if (s === seq.current) setErr(errText(e, "列表暂时没取到")); }
  }, [status]);
  useEffect(() => { const t = setTimeout(() => { setPage(null); setErr(""); void load(); }, 0); return () => { clearTimeout(t); seq.current += 1; }; }, [load]);

  const tabs: { id: string; label: string }[] = [
    { id: "active", label: "进行中" }, { id: "completed", label: "已完成" }, { id: "archived", label: "已归档" }, { id: "all", label: "全部" },
  ];
  return (
    <div>
      <Head kicker="我的实践" title="目标与过程" sub="每一条都是私人草稿；完成项就是你的作品档案。" extra={
        <button type="button" className={styles.ghost} disabled={createBusy} onClick={() => setCreating((v) => !v)}>{creating ? "收起" : "＋ 新目标"}</button>} />
      <div className={styles.tabs} role="tablist">
        {tabs.map((t) => <button key={t.id} type="button" role="tab" aria-selected={status === t.id}
          className={`${styles.tab} ${status === t.id ? styles.tabOn : ""}`} onClick={() => go({ view: "mine", status: t.id })}>{t.label}</button>)}
      </div>
      {reading && srcState === "loading" && <p className={styles.notice}>正在按来源准备练习预填……</p>}
      {reading && (srcState === "err" || srcState === "unknown") && (
        <p className={styles.notice}>
          {srcState === "err" ? "来源索引暂时没取到" : "这个来源没在精读索引里"}——
          <button type="button" disabled={createBusy} onClick={() => void loadIndex(reading)}>重试</button>，或
          <button type="button" disabled={createBusy} onClick={() => go({ view: "mine" })}>不用来源直接新建</button>。
        </p>
      )}
      {creating && <CreateForm prefill={srcState === "ready" ? prefill : null} onBusy={setCreateBusy} onCreated={(p) => go({ view: "mine", p: p.id })} />}
      {err ? <p className={styles.notice}>{err}。<button type="button" onClick={() => void load()}>重试</button></p>
        : page === null ? <State text="正在读列表……" />
        : !page.items.length ? <State text={status === "active" ? "现在没有进行中的实践——点右上「新目标」开一件。" : "这个状态下还没有记录。"} />
        : (
          <>
            <ul className={styles.rows}>
              {page.items.map((p) => (
                <li key={p.id}>
                  <button type="button" className={styles.row} onClick={() => go({ view: "mine", p: p.id, status })}>
                    <span className={styles.rowTitle}>{p.title}
                      {status === "all" && <span className={`${styles.badge} ${STATUS_BADGE[p.status]}`} style={{ marginLeft: ".4rem" }}>{STATUS_LABEL[p.status]}</span>}
                      {p.next_step && <span className={styles.rowStep}>下一步：{p.next_step}</span>}
                    </span>
                    <span className={styles.rowMeta}>{fmt(p.updated_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
            {page.items.length < page.total && (
              <div className={styles.blockTight}>
                <button type="button" className={styles.textBtn} disabled={more}
                  onClick={() => { setMore(true); void load(page.items.length, true).finally(() => setMore(false)); }}>
                  {more ? "加载中…" : `加载更多（还有 ${page.total - page.items.length} 条）`}
                </button>
              </div>
            )}
            <p className={styles.hint}>共 {page.total} 条{page.items.length < page.total ? `，已显示前 ${page.items.length} 条` : ""}。</p>
          </>
        )}
    </div>
  );
}

/* ---------- 我的实践：详情 ---------- */
function PracticeDetail({ id, go }: { id: string; go: (q: Record<string, string>) => void }) {
  const { user } = useAuth();
  const who = user?.username || "me";
  const [p, setP] = useState<Practice | null>(null);
  const [err, setErr] = useState("");
  const [form, setForm] = useState<Record<string, string> | null>(null);
  const [conflict, setConflict] = useState(false);
  const [busy, setBusy] = useState(""); const [msg, setMsg] = useState("");
  const [draftNote, setDraftNote] = useState(false);
  const [submitOpen, setSubmitOpen] = useState(false);
  const [subBody, setSubBody] = useState(""); const [subUrl, setSubUrl] = useState("");
  const [subPreview, setSubPreview] = useState(false);
  const [subNote, setSubNote] = useState("");
  const seq = useRef(0);

  const load = useCallback(async () => {
    const s = ++seq.current;
    try {
      const d = await practiceApi.get(id);
      if (s !== seq.current) return;
      setP(d); setErr(""); setConflict(false);
      const mem = drafts.get(draftKey(who, id));
      setForm(mem ?? { title: d.title, outcome: d.outcome, next_step: d.next_step, notes: d.notes, result_url: d.result_url });
      setDraftNote(!!mem);
    } catch (e) { if (s === seq.current) setErr(errText(e, "这条实践暂时读不到")); }
  }, [id, who]);
  useEffect(() => { const t = setTimeout(() => void load(), 0); return () => { clearTimeout(t); seq.current += 1; }; }, [load]);

  const set = (k: string, v: string) => {
    const next = { ...(form ?? {}), [k]: v };
    setForm(next);
    saveDraft(who, id, next);
  };
  const dirty = !!form && !!p && ["title", "outcome", "next_step", "notes", "result_url"].some((k) => form[k] !== String(p[k as keyof Practice] ?? ""));

  const save = async () => {
    if (!p || !form || busy || !dirty) return;
    setBusy("save"); setErr(""); setMsg("");
    const fields: Record<string, string> = {};
    for (const k of ["title", "outcome", "next_step", "notes", "result_url"]) {
      if (form[k] !== String(p[k as keyof Practice] ?? "")) fields[k] = form[k];
    }
    try {
      const d = await practiceApi.patch(p.id, p.revision, fields);
      setP(d); setConflict(false); setMsg("已保存。"); drafts.delete(draftKey(who, id)); setDraftNote(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setConflict(true);
      else setErr(errText(e, "没存上，再试一次。")); // 失败保稿：form 原样留着
    } finally { setBusy(""); }
  };
  const reloadLatest = async () => { drafts.delete(draftKey(who, id)); setDraftNote(false); setForm(null); await load(); };

  const setStatus = async (status: PracticeStatus) => {
    if (!p || busy) return;
    setBusy(status); setErr(""); setMsg("");
    try { const d = await practiceApi.patch(p.id, p.revision, { status }); setP(d); setMsg(status === "completed" ? "已完成，收进你的档案。" : "已更新。"); }
    catch (e) {
      if (e instanceof ApiError && e.status === 409) setConflict(true);
      else setErr(errText(e, "操作没成功。"));
    } finally { setBusy(""); }
  };

  // 与后端 _text/_url 规范化对齐：多行正文 \r\n→\n、剥行内控制符、trim；链接仅 trim
  const normBody = (v: string) => v.replace(/\r\n/g, "\n").replace(/\r/g, "\n").replace(/[\x00-\x09\x0b-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2060\ufeff]/g, "").trim();
  const normUrl = (v: string) => v.trim();

  const submitTo = async () => {
    if (!p || !subBody.trim() || busy) return;
    // 实践有未保存修改时先拦住：快照会带旧标题/旧 revision，用户以为新版已发
    if (dirty) { setSubNote("实践里有还没保存的修改——先保存出新版本，再提交，快照才带上它。"); return; }
    setBusy("submit"); setErr(""); setSubNote("");
    // 发起前捕获本次规范化内容：同 revision 重复提交时后端幂等返回旧快照，正文可能不同
    const wantBody = normBody(subBody);
    const wantUrl = normUrl(subUrl);
    try {
      const s = await practiceApi.submit(p.id, p.revision, subBody.trim(), subUrl.trim() || undefined);
      if (s.body !== wantBody || s.result_url !== wantUrl) {
        // 幂等重放旧快照：不清编辑器/预览/草稿、不跳转——否则用户以为新写的已发出且稿被吞
        setSubNote("这一版已经提交过了（跳过去看到的是旧快照）。你新写的内容还在下面——先把实践的新进展保存出新版本，再来提交。");
        setSubPreview(false); // 回到编辑态，稿子原样保留
        return;
      }
      setSubPreview(false); setSubmitOpen(false); setSubBody(""); setSubUrl("");
      go({ view: "challenges", c: p.challenge_id as string, s: s.id });
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setConflict(true);
      else setErr(errText(e, "提交没成功，文字还在。"));
    } finally { setBusy(""); }
  };

  if (err && !p) return <State text={err} onRetry={() => void load()} />;
  if (!p || !form) return <State text="正在读这条实践……" />;

  return (
    <div>
      <Head kicker="我的实践" title={p.title} sub="" extra={
        <button type="button" className={styles.textBtn} onClick={() => go({ view: "mine" })}>← 返回列表</button>} />
      <div className={styles.detailMeta}>
        <span className={`${styles.badge} ${STATUS_BADGE[p.status]}`}>{STATUS_LABEL[p.status]}</span>
        <span>更新于 {fmt(p.updated_at)}</span>
        {p.challenge_id && <button type="button" className={styles.textBtn} onClick={() => go({ view: "challenges", c: p.challenge_id as string })}>所属共练 →</button>}
      </div>
      {draftNote && <p className={styles.notice}>恢复了你上次没保存的草稿。不想要就<button type="button" onClick={() => void reloadLatest()}>丢掉，载入已存版本</button>。</p>}
      {conflict && (
        <p className={styles.notice}>这条实践在你打开后被改过了（版本冲突）。你的修改还在，没有丢——
          <button type="button" onClick={() => void reloadLatest()}>放弃修改，载入最新版</button>再看。
        </p>
      )}
      {err && <p className={styles.err}>{err}</p>}
      {msg && <p className={styles.ok}>{msg}</p>}

      <div className={styles.detail}>
        <label className={styles.fieldLabel}>标题
          <input className={styles.input} maxLength={120} value={form.title} onChange={(e) => set("title", e.target.value)} /></label>
        <label className={styles.fieldLabel}>做到什么算完成
          <textarea className={styles.area} maxLength={1000} rows={2} value={form.outcome} onChange={(e) => set("outcome", e.target.value)} /></label>
        <label className={styles.fieldLabel}>下一步
          <input className={styles.input} maxLength={1000} value={form.next_step} onChange={(e) => set("next_step", e.target.value)} /></label>
        <label className={styles.fieldLabel}>过程记录 / 笔记
          <textarea className={styles.area} maxLength={20000} rows={5} value={form.notes} onChange={(e) => set("notes", e.target.value)} placeholder="进展、卡住的地方、试过的办法……" /></label>
        <label className={styles.fieldLabel}>成果链接（可选）
          <input className={styles.input} maxLength={2000} value={form.result_url} onChange={(e) => set("result_url", e.target.value)} placeholder="https:// 或站内 / 路径" /></label>
        <div className={styles.acts}>
          <button type="button" className={styles.primary} disabled={!dirty || !!busy} onClick={() => void save()}>{busy === "save" ? "保存中…" : dirty ? "保存修改" : "没有改动"}</button>
          {p.status === "active" && <button type="button" className={styles.ghost} disabled={!!busy} onClick={() => void setStatus("completed")}>{busy === "completed" ? "处理中…" : "标记完成"}</button>}
          {p.status === "completed" && <button type="button" className={styles.ghost} disabled={!!busy} onClick={() => void setStatus("active")}>恢复进行中</button>}
          {p.status !== "archived" && <button type="button" className={styles.ghost} disabled={!!busy} onClick={() => void setStatus("archived")}>归档</button>}
          {p.status === "archived" && <button type="button" className={styles.ghost} disabled={!!busy} onClick={() => void setStatus("active")}>取消归档</button>}
        </div>
      </div>

      {p.challenge_id && p.status === "active" && (
        <div className={styles.block}>
          <Head kicker="提交到共练" title="把成果发给一起练的人" sub="提交的是一份独立快照：之后你改自己的草稿不会影响已发出的内容。" />
          {!submitOpen ? (
            <div className={styles.acts}><button type="button" className={styles.ghost} onClick={() => setSubmitOpen(true)}>写一份提交 →</button></div>
          ) : (
            <div className={styles.detail}>
              {subNote && <p className={styles.notice}>{subNote}</p>}
              <MarkdownComposer value={subBody} onChange={(v) => { setSubBody(v); if (subNote) setSubNote(""); }} label="这次要展示的成果 / 过程（1–20000 字，支持加粗/列表/引用/代码/链接）" placeholder="做了什么、结果如何、想请大家看什么" maxLength={20000} rows={5} disabled={!!busy} />
              <label className={styles.fieldLabel}>成果链接（可选）
                <input className={styles.input} value={subUrl} onChange={(e) => setSubUrl(e.target.value)} disabled={!!busy} placeholder="https:// 或站内 / 路径" /></label>
              {!subPreview ? (
                <div className={styles.acts}>
                  <button type="button" className={styles.primary} disabled={!subBody.trim() || !!busy} onClick={() => setSubPreview(true)}>预览并确认 →</button>
                  <button type="button" className={styles.ghost} disabled={!!busy} onClick={() => setSubmitOpen(false)}>先不发了</button>
                </div>
              ) : (
                <div className={styles.detail}>
                  <p className={styles.hint}>预览：以下内容将以你的群昵称署名，<b>所有已登录群友可见</b>。你的其他草稿和随手记不会附带。</p>
                  <div className={styles.previewBox}><RichMessage text={subBody} /></div>
                  <p className={styles.previewUrl}>附加链接：{subUrl.trim() ? <a href={subUrl.trim()} target="_blank" rel="noreferrer noopener">{subUrl.trim()}</a> : "无"}</p>
                  <div className={styles.acts}>
                    <button type="button" className={styles.primary} disabled={!!busy} onClick={() => void submitTo()}>{busy === "submit" ? "提交中…" : "确认提交到共练"}</button>
                    <button type="button" className={styles.ghost} disabled={!!busy} onClick={() => setSubPreview(false)}>回去再改</button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------- 共练：列表 + 展开 ---------- */
function ChallengeList({ go, openId }: { go: (q: Record<string, string>) => void; openId: string | null }) {
  const [chs, setChs] = useState<Challenge[] | null>(null);
  const [err, setErr] = useState("");
  const [joining, setJoining] = useState("");
  const seq = useRef(0);
  const load = useCallback(async () => {
    const s = ++seq.current;
    try { const d = await practiceApi.challenges(); if (s === seq.current) { setChs(d.items); setErr(""); } }
    catch (e) { if (s === seq.current) setErr(errText(e, "共练列表暂时没取到")); }
  }, []);
  useEffect(() => { const t = setTimeout(() => void load(), 0); return () => { clearTimeout(t); seq.current += 1; }; }, [load]);

  const join = async (c: Challenge) => {
    if (joining) return;
    setJoining(c.id); setErr("");
    try { const p = await practiceApi.join(c.id); go({ view: "mine", p: p.id }); }
    catch (e) { setErr(errText(e, "参加没成功。")); } finally { setJoining(""); }
  };

  return (
    <div>
      <Head kicker="共练" title="一起练的项目" sub="参加后建一份关联的私人实践；你提交的快照对全部已登录群友可见。" />
      {err ? <p className={styles.notice}>{err}<button type="button" onClick={() => void load()}>重试</button></p>
        : chs === null ? <State text="正在读共练……" />
        : !chs.length ? <State text="现在没有进行中的共练。" />
        : (
          <ul className={styles.rows}>
            {chs.map((c) => (
              <li key={c.id}>
                <button type="button" className={styles.row} onClick={() => go({ view: "challenges", c: openId === c.id ? "" : c.id })} aria-expanded={openId === c.id}>
                  <span className={styles.rowTitle}>{c.title}{c.status === "closed" && <span className={`${styles.badge} ${styles.badgeClosed}`} style={{ marginLeft: ".4rem" }}>已结束</span>}
                    <span className={styles.rowStep}>{c.summary}</span></span>
                  <span className={styles.rowMeta}>{c.submission_count} 份成果 {openId === c.id ? "▴" : "▾"}</span>
                </button>
                {openId === c.id && <ChallengeDetail c={c} go={go} joining={joining} onJoin={() => void join(c)} />}
              </li>
            ))}
          </ul>
        )}
    </div>
  );
}

function ChallengeDetail({ c, go, joining, onJoin }: { c: Challenge; go: (q: Record<string, string>) => void; joining: string; onJoin: () => void }) {
  const [subs, setSubs] = useState<{ items: Submission[]; total: number } | null>(null);
  const [err, setErr] = useState("");
  const [more, setMore] = useState(false);
  const seq = useRef(0);
  const load = useCallback(async (offset = 0, append = false) => {
    const s = ++seq.current;
    try {
      const d = await practiceApi.submissions(c.id, offset, 20);
      if (s === seq.current) { setSubs((prev) => append && prev ? { items: [...prev.items, ...d.items], total: d.total } : d); setErr(""); }
    } catch (e) { if (s === seq.current) setErr(errText(e, "成果列表没取到")); }
  }, [c.id]);
  useEffect(() => { const t = setTimeout(() => void load(), 0); return () => { clearTimeout(t); seq.current += 1; }; }, [load]);

  return (
    <div className={styles.detail}>
      {c.instructions.length > 0 && <ol className={styles.instructions}>{c.instructions.map((s, i) => <li key={i}>{s}</li>)}</ol>}
      {c.outcome && <p className={styles.hint}>做到算数：{c.outcome}</p>}
      <div className={styles.acts}>
        {c.status === "open" && (c.my_practice_id
          ? <button type="button" className={styles.primary} onClick={() => go({ view: "mine", p: c.my_practice_id as string })}>继续我的实践 →</button>
          : <button type="button" className={styles.primary} disabled={!!joining} onClick={onJoin}>{joining === c.id ? "参加中…" : "参加这项共练"}</button>)}
      </div>
      <div className={styles.blockTight}>
        {err ? <p className={styles.notice}>{err}<button type="button" onClick={() => void load()}>重试</button></p>
          : subs === null ? <State text="正在读成果……" />
          : !subs.items.length ? <State text="还没有人提交——你可以是第一个。" />
          : (
            <ul className={styles.rows}>
              {subs.items.map((s) => (
                <li key={s.id}><button type="button" className={styles.row} onClick={() => go({ view: "challenges", c: c.id, s: s.id })}>
                  <span className={styles.rowTitle}>{s.title}{s.is_mine && <span className={styles.badge} style={{ marginLeft: ".4rem" }}>我的</span>}</span>
                  <span className={styles.rowMeta}><SpeakerIdentity name={s.author.name} kind="human" size={32} /><span className="ml-1.5">{fmt(s.created_at)} · {s.reply_count} 回复</span></span>
                </button></li>
              ))}
            </ul>
          )}
        {subs && subs.items.length < subs.total && (
          <div className={styles.blockTight}>
            <button type="button" className={styles.textBtn} disabled={more}
              onClick={() => { setMore(true); void load(subs.items.length, true).finally(() => setMore(false)); }}>
              {more ? "加载中…" : `加载更多成果（还有 ${subs.total - subs.items.length} 份）`}
            </button>
          </div>
        )}
        {subs && <p className={styles.hint}>共 {subs.total} 份成果，已显示 {subs.items.length} 份。</p>}
      </div>
    </div>
  );
}

/* ---------- 提交详情 + 回复 ---------- */
function SubmissionView({ id, go }: { id: string; go: (q: Record<string, string>) => void }) {
  const [s, setS] = useState<Submission | null>(null);
  const [reps, setReps] = useState<{ items: Reply[]; total: number } | null>(null);
  const [err, setErr] = useState(""); const [repErr, setRepErr] = useState("");
  const [text, setText] = useState(""); const [busy, setBusy] = useState(false);
  const [more, setMore] = useState(false);
  // client_id 惰性生成：重试复用同一个（幂等），发送成功后才换下一份的 id
  const clientId = useRef<string | null>(null);
  const newClientId = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);
  const seq = useRef(0);

  const load = useCallback(async () => {
    const cur = ++seq.current;
    const [a, b] = await Promise.allSettled([practiceApi.submission(id), practiceApi.replies(id)]);
    if (cur !== seq.current) return;
    if (a.status === "fulfilled") { setS(a.value); setErr(""); } else setErr(errText(a.reason, "这份成果读不到"));
    if (b.status === "fulfilled") setReps(b.value); else setRepErr("回复列表没取到");
  }, [id]);
  useEffect(() => { const t = setTimeout(() => void load(), 0); return () => { clearTimeout(t); seq.current += 1; }; }, [load]);

  const loadMoreReplies = async () => {
    if (!reps || more) return;
    setMore(true); setRepErr("");
    try {
      const d = await practiceApi.replies(id, reps.items.length, 20);
      setReps((prev) => prev ? { items: [...prev.items, ...d.items], total: d.total } : d);
    } catch (e) { setRepErr(errText(e, "更多回复没取到")); } finally { setMore(false); }
  };

  const send = async () => {
    if (!text.trim() || busy) return;
    setBusy(true); setRepErr("");
    try {
      clientId.current ??= newClientId();
      await practiceApi.reply(id, text.trim(), clientId.current);
      clientId.current = null;
      setText("");
      await load();
    } catch (e) { setRepErr(errText(e, "回复没发出去，文字还在。")); } finally { setBusy(false); }
  };

  return (
    <div>
      <Head kicker="共练成果" title={s ? s.title : "成果详情"} sub="" extra={
        <button type="button" className={styles.textBtn} onClick={() => go({ view: "challenges", c: s?.challenge_id ?? "" })}>← 回共练</button>} />
      {err && !s ? <State text={err} onRetry={() => void load()} /> : !s ? <State text="正在读成果……" /> : (
        <>
          <div className={styles.detailMeta}>
            <SpeakerIdentity name={s.author.name} kind="human" size={32} />
            <span>{fmt(s.created_at)}</span><span>v{s.revision}</span>
            {s.is_mine && <span className={styles.badge}>我的提交</span>}
          </div>
          <div className={styles.detail}>
            <RichMessage text={s.body} className="text-[0.95rem] leading-[1.85] text-ink-2" />
            {s.result_url && <p className={styles.hint}>成果链接：<a href={s.result_url} className="text-blue-text underline underline-offset-2">{s.result_url}</a></p>}
          </div>
          <div className={styles.block}>
            <Head kicker="反馈" title={`回复 ${reps ? `（${reps.total}）` : ""}`} sub="" />
            {repErr && <p className={styles.notice}>{repErr}<button type="button" onClick={() => void load()}>重试</button></p>}
            {reps === null ? <State text="正在读回复……" /> : !reps.items.length ? <State text="还没有回复。" /> : (
              <div>{reps.items.map((r) => (
                <div key={r.id} className={styles.reply}>
                  <div className={styles.replyHead}><SpeakerIdentity name={r.author.name} kind="human" size={32} /><span className="ml-1.5">{fmt(r.created_at)}</span></div>
                  <RichMessage text={r.text} />
                </div>
              ))}</div>
            )}
            {reps && reps.items.length < reps.total && (
              <div className={styles.blockTight}>
                <button type="button" className={styles.textBtn} disabled={more} onClick={() => void loadMoreReplies()}>
                  {more ? "加载中…" : `加载更多回复（还有 ${reps.total - reps.items.length} 条）`}
                </button>
              </div>
            )}
            <div className={styles.detail}>
              <MarkdownComposer value={text} onChange={setText} label="写回复（1–4000 字，支持排版）" placeholder="看完成果，说说具体哪点有用、哪里可以再改" maxLength={4000} rows={3} />
              <div className={styles.acts}>
                <button type="button" className={styles.primary} disabled={!text.trim() || busy} onClick={() => void send()}>{busy ? "发送中…" : "回复"}</button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/* ---------- 入口 ---------- */
export function GrowthWorkspace() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname() || "/me/";
  const view = params.get("view") || "overview";
  const go = useCallback((q: Record<string, string>) => {
    const next = new URLSearchParams(params.toString());
    // reading 是一次性创建意图：任何导航（含创建成功落详情）都清掉，不残留
    for (const k of ["p", "c", "s", "status", "reading"]) next.delete(k);
    for (const [k, v] of Object.entries(q)) { if (v) next.set(k, v); else next.delete(k); }
    router.push(`${pathname}?${next.toString()}`);
  }, [params, pathname, router]);

  if (view === "mine") {
    const p = params.get("p");
    const raw = params.get("status") || "active";
    const status = ["active", "completed", "archived", "all"].includes(raw) ? raw : "active";
    // key=id：URL 快速换条目时整棵重挂载，旧详情/表单/提交状态不残留到新条目
    // 优先级：?p 已有详情 > reading 来源预填——详情在前，预填只在列表态生效
    return p ? <PracticeDetail key={p} id={p} go={go} /> : <MineList go={go} status={status} reading={params.get("reading")} />;
  }
  if (view === "challenges") {
    const s = params.get("s");
    return s ? <SubmissionView key={s} id={s} go={go} /> : <ChallengeList go={go} openId={params.get("c")} />;
  }
  return <Overview go={go} />;
}
