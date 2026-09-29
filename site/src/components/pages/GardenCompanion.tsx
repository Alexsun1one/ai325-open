"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/auth";
import {
  gardenCompanionApi,
  type CodexCrop, type CompanionResponse, type FootprintDay, type GuardianOption, type Milestone,
} from "@/lib/garden-companion";
import styles from "./GardenCompanion.module.css";

/* Design Contract（≤10 行）
   屏职：家园折叠区内的内容（外层 details 由父级负责，首次展开才挂载）——护法陪伴、作物图鉴、种植成就与近 7 日足迹。
   主操作：选/换一位护法；其余只读。手动「刷新」+ 父级 revisionKey 变化时重拉。
   层级：护法（左，主）＞图鉴 ＞ 成就 ＞ 足迹（右侧列表，非卡片墙）。
   必备态：读取中/失败可重试/未开通空状态/新人全 0/保存中。
   禁：假成就、断签惩罚、倒计时话术、护法冒充真人/Agent 或承诺自动收割防偷、固定高频轮询、无限动画。 */

const errText = (e: unknown, fb: string) => (e instanceof ApiError ? e.message : fb);
const isAbort = (e: unknown, signal: AbortSignal) => signal.aborted || (e instanceof ApiError && e.status === 0 && /取消/.test(e.message));
const md = (iso: string) => { const m = /^\d{4}-(\d{2})-(\d{2})/.exec(iso); return m ? `${+m[1]}/${+m[2]}` : iso; };
const fmtDur = (s: number) =>
  s < 90 ? `${Math.max(1, Math.round(s))} 秒` : s < 3300 ? `约 ${Math.round(s / 60)} 分钟` : `约 ${(s / 3600).toFixed(1).replace(/\.0$/, "")} 小时`;
const clock = (iso: string | null) => {
  const d = iso ? new Date(iso) : null;
  return d && !Number.isNaN(+d) ? `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}` : "";
};

const CODEX_LABEL = { locked: "未解锁", planted: "种过", harvested: "收过" } as const;

function GuardianPicker({
  options, selectedId, busy, onPick,
}: { options: GuardianOption[]; selectedId: string | null; busy: boolean; onPick: (id: string | null) => void }) {
  return (
    <fieldset className={styles.picker} disabled={busy}>
      <legend className={styles.legend}>选一位护法</legend>
      {options.map((o) => (
        <label key={o.id} className={styles.pick}>
          <input
            type="radio" name="garden-guardian" className={styles.pickInput}
            checked={selectedId === o.id} onChange={() => onPick(o.id)}
          />
          {/* 装饰头像：名字和物种已在文字里 */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={o.sprite} alt="" width={48} height={48} loading="lazy" decoding="async" className={styles.pickImg} />
          <span className={styles.pickText}>
            <strong>{o.name}</strong> <small>{o.species}</small>
            <span className={styles.pickTag}>{o.tagline}</span>
          </span>
          <span className={styles.pickMark} aria-hidden>{selectedId === o.id ? "当前" : ""}</span>
        </label>
      ))}
      {selectedId && (
        <button type="button" className={styles.linkBtn} onClick={() => onPick(null)}>不带护法</button>
      )}
    </fieldset>
  );
}

function CodexRow({ c }: { c: CodexCrop }) {
  return (
    <li className={`${styles.row} ${c.status === "locked" ? styles.rowLocked : ""}`}>
      <div className={styles.rowMain}>
        <span className={styles.rowName}>{c.name}</span>
        <span className={`${styles.badge} ${styles[`badge_${c.status}`]}`}>{CODEX_LABEL[c.status]}</span>
      </div>
      <p className={styles.rowSub}>
        {c.status === "locked"
          ? `还没种过。${fmtDur(c.duration_seconds)}成熟，每茬 ${c.yield} 份。`
          : `种过 ${c.planted} 次 · 收过 ${c.harvested} 次${c.harvested ? ` · 共收 ${c.harvested_amount} 份` : ""}`}
      </p>
    </li>
  );
}

function MilestoneRow({ m }: { m: Milestone }) {
  const shown = Math.min(m.value, m.target);
  const pct = Math.round((shown / m.target) * 100);
  return (
    <li className={`${styles.row} ${m.unlocked ? styles.rowDone : ""}`}>
      <div className={styles.rowMain}>
        <span className={styles.rowName}>{m.title}</span>
        <span className={styles.rowNum}>{m.unlocked ? `已达成${m.unlocked_at ? ` · ${md(m.unlocked_at)}` : ""}` : `${shown} / ${m.target}`}</span>
      </div>
      <p className={styles.rowSub}>{m.description}</p>
      <div className={styles.meter} role="progressbar" aria-label={m.title} aria-valuemin={0} aria-valuemax={m.target} aria-valuenow={shown}>
        <span style={{ width: `${pct}%` }} />
      </div>
    </li>
  );
}

function Footprint({ days, totals, tz }: { days: FootprintDay[]; totals: CompanionResponse["footprint"]["totals"]; tz: string }) {
  const peak = Math.max(1, ...days.map((d) => d.planted + d.harvested));
  return (
    <div>
      <ol className={styles.days}>
        {days.map((d) => (
          <li key={d.date} className={styles.day} aria-label={`${md(d.date)}：播种 ${d.planted} 次，收获 ${d.harvested} 次`}>
            <span className={styles.dayNum}>{d.planted + d.harvested}</span>
            <span className={styles.dayBar} aria-hidden>
              <i className={styles.dayHarvest} style={{ height: `${(d.harvested / peak) * 100}%` }} />
              <i className={styles.dayPlant} style={{ height: `${(d.planted / peak) * 100}%` }} />
            </span>
            <span className={styles.dayLabel}>{md(d.date)}</span>
          </li>
        ))}
      </ol>
      <p className={styles.legendLine}>
        <span className={styles.keyPlant}>播种</span> <span className={styles.keyHarvest}>收获</span>
        　近 {days.length} 天（{tz}）：播种 {totals.planted} 次 · 收获 {totals.harvested} 次 · 收成 {totals.harvested_amount} 份
      </p>
    </div>
  );
}

/** 家园里「我的护法与图鉴」。父组件在种/收成功后换 revisionKey 即可刷新；无固定轮询。 */
export default function GardenCompanion({ revisionKey }: { revisionKey?: string }) {
  const [data, setData] = useState<CompanionResponse | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState("");
  const ctl = useRef<AbortController | null>(null);
  const seq = useRef(0);

  /** 拉取聚合：新请求作废旧请求；silent 时不闪「刷新中」（首屏/父级换 key）。 */
  const fetchData = useCallback(async () => {
    ctl.current?.abort();
    const c = new AbortController();
    ctl.current = c;
    const mine = ++seq.current;
    try {
      const r = await gardenCompanionApi.get(c.signal);
      if (mine === seq.current) { setData(r); setErr(""); }
    } catch (e) {
      if (mine !== seq.current || isAbort(e, c.signal)) return;
      setErr(errText(e, "读不到护法与图鉴。"));
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, []);

  const load = () => { setLoading(true); setErr(""); void fetchData(); };

  useEffect(() => {
    // 首屏/换 key 拉取：setState 都在 await 之后，属订阅外部数据，非级联渲染
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchData();
    const seqRef = seq;
    const ctlRef = ctl;
    return () => { seqRef.current++; ctlRef.current?.abort(); };
  }, [fetchData, revisionKey]);

  const pick = async (id: string | null) => {
    if (saving) return;
    setSaving(true);
    setSaveErr("");
    try {
      const r = await gardenCompanionApi.setGuardian(id);
      seq.current++; // 作废在途的旧读取，避免旧数据覆盖刚保存的选择
      ctl.current?.abort();
      setLoading(false);
      setData(r);
    } catch (e) {
      setSaveErr(errText(e, "没保存成功，再试一次。"));
    } finally {
      setSaving(false);
    }
  };

  const selected = data?.guardian.options.find((o) => o.id === data.guardian.selected_id) ?? null;
  const watch = data?.guardian.watch ?? null;
  const p = data?.protection;

  return (
    <section className={styles.box} aria-busy={loading}>
      <div className={styles.body}>
        <div className={styles.toolbar}>
          <p className={styles.hint}>
            {data ? `图鉴 ${data.codex.unlocked}/${data.codex.total} · 成就 ${data.milestones.unlocked}/${data.milestones.total}。` : ""}
            由你自己的种植和收获记录得出；偷来的菜不算。
          </p>
          <button type="button" className={styles.linkBtn} onClick={() => load()} disabled={loading}>
            {loading ? "刷新中……" : "刷新"}
          </button>
        </div>

        {err && !data && (
          <div className={styles.state}>{err}<button type="button" className={styles.linkBtn} onClick={() => load()}>重试</button></div>
        )}
        {err && data && <p className={styles.err}>{err}<button type="button" className={styles.linkBtn} onClick={() => load()}>重试</button></p>}
        {!data && loading && <div className={styles.state}>正在读取……</div>}

        {data && (
          <div className={styles.layout}>
            <section className={styles.side} aria-labelledby="gc-guardian">
              <h3 id="gc-guardian" className={styles.h3}>护法</h3>
              <div className={styles.watch} role="status" aria-live="polite">
                {selected && watch ? (
                  <>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={selected.sprite} alt="" width={64} height={64} decoding="async" className={styles.watchImg} />
                    <p className={styles.watchText}>
                      <strong>{selected.name}：</strong>{watch.message}
                      {watch.kind === "waiting" && clock(watch.situation.next_ripe_at) && (
                        <small>最近一块约 {clock(watch.situation.next_ripe_at)} 成熟。</small>
                      )}
                    </p>
                  </>
                ) : (
                  <p className={styles.watchText}>还没选护法。选一位，它会照你当前的地块说一句话。</p>
                )}
              </div>
              <GuardianPicker options={data.guardian.options} selectedId={data.guardian.selected_id} busy={saving} onPick={(id) => void pick(id)} />
              {saveErr && <p className={styles.err}>{saveErr}</p>}
              <p className={styles.hint}>{data.guardian.note}</p>
              {p && (
                <p className={styles.hint}>
                  真实保护以家园规则为准：每茬至少给主人留 {Math.round((1 - p.steal_fraction) * 100)}%，访客每次最多摘 {p.steal_amount} 个。
                </p>
              )}
            </section>

            <div className={styles.main}>
              {!data.garden_open && (
                <p className={styles.empty}>家园还没开通。图鉴、成就和足迹会从你第一次播种开始记录，现在都是 0。</p>
              )}

              <section aria-labelledby="gc-codex">
                <h3 id="gc-codex" className={styles.h3}>作物图鉴 <small>{data.codex.unlocked}/{data.codex.total}</small></h3>
                <ul className={styles.list}>{data.codex.crops.map((c) => <CodexRow key={c.id} c={c} />)}</ul>
              </section>

              <section aria-labelledby="gc-ms">
                <h3 id="gc-ms" className={styles.h3}>种植成就 <small>{data.milestones.unlocked}/{data.milestones.total}</small></h3>
                <ul className={styles.list}>{data.milestones.items.map((m) => <MilestoneRow key={m.id} m={m} />)}</ul>
              </section>

              <section aria-labelledby="gc-fp">
                <h3 id="gc-fp" className={styles.h3}>近 {data.footprint.days.length} 日足迹</h3>
                <Footprint days={data.footprint.days} totals={data.footprint.totals} tz={data.footprint.timezone} />
              </section>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
