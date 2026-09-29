"use client";
import { useEffect, useState } from "react";
import { ApiError, apiFetch, useAuth } from "@/lib/auth";
import { Note } from "./FormBits";
import { GapNote } from "./PageHead";
import { CommunitySpark, DegreePath, RankBars, SparkBars, nfmt } from "./AdminDashboardCharts";

/** 契约：GET /api/admin/stats?days=30 */
interface WindowM { has_data: boolean; pv: number; uv: number | null; observed_pv: number }
interface TrendPt { date: string; pv: number; uv: number | null }
interface Rank { page?: string; source?: string; device?: string; pv: number }
interface CommPt {
  date: string; messages: number; speakers: number; new_faces: number;
  essays: number; quotes: number; arsenal: number; cellar_units: number;
}
interface Payload {
  as_of: string;
  generated_at: string;
  ingest: {
    last_run: string | null;
    files: string[];
    coverage?: { first_day: string | null; last_day: string | null; days: number } | null;
  };
  traffic: {
    available: boolean;
    uv_available: boolean;
    uv_reason: string | null;
    windows: { today?: WindowM; "7d"?: WindowM; "30d"?: WindowM };
    filters: {
      parsed_requests?: number; excluded_bots?: number; excluded_internal?: number;
      page_views_considered?: number; observed_page_views?: number; proxy_masked_page_views?: number;
    };
    trend: TrendPt[];
    top_pages: Rank[];
    sources: Rank[];
    devices: Rank[];
  };
  community: { available: boolean; trend: CommPt[] };
  publication: {
    available?: boolean;
    streak_days?: number | null;
    published_days?: number | null;
    latest_date?: string | null;
    expected_latest?: string | null;
    missing_dates?: string[];
    health?: string;
    degree_curve?: { date: string; degree: number | null }[];
    alerts?: { available?: boolean; total?: number | null; unresolved?: number | null };
    gate_blocks?: { available?: boolean; total?: number | null };
  };
}

function Metric({ k, v, sub }: { k: string; v: string; sub: string }) {
  return (
    <div className="min-h-[108px] border-l-4 border-blue bg-paper-2/80 px-4 py-3">
      <div className="label">{k}</div>
      <div className="num mt-1.5 font-serif text-[32px] font-bold leading-none text-blue">{v}</div>
      <div className="mt-2 font-sans text-[12px] text-ink-3">{sub}</div>
    </div>
  );
}

function Panel({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 border border-rule bg-paper/40 p-4">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 className="font-serif text-[16px] font-bold text-ink">{title}</h3>
        {hint && <span className="font-sans text-[11.5px] text-ink-3">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

export function AdminDashboard() {
  const { status, user, netErr, refresh } = useAuth();
  if (status === "loading") return <p className="py-10 font-sans text-[14px] text-ink-3">正在验票……</p>;
  if (netErr) return (
    <Note tone="bad">
      {netErr}{" "}
      <button
        type="button"
        onClick={() => void refresh()}
        className="ml-2 inline-flex min-h-[44px] items-center border border-cinnabar-text px-3 font-sans text-[13px] text-cinnabar-text"
      >
        重试
      </button>
    </Note>
  );
  if (status === "out") return <Note tone="bad">请先登录。这一页只对群主（admin）开放。</Note>;
  if (user?.role !== "admin") return <Note tone="bad">这页只对群主开放，你的账号没有这个权限。</Note>;
  return <AdminDashboardBody key={`${user.username}:${user.role}`} />;
}

function AdminDashboardBody() {
  const [data, setData] = useState<Payload | null>(null);
  const [err, setErr] = useState("");
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const ac = new AbortController();
    let dead = false;
    (async () => {
      try {
        const p = await apiFetch<Payload>("/api/admin/stats?days=30", { signal: ac.signal });
        if (!dead) { setData(p); setErr(""); }
      } catch (e) {
        if (!dead && !ac.signal.aborted) {
          setData(null);
          setErr(e instanceof ApiError ? e.message : "数据大盘没取到");
        }
      } finally {
        if (!dead) setBusy(false);
      }
    })();
    return () => { dead = true; ac.abort(); };
  }, [tick]);

  if (err && !data) return (
    <Note tone="bad">
      {err}{" "}
      <button
        type="button"
        disabled={busy}
        onClick={() => { setBusy(true); setTick((v) => v + 1); }}
        className="ml-2 inline-flex min-h-[44px] items-center border border-cinnabar-text px-3 font-sans text-[13px] text-cinnabar-text disabled:opacity-50"
      >
        重试
      </button>
    </Note>
  );
  if (!data) return <p className="py-10 font-sans text-[14px] text-ink-3">正在读聚合表……</p>;

  const t = data.traffic;
  const w = t.windows || {};
  const winPv = (win?: WindowM) => (win && win.has_data ? nfmt(win.pv) : "未知");
  const winUv = (win?: WindowM) => (!win || !win.has_data ? "暂无采集数据" : `UV ${nfmt(win.uv ?? null)}`);
  const f = t.filters || {};
  const pub = data.publication || {};
  const alerts = pub.alerts || {};
  const gates = pub.gate_blocks || {};
  const comm = data.community.trend || [];
  const recent = comm.filter((r) => r.messages || r.speakers || r.essays || r.quotes || r.arsenal || r.cellar_units).slice(-10);
  const missing = pub.missing_dates || [];
  const hasGap = pub.health === "gap" || missing.length > 0;

  return (
    <div className="space-y-10">
      {hasGap ? (
        <div className="border border-cinnabar bg-cinnabar-wash px-4 py-3 text-cinnabar-text">
          <div className="font-serif text-[17px] font-bold">出刊断更</div>
          <p className="mt-1 font-sans text-[13px]">
            应出刊日 {pub.expected_latest || "—"} 缺失：{missing.join("、") || "未知日期"}。
            最新已出 {pub.latest_date || "—"}。请立刻补蒸，勿等晨间告警。
          </p>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3 border border-ink bg-ink px-4 py-3 text-paper">
        <div>
          <div className="font-serif text-[17px] font-bold text-amber">日志 → 增量聚合 → 运营判断</div>
          <p className="mt-1 font-sans text-[12px] text-paper/70">
            统计日 {data.as_of} · 数据截至 {data.ingest.coverage?.last_day || "—"} · 上次采集 {data.ingest.last_run || "尚未跑过"}
          </p>
          {data.ingest.coverage?.first_day ? (
            <p className="mt-0.5 font-sans text-[11px] text-paper/55">
              覆盖 {data.ingest.coverage.first_day} ~ {data.ingest.coverage.last_day || "—"} · {nfmt(data.ingest.coverage.days)} 天
            </p>
          ) : null}
        </div>
        <span className="border border-paper/35 px-2 py-1 font-sans text-[11px] tracking-wide text-paper/80">只读 · 零埋点</span>
      </div>

      <section>
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="shrink-0 whitespace-nowrap font-serif text-[22px] font-bold text-ink">访问量</h2>
          <span className="font-sans text-[12px] text-ink-3">成功文档请求，排除 API / 静态 / 爬虫 / 内网</span>
        </div>
        {!t.available ? (
          <GapNote>访问量聚合尚未跑过。宿主机每 10 分钟增量解析 nginx access.log，落 /data/analytics.db；API 不扫全量日志。</GapNote>
        ) : (
          <>
            <div className="grid gap-2 sm:grid-cols-3">
              <Metric k="今日" v={winPv(w.today)} sub={winUv(w.today)} />
              <Metric k="近 7 日" v={winPv(w["7d"])} sub={winUv(w["7d"])} />
              <Metric k="近 30 日" v={winPv(w["30d"])} sub={winUv(w["30d"])} />
            </div>
            {!t.uv_available && t.uv_reason && <div className="mt-3"><GapNote>{t.uv_reason}</GapNote></div>}
            <p className="mt-3 font-sans text-[12px] text-ink-3">
              近 30 日观测页 {nfmt(f.observed_page_views)} · 排除爬虫 {nfmt(f.excluded_bots)} · 排除内网 {nfmt(f.excluded_internal)}
              {f.proxy_masked_page_views ? ` · 代理回环 ${nfmt(f.proxy_masked_page_views)}` : ""}
            </p>
            <p className="mt-1.5 font-sans text-[12px] text-ink-3">
              口径：仅计成功 GET 文档请求，不含 HEAD 与 _rsc 预取；UV 为同一访客在窗口内去重。
              {data.ingest.coverage?.first_day ? "早期聚合口径与现口径可能不同，新栏目历史访问尚未全部补算。" : ""}
            </p>
            <div className="mt-4 grid gap-4 lg:grid-cols-[1.15fr_.85fr]">
              <Panel title="近 30 日 PV" hint="琥珀柱">
                <SparkBars points={t.trend} label="近 30 日页面访问" />
              </Panel>
              <Panel title="热门页 TOP10" hint="蓝条">
                <RankBars items={t.top_pages.map((x) => ({ name: x.page ?? "—", pv: x.pv }))} label="热门页面" />
              </Panel>
            </div>
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <Panel title="来源" hint="referer 域名">
                <RankBars items={t.sources.map((x) => ({ name: x.source ?? "—", pv: x.pv }))} label="来源" />
              </Panel>
              <Panel title="设备" hint="UA 粗分">
                <RankBars items={t.devices.map((x) => ({ name: x.device ?? "—", pv: x.pv }))} label="设备" />
              </Panel>
            </div>
          </>
        )}
      </section>

      <section>
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="shrink-0 whitespace-nowrap font-serif text-[22px] font-bold text-ink">内容与社群</h2>
          <span className="font-sans text-[12px] text-ink-3">琥珀=消息 · 蓝点=发言人数</span>
        </div>
        {!data.community.available ? (
          <GapNote>社群聚合尚未写入。ingest 会从 xf.db 按日刷新消息/发言人/新面孔与治理产物。</GapNote>
        ) : (
          <>
            <Panel title="近 14 日消息与发言" hint="柱=消息，线=发言人">
              <CommunitySpark points={comm} />
            </Panel>
            <div className="mt-4 overflow-x-auto border border-rule">
              <table className="w-full min-w-[720px] border-collapse font-sans text-[13px]">
                <thead>
                  <tr className="border-b border-rule text-left font-serif text-[14px]">
                    {["日期", "消息", "发言人", "新面孔", "小作文", "金句", "军火库", "窖藏块"].map((h) => (
                      <th key={h} className="px-2.5 py-2 font-semibold">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(recent.length ? recent : comm.slice(-10)).map((r) => (
                    <tr key={r.date} className="border-b border-rule-soft">
                      <td className="px-2.5 py-2 text-ink-2">{r.date}</td>
                      <td className="num px-2.5 py-2 text-right">{nfmt(r.messages)}</td>
                      <td className="num px-2.5 py-2 text-right">{nfmt(r.speakers)}</td>
                      <td className="num px-2.5 py-2 text-right">{nfmt(r.new_faces)}</td>
                      <td className="num px-2.5 py-2 text-right">{nfmt(r.essays)}</td>
                      <td className="num px-2.5 py-2 text-right">{nfmt(r.quotes)}</td>
                      <td className="num px-2.5 py-2 text-right">{nfmt(r.arsenal)}</td>
                      <td className="num px-2.5 py-2 text-right">{nfmt(r.cellar_units)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 font-sans text-[12px] text-ink-3">上表为有数据的最近窗口，不是全库；金句/军火库来自 governed 产物，窖藏块为已发布 context_units。</p>
          </>
        )}
      </section>

      <section>
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
          <h2 className={`shrink-0 whitespace-nowrap font-serif text-[22px] font-bold ${hasGap ? "text-cinnabar-text" : "text-ink"}`}>
            出刊健康{hasGap ? " · 断更" : ""}
          </h2>
          <span className="font-sans text-[12px] text-ink-3">缺文件显示 —，不补成 0</span>
        </div>
        <div className="grid gap-2 sm:grid-cols-3">
          <Metric
            k="连续出刊"
            v={pub.streak_days == null ? "—" : `${nfmt(pub.streak_days)} 天`}
            sub={hasGap
              ? `断更 ${missing.join("、")} · 最新 ${pub.latest_date || "—"}`
              : `可见 ${nfmt(pub.published_days ?? null)} 期 · 最新 ${pub.latest_date || "—"}`}
          />
          <Metric k="门禁拦截" v={nfmt(gates.total ?? null)} sub={gates.available ? "daily 日志命中 quality/publish gate" : "暂无日志"} />
          <Metric k="告警未解" v={nfmt(alerts.unresolved ?? null)} sub={alerts.available ? `总计 ${nfmt(alerts.total ?? null)}` : "告警 JSONL 暂无"} />
        </div>
        <div className="mt-4">
          <Panel title="度数曲线" hint="琥珀点，蓝描边">
            <DegreePath points={pub.degree_curve || []} />
          </Panel>
        </div>
      </section>
    </div>
  );
}
