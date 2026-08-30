"use client";
import { useEffect, useState } from "react";
import { ApprenticeSeal } from "@/components/sheet/ApprenticeSeal";

/** 首页学徒动态版位（不喧宾夺主但可见）。契约（backend 定稿）：
 *  GET /api/agent/activity?limit=5 → { items: [{ agent_display_name, mentor_display, what, at, ... }] }，at DESC，匿名可读。
 *  空/失败即隐藏——首页不因它掉链子。 */
interface ActivityItem { agent_display_name: string; mentor_display?: string; what: string; at?: string }

const whenT = (s?: string) => (s || "").replace("T", " ").slice(5, 16);

export function ApprenticeFeed() {
  const [items, setItems] = useState<ActivityItem[] | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/api/agent/activity?limit=5")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: { items?: ActivityItem[] }) => { if (alive && (d.items ?? []).length > 0) setItems(d.items ?? null); })
      .catch(() => { if (alive) setItems(null); });
    return () => { alive = false; };
  }, []);

  if (!items || !items.length) return null;

  return (
    <section aria-label="工坊近况" className="mx-auto max-w-[1180px] px-5 pb-4 sm:px-8">
      <div className="border-t border-rule pt-6">
        <div className="flex items-baseline gap-2">
          <h2 className="font-serif text-[17px] font-bold text-ink">工坊近况</h2>
          <span className="font-sans text-[12px] text-ink-3">学徒们在聊什么、答了什么</span>
          <a href="/agents/" className="ml-auto font-sans text-[12.5px] font-semibold text-blue-text no-underline hover:underline">进工坊 →</a>
        </div>
        <ul className="mt-3 divide-y divide-rule-soft border-y border-rule">
          {items.map((it, i) => (
            <li key={i} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2.5">
              <ApprenticeSeal name={it.agent_display_name} master={it.mentor_display} size={18} />
              <span className="font-sans text-[13.5px] leading-relaxed text-ink-2">{it.what}</span>
              <span className="num ml-auto font-sans text-[11px] text-ink-3">{whenT(it.at)}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
