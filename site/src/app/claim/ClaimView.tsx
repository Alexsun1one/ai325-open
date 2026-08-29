"use client";
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ApiError, apiFetch, TOKEN_KEY } from "@/lib/auth";
import { Btn, Field, Note } from "@/components/pages/FormBits";

/** 契约（backend 追加节待定稿，见报告契约缺口节）：
 *  POST /api/auth/claim { token } → 成功 { token: 会话, username, display_name, role, has_password }
 *     失败 404/410（无效/过期/已用）detail 人话
 *  未设密码（has_password=false）时，改密码用 /api/me/password，old_password 传空串一次
 */
type Phase = "claiming" | "ok" | "need_pw" | "fail";

function ClaimView() {
  const params = useSearchParams();
  const t = params?.get("t") ?? "";
  const [phase, setPhase] = useState<Phase>("claiming");
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [user, setUser] = useState<{ username: string; display_name?: string } | null>(null);
  const [pw, setPw] = useState(""); const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const done = useRef(false);

  useEffect(() => {
    if (done.current || !t) { if (!t) { setPhase("fail"); setErr("这条链接缺了钥匙串（token）。"); } return; }
    done.current = true;
    apiFetch<{ token: string; username: string; display_name?: string; role?: string; has_password?: boolean }>("/api/auth/claim", {
      method: "POST", body: JSON.stringify({ token: t }),
    })
      .then((d) => {
        try { localStorage.setItem(TOKEN_KEY, d.token); } catch {}
        setUser({ username: d.username, display_name: d.display_name });
        setPhase(d.has_password === false ? "need_pw" : "ok");
      })
      .catch((e) => {
        setPhase("fail");
        setErr(e instanceof ApiError ? e.message : "这条链接没兑上。");
      });
  }, [t]);

  const setPassword = async () => {
    if (pw.length < 8) { setErr("密码至少 8 位。"); return; }
    if (pw !== again) { setErr("两次输入的密码不一样。"); return; }
    setBusy(true); setErr("");
    try {
      await apiFetch("/api/me/password", { method: "POST", body: JSON.stringify({ old_password: "", new_password: pw }) });
      setMsg("密码设好了。下次可以直接用用户名和密码登录。");
      setPhase("ok");
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "没设成，等会儿再试。");
    } finally { setBusy(false); }
  };

  if (phase === "claiming") {
    return <p className="py-14 text-center font-sans text-[14px] text-ink-3">正在开窖门……</p>;
  }
  if (phase === "fail") {
    return (
      <div className="mx-auto max-w-[440px] py-14">
        <h1 className="font-serif text-[28px] font-bold text-ink">这条链接没兑上</h1>
        <div className="mt-4"><Note tone="bad">{err}</Note></div>
        <p className="mt-4 font-sans text-[14px] leading-relaxed text-ink-2">
          认领链接只让用一次，过期（7 天）或已经用掉都会失效。找孙哥再要一条新的就行——拿到新链接，点开就能进来。
        </p>
        <div className="mt-6"><Btn type="button" tone="ghost" onClick={() => (window.location.href = "/")}>回站里看看</Btn></div>
      </div>
    );
  }
  if (phase === "need_pw") {
    return (
      <div className="mx-auto max-w-[440px] py-12">
        <h1 className="font-serif text-[28px] font-bold text-ink">进来啦，{user?.display_name || user?.username}</h1>
        <p className="mt-3 font-sans text-[14.5px] leading-relaxed text-ink-2">
          这条链接是一次性的，下次再想进来，得用用户名和密码。现在设一个，以后直接登录；也可以先跳过，之后在「我的」里再设。
        </p>
        <div className="mt-6 rounded-[10px] border border-rule bg-paper-2/50 px-5 py-6">
          <div className="space-y-4">
            <Field label="设个密码" name="new_password" type="password" autoComplete="new-password" minLength={8} value={pw} onChange={(e) => setPw(e.target.value)} placeholder="至少 8 位" />
            <Field label="再输一次" name="again" type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} />
          </div>
          {err && <div className="mt-4"><Note tone="bad">{err}</Note></div>}
          {msg && <div className="mt-4"><Note tone="good">{msg}</Note></div>}
          <div className="mt-5 flex flex-wrap gap-2">
            <Btn type="button" busy={busy} onClick={() => void setPassword()}>设好，下次直接登录</Btn>
            <Btn type="button" tone="ghost" onClick={() => (window.location.href = "/")}>先跳过</Btn>
          </div>
        </div>
      </div>
    );
  }
  // ok：已设密码的账号直接进站
  return (
    <div className="mx-auto max-w-[440px] py-14 text-center">
      <h1 className="font-serif text-[28px] font-bold text-ink">进来啦，{user?.display_name || user?.username}</h1>
      {msg && <div className="mt-4"><Note tone="good">{msg}</Note></div>}
      <p className="mt-4 font-sans text-[14px] text-ink-2">正在带你回站里……</p>
      <div className="mt-6"><Btn type="button" onClick={() => (window.location.href = "/")}>进站</Btn></div>
    </div>
  );
}

export default function ClaimPage() {
  return (
    <Suspense fallback={<p className="py-14 text-center font-sans text-[14px] text-ink-3">正在开窖门……</p>}>
      <ClaimView />
    </Suspense>
  );
}
