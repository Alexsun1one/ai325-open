"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import type { MemberFocus } from "@/lib/shared";
import { ToneTag } from "./ToneTag";
import { FocusFaces } from "./FocusFaces";
import { Avatar } from "@/components/pages/AvatarRow";
import { loadPeople, type Person } from "./PersonHover";

/** 成员高光：本期最值得看见的人。头像与完整画像在登录后的群像页。 */
export function MembersFocus({ items, thanks = [] }: { items: MemberFocus[]; thanks?: { name: string; why: string }[] }) {
  // 头像与上方的 FocusFaces 同源（loadPeople 模块级缓存，这里是第二个读者，不多发一次请求）。
  // 首帧先渲染姓名首字圆牌，图片到位后就地替换——尺寸一致，不会有跳版。
  const [avatars, setAvatars] = useState<Record<string, string>>({});
  useEffect(() => {
    let alive = true;
    loadPeople().then((ps: Person[]) => {
      if (!alive) return;
      const m: Record<string, string> = {};
      for (const it of items) {
        const p = ps.find((x) => x.name === it.name || x.aliases.includes(it.name));
        if (p?.avatar) m[it.name] = p.avatar;
      }
      setAvatars(m);
    });
    return () => { alive = false; };
  }, [items]);
  return (
    <div>
      <FocusFaces names={items.map((m) => m.name)} />
      {thanks.length > 0 && (
        <div className="mb-9 rounded-[12px] border border-rule bg-paper-2/60 px-5 py-4">
          <div className="label">本期感谢</div>
          <ul className="mt-2.5 space-y-2">
            {thanks.map((t, i) => (
              <li key={i} className="hand text-[17px] leading-[1.8]">
                <span className="mr-1 font-sans text-[14px] font-semibold text-blue-text">{t.name}</span>—— {t.why}
              </li>
            ))}
          </ul>
        </div>
      )}
      <ul className="grid gap-x-10 gap-y-6 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((m, i) => (
          // 左侧 28px 挂头像（悬挂缩进），名字/角色/引语都从第二列同一条左边线起排，ruled 行不变
          <li key={i} className="grid min-w-0 grid-cols-[28px_minmax(0,1fr)] gap-x-3 border-t border-rule-soft pt-3.5">
            <span className="col-start-1 row-start-1 flex items-center justify-center">
              <Avatar f={{ name: m.name, role: m.role, avatar: avatars[m.name] }} size={26} />
            </span>
            {/* 名字与条数同基线：条数是仪器读数，永远靠右、永远 tabular */}
            <div className="col-start-2 row-start-1 flex items-baseline justify-between gap-3">
              <span data-person={m.name} className="min-w-0 font-serif text-[17px] font-bold leading-[1.5] text-ink">{m.name}</span>
              <span className="num shrink-0 font-sans text-[12px] text-ink-3">{m.msgs} 条</span>
            </div>
            <div className="col-start-2 row-start-2 mt-1 font-sans text-[12.5px] leading-[1.5] text-blue-text">{m.role}</div>
            {m.quote && (
              <p className="prose-sheet col-start-2 row-start-3 mt-2.5 text-[15px] leading-[1.75] text-ink-2">
                <span className="-mr-[0.18em] text-ink-3">「</span>{m.quote}<span className="-ml-[0.18em] mr-1.5 text-ink-3">」</span>
                <ToneTag g={m.tone} />
              </p>
            )}
          </li>
        ))}
      </ul>
      <div className="mt-9 flex flex-wrap items-center gap-x-4 gap-y-2.5 font-sans text-[13.5px]">
        <Link
          href="/members/"
          className="inline-flex items-center gap-2 rounded-md border border-blue bg-blue-wash px-3.5 py-2 font-medium text-blue-text no-underline transition-colors duration-200 ease-[var(--ease-out-expo)] hover:bg-blue-wash-2 active:bg-blue-wash-2"
        >
          看全部 51 人画像与头像
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden className="shrink-0"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>
        </Link>
        <span className="text-ink-3">群友凭邀请码登录；真人头像与姓名不对外。</span>
      </div>
    </div>
  );
}
