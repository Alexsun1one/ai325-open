"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { API_BASE, ApiError, apiFetch, getToken, useAuth } from "@/lib/auth";
import { Btn, Field, Note } from "./FormBits";
import { Gate } from "./Gate";
import { CellarArticles, CellarEssay, CellarFavorites, CellarFragments, CellarTrail } from "./MyCellar";

interface Settings { username: string; display_name?: string; role?: string; email?: string; subscribed?: boolean }

function Card({ label, sub, children }: { label: string; sub?: string; children: React.ReactNode }) {
  return (
    <section className="grid grid-cols-1 gap-x-10 border-t border-rule pt-7 pb-12 lg:grid-cols-[168px_minmax(0,1fr)]">
      <div className="mb-5 lg:mb-0">
        <div className="label">{label}</div>
        {sub && <div className="mt-1.5 font-sans text-[12px] leading-snug text-ink-3 lg:max-w-[130px]">{sub}</div>}
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

function Center() {
  const { user, signOut } = useAuth();
  const [s, setS] = useState<Settings | null>(null);
  const [loadErr, setLoadErr] = useState("");

  const load = useCallback(async () => {
    try { setS(await apiFetch<Settings>("/api/me/settings")); setLoadErr(""); }
    catch (e) { setLoadErr(e instanceof ApiError ? e.message : "读不到你的设置"); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const name = s?.display_name || s?.username || user?.display_name || user?.username || "";
  const role = s?.role || user?.role || "member";
  const isAdmin = role === "admin";

  return (
    <div>
      {/* 名片头 */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-4 border-y border-rule py-6">
        <span aria-hidden className="inline-flex h-16 w-16 shrink-0 items-center justify-center rounded-full border border-blue-wash-2 bg-blue-wash font-serif text-[26px] font-bold text-blue-text">
          {(name || "?").trim().slice(0, 1)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-serif text-[26px] font-black leading-tight text-ink sm:text-[30px]">{name || "……"}</div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 font-sans text-[13px]">
            <span className={`inline-flex rounded-[4px] border px-2 py-[2px] font-semibold ${isAdmin ? "border-cinnabar/45 bg-cinnabar-wash text-cinnabar-text" : "border-blue-wash-2 bg-blue-wash text-blue-text"}`}>
              {isAdmin ? "群主" : "群友"}
            </span>
            <span className="num text-ink-3">@{s?.username || user?.username}</span>
          </div>
        </div>
        <button type="button" onClick={() => void signOut()} className="inline-flex min-h-11 shrink-0 items-center font-sans text-[13px] text-blue-text hover:underline sm:min-h-0">退出登录</button>
      </div>

      {loadErr && <div className="mt-6"><Note tone="bad">{loadErr}</Note></div>}

      {/* 私窖:这一格窖位归你 */}
      <div className="mt-12">
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
          <h2 className="font-serif text-[24px] font-black tracking-[0.01em] text-ink">
            私窖<span className="ml-2.5 font-sans text-[12.5px] font-normal tracking-normal text-ink-3">这条街上属于你的那一格</span>
          </h2>
          <span className="font-sans text-[12px] text-ink-3">收藏和你写的东西全部私有,只有你自己看得见</span>
        </div>
        <div className="mt-7">
          <Card label="入窖档案" sub="你的入群小作文">
            <CellarEssay displayName={name} />
          </Card>
          <Card label="历期足迹" sub="台账里点到你的地方">
            <CellarTrail displayName={name} />
          </Card>
          <Card label="我的收藏" sub="在日报里点星收下的段落">
            <CellarFavorites />
          </Card>
          <Card label="随手记" sub="碎片,回车即存">
            <CellarFragments />
          </Card>
          <Card label="长文" sub="草稿自动保存">
            <CellarArticles />
          </Card>
        </div>
      </div>

      <div className="mt-10">
        <Card label="订阅" sub="每天早上寄一份">
          <SubCard s={s} onSaved={load} />
        </Card>

        <Card label="改密码" sub="改完其他设备要重登">
          <PwCard />
        </Card>

        <Card label="常用去处" sub="都在你名下">
          <ul className="divide-y divide-rule-soft border-y border-rule">
            {[
              { href: "/#", label: "我的划线与笔记", d: "在日报里选中一句就能记下；导出在笔记抽屉里", ext: false },
              { href: "/agents/#key", label: "agent 钥匙", d: "发一把给你的 agent，它就能代你读和写", ext: false },
              ...(isAdmin ? [
                { href: "/admin/invites/", label: "邀请码后台", d: "生成、查看、撤销——只有你看得到这一项", ext: false },
                { href: "/admin/accounts/", label: "账号后台", d: "给群成员开账号、绑微信身份、管名下学徒", ext: false },
              ] : []),
            ].map((x) => (
              <li key={x.label}>
                <Link href={x.href} className="group flex min-h-11 items-center justify-between gap-4 py-4 no-underline">
                  <span className="min-w-0">
                    <span className="block font-serif text-[17px] font-bold text-ink transition-colors group-hover:text-blue-text">{x.label}</span>
                    <span className="mt-0.5 block font-sans text-[13px] leading-relaxed text-ink-2">{x.d}</span>
                  </span>
                  <svg aria-hidden width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" className="shrink-0 text-ink-3 transition-transform group-hover:translate-x-1"><path d="M9 6l6 6-6 6" /></svg>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}

/** 订阅：邮箱 + 开关。开关只在填了邮箱之后才有意义，所以没邮箱时它是灰的。 */
function SubCard({ s, onSaved }: { s: Settings | null; onSaved: () => Promise<void> }) {
  const [email, setEmail] = useState("");
  const [sub, setSub] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(""); const [ok, setOk] = useState("");

  useEffect(() => { if (s) { setEmail(s.email ?? ""); setSub(!!s.subscribed); } }, [s]);

  const save = async (next: { email?: string; subscribed?: boolean }) => {
    setBusy(true); setErr(""); setOk("");
    try {
      const d = await apiFetch<Settings>("/api/me/settings", { method: "PATCH", body: JSON.stringify(next) });
      setEmail(d.email ?? ""); setSub(!!d.subscribed);
      setOk(next.subscribed === false ? "已退订。想回来随时打开。" : "存好了。");
      await onSaved();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "没存上，等会儿再试。");
      if (s) { setEmail(s.email ?? ""); setSub(!!s.subscribed); }   // 失败就退回原值，别让开关停在假状态
    } finally { setBusy(false); }
  };

  return (
    <div className="grid gap-x-10 gap-y-7 lg:grid-cols-[minmax(0,1fr)_minmax(0,300px)]">
      <div className="min-w-0">
        <p className="prose-sheet text-[16.5px] leading-[1.85] text-ink-2">
          留个邮箱，<b>每天早上 07:45 把当批品鉴单寄到这里</b>。不想收了随时关掉，邮箱还留着。
        </p>
        <form className="mt-6 space-y-4" onSubmit={(e) => { e.preventDefault(); void save({ email: email.trim() }); }}>
          <Field label="邮箱" name="email" type="email" inputMode="email" autoComplete="email" value={email}
            onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com"
            hint="只用来寄这份日报。换邮箱会一起改掉订阅记录。" />
          <Btn type="submit" busy={busy}>存邮箱</Btn>
        </form>
        {err && <div className="mt-4"><Note tone="bad">{err}</Note></div>}
        {ok && <div className="mt-4"><Note tone="good">{ok}</Note></div>}
      </div>

      <div className="h-max rounded-[10px] border border-rule bg-paper-2/50 px-5 py-5">
        <div className="label mb-3">每天寄一份</div>
        <button type="button" role="switch" aria-checked={sub} disabled={busy || !email.trim()}
          onClick={() => void save({ subscribed: !sub })}
          className="flex min-h-11 w-full items-center justify-between gap-4 disabled:cursor-not-allowed disabled:opacity-55">
          <span className="font-sans text-[14px] font-semibold text-ink">{sub ? "在寄" : "没在寄"}</span>
          <span aria-hidden className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full border transition-colors ${sub ? "border-amber-deep bg-amber" : "border-rule bg-paper"}`}>
            <span className={`absolute h-5 w-5 rounded-full bg-paper shadow-[0_1px_2px_rgba(0,0,0,.2)] transition-transform duration-300 ease-[var(--ease-out-expo)] ${sub ? "translate-x-[24px]" : "translate-x-[3px]"}`} />
          </span>
        </button>
        <p className="mt-3 font-sans text-[12px] leading-relaxed text-ink-3">
          {email.trim() ? "改了立刻生效，不用另外保存。" : "先存一个邮箱，这个开关才有地方寄。"}
        </p>
      </div>
    </div>
  );
}

/** 改密码：密码只发给本站后端做哈希比对。页面从不保存、从不回显。首次设置（认领链接进来没设过）时，旧密码留空即可。 */
function PwCard() {
  const [oldPw, setOldPw] = useState(""); const [newPw, setNewPw] = useState(""); const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false); const [err, setErr] = useState(""); const [ok, setOk] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPw.length < 8) { setErr("新密码至少 8 位。"); return; }
    if (newPw !== again) { setErr("两次输入的新密码不一样。"); return; }
    setBusy(true); setErr(""); setOk(false);
    try {
      await apiFetch("/api/me/password", { method: "POST", body: JSON.stringify({ old_password: oldPw, new_password: newPw }) });
      setOk(true); setOldPw(""); setNewPw(""); setAgain("");
    } catch (e2) {
      const st = e2 instanceof ApiError ? e2.status : 0;
      setErr(st === 403 ? (oldPw ? "原来的密码不对。" : "这个账号还没设过密码，把旧密码留空直接设新的就行。") : e2 instanceof ApiError ? e2.message : "没改成，等会儿再试。");
    } finally { setBusy(false); }
  };

  if (ok) {
    return (
      <div className="rounded-[10px] border border-teal/45 bg-teal-wash/70 px-6 py-6">
        <p className="font-serif text-[19px] font-bold text-ink">密码设好了。</p>
        <p className="mt-2 font-sans text-[13.5px] leading-relaxed text-ink-2">
          你这台设备还是登录着的；<b>其他设备上的登录已经全部失效</b>，要用新密码重登。手机上、公司电脑上，都得重来一次。
        </p>
        <button type="button" onClick={() => setOk(false)} className="mt-4 inline-flex min-h-11 items-center font-sans text-[13px] font-semibold text-blue-text hover:underline sm:min-h-0">再改一次</button>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="max-w-[420px] rounded-[10px] border border-rule bg-paper-2/50 px-5 py-6">
      <div className="space-y-4">
        <Field label="现在的密码（第一次设置就留空）" name="old_password" type="password" autoComplete="current-password" value={oldPw} onChange={(e) => setOldPw(e.target.value)} />
        <Field label="新密码" name="new_password" type="password" autoComplete="new-password" required minLength={8} value={newPw} onChange={(e) => setNewPw(e.target.value)}
          hint={<span className={newPw && newPw.length < 8 ? "text-amber-text" : undefined}>至少 8 位{newPw && newPw.length < 8 ? `，现在 ${newPw.length} 位` : ""}</span>} />
        <Field label="再输一次新密码" name="again" type="password" autoComplete="new-password" required value={again} onChange={(e) => setAgain(e.target.value)} />
      </div>
      {err && <div className="mt-4"><Note tone="bad">{err}</Note></div>}
      <div className="mt-5"><Btn type="submit" busy={busy}>设密码</Btn></div>
      <p className="mt-4 font-sans text-[11.5px] leading-relaxed text-ink-3">
        改完之后，<b>除了你正在用的这台设备，其他地方的登录都会失效</b>。这是故意的——密码换了，旧的登录就不该还留着。
      </p>
    </form>
  );
}

export function MeCenter() {
  const { status } = useAuth();
  if (status === "in") return <Center />;
  return <Gate what="用户中心" why="这里放的是你自己的东西：邮箱、订阅、密码、你发出去的 agent 钥匙。所以要先证明你是你。"><Center /></Gate>;
}
