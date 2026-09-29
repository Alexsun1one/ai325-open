"use client";
import { Icon } from "@/components/ui/Icon";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";

/** 登录了就在导航右侧露一个头像，点进「我的」；没登录什么都不显示，不占地方。 */
export function MeLink() {
  const { status, user } = useAuth();
  const path = usePathname() || "/";
  if (status !== "in" || !user) return <Link href="/me/" aria-label="登录账号" className="inline-flex min-h-11 items-center gap-1.5 px-1 font-sans text-[12px] text-blue-text"><Icon name="people" size={17} /><span className="hidden sm:inline">登录</span></Link>;
  const name = (user.display_name || user.username || "?").trim().slice(0, 1);
  const on = path.startsWith("/me");
  return (
    <Link href="/me/" aria-label="我的成长" aria-current={on ? "page" : undefined} title={user.display_name || user.username}
      className="inline-flex min-h-11 shrink-0 items-center gap-1.5 no-underline">
      <span aria-hidden className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full border font-serif text-[15px] font-bold transition-colors ${on ? "border-blue bg-blue text-paper" : "border-blue-wash-2 bg-blue-wash text-blue-text"}`}>
        {name}
      </span>
      <span className={`hidden font-sans text-[12.5px] font-semibold min-[400px]:inline ${on ? "text-blue-text" : "text-ink-2"}`}>我的成长</span>
    </Link>
  );
}
