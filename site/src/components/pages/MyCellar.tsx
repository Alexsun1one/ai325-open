"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, apiFetch } from "@/lib/auth";
import { fmtInt, pad3 } from "@/lib/shared";
import { loadPeople } from "../sheet/PersonHover";
import { Btn, Field, Note } from "./FormBits";

/* ── 私窖:每个群友在 /me 下的那一格窖位 ──
   一期 入窖档案+历期足迹(纯聚合,数据来自公开治理产物);
   二期 我的收藏;三期 随手记/长文(全部私有)。 */

type St = "loading" | "ok" | "err";

function fmtAt(s?: string) {
  return (s ?? "").replace("T", " ").slice(0, 16);
}

/** display_name 与台账里的名字可能不一致:用 people.json 的 aliases 辅助,凑不上就是凑不上。 */
function useMatchNames(displayName: string) {
  const [names, setNames] = useState<string[] | null>(null);
  useEffect(() => {
    let alive = true;
    loadPeople().then((ps) => {
      if (!alive) return;
      if (!displayName) { setNames([]); return; }
      const p = ps.find((x) => x.name === displayName || x.aliases.includes(displayName));
      setNames(Array.from(new Set([displayName, ...(p ? [p.name, ...p.aliases] : [])])));
    });
    return () => { alive = false; };
  }, [displayName]);
  return names;
}

/* ── 一期 · 入窖档案 ── */

interface Essay { title: string; author: string; date: string; word_count: number }

export function CellarEssay({ displayName }: { displayName: string }) {
  const names = useMatchNames(displayName);
  const [st, setSt] = useState<St>("loading");
  const [items, setItems] = useState<Essay[]>([]);

  useEffect(() => {
    let alive = true;
    apiFetch<{ items: Essay[] }>("/api/governed/essays")
      .then((d) => { if (alive) { setItems(d.items ?? []); setSt("ok"); } })
      .catch(() => { if (alive) setSt("err"); });
    return () => { alive = false; };
  }, []);

  // 窖藏页按「入窖日期升序、同日按作者」排架,#essay-N 的 N 就是这个序;这里照同一把尺子算回去
  const shelf = useMemo(() => items.slice().sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.author.localeCompare(b.author))), [items]);
  const mine = useMemo(() => {
    if (!names) return [];
    return shelf.map((e, i) => ({ e, i })).filter(({ e }) => names.includes(e.author));
  }, [shelf, names]);

  if (st === "loading" || names === null) return <p className="font-sans text-[13px] text-ink-3">正在开窖……</p>;
  if (st === "err") return <Note tone="bad">窖藏这会儿读不到,等会儿再来看。</Note>;
  if (!mine.length) {
    return (
      <p className="font-sans text-[13.5px] leading-relaxed text-ink-2">
        窖里还没有你署名的瓶子。写一篇入群小作文交给群主,入窖之后会出现在这里
        {displayName ? <>(按「<b className="text-ink">{displayName}</b>」这个名字找的;台账里若用的是别的称呼,可能对不上号)</> : null}。
      </p>
    );
  }
  return (
    <ul className="divide-y divide-rule-soft border-y border-rule">
      {mine.map(({ e, i }) => (
        <li key={`${e.author}-${e.date}`}>
          <a href={`/essays/#essay-${i + 1}`} className="group flex min-h-11 items-center justify-between gap-4 py-4 no-underline">
            <span className="min-w-0">
              <span className="block truncate font-serif text-[17px] font-bold text-ink transition-colors group-hover:text-blue-text">{e.title}</span>
              <span className="num mt-0.5 block font-sans text-[12.5px] text-ink-3">{e.date} 入窖 · {fmtInt(e.word_count)} 字</span>
            </span>
            <svg aria-hidden width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" className="shrink-0 text-ink-3 transition-transform group-hover:translate-x-1"><path d="M9 6l6 6-6 6" /></svg>
          </a>
        </li>
      ))}
    </ul>
  );
}

/* ── 一期 · 历期足迹:遍历各期台账里点到我名字的地方 ── */

interface LedgerSummary { date: string; issue: number | null }
interface LedgerDetail {
  date?: string; issue?: number | null;
  members_focus?: { name: string; role?: string; msgs?: number; quote?: string }[];
  quotes?: { t: string; a: string }[];
  newcomers?: { name: string; note?: string; first_words?: string }[];
}
interface Step { date: string; issue: number | null; kind: string; text: string; url: string }

const TRAIL_SCAN_LIMIT = 60; // 一天一期,60 期 ≈ 两个月;再往前的翻往期页去看

export function CellarTrail({ displayName }: { displayName: string }) {
  const names = useMatchNames(displayName);
  const [st, setSt] = useState<St>("loading");
  const [steps, setSteps] = useState<Step[]>([]);

  useEffect(() => {
    if (!names) return;
    let alive = true;
    (async () => {
      try {
        const list = await apiFetch<{ items: LedgerSummary[] }>("/api/governed/ledgers");
        const dates = (list.items ?? []).slice(0, TRAIL_SCAN_LIMIT);
        const details = await Promise.all(dates.map((s) =>
          apiFetch<LedgerDetail>(`/api/governed/ledgers/${s.date}`).catch(() => null)
        ));
        if (!alive) return;
        const out: Step[] = [];
        for (const d of details) {
          if (!d?.date) continue;
          const at = (kind: string, text: string, sec: string) =>
            out.push({ date: d.date!, issue: d.issue ?? null, kind, text, url: `/ledger/${d.date}/#${sec}` });
          for (const m of d.members_focus ?? []) if (names.includes(m.name)) at("高光", m.quote || m.role || "", "members");
          for (const q of d.quotes ?? []) if (names.includes(q.a)) at("金句", q.t, "quotes");
          for (const n of d.newcomers ?? []) if (names.includes(n.name)) at("新面孔", n.first_words || n.note || "", "members");
        }
        // 同一句常同时进「高光」和「逐字摘录」,按 日期+原文 去重,留先扫到的那条
        const seen = new Set<string>();
        const uniq = out.filter((s) => { const k = `${s.date}|${s.text}`; if (seen.has(k)) return false; seen.add(k); return true; });
        uniq.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
        setSteps(uniq); setSt("ok");
      } catch {
        if (alive) setSt("err");
      }
    })();
    return () => { alive = false; };
  }, [names]);

  if (st === "loading" || names === null) return <p className="font-sans text-[13px] text-ink-3">正在沿着台账找你的脚印……</p>;
  if (st === "err") return <Note tone="bad">台账这会儿读不到,等会儿再来看。</Note>;
  if (!steps.length) {
    return (
      <p className="font-sans text-[13.5px] leading-relaxed text-ink-2">
        台账里还没你的足迹——多说话,蒸馏器听着呢。
        {displayName ? <span className="text-ink-3">(按「{displayName}」找的;群里若用别的名字,足迹就记在那个名字底下)</span> : null}
      </p>
    );
  }
  return (
    <div>
      <p className="mb-3 font-sans text-[12.5px] text-ink-3">
        从近往回数,台账点到你 <b className="num font-semibold text-amber-text">{steps.length}</b> 次。这就是你进群以来被蒸出来的样子。
      </p>
      <ol className="border-l border-rule pl-5">
        {steps.map((s, i) => (
          <li key={`${s.date}-${s.kind}-${i}`} className="relative pb-6 last:pb-0">
            <span aria-hidden className={`absolute -left-[23px] top-[7px] h-[7px] w-[7px] rounded-full ${s.kind === "新面孔" ? "bg-teal" : s.kind === "金句" ? "bg-amber" : "bg-blue"}`} />
            <a href={s.url} className="group block no-underline">
              <span className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
                <span className="num font-sans text-[12.5px] font-semibold text-ink-2">{s.issue != null ? `第 ${pad3(s.issue)} 批` : s.date}</span>
                <span className="label text-[11px]">{s.kind}</span>
                <span className="num font-sans text-[11.5px] text-ink-3">{s.date}</span>
              </span>
              {s.text && <span className="prose-sheet mt-1 block text-[15.5px] leading-[1.8] text-ink-2 transition-colors group-hover:text-ink">「{s.text}」</span>}
              <span className="mt-0.5 inline-block font-sans text-[12px] text-blue-text opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">跳回那一期 →</span>
            </a>
          </li>
        ))}
      </ol>
    </div>
  );
}

/* ── 二期 · 我的收藏 ── */

interface Fav { id: number; anchor: string; text: string; section: string; date: string; created_at: string }

function favUrl(anchor: string): string | null {
  const i = anchor.indexOf("#");
  if (i < 0) return null;
  const date = anchor.slice(0, i);
  const sec = anchor.slice(i + 1).replace(/-p\d+$/, "");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !sec) return null;
  return `/ledger/${date}/#${sec}`;
}

export function CellarFavorites() {
  const [st, setSt] = useState<St>("loading");
  const [items, setItems] = useState<Fav[]>([]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    apiFetch<{ items: Fav[] }>("/api/me/favorites")
      .then((d) => { if (alive) { setItems(d.items ?? []); setSt("ok"); } })
      .catch(() => { if (alive) setSt("err"); });
    return () => { alive = false; };
  }, []);

  const del = async (id: number) => {
    setBusyId(id); setErr("");
    try { await apiFetch(`/api/me/favorites/${id}`, { method: "DELETE" }); setItems((xs) => xs.filter((x) => x.id !== id)); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "没删掉,等会儿再试。"); }
    finally { setBusyId(null); }
  };

  if (st === "loading") return <p className="font-sans text-[13px] text-ink-3">正在取你收着的段落……</p>;
  if (st === "err") return <Note tone="bad">收藏这会儿读不到,等会儿再来看。</Note>;
  if (!items.length) {
    return (
      <p className="font-sans text-[13.5px] leading-relaxed text-ink-2">
        还一条都没收。翻日报的时候,悬停任意一段,点 <b className="text-amber-text">星</b> 就收进这里——好句子过眼就忘,收下来才是你的。
      </p>
    );
  }
  return (
    <div>
      {err && <div className="mb-4"><Note tone="bad">{err}</Note></div>}
      <ul className="divide-y divide-rule-soft border-y border-rule">
        {items.map((f) => {
          const url = favUrl(f.anchor);
          return (
            <li key={f.id} className="py-5">
              <blockquote className="prose-sheet border-l-2 border-amber-deep/60 pl-4 text-[15.5px] leading-[1.85] text-ink-2">{f.text}</blockquote>
              <div className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 pl-4">
                <span className="num font-sans text-[12px] text-ink-3">
                  {f.section || "日报"}{f.date ? ` · ${f.date}` : ""}
                  {url && <a href={url} className="ml-2.5 font-medium text-blue-text no-underline hover:underline">跳回原文 →</a>}
                </span>
                <button type="button" onClick={() => void del(f.id)} disabled={busyId === f.id}
                  className="font-sans text-[12px] text-ink-3 transition-colors hover:text-cinnabar-text disabled:opacity-50">
                  {busyId === f.id ? "撤下中…" : "撤下"}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/* ── 三期 · 随手记(fragment):回车即存,倒序流 ── */

interface NoteItem { id: number; kind: string; title: string; content: string; created_at: string; updated_at: string }

export function CellarFragments() {
  const [st, setSt] = useState<St>("loading");
  const [items, setItems] = useState<NoteItem[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    apiFetch<{ items: NoteItem[] }>("/api/me/notes?kind=fragment")
      .then((d) => { if (alive) { setItems(d.items ?? []); setSt("ok"); } })
      .catch(() => { if (alive) setSt("err"); });
    return () => { alive = false; };
  }, []);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;
    setBusy(true); setErr("");
    try {
      const d = await apiFetch<{ id: number }>("/api/me/notes", { method: "POST", body: JSON.stringify({ kind: "fragment", content: text }) });
      const now = new Date();
      const at = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")} ${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
      setItems((xs) => [{ id: d.id, kind: "fragment", title: "", content: text, created_at: at, updated_at: at }, ...xs]);
      setDraft("");
    } catch (e2) { setErr(e2 instanceof ApiError ? e2.message : "没记上,等会儿再试。"); }
    finally { setBusy(false); }
  };

  const del = async (id: number) => {
    setBusyId(id); setErr("");
    try { await apiFetch(`/api/me/notes/${id}`, { method: "DELETE" }); setItems((xs) => xs.filter((x) => x.id !== id)); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "没删掉,等会儿再试。"); }
    finally { setBusyId(null); }
  };

  return (
    <div>
      <form onSubmit={add}>
        <label className="block">
          <span className="sr-only">记一笔</span>
          <input value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={2000} disabled={busy}
            placeholder="记一笔,想到什么写什么——回车即存"
            className="hand block min-h-11 w-full rounded-[4px] border border-rule bg-paper px-3 py-2 text-[16px] leading-[1.7] text-ink outline-none transition-colors placeholder:text-ink-3/70 focus:border-blue-2 focus:bg-paper-2/50 disabled:opacity-60" />
        </label>
      </form>
      {err && <div className="mt-3"><Note tone="bad">{err}</Note></div>}

      {st === "loading" && <p className="mt-4 font-sans text-[13px] text-ink-3">正在开你的格子……</p>}
      {st === "err" && <div className="mt-4"><Note tone="bad">随手记这会儿读不到,等会儿再来看。</Note></div>}
      {st === "ok" && !items.length && (
        <p className="mt-4 font-sans text-[13px] leading-relaxed text-ink-3">还空着。第一笔从上面那个框开始——碎片多了,自然就想写深的。</p>
      )}
      {items.length > 0 && (
        <ul className="mt-5 divide-y divide-rule-soft border-y border-rule">
          {items.map((n) => (
            <li key={n.id} className="py-4">
              <p className="hand whitespace-pre-wrap text-[16px] leading-[1.8] text-ink">{n.content}</p>
              <div className="mt-1.5 flex items-center justify-between gap-4">
                <span className="num font-sans text-[11.5px] text-ink-3">{fmtAt(n.created_at)}</span>
                <button type="button" onClick={() => void del(n.id)} disabled={busyId === n.id}
                  className="font-sans text-[12px] text-ink-3 transition-colors hover:text-cinnabar-text disabled:opacity-50">
                  {busyId === n.id ? "撤下中…" : "撤下"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ── 三期 · 长文(article):标题+正文,草稿自动保存 ── */

export function CellarArticles() {
  const [st, setSt] = useState<St>("loading");
  const [items, setItems] = useState<NoteItem[]>([]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [listErr, setListErr] = useState("");

  const [edit, setEdit] = useState<{ id: number | null; title: string; content: string } | null>(null);
  const [saveSt, setSaveSt] = useState<"idle" | "saving" | "saved" | "err">("idle");
  const [savedAt, setSavedAt] = useState("");
  const idRef = useRef<number | null>(null);
  const saveT = useRef<number | undefined>(undefined);
  const savingRef = useRef(false);
  const dirtyRef = useRef(false);
  const latest = useRef<{ title: string; content: string }>({ title: "", content: "" });

  const load = useCallback(async () => {
    try { const d = await apiFetch<{ items: NoteItem[] }>("/api/me/notes?kind=article"); setItems(d.items ?? []); setSt("ok"); }
    catch { setSt("err"); }
  }, []);
  useEffect(() => {
    let alive = true;
    apiFetch<{ items: NoteItem[] }>("/api/me/notes?kind=article")
      .then((d) => { if (alive) { setItems(d.items ?? []); setSt("ok"); } })
      .catch(() => { if (alive) setSt("err"); });
    return () => { alive = false; };
  }, []);

  const doSave = useCallback(async () => {
    if (savingRef.current) { dirtyRef.current = true; return; }
    savingRef.current = true;
    do {
      dirtyRef.current = false;
      const { title, content } = latest.current;
      if (!title.trim() && !content.trim()) break;
      setSaveSt("saving");
      try {
        if (idRef.current == null) {
          const d = await apiFetch<{ id: number }>("/api/me/notes", { method: "POST", body: JSON.stringify({ kind: "article", title, content }) });
          idRef.current = d.id;
          setEdit((cur) => (cur ? { ...cur, id: d.id } : cur));
        } else {
          await apiFetch(`/api/me/notes/${idRef.current}`, { method: "PATCH", body: JSON.stringify({ title, content }) });
        }
        setSaveSt("saved");
        const now = new Date();
        setSavedAt(`${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`);
      } catch { setSaveSt("err"); }
    } while (dirtyRef.current);
    savingRef.current = false;
  }, []);

  const schedule = useCallback((next: { title: string; content: string }) => {
    latest.current = next;
    window.clearTimeout(saveT.current);
    saveT.current = window.setTimeout(() => { void doSave(); }, 900);
  }, [doSave]);
  useEffect(() => () => window.clearTimeout(saveT.current), []);

  const openNew = () => { idRef.current = null; latest.current = { title: "", content: "" }; setSaveSt("idle"); setSavedAt(""); setEdit({ id: null, title: "", content: "" }); };
  const openOld = (n: NoteItem) => { idRef.current = n.id; latest.current = { title: n.title, content: n.content }; setSaveSt("idle"); setSavedAt(""); setEdit({ id: n.id, title: n.title, content: n.content }); };
  const close = async () => {
    window.clearTimeout(saveT.current);
    if (latest.current.title.trim() || latest.current.content.trim()) await doSave();
    setEdit(null); await load();
  };

  const del = async (id: number) => {
    setBusyId(id); setListErr("");
    try { await apiFetch(`/api/me/notes/${id}`, { method: "DELETE" }); setItems((xs) => xs.filter((x) => x.id !== id)); }
    catch (e) { setListErr(e instanceof ApiError ? e.message : "没删掉,等会儿再试。"); }
    finally { setBusyId(null); }
  };

  if (edit) {
    return (
      <div className="rounded-[10px] border border-rule bg-paper-2/50 px-5 py-6">
        <div className="space-y-4">
          <Field label="标题" name="title" maxLength={80} value={edit.title} placeholder="这篇想说什么"
            onChange={(e) => { const v = e.target.value; setEdit((c) => c && { ...c, title: v }); schedule({ title: v, content: edit.content }); }} />
          <label className="block">
            <span className="label">正文</span>
            <textarea value={edit.content} maxLength={20000} rows={14} placeholder="展开写。纯文本就好,空一行是分段。"
              onChange={(e) => { const v = e.target.value; setEdit((c) => c && { ...c, content: v }); schedule({ title: edit.title, content: v }); }}
              className="prose-sheet mt-1.5 block w-full resize-y rounded-[4px] border border-rule bg-paper px-3.5 py-3 text-[16.5px] leading-[1.85] text-ink outline-none transition-colors placeholder:font-sans placeholder:text-[14px] placeholder:text-ink-3/70 focus:border-blue-2" />
          </label>
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <span className="num font-sans text-[12px] text-ink-3" role="status">
            {saveSt === "saving" ? "存草稿中…" : saveSt === "saved" ? `草稿已存 ${savedAt}` : saveSt === "err" ? "草稿没存上,还在重试——先别关页面" : "边写边自动存,不用手动保存"}
          </span>
          <Btn type="button" onClick={() => void close()}>写完了,回列表</Btn>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="font-sans text-[13.5px] leading-relaxed text-ink-2">碎片攒多了,就值得写一篇像样的。</p>
        <Btn type="button" onClick={openNew}>写一篇</Btn>
      </div>
      {listErr && <div className="mt-4"><Note tone="bad">{listErr}</Note></div>}

      {st === "loading" && <p className="mt-4 font-sans text-[13px] text-ink-3">正在开你的格子……</p>}
      {st === "err" && <div className="mt-4"><Note tone="bad">长文这会儿读不到,等会儿再来看。</Note></div>}
      {st === "ok" && !items.length && (
        <p className="mt-4 font-sans text-[13px] leading-relaxed text-ink-3">一篇都还没有。不急——随手记那边碎片攒够了,这里自然会有第一篇。</p>
      )}
      {items.length > 0 && (
        <ul className="mt-5 divide-y divide-rule-soft border-y border-rule">
          {items.map((n) => (
            <li key={n.id} className="flex min-h-11 items-center justify-between gap-4 py-4">
              <button type="button" onClick={() => openOld(n)} className="group min-w-0 flex-1 text-left">
                <span className="block truncate font-serif text-[17px] font-bold text-ink transition-colors group-hover:text-blue-text">{n.title.trim() || "未命名的一篇"}</span>
                <span className="num mt-0.5 block font-sans text-[12px] text-ink-3">{fmtAt(n.updated_at)} 改过 · {fmtInt(n.content.replace(/\s+/g, "").length)} 字</span>
              </button>
              <button type="button" onClick={() => void del(n.id)} disabled={busyId === n.id}
                className="shrink-0 font-sans text-[12px] text-ink-3 transition-colors hover:text-cinnabar-text disabled:opacity-50">
                {busyId === n.id ? "撤下中…" : "撤下"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
