"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, apiFetch } from "@/lib/auth";
import { Btn, Note } from "./FormBits";

interface Issue {
  date: string;
  published: boolean;
  degree: number | null;
  gate_passed: boolean | null;
  grade?: string | null;
  redistill_count: number | null;
  hard_fail: string[];
  needs_redistill: boolean;
}
interface IssuesPayload {
  as_of: string;
  published_days: number;
  streak_days: number | null;
  latest_date: string | null;
  expected_latest?: string | null;
  missing_dates?: string[];
  health?: string;
  issues: Issue[];
  alert_entry: { href: string; label: string };
}
interface AlertPayload { unread?: number; total?: number }

export function AdminOpsPublish() {
  const [data, setData] = useState<IssuesPayload | null>(null);
  const [alerts, setAlerts] = useState<AlertPayload | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tone: "good" | "bad"; text: string } | null>(null);

  const load = useCallback(async () => {
    try { setData(await apiFetch<IssuesPayload>("/api/admin/ops/issues")); setErr(""); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "历期读不到"); }
    try { setAlerts(await apiFetch<AlertPayload>("/api/admin/alerts?limit=5")); }
    catch { setAlerts(null); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const trigger = async (day: string, force: boolean) => {
    const label = force ? `重蒸 ${day}` : `出刊 ${day}`;
    if (!window.confirm(`确认${label}？会写下 host 请求，容器自己不跑蒸馏。`)) return;
    setBusy(day + String(force)); setMsg(null);
    try {
      const d = await apiFetch<{ ok: boolean; note?: string; command?: string }>("/api/admin/ops/publish", {
        method: "POST", body: JSON.stringify({ date: day, force_redistill: force }),
      });
      setMsg({ tone: "good", text: d.note || `已记下 ${d.command}` });
    } catch (e) { setMsg({ tone: "bad", text: e instanceof ApiError ? e.message : "没记下" }); }
    finally { setBusy(null); }
  };

  if (err && !data) return <Note tone="bad">{err}</Note>;
  if (!data) return <p className="py-6 font-sans text-[13.5px] text-ink-3">正在取出刊记录……</p>;

  const missing = data.missing_dates || [];
  const hasGap = data.health === "gap" || missing.length > 0;

  return (
    <section>
      <h3 className="font-serif text-[19px] font-bold text-ink">出刊管理</h3>
      {hasGap ? (
        <div className="mt-3 border border-cinnabar/50 bg-cinnabar-wash px-3 py-2.5 font-sans text-[13px] text-cinnabar-text">
          <b className="font-semibold">出刊断更</b>
          ：应出 {data.expected_latest || "—"}，缺失 {missing.join("、") || "—"}。下方可强制重蒸补刊。
        </div>
      ) : null}
      <p className="mt-1 max-w-[46em] font-sans text-[13.5px] leading-relaxed text-ink-2">
        连续出刊 {data.streak_days ?? "—"} 天 · 已发布 {data.published_days} 期 · 最新 {data.latest_date ?? "—"}。
        手动触发只写请求文件，不从网站容器里直接跑 server-daily。
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Link href={data.alert_entry.href} className="font-sans text-[13px] text-blue-text hover:underline">{data.alert_entry.label}</Link>
        {alerts && <span className="num font-sans text-[12px] text-ink-3">值守未读 {alerts.unread ?? "—"} / 共 {alerts.total ?? "—"}</span>}
      </div>
      {msg && <div className="mt-3"><Note tone={msg.tone}>{msg.text}</Note></div>}
      <div className="mt-4 overflow-x-auto">
        <table className="w-full border-collapse text-left font-sans text-[13px]">
          <thead>
            <tr className="border-b border-rule font-serif text-[14px]">
              <th className="py-2 pr-2 font-medium">日期</th>
              <th className="py-2 pr-2 font-medium">度数</th>
              <th className="py-2 pr-2 font-medium">门禁</th>
              <th className="py-2 pr-2 font-medium">重蒸</th>
              <th className="py-2 pr-2 font-medium">hard_fail</th>
              <th className="py-2 font-medium">动作</th>
            </tr>
          </thead>
          <tbody>
            {data.issues.length === 0 ? (
              <tr><td className="py-5 text-ink-3" colSpan={6}>暂无历期文件。</td></tr>
            ) : data.issues.map((it) => {
              const gate = it.gate_passed === true ? "通过" : it.gate_passed === false ? "未过" : "—";
              const gateCls = it.gate_passed === true ? "text-teal-text" : it.gate_passed === false ? "text-cinnabar-text" : "text-ink-3";
              return (
                <tr key={it.date} className="border-b border-rule-soft align-top">
                  <td className="num py-2.5 pr-2">{it.date}</td>
                  <td className="num py-2.5 pr-2">{it.degree == null ? "—" : `${it.degree}°`}</td>
                  <td className={`py-2.5 pr-2 ${gateCls}`}>{gate}{it.grade ? ` ${it.grade}` : ""}</td>
                  <td className="num py-2.5 pr-2">{it.redistill_count ?? "—"}</td>
                  <td className="py-2.5 pr-2 text-ink-2">{it.hard_fail.join("；") || "—"}</td>
                  <td className="py-2.5">
                    <div className="flex flex-wrap gap-1.5">
                      <Btn type="button" tone="ghost" busy={busy === it.date + "false"} onClick={() => void trigger(it.date, false)} className="min-h-9 px-3 py-1.5 text-[12px]">出刊</Btn>
                      <Btn type="button" tone={it.needs_redistill ? "primary" : "ghost"} busy={busy === it.date + "true"} onClick={() => void trigger(it.date, true)} className="min-h-9 px-3 py-1.5 text-[12px]">重蒸</Btn>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
