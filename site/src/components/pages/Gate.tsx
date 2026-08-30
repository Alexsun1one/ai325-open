"use client";
import { useEffect, useState } from "react";
import { ApiError, apiFetch, useAuth } from "@/lib/auth";
import { Btn, Field, Note } from "./FormBits";

/** 登录墙：群像与窖藏只对群友开放。未登录时给一张表单，不给假预览。 */
/** children 必须是已渲染的元素（不能是函数）：这一层会被服务端组件直接引用，函数没法跨 RSC 边界传。 */
export function Gate({ what, why, children }: { what: string; why: string; children: React.ReactNode }) {
  const { status, user, signIn, signUp, signOut } = useAuth();
  const [mode, setMode] = useState<"in" | "up">("in");
  const [u, setU] = useState(""); const [p, setP] = useState(""); const [code, setCode] = useState(""); const [name, setName] = useState("");
  const [names, setNames] = useState<string[]>([]);
  const [busy, setBusy] = useState(false); const [err, setErr] = useState("");

  // 注册页的群昵称下拉：从公开名单取，选中即按微信身份绑定（后端按显示名唯一匹配）
  useEffect(() => {
    apiFetch<{ names: string[] }>("/api/members/names").then((d) => setNames(d.names)).catch(() => {});
  }, []);

  if (status === "loading") {
    return <p className="py-10 font-sans text-[14px] text-ink-3">正在验票……</p>;
  }
  if (status === "in" && user) {
    return (
      <div>
        <div className="mb-8 flex flex-wrap items-center justify-between gap-3 rounded-[8px] border border-rule bg-paper-2/60 px-4 py-2.5">
          <span className="font-sans text-[13px] text-ink-2">已登录：<span className="font-semibold text-ink">{user.display_name || user.username}</span>{user.role && <span className="ml-2 text-ink-3">{user.role}</span>}</span>
          <button type="button" onClick={() => void signOut()} className="font-sans text-[13px] text-blue-text hover:underline">退出</button>
        </div>
        {children}
      </div>
    );
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      if (mode === "in") await signIn(u.trim(), p);
      else await signUp(name.trim(), p, code.trim(), name.trim()); // 注册瘦身：用户名=群昵称，不再单独填
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "出了点问题，请再试一次。");
    } finally { setBusy(false); }
  };

  return (
    <div className="grid gap-x-12 gap-y-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,340px)]">
      <div className="min-w-0">
        <h2 className="font-serif text-[26px] font-bold leading-snug text-ink sm:text-[30px]">{what}需要登录</h2>
        <p className="prose-sheet mt-4 text-[16.5px] leading-[1.85] text-ink-2">{why}</p>
        <dl className="mt-7 space-y-4 border-t border-rule pt-5">
          <div><dt className="label">谁能进</dt><dd className="mt-1 font-sans text-[14px] leading-relaxed text-ink-2">群友。注册要邀请码——由群主发放，一人一码、可撤销，群内向 Sun 索取。</dd></div>
          <div><dt className="label">存了什么</dt><dd className="mt-1 font-sans text-[14px] leading-relaxed text-ink-2">用户名、密码的哈希、一张 90 天有效的登录票据（常来会自动续期，基本不用重复登录）。凭证只留在你这台设备的浏览器里，退出登录就清掉（存放细节写在<a href="/about/#invite" className="inline-flex min-h-11 items-center text-blue-text underline underline-offset-2 sm:min-h-0">关于</a>页）。</dd></div>
          <div><dt className="label">看不到什么</dt><dd className="mt-1 font-sans text-[14px] leading-relaxed text-ink-2">原始聊天记录。登录也看不到——它根本不上站。</dd></div>
        </dl>
      </div>

      <form onSubmit={submit} className="rounded-[10px] border border-rule bg-paper-2/50 px-5 py-6 sm:px-6">
        <div className="space-y-4">
          <Field label="用户名" name="username" autoComplete="username" required value={u} onChange={(e) => setU(e.target.value)} placeholder="群里认得出你的名字" />
          <Field label="密码" name="password" type="password" autoComplete={mode === "in" ? "current-password" : "new-password"} required value={p} onChange={(e) => setP(e.target.value)} placeholder="至少 6 位" minLength={6} />
          {mode === "up" && (
            <>
              <label className="block">
                <span className="label">群昵称（选一个，这就是你的用户名）</span>
                <select value={name} onChange={(e) => setName(e.target.value)}
                  className="mt-1.5 block min-h-11 w-full rounded-[4px] border border-rule bg-paper px-3 py-2 font-sans text-[15px] text-ink outline-none transition-colors focus:border-blue-2 focus:bg-paper-2/50">
                  <option value="">选你的群昵称…</option>
                  {names.map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
                <span className="mt-1.5 block font-sans text-[12px] leading-snug text-ink-3">选对群昵称，登录后头像就是你的微信头像，发言也能对到人。用户名就用它，不用另起。</span>
              </label>
              <Field label="邀请码" name="invite_code" required value={code} onChange={(e) => setCode(e.target.value)} placeholder="群主发给你的那一串" hint={<>邀请码由群主发放，群内向 Sun 索取。一人一码、可撤销，填错会直接被挡下，不会建号。</>} />
            </>
          )}
        </div>
        {err && <div className="mt-4"><Note tone="bad">{err}</Note></div>}
        <div className="mt-5">
          <Btn type="submit" busy={busy}>{mode === "in" ? "登录" : "注册并登录"}</Btn>
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 font-sans text-[12px] text-ink-3">
          {mode === "in" ? (
            <>
              <span>没有账号？<span className="text-ink-2">找孙哥要一条认领链接，点开就能进来。</span></span>
              <button type="button" onClick={() => { setMode("up"); setErr(""); }} className="font-sans text-[12px] text-ink-3 underline decoration-1 underline-offset-[3px] transition-colors hover:text-blue-text">新人注册</button>
            </>
          ) : (
            <button type="button" onClick={() => { setMode("in"); setErr(""); }} className="font-sans text-[12px] text-ink-3 underline decoration-1 underline-offset-[3px] transition-colors hover:text-blue-text">← 回登录</button>
          )}
        </div>
        <p className="mt-4 font-sans text-[11.5px] leading-relaxed text-ink-3">
          密码只发给本站后端做哈希比对，不存明文、不发给第三方。这台设备退出登录会清掉票据。
        </p>
      </form>
    </div>
  );
}
