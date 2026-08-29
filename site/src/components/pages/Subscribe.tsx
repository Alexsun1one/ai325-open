"use client";
import { useState } from "react";
import { ApiError, apiFetch } from "@/lib/auth";
import { Btn, Field, Note } from "./FormBits";

/** 订阅登记：POST /api/subscribe。后端没有配 SMTP，所以只是登记，不发信——页面照实说。 */
export function Subscribe() {
  const [email, setEmail] = useState(""); const [name, setName] = useState("");
  const [busy, setBusy] = useState(false); const [err, setErr] = useState(""); const [ok, setOk] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(""); setOk(""); setBusy(true);
    try {
      await apiFetch<{ ok: boolean; message?: string }>("/api/subscribe", { method: "POST", body: JSON.stringify({ email: email.trim(), name: name.trim() }) });
      setOk("已登记。发信通道还没配，所以现在不会有邮件寄出——通道通了会从这份名单开始发。");
      setEmail(""); setName("");
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "登记失败，请稍后再试。");
    } finally { setBusy(false); }
  };

  return (
    <form onSubmit={submit} className="rounded-[10px] border border-rule bg-paper-2/50 px-5 py-6 sm:px-6">
      <div className="space-y-4">
        <Field label="邮箱" name="email" type="email" required inputMode="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
        <Field label="称呼（可空）" name="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="群里怎么叫你" />
      </div>
      {err && <div className="mt-4"><Note tone="bad">{err}</Note></div>}
      {ok && <div className="mt-4"><Note tone="good">{ok}</Note></div>}
      <div className="mt-5"><Btn type="submit" busy={busy}>登记邮箱</Btn></div>
      <p className="mt-4 font-sans text-[11.5px] leading-relaxed text-ink-3">
        只存邮箱、称呼和登记时间，存在本站自己的库里，不给第三方、不做画像。随时可以要求删除。
      </p>
    </form>
  );
}
