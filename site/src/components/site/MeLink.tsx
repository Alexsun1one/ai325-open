"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";

/** 登录了就在导航右侧露一个头像，点进「我的」；没登录什么都不显示，不占地方。 */
export function MeLink() {
  const { status, user } = useAuth();
  const path = usePathname() || "/";
  if (status !== "in" || !user) return null;
  const name = (user.display_name || user.username || "?").trim().slice(0, 1);
  const on = path.startsWith("/me");
  return (
    <Link href="/me/" aria-label="我的" aria-current={on ? "page" : undefined} title={user.display_name || user.username}
      className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full border font-serif text-[15px] font-bold transition-colors ${on ? "border-blue bg-blue text-paper" : "border-blue-wash-2 bg-blue-wash text-blue-text hover:border-blue-2"}`}>
      {name}
    </Link>
  );
}
