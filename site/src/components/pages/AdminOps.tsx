"use client";
import { useAuth } from "@/lib/auth";
import { Note } from "./FormBits";
import { AdminOpsQueue } from "./AdminOpsQueue";
import { AdminOpsMembers } from "./AdminOpsMembers";
import { AdminOpsPublish } from "./AdminOpsPublish";

/** 运营台壳：admin 才渲染三块。数据各自取，一块失败不空白整页。 */
export function AdminOps() {
  const { status, user } = useAuth();
  if (status === "loading") return <p className="py-10 font-sans text-[14px] text-ink-3">正在验票……</p>;
  if (status === "out") return <Note tone="bad">请先登录。这一页只对群主（admin）开放。</Note>;
  if (user?.role !== "admin") return <Note tone="bad">这页只对群主开放，你的账号没有这个权限。</Note>;
  return (
    <div className="space-y-14">
      <AdminOpsQueue />
      <AdminOpsMembers />
      <AdminOpsPublish />
    </div>
  );
}
