"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { apiFetch } from "@/lib/auth";
import type { EventItem } from "./eventdata";

type Seeded = EventItem & { hasCover: boolean };
interface ApiEvent { slug: string; title: string; kind?: string; status?: string; starts_at?: string; ends_at?: string; rules_md?: string; reward?: string; cover_path?: string }

/* 后端用英文词，页面上说中文。对不上的原样透出，不猜。 */
const STATUS_CN: Record<string, string> = { open: "进行中", upcoming: "筹备中", closed: "已结束", draft: "筹备中" };
const KIND_CN: Record<string, string> = { contest: "比赛", essay: "仪式", custom: "长期", design: "设计" };
const cn = (m: Record<string, string>, v?: string) => (v ? m[v] ?? v : "");

/** 后端日期带时区（2026-08-23T17:25:00+08:00），页面只要「日期 + 时分」。 */
function stamp(v?: string | null) {
  if (!v) return "";
  const m = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(v);
  return m ? `${m[1]} ${m[2]}` : v;
}

/** 列表以种子为准（它带封面、时间轴、规则全文），再问一次后端：
 *  同名活动用后端的标题/状态/奖励覆盖；后端多出来的活动也列出来，但它没有独立页面，直接展开显示。 */
export function EventsLive({ seeded, statusStyle }: { seeded: Seeded[]; statusStyle: Record<string, string> }) {
  const [live, setLive] = useState<ApiEvent[] | null>(null);
  const reduce = useReducedMotion();

  useEffect(() => {
    let alive = true;
    // 后端实际返回 { items: [...] }；早期文档写的是 { events: [...] }，两种都认
    apiFetch<{ items?: ApiEvent[]; events?: ApiEvent[] }>("/api/events")
      .then((d) => { if (alive) setLive(d.items ?? d.events ?? []); })
      .catch(() => { if (alive) setLive(null); });   // 问不到就用种子，不打扰读者
    return () => { alive = false; };
  }, []);

  const bySlug = new Map((live ?? []).map((e) => [e.slug, e]));
  const merged = seeded.map((s) => {
    const l = bySlug.get(s.slug);
    // 标题 / 封面 / 简介用种子的（它是为这个版面写的）；状态·奖励·截止以后端为准，那是活的
    return l ? { ...s, status: cn(STATUS_CN, l.status) || s.status, kind: cn(KIND_CN, l.kind) || s.kind, reward: l.reward || s.reward, ends_at: stamp(l.ends_at) || s.ends_at } : s;
  });
  const extra = (live ?? []).filter((e) => !seeded.some((s) => s.slug === e.slug));

  return (
    <div>
      <div className="space-y-8">
        {merged.map((e, i) => (
          <motion.article key={e.slug}
            initial={reduce ? false : { opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.55, delay: Math.min(i, 4) * 0.08, ease: [0.16, 1, 0.3, 1] }}
            className="group overflow-hidden rounded-[12px] border border-rule bg-paper">
            <Link href={`/events/${e.slug}/`} className="block no-underline">
              {e.hasCover && (
                <div className="overflow-hidden border-b border-rule bg-paper-2">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={`/art/${e.cover}`} alt="" width={1600} height={900} loading={i ? "lazy" : "eager"}
                    className="block aspect-[21/9] w-full object-cover transition-transform duration-700 ease-[var(--ease-out-expo)] group-hover:scale-[1.025]" />
                </div>
              )}
              <div className="grid gap-x-8 gap-y-4 px-5 py-6 sm:px-7 lg:grid-cols-[minmax(0,1fr)_240px]">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <span className={`inline-flex rounded-[4px] border px-2 py-[3px] font-sans text-[11.5px] font-semibold ${statusStyle[e.status] ?? statusStyle["筹备中"]}`}>{e.status}</span>
                    <span className="font-sans text-[12px] text-ink-3">{e.kind}</span>
                  </div>
                  <h2 className="mt-2.5 font-serif text-[26px] font-black leading-tight text-ink transition-colors group-hover:text-blue-text sm:text-[30px]">{e.title}</h2>
                  {e.one_line && <p className="prose-sheet mt-2.5 text-[16.5px] leading-[1.8] text-ink-2">{e.one_line}</p>}
                  <span className="mt-4 inline-flex items-center gap-1.5 font-sans text-[13.5px] font-semibold text-blue-text">
                    进去看看
                    <svg aria-hidden width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" className="transition-transform duration-300 group-hover:translate-x-1"><path d="M9 6l6 6-6 6" /></svg>
                  </span>
                </div>
                <dl className="grid grid-cols-2 gap-x-5 gap-y-3 self-start border-t border-rule pt-4 font-sans text-[13px] lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
                  <div><dt className="label">开始</dt><dd className="num mt-0.5 text-ink">{e.starts_at || "—"}</dd></div>
                  <div><dt className="label">截止</dt><dd className="mt-0.5 text-ink">{e.ends_at ? <span className="num">{e.ends_at}</span> : <span className="text-ink-3">还没定</span>}</dd></div>
                  <div className="col-span-2"><dt className="label">给什么</dt><dd className="mt-0.5 text-ink">{e.reward || "—"}</dd></div>
                </dl>
              </div>
            </Link>
          </motion.article>
        ))}
      </div>

      {extra.length > 0 && (
        <div className="mt-10 rounded-[10px] border border-blue-wash-2 bg-blue-wash/60 px-5 py-4">
          <div className="label mb-2">刚开的新活动</div>
          <ul className="space-y-2">
            {extra.map((e) => (
              <li key={e.slug} className="font-sans text-[14px] text-ink-2">
                <b className="text-ink">{e.title}</b>
                {e.status && <span className="ml-2 text-ink-3">{cn(STATUS_CN, e.status)}</span>}
                {e.starts_at && <span className="num ml-2 text-ink-3">{stamp(e.starts_at)}</span>}
              </li>
            ))}
          </ul>
          <p className="mt-2.5 font-sans text-[12px] leading-relaxed text-ink-3">
            这几件是刚开的，还没来得及做单独的页面，下次更新站点就有了。
          </p>
        </div>
      )}
    </div>
  );
}
