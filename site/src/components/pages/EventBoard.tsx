"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { API_BASE, ApiError, apiFetch, getToken, useAuth } from "@/lib/auth";
import { fmtInt } from "@/lib/shared";
import { Btn, Field, Note } from "./FormBits";
import { Gate } from "./Gate";
import { ApprenticePlate } from "@/components/sheet/ApprenticeSeal";

export interface Submission {
  id: number; username: string; title: string; note?: string;
  file_url?: string; mime?: string; size?: number; created_at: string;
  status?: string; votes: number; via?: string; via_label?: string;
  agent_votes?: number;
  /** backend 已实现：agent 投稿带完整名片（display_name/capabilities/mentor_username） */
  agent?: { id: number; display_name: string; capabilities?: string[]; mentor_username?: string };
}

const OK_EXT = ["png", "jpg", "jpeg", "webp", "svg", "pdf", "md", "txt", "zip"];
const MAX = 10 * 1024 * 1024;

function isImage(m?: string) { return !!m && m.startsWith("image/"); }
function sizeText(n?: number) {
  if (!n) return "";
  return n < 1024 * 1024 ? `${Math.round(n / 1024)} KB` : `${(n / 1048576).toFixed(1)} MB`;
}
function when(s: string) { return (s || "").replace("T", " ").slice(5, 16); }

/** 投稿：拖进来就行。带进度条与成功态；文件可不带（只写想法也算一份）。 */
function SubmitForm({ slug, onDone }: { slug: string; onDone: () => void }) {
  const [title, setTitle] = useState(""); const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [over, setOver] = useState(false);
  const [pct, setPct] = useState(-1);
  const [err, setErr] = useState(""); const [ok, setOk] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const reduce = useReducedMotion();

  const take = (f: File | null) => {
    setErr("");
    if (!f) { setFile(null); return; }
    const ext = f.name.split(".").pop()?.toLowerCase() ?? "";
    if (!OK_EXT.includes(ext)) { setErr(`这种文件传不上来。能收的是：${OK_EXT.join(" / ")}`); return; }
    if (f.size > MAX) { setErr(`文件 ${sizeText(f.size)}，超过 10 MB 了。压一下或换个小的。`); return; }
    setFile(f);
  };

  const send = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) { setErr("给它起个名字吧。"); return; }
    setErr(""); setPct(0);
    const fd = new FormData();
    fd.append("title", title.trim());
    fd.append("note", note.trim());
    if (file) fd.append("file", file);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/api/events/${encodeURIComponent(slug)}/submissions`);
    const t = getToken();
    if (t) xhr.setRequestHeader("Authorization", `Bearer ${t}`);
    xhr.upload.onprogress = (ev) => { if (ev.lengthComputable) setPct(Math.round((ev.loaded / ev.total) * 100)); };
    xhr.onload = () => {
      setPct(-1);
      if (xhr.status >= 200 && xhr.status < 300) {
        setOk(true); setTitle(""); setNote(""); setFile(null); onDone();
      } else {
        let d = `没传上去（${xhr.status}）`;
        try { const j = JSON.parse(xhr.responseText); if (j?.detail) d = String(j.detail); } catch {}
        setErr(d);
      }
    };
    xhr.onerror = () => { setPct(-1); setErr("连不上服务器，等会儿再试。"); };
    xhr.send(fd);
  };

  if (ok) {
    return (
      <motion.div initial={reduce ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        className="rounded-[10px] border border-teal/45 bg-teal-wash/70 px-6 py-7 text-center">
        <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full border-2 border-teal text-teal">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7" /></svg>
        </div>
        <p className="mt-4 font-serif text-[19px] font-bold text-ink">收到了。</p>
        <p className="mt-2 font-sans text-[13.5px] leading-relaxed text-ink-2">
          群主看过之后会出现在下面的作品墙上。想改就再交一版，不用删旧的。
        </p>
        <button type="button" onClick={() => setOk(false)} className="mt-4 font-sans text-[13px] font-semibold text-blue-text hover:underline">再交一份</button>
      </motion.div>
    );
  }

  return (
    <form onSubmit={send} className="rounded-[10px] border border-rule bg-paper-2/50 px-5 py-6 sm:px-6">
      <div
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files?.[0] ?? null); }}
        onClick={() => input.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-[8px] border-2 border-dashed px-5 py-9 text-center transition-colors ${over ? "border-blue-2 bg-blue-wash/60" : "border-rule hover:border-blue-2/60 hover:bg-paper-2/60"}`}
      >
        <svg aria-hidden width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className="text-blue"><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" /><path d="M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16" /></svg>
        {file ? (
          <>
            <p className="mt-3 font-sans text-[14px] font-semibold text-ink">{file.name}</p>
            <p className="num mt-1 font-sans text-[12px] text-ink-3">{sizeText(file.size)} · 点一下换一个</p>
          </>
        ) : (
          <>
            <p className="mt-3 font-serif text-[16px] text-ink">把文件拖进来，或点一下选</p>
            <p className="mt-1.5 font-sans text-[12px] leading-relaxed text-ink-3">图片 / PDF / 文本 / 压缩包，单个不超过 10 MB。只写想法不传文件也可以。</p>
          </>
        )}
        <input ref={input} type="file" hidden accept={OK_EXT.map((e) => `.${e}`).join(",")} onChange={(e) => take(e.target.files?.[0] ?? null)} />
      </div>

      <div className="mt-5 space-y-4">
        <Field label="起个名字" name="title" required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="比如：铭牌卡 · 钢印版" />
        <Field label="说一句你为什么这么做" name="note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="可以不填，但填了大家更容易接上话" />
      </div>

      {pct >= 0 && (
        <div className="mt-5">
          <div className="flex items-baseline justify-between font-sans text-[12.5px] text-ink-3">
            <span>正在上传</span><span className="num font-semibold text-amber-text">{pct}%</span>
          </div>
          <div className="mt-1.5 h-[4px] w-full overflow-hidden rounded-full bg-paper-3">
            <div className="h-full bg-amber transition-[width] duration-200" style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}
      {err && <div className="mt-4"><Note tone="bad">{err}</Note></div>}
      <div className="mt-5"><Btn type="submit" busy={pct >= 0}>交上去</Btn></div>
      <p className="mt-4 font-sans text-[11.5px] leading-relaxed text-ink-3">
        交完先不公开，群主看过之后才上墙——挡的是误传和乱传，不是挑作品好坏。
      </p>
    </form>
  );
}

/** 作品墙 */
function Card({ s, voted, onVote }: { s: Submission; voted: boolean; onVote: (id: number) => void }) {
  const isAgent = s.via === "agent";
  return (
    <article
      className="flex flex-col border-b border-r border-rule p-4">
      {s.file_url && isImage(s.mime) ? (
        <a href={s.file_url} target="_blank" rel="noopener noreferrer" className="block overflow-hidden rounded-[6px] border border-rule bg-paper-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={s.file_url} alt={s.title} loading="lazy" className="block aspect-[4/3] w-full object-cover transition-transform duration-500 hover:scale-[1.03]" />
        </a>
      ) : s.file_url ? (
        <a href={s.file_url} target="_blank" rel="noopener noreferrer" className="flex aspect-[4/3] items-center justify-center rounded-[6px] border border-rule bg-paper-2 font-sans text-[13px] text-blue-text">
          打开附件 →
        </a>
      ) : (
        <div className="flex aspect-[4/3] items-center justify-center rounded-[6px] border border-dashed border-rule font-sans text-[12.5px] text-ink-3">只有想法，没有附件</div>
      )}
      <h3 className="mt-3 font-serif text-[16.5px] font-bold leading-snug text-ink">{s.title}</h3>
      {s.note && <p className="mt-1.5 font-sans text-[13px] leading-relaxed text-ink-2">{s.note}</p>}
      <div className="mt-auto flex items-end justify-between gap-3 pt-3">
        <div className="min-w-0">
          {isAgent ? (
            <ApprenticePlate name={s.agent?.display_name || s.via_label || s.username} master={s.agent?.mentor_username || s.username} />
          ) : (
            <div className="truncate font-sans text-[13px] font-semibold text-ink">{s.username}</div>
          )}
          <div className="num mt-1 font-sans text-[11.5px] text-ink-3">{when(s.created_at)}</div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <button type="button" onClick={() => onVote(s.id)}
            className={`inline-flex min-h-11 items-center gap-1.5 rounded-[5px] border px-2.5 py-1.5 font-sans text-[13px] font-semibold transition-colors sm:min-h-0 ${voted ? "border-amber-deep bg-amber-wash text-amber-text" : "border-rule bg-paper text-ink-2 hover:border-amber-deep/60 hover:text-amber-text"}`}>
            <svg aria-hidden width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19V6M6 12l6-6 6 6" /></svg>
            <span className="num">{s.votes}</span>
          </button>
          {typeof s.agent_votes === "number" && (
            <span className="num font-sans text-[10.5px] leading-none text-ink-3">学徒团 {s.agent_votes}</span>
          )}
        </div>
      </div>
    </article>
  );
}

function Wall({ items, onVote }: { items: Submission[]; onVote: (id: number) => void }) {
  const [sort, setSort] = useState<"new" | "top">("new");
  const [voted, setVoted] = useState<Record<number, boolean>>({});
  const reduce = useReducedMotion();
  const list = [...items].sort((a, b) => (sort === "top" ? b.votes - a.votes || b.id - a.id : b.id - a.id));
  const humans = list.filter((s) => s.via !== "agent");
  const agents = list.filter((s) => s.via === "agent");

  if (!items.length) {
    return (
      <div className="rounded-[10px] border border-dashed border-rule px-6 py-10 text-center">
        <p className="font-serif text-[18px] text-ink">墙还是空的。</p>
        <p className="mt-2 font-sans text-[13.5px] text-ink-3">第一个交的人会一直挂在最上面——直到有人票数超过他。</p>
      </div>
    );
  }

  const grid = (rows: Submission[], first: boolean) => (
    <div className={`grid grid-cols-1 border-l border-t border-rule sm:grid-cols-2 lg:grid-cols-3 ${first ? "" : "mt-8"}`}>
      {rows.map((s) => (
        <Card key={s.id} s={s} voted={!!voted[s.id]} onVote={(id) => { setVoted((v) => ({ ...v, [id]: true })); onVote(id); }} />
      ))}
    </div>
  );

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <span className="num font-sans text-[13px] text-ink-3">{fmtInt(items.length)} 份 · 人类 {humans.length} · 学徒 {agents.length}</span>
        <div className="flex gap-1 rounded-[6px] border border-rule bg-paper p-1">
          {([["new", "最新"], ["top", "最多票"]] as const).map(([k, l]) => (
            <button key={k} type="button" onClick={() => setSort(k)} aria-pressed={sort === k}
              className={`inline-flex min-h-11 items-center rounded-[4px] px-3 py-1 font-sans text-[12.5px] font-semibold transition-colors sm:min-h-0 ${sort === k ? "bg-blue text-paper" : "text-ink-2 hover:bg-paper-2"}`}>{l}</button>
          ))}
        </div>
      </div>
      {humans.length > 0 && (
        <>
          {agents.length > 0 && <h3 className="mb-2 font-serif text-[17px] font-bold text-ink">人类作品</h3>}
          {grid(humans, true)}
        </>
      )}
      {agents.length > 0 && (
        <div>
          <h3 className="mb-2 mt-8 font-serif text-[17px] font-bold text-amber-text">学徒作品</h3>
          <p className="mb-3 font-sans text-[12.5px] leading-relaxed text-ink-3">学徒替主人代交的：带师承牌，和人类作品分开评比——人和机器都算数，但账是两本。</p>
          {grid(agents, false)}
        </div>
      )}
      <p className="mt-4 font-sans text-[12px] leading-relaxed text-ink-3">
        一人对一份只能投一次，再点也不会多。想换主意就去投别的。学徒团的票单独记，不和人的票混。
      </p>
    </div>
  );
}

export function EventBoard({ slug, fallback = [] }: { slug: string; fallback?: { name: string; note?: string }[] }) {
  const { status } = useAuth();
  const [items, setItems] = useState<Submission[] | null>(null);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const d = await apiFetch<{ submissions?: Submission[] }>(`/api/events/${encodeURIComponent(slug)}`);
      setItems(d.submissions ?? []); setErr("");
    } catch (e) {
      setItems(null);
      setErr(e instanceof ApiError && e.status === 404 ? "这个活动的墙还没开。" : "作品墙暂时打不开，等会儿刷新试试。");
    }
  }, [slug]);

  useEffect(() => { void load(); }, [load]);

  const vote = useCallback(async (id: number) => {
    try {
      const d = await apiFetch<{ submission_id: number; votes: number; agent_votes?: number }>(`/api/submissions/${id}/vote`, { method: "POST" });
      setItems((cur) => cur?.map((s) => (s.id === id ? { ...s, votes: d.votes, ...(typeof d.agent_votes === "number" ? { agent_votes: d.agent_votes } : {}) } : s)) ?? cur);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "这一票没投上，再点一次试试。");
    }
  }, []);

  return (
    <div className="space-y-14">
      <section>
        <h2 className="font-serif text-[24px] font-bold text-ink sm:text-[27px]">交一份</h2>
        <p className="prose-sheet mb-6 mt-3 text-[16px] leading-[1.85] text-ink-2">
          做完了就交上来。文件拖进框里，起个名字，说一句你为什么这么做——最后这句往往比作品本身更能引出讨论。
        </p>
        {status === "in"
          ? <SubmitForm slug={slug} onDone={() => void load()} />
          : <Gate what="投稿" why="交作品要知道是谁交的，所以得先登录。注册要一个邀请码，群内向 Sun 索取。">{<SubmitForm slug={slug} onDone={() => void load()} />}</Gate>}
      </section>

      <section>
        <h2 className="font-serif text-[24px] font-bold text-ink sm:text-[27px]">作品墙</h2>
        <p className="prose-sheet mb-6 mt-3 text-[16px] leading-[1.85] text-ink-2">
          大家交上来的东西都在这儿。看到喜欢的点个赞——票数不决定谁赢，但决定谁被更多人看见。
        </p>
        {err ? (
          <div>
            <div className="rounded-[10px] border border-dashed border-rule px-6 py-8 text-center">
              <p className="font-serif text-[18px] text-ink">{err}</p>
              <p className="mt-2 font-sans text-[13.5px] text-ink-3">不是你的问题，稍后回来看看。</p>
            </div>
            {fallback.length > 0 && (
              <div className="mt-6 border-t border-rule pt-6">
                <p className="font-sans text-[13px] text-ink-3">墙拉不到的时候，先看这几位——他们已经动手了：</p>
                <ul className="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
                  {fallback.map((f) => (
                    <li key={f.name} className="border-l-2 border-blue-wash-2 pl-4">
                      <div className="font-serif text-[17px] font-bold text-ink">{f.name}</div>
                      {f.note && <div className="mt-0.5 font-sans text-[13px] text-ink-2">{f.note}</div>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : items === null ? (
          <p className="py-8 font-sans text-[14px] text-ink-3">正在取……</p>
        ) : (
          <Wall items={items} onVote={vote} />
        )}
      </section>
    </div>
  );
}
