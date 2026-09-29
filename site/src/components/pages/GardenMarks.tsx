"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/auth";
import { newClientId } from "@/lib/garden";
import {
  gardenMarksApi,
  type OwnerMark, type OwnerMarks, type VisitorMark, type VisitorMarks,
} from "@/lib/garden-marks";
import { practiceApi, type Practice } from "@/lib/practice";
import styles from "./GardenMarks.module.css";

/* Design Contract（≤10 行）
   屏职：家园里的一段「成果木牌」——主人把已完成的练习以标题+阅读来源挂在院里；访客只读。
   主操作：选一条已完成练习→挂牌（默认仅自己可见）→预览公开字段→确认「展示给群友」。
   层级：木牌条列表（最多 max_marks 块，含仅自己可见）＞挂牌/展示确认条＞练习选择器。
   必备态：读取中/失败重试/未开通小院/空/满额/pending 禁重/确认中/失败保留状态。
   禁：奖励/积分话术、自动公开、正文/笔记外露、四张大卡片、无限动效、固定轮询。 */

const errText = (e: unknown, fb: string) => (e instanceof ApiError ? e.message : fb);
const isAbort = (e: unknown, s: AbortSignal) => s.aborted || (e instanceof ApiError && e.status === 0 && /取消/.test(e.message));
const md = (iso: string) => { const m = /^\d{4}-(\d{2})-(\d{2})/.exec(iso); return m ? `${+m[1]}/${+m[2]}` : ""; };
/** 只把本站精读路径渲染成链接（后端已校验，这里再兜一层）。 */
const readingHref = (u: string | null) => (u && /^\/readings\/(books\/)?[\w.-]+\/$/.test(u) ? u : null);
const PAGE = 10;

type Step = { kind: "create"; practice: Practice } | { kind: "show" | "hide" | "remove"; mark: OwnerMark } | null;
interface View { key: string; owner?: OwnerMarks; visitor?: VisitorMarks }

function Source({ title, url }: { title: string; url: string | null }) {
  if (!title && !url) return null;
  const href = readingHref(url);
  const label = title || "阅读来源";
  return <span className={styles.src}>读自 {href ? <Link href={href}>{label}</Link> : label}</span>;
}

/** 家园成果木牌。父级传 gardenId/isMine；revisionKey 变化时重拉，无固定轮询。 */
export default function GardenMarks({ gardenId, isMine, revisionKey }: { gardenId: string | null; isMine: boolean; revisionKey?: string }) {
  const key = `${isMine ? "m" : "v"}:${gardenId ?? ""}`;
  const idle = !isMine && !gardenId;
  const [view, setView] = useState<View | null>(null);
  const [loading, setLoading] = useState(!idle);
  const [err, setErr] = useState<{ key: string; text: string } | null>(null);
  const [note, setNote] = useState("");
  const [fail, setFail] = useState("");
  const [busy, setBusy] = useState("");
  const [step, setStep] = useState<Step>(null);
  const [picker, setPicker] = useState<{ open: boolean; items: Practice[]; total: number; loading: boolean; err: string }>(
    { open: false, items: [], total: 0, loading: false, err: "" },
  );
  const seq = useRef(0);
  const ctl = useRef<AbortController | null>(null);
  const busyRef = useRef(false);
  const ids = useRef<Record<string, string>>({});
  const pctl = useRef<AbortController | null>(null);
  const pseq = useRef(0);

  const fetchData = useCallback(async () => {
    ctl.current?.abort();
    if (idle) return;
    const c = new AbortController();
    ctl.current = c;
    const mine = ++seq.current;
    try {
      const v: View = isMine
        ? { key, owner: await gardenMarksApi.mine(c.signal) }
        : { key, visitor: await gardenMarksApi.visit(gardenId as string, c.signal) };
      if (mine === seq.current) { setView(v); setErr(null); }
    } catch (e) {
      if (mine !== seq.current || isAbort(e, c.signal)) return;
      setErr({ key, text: errText(e, "读不到院里的木牌。") });
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, [key, idle, isMine, gardenId]);

  useEffect(() => {
    // 首屏/换园/换 key 拉取：setState 都在 await 之后
    void fetchData();
    const seqRef = seq, ctlRef = ctl, pRef = pctl, psRef = pseq;
    return () => { seqRef.current++; ctlRef.current?.abort(); psRef.current++; pRef.current?.abort(); };
  }, [fetchData, revisionKey]);

  const cur = view && view.key === key ? view : null;
  const curErr = err && err.key === key ? err.text : "";
  const reload = () => { setLoading(true); setErr(null); void fetchData(); };

  /** 一次 mutation：同意图复用 client_id（0/5xx 重试同 id），4xx 确定失败则换新意图。 */
  const run = async (intent: string, call: (cid: string) => Promise<OwnerMarks>, ok: string) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(intent); setNote(""); setFail("");
    const cid = (ids.current[intent] ??= newClientId());
    try {
      const r = await call(cid);
      delete ids.current[intent];
      seq.current++; ctl.current?.abort(); setLoading(false);
      setView({ key, owner: { garden_id: r.garden_id, max_marks: r.max_marks, items: r.items } });
      setStep(null); setNote(ok);
    } catch (e) {
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) delete ids.current[intent];
      const st = e instanceof ApiError ? e.status : 0;
      // 0/5xx：服务端可能已成功，不能说“没变”；保留 client_id，再点一次即安全确认
      setFail(st === 0 || st >= 500 ? "结果暂未确认，请重试确认（同一操作不会重复）。" : errText(e, "没成功，请刷新后再试。"));
      if (st === 404 || st === 409) { setStep(null); void fetchData(); } // 旧确认条带旧 revision，失效需重选
    } finally {
      busyRef.current = false;
      setBusy("");
    }
  };

  const loadPractices = async (offset: number) => {
    pctl.current?.abort();
    const c = new AbortController();
    pctl.current = c;
    const mine = ++pseq.current;
    setPicker((p) => ({ ...p, open: true, loading: true, err: "" }));
    try {
      const r = await practiceApi.listMine("completed", offset, PAGE, c.signal);
      if (c.signal.aborted || mine !== pseq.current) return; // 已收起/换请求：迟到响应不得重开
      setPicker((p) => ({ open: true, items: offset ? [...p.items, ...r.items] : r.items, total: r.total, loading: false, err: "" }));
    } catch (e) {
      if (isAbort(e, c.signal) || mine !== pseq.current) return;
      setPicker((p) => ({ ...p, loading: false, err: errText(e, "读不到你的练习。") }));
    }
  };
  const togglePicker = () => {
    if (picker.open) { pseq.current++; pctl.current?.abort(); setPicker((p) => ({ ...p, open: false, loading: false })); return; }
    setStep(null);
    void loadPractices(0);
  };

  /* ───── 访客只读 ───── */
  if (!isMine) {
    const items: VisitorMark[] = cur?.visitor?.items ?? [];
    if (idle || (!items.length && !curErr)) return null;
    return (
      <section className={styles.box} aria-labelledby="gm-title" aria-busy={loading}>
        <h3 id="gm-title" className={styles.h3}>院里的成果 <small>群友挂出的练习</small></h3>
        {curErr && <p className={styles.err}>{curErr}<button type="button" className={styles.linkBtn} onClick={reload}>重试</button></p>}
        <ul className={styles.list}>
          {items.map((m) => (
            <li key={m.id} className={styles.row}>
              <span className={styles.title}>{m.title}</span>
              <Source title={m.source_title} url={m.source_url} />
              <span className={styles.meta}>{md(m.created_at)}</span>
            </li>
          ))}
        </ul>
      </section>
    );
  }

  /* ───── 主人 ───── */
  const owner = cur?.owner;
  const items = owner?.items ?? [];
  const max = owner?.max_marks ?? 0;
  const full = !!owner && items.length >= max;
  const marked = new Set(items.map((m) => m.practice_id));
  const hasGarden = !owner || owner.garden_id !== null;
  // 确认条只对“当前真值里仍是同一 revision 的木牌 / 尚未挂的练习”有效，刷新后旧条自动失效
  const stepOk = !step ? null : step.kind === "create"
    ? (marked.has(step.practice.id) ? null : step)
    : (items.some((m) => m.id === step.mark.id && m.revision === step.mark.revision) ? step : null);

  return (
    <section className={styles.box} aria-labelledby="gm-title" aria-busy={loading}>
      <h3 id="gm-title" className={styles.h3}>院里的成果{owner && <small>{items.length}/{max}</small>}</h3>
      <p className={styles.hint}>只挂标题和阅读来源，练习正文仍然私密。挂上后默认只有你自己看得到，确认后才展示给群友。</p>

      {curErr && !owner && <div className={styles.state}>{curErr}<button type="button" className={styles.linkBtn} onClick={reload}>重试</button></div>}
      {!owner && !curErr && <div className={styles.state}>正在读取……</div>}
      {curErr && owner && <p className={styles.err}>{curErr}<button type="button" className={styles.linkBtn} onClick={reload}>重试</button></p>}
      {owner && !hasGarden && <p className={styles.state}>先开通小院，才能在院里挂木牌。</p>}

      {owner && hasGarden && (
        <>
          {items.length === 0 && <p className={styles.state}>还没有木牌。做完一条练习，就能把它挂在这里。</p>}
          <ul className={styles.list}>
            {items.map((m) => (
              <li key={m.id} className={`${styles.row} ${m.shown ? styles.rowShown : ""}`}>
                <div className={styles.rowHead}>
                  <span className={styles.title}>{m.title}</span>
                  <span className={`${styles.chip} ${m.shown ? styles.chipShown : ""}`}>{m.shown ? "已设为展示" : "仅自己可见"}</span>
                </div>
                <Source title={m.source_title} url={m.source_url} />
                <div className={styles.actions}>
                  {m.shown
                    ? <button type="button" className={styles.btn} disabled={!!busy} onClick={() => setStep({ kind: "hide", mark: m })}>收回为仅自己可见</button>
                    : <button type="button" className={styles.btn} disabled={!!busy} onClick={() => setStep({ kind: "show", mark: m })}>展示给群友</button>}
                  <button type="button" className={styles.btnQuiet} disabled={!!busy} onClick={() => setStep({ kind: "remove", mark: m })}>撤下</button>
                </div>
              </li>
            ))}
          </ul>
          {items.some((m) => m.shown) && <p className={styles.hint}>「已设为展示」仍遵循院门设置：院门关着时，群友看不到任何木牌。</p>}

          {stepOk && stepOk.kind !== "create" && (
            <div className={styles.confirm} role="group" aria-label="确认操作">
              {stepOk.kind === "show" && (
                <>
                  <p className={styles.confirmText}>群友将看到：</p>
                  <p className={styles.preview}><strong>{stepOk.mark.title}</strong><Source title={stepOk.mark.source_title} url={stepOk.mark.source_url} /></p>
                  <p className={styles.hint}>不会公开：练习正文、笔记、成果链接。仍遵循院门设置——院门关着时群友看不到。随时可以收回。</p>
                </>
              )}
              {stepOk.kind === "hide" && <p className={styles.confirmText}>收回后，群友看不到「{stepOk.mark.title}」，木牌仍留在你的院里。</p>}
              {stepOk.kind === "remove" && <p className={styles.confirmText}>撤下「{stepOk.mark.title}」？只撤木牌，练习本身不会被删除。</p>}
              <div className={styles.actions}>
                <button
                  type="button" className={styles.primary} disabled={!!busy}
                  onClick={() => {
                    const m = stepOk.mark;
                    if (stepOk.kind === "remove") void run(`del:${m.id}`, (c) => gardenMarksApi.remove(m.id, c), "已撤下，练习还在。");
                    else {
                      const shown = stepOk.kind === "show";
                      void run(`vis:${m.id}:${shown}:${m.revision}`, (c) => gardenMarksApi.setShown(m.id, shown, m.revision, c), shown ? "已设为展示（院门开着时群友可见）。" : "已收回，仅自己可见。");
                    }
                  }}
                >{busy ? "处理中……" : stepOk.kind === "show" ? "确认展示给群友" : stepOk.kind === "hide" ? "确认收回" : "确认撤下"}</button>
                <button type="button" className={styles.btnQuiet} disabled={!!busy} onClick={() => setStep(null)}>先不了</button>
              </div>
            </div>
          )}

          {stepOk?.kind === "create" && (
            <div className={styles.confirm} role="group" aria-label="确认挂牌">
              <p className={styles.confirmText}>把这一条挂到院里？只挂标题和阅读来源，默认仅自己可见。</p>
              <p className={styles.preview}><strong>{stepOk.practice.title}</strong><Source title={stepOk.practice.source_title} url={null} /></p>
              <div className={styles.actions}>
                <button
                  type="button" className={styles.primary} disabled={!!busy}
                  onClick={() => { const p = stepOk.practice; void run(`new:${p.id}`, (c) => gardenMarksApi.create(p.id, c), "已挂上，目前仅自己可见。"); }}
                >{busy ? "挂牌中……" : "挂到院里（仅自己可见）"}</button>
                <button type="button" className={styles.btnQuiet} disabled={!!busy} onClick={() => setStep(null)}>先不了</button>
              </div>
            </div>
          )}

          {note && <p className={styles.ok} role="status">{note}</p>}
          {fail && <p className={styles.err} role="alert">{fail}</p>}

          <div className={styles.addBar}>
            <button type="button" className={styles.btn} onClick={togglePicker} disabled={full || !!busy} aria-expanded={picker.open}>
              {picker.open ? "收起练习列表" : "从已完成的练习里挂一块"}
            </button>
            {full && <span className={styles.hint}>已挂满 {max} 块（含仅自己可见的），先撤下一块。</span>}
          </div>

          {picker.open && !full && (
            <div className={styles.picker}>
              {picker.err && <p className={styles.err}>{picker.err}<button type="button" className={styles.linkBtn} onClick={() => void loadPractices(0)}>重试</button></p>}
              {!picker.err && !picker.loading && picker.items.length === 0 && (
                <p className={styles.state}>还没有已完成的练习。到<Link href="/me/?view=mine">我的练习</Link>把一条标为完成，再回来挂牌。</p>
              )}
              <ul className={styles.list}>
                {picker.items.map((p) => (
                  <li key={p.id} className={styles.pickRow}>
                    <span className={styles.pickText}>
                      <span className={styles.title}>{p.title}</span>
                      {p.source_title && <span className={styles.meta}>读自 {p.source_title}</span>}
                    </span>
                    {marked.has(p.id)
                      ? <span className={styles.meta}>已挂</span>
                      : <button type="button" className={styles.btn} disabled={!!busy} onClick={() => { setStep({ kind: "create", practice: p }); setNote(""); setFail(""); }}>挂牌</button>}
                  </li>
                ))}
              </ul>
              {picker.loading && <p className={styles.hint}>读取中……</p>}
              {!picker.loading && picker.items.length < picker.total && (
                <button type="button" className={styles.linkBtn} onClick={() => void loadPractices(picker.items.length)}>
                  再看更多（已显示 {picker.items.length}/{picker.total}）
                </button>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
