"use client";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";
import { ApiError, apiFetch, useAuth } from "@/lib/auth";
import { Btn, Field, Note } from "./FormBits";
import { Gate } from "./Gate";
import { CellarArticles, CellarEssay, CellarFavorites, CellarFragments, CellarTrail } from "./MyCellar";
import { VitalityCard } from "./VitalityCard";
import { GrowthWorkspace } from "./GrowthWorkspace";
import ws from "./GrowthWorkspace.module.css";
import m from "./MeCenter.module.css";

/** 家园视图按需加载。 */
const GardenView = dynamic(() => import("./GardenView").then((m) => m.default), {
  ssr: false,
  loading: () => <p className="py-8 font-sans text-[13px] text-ink-3">正在打开家园……</p>,
});

/** 值守台只有群主展开时才加载、才发请求。 */
const AlertCenter = dynamic(() => import("./AlertCenter").then((m) => m.AlertCenter), {
  ssr: false,
  loading: () => <p className="py-4 font-sans text-[13px] text-ink-3">正在读值守台……</p>,
});

/** 阅读与足迹：按需挂载，不让公共书库加载全站历史。 */
const ReadingHistory = dynamic(() => import("./ReadingHistory").then((m) => m.default), {
  ssr: false,
  loading: () => <p className="py-4 font-sans text-[13px] text-ink-3">正在读阅读足迹……</p>,
});

interface Settings { username: string; display_name?: string; member_key?: string; role?: string; email?: string; subscribed?: boolean }

/** 分区导航按使用频率分组；view query 的取值（深链）保持不变。 */
const GROUPS = [
  { label: "成长", items: [
    { id: "overview", label: "概览", d: "继续眼前的事" },
    { id: "mine", label: "我的实践", d: "目标与过程" },
    { id: "challenges", label: "共练", d: "一起练的项目" },
    { id: "garden", label: "家园", d: "偷菜小院" },
    { id: "reading", label: "阅读与足迹", d: "读过·收藏·读完" },
  ] },
  { label: "资料", items: [
    { id: "saved", label: "收藏与笔记", d: "收藏·随手记·长文" },
    { id: "vitality", label: "酒力", d: "我的贡献" },
  ] },
  { label: "账号", items: [
    { id: "agent", label: "我的 Agent", d: "协作者入口" },
    { id: "account", label: "账号", d: "订阅·密码·设置" },
  ] },
];
const VIEW_IDS = new Set(GROUPS.flatMap((g) => g.items.map((v) => v.id)));

function Section({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-rule pt-5 pb-8">
      <h3 className="font-serif text-[17px] font-bold text-ink">{title}{sub && <span className="ml-2.5 font-sans text-[12px] font-normal text-ink-3">{sub}</span>}</h3>
      <div className="mt-4 min-w-0">{children}</div>
    </section>
  );
}

/** 低频区块：首次展开才挂载（才取数），展开过后收起只是隐藏，组件状态和未存草稿都留着。 */
function Fold({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [used, setUsed] = useState(false);
  return (
    <section className="border-t border-rule">
      <button type="button" className={m.fold} aria-expanded={open} aria-controls={id} onClick={() => { setOpen((o) => !o); setUsed(true); }}>
        <span className="min-w-0"><span className={m.foldTitle}>{title}</span>{hint && <span className={m.foldHint}>{hint}</span>}</span>
        <svg aria-hidden width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" className={m.chev} data-open={open}><path d="M9 6l6 6-6 6" /></svg>
      </button>
      <div id={id} hidden={!open} className="pb-8 pt-1">{used && children}</div>
    </section>
  );
}

function Center() {
  const { user, signOut } = useAuth();
  const router = useRouter();
  const pathname = usePathname() || "/me/";
  const params = useSearchParams();
  const [s, setS] = useState<Settings | null>(null);
  const [loadErr, setLoadErr] = useState("");
  const seq = useRef(0);

  const load = useCallback(async () => {
    const cur = ++seq.current;
    try { const d = await apiFetch<Settings>("/api/me/settings"); if (cur === seq.current) { setS(d); setLoadErr(""); } }
    catch (e) { if (cur === seq.current) setLoadErr(e instanceof ApiError ? e.message : "读不到你的设置"); }
  }, []);
  useEffect(() => { const t = setTimeout(() => void load(), 0); return () => { clearTimeout(t); seq.current += 1; }; }, [load]);

  const name = s?.display_name || s?.username || user?.display_name || user?.username || "";
  const role = s?.role || user?.role || "member";
  const isAdmin = role === "admin";
  const rawView = params.get("view") || "";
  const view = VIEW_IDS.has(rawView) ? rawView : "overview";   // 未知值安全回概览
  const goView = (v: string) => router.push(`${pathname}?view=${v}`);

  return (
    <div>
      {/* 名片头 */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3 border-y border-rule py-4">
        <span aria-hidden className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-blue-wash-2 bg-blue-wash font-serif text-[22px] font-bold text-blue-text">
          {(name || "?").trim().slice(0, 1)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-serif text-[22px] font-black leading-tight text-ink sm:text-[26px]">{name || "……"}</div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 font-sans text-[13px]">
            <span className={`inline-flex rounded-[4px] border px-2 py-[2px] font-semibold ${isAdmin ? "border-cinnabar/45 bg-cinnabar-wash text-cinnabar-text" : "border-blue-wash-2 bg-blue-wash text-blue-text"}`}>
              {isAdmin ? "群主" : "群友"}
            </span>
            <span className="num text-ink-3">@{s?.username || user?.username}</span>
          </div>
        </div>
        <button type="button" onClick={() => void signOut()} className="inline-flex min-h-11 shrink-0 items-center font-sans text-[13px] text-blue-text hover:underline">退出登录</button>
      </div>

      {/* 工作区：左栏分组导航 + 右栏任务；手机换成分组下拉。每次只挂载当前分区。 */}
      <div className={ws.layout}>
        <nav aria-label="工作区分区">
          <label className="sr-only" htmlFor="me-view-select">选择分区</label>
          <select id="me-view-select" className={ws.viewSelect} value={view} onChange={(e) => goView(e.target.value)}>
            {GROUPS.map((g) => (
              <optgroup key={g.label} label={g.label}>
                {g.items.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
              </optgroup>
            ))}
          </select>
          <div className={ws.side}>
            {GROUPS.map((g) => (
              <div key={g.label} className="contents">
                <div className={m.group}>{g.label}</div>
                {g.items.map((v) => (
                  <button key={v.id} type="button" aria-current={view === v.id ? "page" : undefined}
                    className={`${ws.sideLink} ${view === v.id ? ws.sideOn : ""}`} onClick={() => goView(v.id)}>
                    {v.label}<small>{v.d}</small>
                  </button>
                ))}
              </div>
            ))}
          </div>
        </nav>
        <div className="min-w-0">
          {loadErr && <p className="mt-2 font-sans text-[12px] text-ink-3">{loadErr}<button type="button" className="ml-2 inline-flex min-h-11 items-center text-blue-text underline underline-offset-2" onClick={() => void load()}>重试</button></p>}
          {(view === "overview" || view === "mine" || view === "challenges") && <GrowthWorkspace />}

          {view === "garden" && <GardenView />}
          {view === "reading" && <ReadingHistory />}

          {view === "saved" && (
            <div>
              <div className="border-t-2 border-ink pt-4">
                <h2 className="font-serif text-[20px] font-black text-ink">收藏与笔记</h2>
                <p className="mt-1 font-sans text-[12px] leading-relaxed text-ink-3">随手记和长文草稿归你本人；收藏的段落与入群档案来自站内已有内容，原文可能是公开的。</p>
              </div>
              <div className="mt-4">
                <Section title="我的收藏" sub="在日报里点星收下的段落"><CellarFavorites /></Section>
                <Section title="随手记" sub="碎片,回车即存"><CellarFragments /></Section>
              </div>
              <div className="border-b border-rule">
                <Fold title="长文" hint="草稿自动保存"><CellarArticles /></Fold>
                <Fold title="入群档案" hint="你的入群小作文"><CellarEssay displayName={name} memberKey={s?.member_key} /></Fold>
                <Fold title="历期足迹" hint="台账里点到你的地方"><CellarTrail displayName={name} /></Fold>
              </div>
            </div>
          )}

          {view === "vitality" && (
            <div>
              <div className="border-t-2 border-ink pt-4">
                <h2 className="font-serif text-[20px] font-black text-ink">酒力<span className="ml-2.5 font-sans text-[12.5px] font-normal text-ink-3">我的贡献</span></h2>
                <p className="mt-1 font-sans text-[12px] text-ink-3">发言有日封顶；入窖、金句、批注才是大头。</p>
              </div>
              <div className="mt-5"><VitalityCard /></div>
            </div>
          )}

          {view === "agent" && (
            <div>
              <div className="border-t-2 border-ink pt-4">
                <h2 className="font-serif text-[20px] font-black text-ink">我的 Agent<span className="ml-2.5 font-sans text-[12.5px] font-normal text-ink-3">你的协作者</span></h2>
              </div>
              <p className="mt-4 max-w-[560px] font-sans text-[14px] leading-relaxed text-ink-2">
                Agent 的头像、身份和凭证统一在入驻页管理——换头像、发新钥匙、看绑定状态都在那里，这里不再放第二套。
              </p>
              <div className="mt-4">
                <Link href="/agents/join/" className="inline-flex min-h-11 items-center font-sans text-[13.5px] font-semibold text-blue-text underline underline-offset-4">管理我的 Agent →</Link>
              </div>
            </div>
          )}

          {view === "account" && (
            <div>
              <div className="border-t-2 border-ink pt-4">
                <h2 className="font-serif text-[20px] font-black text-ink">账号与设置</h2>
              </div>
              <div className="mt-3">
                <SubCard s={s} onSaved={load} />
                <PwRow />
                {isAdmin && (
                  <section className="border-t border-rule pt-5 pb-8">
                    <h3 className="font-serif text-[17px] font-bold text-ink">管理<span className="ml-2.5 font-sans text-[12px] font-normal text-ink-3">只有群主看得到</span></h3>
                    <ul className="mt-3 divide-y divide-rule-soft border-y border-rule">
                      {[
                        { href: "/admin/invites/", label: "邀请码后台", d: "生成、查看、撤销" },
                        { href: "/admin/accounts/", label: "账号后台", d: "开账号、绑微信身份、管名下学徒" },
                      ].map((x) => (
                        <li key={x.label}>
                          <Link href={x.href} className="group flex min-h-11 items-center justify-between gap-4 py-3 no-underline">
                            <span className="min-w-0">
                              <span className="block font-serif text-[16px] font-bold text-ink transition-colors group-hover:text-blue-text">{x.label}</span>
                              <span className="mt-0.5 block font-sans text-[12.5px] leading-relaxed text-ink-2">{x.d}</span>
                            </span>
                            <svg aria-hidden width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" className="shrink-0 text-ink-3"><path d="M9 6l6 6-6 6" /></svg>
                          </Link>
                        </li>
                      ))}
                    </ul>
                    <div className="mt-2"><Fold title="值守台" hint="自动化出没出事的灯，展开才读取"><AlertCenter /></Fold></div>
                  </section>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** 订阅：默认只给摘要 + 「修改」。开关只作用于服务器已存的邮箱；输入框里未存的邮箱是草稿，不参与开关。 */
function SubCard({ s, onSaved }: { s: Settings | null; onSaved: () => Promise<void> }) {
  const [saved, setSaved] = useState({ email: "", subscribed: false });   // 服务器已存
  const [draft, setDraft] = useState("");                                  // 输入框草稿
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(""); const [ok, setOk] = useState("");
  const [seeded, setSeeded] = useState<Settings | null>(null);

  // 设置对象到达时在渲染期同步（adjust-state-on-prop-change，不走 effect）；草稿有未存改动就不覆盖
  if (s && s !== seeded) {
    setSeeded(s);
    const e = s.email ?? "";
    if (draft.trim() === saved.email) setDraft(e);
    setSaved({ email: e, subscribed: !!s.subscribed });
  }
  const dirty = draft.trim() !== saved.email;

  const save = async (next: { email?: string; subscribed?: boolean }) => {
    setBusy(true); setErr(""); setOk("");
    try {
      const d = await apiFetch<Settings>("/api/me/settings", { method: "PATCH", body: JSON.stringify(next) });
      const e = d.email ?? "";
      setSaved({ email: e, subscribed: !!d.subscribed });
      if (next.email !== undefined) setDraft(e);
      setOk(next.subscribed === false ? "已退订，邮箱还留着。" : next.subscribed ? "已订阅。" : "邮箱已保存。");
      await onSaved();
    } catch (e) {
      const why = e instanceof ApiError ? e.message : "等会儿再试";
      setErr(next.email !== undefined ? `没有保存：${why}。你填的邮箱还在输入框里。` : `订阅状态没有改成：${why}。`);
    } finally { setBusy(false); }
  };

  return (
    <section className="border-t border-rule pt-5 pb-8">
      <h3 className="font-serif text-[17px] font-bold text-ink">订阅</h3>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className={`${m.pill} ${saved.subscribed ? m.pillOn : ""}`}>{saved.subscribed ? "已订阅" : "未订阅"}</span>
        <span className="min-w-0 break-all font-sans text-[13.5px] text-ink-2">{saved.email || "还没填邮箱"}</span>
        <button type="button" className={m.act} aria-expanded={open} onClick={() => setOpen((o) => !o)}>{open ? "收起" : "修改"}</button>
      </div>
      {err && <div className="mt-3"><Note tone="bad">{err}</Note></div>}
      {ok && <div className="mt-3"><Note tone="good">{ok}</Note></div>}
      {open && (
        <div className="mt-4 grid gap-x-10 gap-y-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,300px)]">
          <form className="min-w-0 space-y-4" onSubmit={(e) => { e.preventDefault(); void save({ email: draft.trim() }); }}>
            <Field label="邮箱" name="email" type="email" inputMode="email" autoComplete="email" value={draft}
              onChange={(e) => setDraft(e.target.value)} placeholder="you@example.com"
              hint="只用来接收品鉴单。换邮箱会一起改掉订阅记录。" />
            <Btn type="submit" busy={busy} disabled={!dirty}>存邮箱</Btn>
          </form>
          <div className="h-max rounded-[10px] border border-rule bg-paper-2/50 px-5 py-4">
            <div className="label mb-2">订阅品鉴单</div>
            <button type="button" role="switch" aria-checked={saved.subscribed} disabled={busy || !saved.email}
              onClick={() => void save({ subscribed: !saved.subscribed })}
              className="flex min-h-11 w-full items-center justify-between gap-4 disabled:cursor-not-allowed disabled:opacity-55">
              <span className="font-sans text-[14px] font-semibold text-ink">{saved.subscribed ? "已订阅" : "未订阅"}</span>
              <span aria-hidden className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full border transition-colors ${saved.subscribed ? "border-amber-deep bg-amber" : "border-rule bg-paper"}`}>
                <span className={`absolute h-5 w-5 rounded-full bg-paper shadow-[0_1px_2px_rgba(0,0,0,.2)] transition-transform duration-300 ease-[var(--ease-out-expo)] motion-reduce:transition-none ${saved.subscribed ? "translate-x-[24px]" : "translate-x-[3px]"}`} />
              </span>
            </button>
            <p className="mt-2 font-sans text-[12px] leading-relaxed text-ink-3">
              {!saved.email ? "先存一个邮箱，这个开关才有地方用。" : dirty ? "输入框里的新邮箱还没保存；开关只作用于已保存的邮箱。" : "开关立即保存，不用另外点保存。"}
            </p>
          </div>
        </div>
      )}
    </section>
  );
}

/** 密码入口：默认一行，展开才出表单。 */
function PwRow() {
  const [open, setOpen] = useState(false);
  return (
    <section className="border-t border-rule pt-5 pb-8">
      <h3 className="font-serif text-[17px] font-bold text-ink">登录密码<span className="ml-2.5 font-sans text-[12px] font-normal text-ink-3">改完其他设备要重登</span></h3>
      <div className="mt-1"><button type="button" className={m.act} aria-expanded={open} onClick={() => setOpen((o) => !o)}>{open ? "收起" : "修改密码"}</button></div>
      {open && <div className="mt-3"><PwCard /></div>}
    </section>
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
      setErr(st === 403 ? "当前密码未通过验证，请核对后重试。" : e2 instanceof ApiError ? e2.message : "没改成，等会儿再试。");
    } finally { setBusy(false); }
  };

  if (ok) {
    return (
      <div className="rounded-[10px] border border-teal/45 bg-teal-wash/70 px-6 py-6">
        <p className="font-serif text-[19px] font-bold text-ink">密码设好了。</p>
        <p className="mt-2 font-sans text-[13.5px] leading-relaxed text-ink-2">
          你这台设备还是登录着的；<b>其他设备上的登录已经全部失效</b>，要用新密码重登。手机上、公司电脑上，都得重来一次。
        </p>
        <button type="button" onClick={() => setOk(false)} className="mt-4 inline-flex min-h-11 items-center font-sans text-[13px] font-semibold text-blue-text hover:underline">再改一次</button>
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
  const { status, user } = useAuth();
  // 按账号身份 key 隔离：换账号登录整棵重挂载，旧账号的设置/私稿不会残留到新会话
  if (status === "in" && user) return <Center key={user.username} />;
  return <Gate what="我的成长" why="这里是你的工作区：实践目标、收藏与随手记、邮箱订阅、密码和 agent 钥匙都在这里；私人笔记只归你，你主动提交的共练成果会署名供登录群友交流。所以要先证明你是你。"><Center /></Gate>;
}
