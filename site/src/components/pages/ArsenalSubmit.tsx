"use client";
import { useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { API_BASE, ApiError, apiFetch, getToken, useAuth } from "@/lib/auth";
import { Btn, Field, Note } from "./FormBits";
import { Gate } from "./Gate";

/** 与后端 Literal 完全一致，多一个字都会被 422 挡下。 */
const KINDS = ["提示词", "方法", "技能", "文章", "案例", "工具", "论文", "拆书"];
const ONE_MAX = 40;      // 后端 one_line 上限
const TAKE_MIN = 3, TAKE_MAX = 5;   // 后端 takeaways 3–5 条

function Form() {
  const [kind, setKind] = useState("提示词");
  const [title, setTitle] = useState("");
  const [one, setOne] = useState("");
  const [why, setWhy] = useState("");
  const [forWhom, setForWhom] = useState("");
  const [srcName, setSrcName] = useState("");
  const [srcUrl, setSrcUrl] = useState("");
  const [srcAuthor, setSrcAuthor] = useState("");
  const [takeaways, setTakeaways] = useState("");
  const [tags, setTags] = useState("");
  const [body, setBody] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [pct, setPct] = useState(-1);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState(false);
  const reduce = useReducedMotion();

  const takeList = takeaways.split("\n").map((x) => x.trim()).filter(Boolean);

  const send = (e: React.FormEvent) => {
    e.preventDefault();
    // 这几条是后端硬卡的，先在这儿说清楚，别让人白填一遍
    if (!title.trim() || !one.trim()) { setErr("标题和那句话是必须的——别人就靠这两行决定要不要点开。"); return; }
    if (one.trim().length > ONE_MAX) { setErr(`那句话太长了（${one.trim().length} 字），${ONE_MAX} 字以内。`); return; }
    if (!why.trim()) { setErr("说说为什么值得群友花时间——这一栏不能空。"); return; }
    if (!forWhom.trim()) { setErr("写一句「谁该看」，别人才知道要不要点进来。"); return; }
    if (takeList.length < TAKE_MIN || takeList.length > TAKE_MAX) {
      setErr(`「拿走这几条」要 ${TAKE_MIN}–${TAKE_MAX} 条，你写了 ${takeList.length} 条。`); return;
    }
    setErr(""); setPct(0);
    // 形状照 backend 报告：multipart 的字段名就叫 item，值是一整个 JSON；附件叫 file
    const item = {
      kind, title: title.trim(), one_line: one.trim(), why: why.trim(),
      for_whom: forWhom.trim(),
      source: { name: srcName.trim() || "群友上架", url: srcUrl.trim(), author: srcAuthor.trim(), published_at: "" },
      takeaways: takeList,
      tags: tags.split(/[,，\s]+/).map((x) => x.trim()).filter(Boolean).slice(0, 10),
      body_md: body.trim(),
    };
    const fd = new FormData();
    fd.append("item", JSON.stringify(item));
    if (file) fd.append("file", file);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/api/arsenal/items`);
    const t = getToken();
    if (t) xhr.setRequestHeader("Authorization", `Bearer ${t}`);
    xhr.upload.onprogress = (ev) => { if (ev.lengthComputable) setPct(Math.round((ev.loaded / ev.total) * 100)); };
    xhr.onload = () => {
      setPct(-1);
      if (xhr.status >= 200 && xhr.status < 300) { setOk(true); setTitle(""); setOne(""); setWhy(""); setForWhom(""); setTakeaways(""); setTags(""); setSrcName(""); setSrcUrl(""); setSrcAuthor(""); setBody(""); setFile(null); }
      else {
        let d = xhr.status === 404 ? "上架口还没开。" : xhr.status === 413 ? "包太大了，压缩包不超过 5 MB。" : `没交上去（${xhr.status}）`;
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
        <p className="mt-4 font-serif text-[19px] font-bold text-ink">收到了，排在待上架里。</p>
        <p className="mt-2 font-sans text-[13.5px] leading-relaxed text-ink-2">守门人看过、群主点头就上架。上架之后它会自己出现在对应那一架上，也能被 agent 取走。在那之前只有你自己看得到。</p>
        <button type="button" onClick={() => setOk(false)} className="mt-4 font-sans text-[13px] font-semibold text-blue-text hover:underline">再上一件</button>
      </motion.div>
    );
  }

  return (
    <form onSubmit={send} className="rounded-[10px] border border-rule bg-paper-2/50 px-5 py-6 sm:px-6">
      <div className="mb-5">
        <span className="label">哪一架</span>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {KINDS.map((k) => (
            <button key={k} type="button" onClick={() => setKind(k)} aria-pressed={kind === k}
              className={`inline-flex min-h-11 items-center rounded-[5px] border px-2.5 py-1.5 font-sans text-[13px] font-medium transition-colors sm:min-h-0 ${kind === k ? "border-blue bg-blue text-paper" : "border-rule bg-paper text-ink-2 hover:bg-paper-2"}`}>{k}</button>
          ))}
        </div>
      </div>
      <div className="space-y-4">
        <Field label="标题" name="title" required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="它叫什么" />
        <Field label="一句话" name="one_line" required maxLength={ONE_MAX} value={one} onChange={(e) => setOne(e.target.value)} placeholder="它是什么、解决什么（说人话）"
          hint={<span className={one.length > ONE_MAX - 6 ? "text-amber-text" : undefined}>还能写 <span className="num">{Math.max(0, ONE_MAX - one.length)}</span> 字</span>} />
        <label className="block">
          <span className="label">为什么值得群友花时间</span>
          <textarea value={why} onChange={(e) => setWhy(e.target.value)} rows={3} placeholder="要有判断，别复述原文。两三句就够。"
            className="mt-1.5 block w-full resize-none rounded-[4px] border border-rule bg-paper px-3 py-2 font-sans text-[15px] leading-relaxed text-ink outline-none transition-colors placeholder:text-ink-3/70 focus:border-blue-2" />
        </label>
        <Field label="谁该看" name="for_whom" required value={forWhom} onChange={(e) => setForWhom(e.target.value)} placeholder="什么样的人、在什么时候用得上（一句话）" />
        <label className="block">
          <span className="label">拿走这几条</span>
          <textarea value={takeaways} onChange={(e) => setTakeaways(e.target.value)} rows={4} placeholder="一行一条，三到五条。用你自己的话，可执行。"
            className="mt-1.5 block w-full resize-none rounded-[4px] border border-rule bg-paper px-3 py-2 font-sans text-[15px] leading-relaxed text-ink outline-none transition-colors placeholder:text-ink-3/70 focus:border-blue-2" />
          <span className={`mt-1.5 block font-sans text-[12px] ${takeList.length && (takeList.length < TAKE_MIN || takeList.length > TAKE_MAX) ? "text-amber-text" : "text-ink-3"}`}>
            一行一条，不用编号。要 {TAKE_MIN}–{TAKE_MAX} 条{takeList.length > 0 && <>，现在 <span className="num">{takeList.length}</span> 条</>}。
          </span>
        </label>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="出处（可空）" name="src_name" value={srcName} onChange={(e) => setSrcName(e.target.value)} placeholder="留空就写「群友上架」" />
          <Field label="原作者（可空）" name="src_author" value={srcAuthor} onChange={(e) => setSrcAuthor(e.target.value)} placeholder="自己写的就填自己" />
        </div>
        <Field label="原文链接（可空）" name="src_url" type="url" value={srcUrl} onChange={(e) => setSrcUrl(e.target.value)} placeholder="https://…　自己写的就留空" />
        <Field label="标签（可空）" name="tags" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="逗号或空格分开，最多 10 个" />
        <label className="block">
          <span className="label">正文（可空）</span>
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={6} placeholder="提示词就把全文贴进来，别人要一键复制。支持 Markdown 与 ``` 代码块。"
            className="mt-1.5 block w-full resize-none rounded-[4px] border border-rule bg-paper px-3 py-2 font-sans text-[14px] leading-relaxed text-ink outline-none transition-colors placeholder:text-ink-3/70 focus:border-blue-2" />
        </label>
        <label className="block">
          <span className="label">或者传个包（可空）</span>
          <input type="file" accept=".zip,.md,.txt,.pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="mt-1.5 block w-full rounded-[4px] border border-dashed border-rule bg-paper px-3 py-2.5 font-sans text-[13px] text-ink-2 file:mr-3 file:rounded-[4px] file:border file:border-rule file:bg-paper-2 file:px-3 file:py-1.5 file:font-sans file:text-[13px] file:text-ink-2" />
          <span className="mt-1.5 block font-sans text-[12px] text-ink-3">技能就打成 zip，<b>里面必须有一个 SKILL.md</b>，否则会被退回。压缩包不超过 5 MB、不超过 100 个文件。</span>
        </label>
      </div>
      {pct >= 0 && (
        <div className="mt-5">
          <div className="flex items-baseline justify-between font-sans text-[12.5px] text-ink-3"><span>正在上传</span><span className="num font-semibold text-amber-text">{pct}%</span></div>
          <div className="mt-1.5 h-[4px] w-full overflow-hidden rounded-full bg-paper-3"><div className="h-full bg-amber transition-[width] duration-200" style={{ width: `${pct}%` }} /></div>
        </div>
      )}
      {err && <div className="mt-4"><Note tone="bad">{err}</Note></div>}
      <div className="mt-5"><Btn type="submit" busy={pct >= 0}>上架</Btn></div>
      <p className="mt-4 font-sans text-[11.5px] leading-relaxed text-ink-3">
        交完先不公开：守门人看过、群主点头才上架。挡的是重复和凑数，不是挑你水平。
      </p>
    </form>
  );
}

export function ArsenalSubmit() {
  const { status } = useAuth();
  if (status === "in") return <Form />;
  return <Gate what="上架" why="上架的东西会挂上你的名字，所以先登录。注册要一个邀请码，群内向 Sun 索取。"><Form /></Gate>;
}
