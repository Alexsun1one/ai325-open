"use client";
import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ApiError, apiFetch } from "@/lib/auth";
import { TONE_META, type Tone, fmtInt, maskRawIds } from "@/lib/shared";
import { ToneTag } from "@/components/sheet/ToneTag";
import { Avatar, AvatarRow } from "./AvatarRow";
import { Note } from "./FormBits";
import { GapNote } from "./PageHead";

export interface Profile {
  name: string; role: string; msgs: number; ct: string; tags: string[];
  tone: Tone; quote: string; deep: string; filter: string[]; thin: boolean; avatar?: string;
}
interface Payload { generated?: string; count?: number; profiles: Profile[] }

const CHIPS: { k: string; label: string }[] = [
  { k: "all", label: "全部" },
  { k: "core", label: "核心七曜" },
  { k: "essay", label: "小作文自曝者" },
  { k: "boss", label: "老板创业者" },
  { k: "tech", label: "技术研究派" },
  { k: "d1", label: "建群日骨干" },
  { k: "thin", label: "薄数据" },
];

function Row({ p, i }: { p: Profile; i: number }) {
  const [open, setOpen] = useState(false);
  const reduce = useReducedMotion();
  return (
    <motion.article
      layout={reduce ? false : "position"}
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: Math.min(i, 12) * 0.025, ease: [0.16, 1, 0.3, 1] }}
      className="border-b border-rule-soft py-5"
    >
      <div className="grid grid-cols-[44px_minmax(0,1fr)_auto] items-start gap-x-4 gap-y-2">
        <Avatar f={p} size={44} />
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h3 className="font-serif text-[18px] font-bold leading-tight text-ink">{p.name}</h3>
            <ToneTag g={p.tone} />
            {p.thin && <span className="rounded-[4px] border border-rule bg-paper-2 px-1.5 py-[2px] font-sans text-[10.5px] font-semibold text-ink-3">薄数据</span>}
          </div>
          <div className="mt-1 font-sans text-[13px] leading-snug text-ink-2">{p.role}</div>
          {p.quote && <p className="prose-sheet mt-2.5 text-[16px] leading-[1.8] text-ink-2">「{maskRawIds(p.quote)}」</p>}
          {p.tags?.length > 0 && (
            <ul className="mt-2.5 flex flex-wrap gap-x-2 gap-y-1.5">
              {p.tags.map((t) => (
                <li key={t} className="rounded-[4px] border border-blue-wash-2 bg-blue-wash/70 px-1.5 py-[2px] font-sans text-[11.5px] text-blue-text">{t}</li>
              ))}
            </ul>
          )}
          {p.deep && (
            <>
              <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
                className="mt-3 inline-flex items-center gap-1.5 font-sans text-[13px] font-semibold text-blue-text hover:underline">
                <svg aria-hidden width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" className={`transition-transform ${open ? "rotate-90" : ""}`}><path d="M9 6l6 6-6 6" /></svg>
                深读
              </button>
              <AnimatePresence initial={false}>
                {open && (
                  <motion.div
                    initial={reduce ? { height: "auto", opacity: 1 } : { height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={reduce ? { opacity: 0 } : { height: 0, opacity: 0 }}
                    transition={{ duration: 0.34, ease: [0.16, 1, 0.3, 1] }}
                    className="overflow-hidden"
                  >
                    <p className="prose-sheet mt-3 border-l-2 border-amber-wash-2 pl-4 text-[16px] leading-[1.85] text-ink-2" dangerouslySetInnerHTML={{ __html: maskRawIds(p.deep) }} />
                  </motion.div>
                )}
              </AnimatePresence>
            </>
          )}
        </div>
        <div className="text-right">
          <div className="num font-sans text-[19px] font-semibold leading-none text-ink">{fmtInt(p.msgs)}</div>
          <div className="num mt-1 font-sans text-[11px] leading-tight text-ink-3">{p.ct || "条"}</div>
        </div>
      </div>
    </motion.article>
  );
}

/** 群像名册：51 人一栏一人，不是卡片墙。上方叠排头像行，chips 按 filter 字段筛。 */
export function MembersRoster() {
  const [data, setData] = useState<Payload | null>(null);
  const [err, setErr] = useState("");
  const [chip, setChip] = useState("all");

  useEffect(() => {
    let alive = true;
    apiFetch<Payload>("/api/governed/members")
      .then((d) => { if (alive) setData(d); })
      .catch((e) => { if (alive) setErr(e instanceof ApiError ? e.message : "读取失败"); });
    return () => { alive = false; };
  }, []);

  const profiles = data?.profiles ?? [];
  const counts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const c of CHIPS) m[c.k] = profiles.filter((p) => p.filter?.includes(c.k)).length;
    return m;
  }, [profiles]);
  const list = useMemo(() => profiles.filter((p) => p.filter?.includes(chip)).sort((a, b) => b.msgs - a.msgs), [profiles, chip]);

  if (err) return <Note tone="bad">{err}</Note>;
  if (!data) return <p className="py-10 font-sans text-[14px] text-ink-3">正在取群像……</p>;

  return (
    <div>
      <div className="mb-8">
        <AvatarRow faces={profiles.slice().sort((a, b) => b.msgs - a.msgs)} />
      </div>

      <div className="flex flex-wrap gap-2 border-y border-rule py-3">
        {CHIPS.map((c) => {
          const on = chip === c.k;
          return (
            <button key={c.k} type="button" onClick={() => setChip(c.k)} aria-pressed={on}
              className={`inline-flex min-h-11 items-center gap-1.5 rounded-[5px] border px-2.5 py-1.5 font-sans text-[13px] font-medium transition-colors sm:min-h-0 ${on ? "border-blue bg-blue text-paper" : "border-rule bg-paper text-ink-2 hover:bg-paper-2"}`}>
              {c.label}
              <span className={`num text-[11.5px] ${on ? "text-paper/75" : "text-ink-3"}`}>{counts[c.k] ?? 0}</span>
            </button>
          );
        })}
      </div>

      {chip === "core" && counts.core !== 7 && (
        <div className="mt-5">
          <GapNote>
            「七曜」是群里的叫法，画像数据里标为核心的实际是 <span className="num">{counts.core}</span> 人。这里按数据显示，不凑数。
          </GapNote>
        </div>
      )}
      {chip === "thin" && (
        <div className="mt-5">
          <GapNote>
            这 <span className="num">{counts.thin}</span> 位在原始库里的发言样本很少，画像只能写到这个程度。<b>薄不代表不重要</b>——只代表我们目前掌握的证据薄。
          </GapNote>
        </div>
      )}

      <div className="mt-2 border-t border-rule">
        {list.map((p, i) => <Row key={p.name} p={p} i={i} />)}
      </div>

      <p className="mt-6 font-sans text-[12.5px] leading-relaxed text-ink-3">
        共 <span className="num">{profiles.length}</span> 人{data.generated && <> · 生成于 <span className="num">{data.generated}</span></>}；当前筛选 <span className="num">{list.length}</span> 人，按发言量倒序。
        语气章标的是这个人在群里的<b>主要说话方式</b>（{Object.values(TONE_META).map((m) => m.label).join(" / ")}），不是评价。
      </p>
    </div>
  );
}
