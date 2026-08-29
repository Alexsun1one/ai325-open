"use client";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/auth";

interface Cap { name: string; endpoints?: string[]; auth?: boolean | string }
interface Manifest { name?: string; description?: string; learn_here?: string; capabilities?: Cap[] }

const NEEDS = (a: Cap["auth"]) => (a === true ? "要钥匙" : a === false ? "不用钥匙" : "读不用 · 写要钥匙");

/** 能力清单从 /api/agent/manifest 现取——后端加了新能力，这一页自动跟上，不用我改代码。 */
export function AgentLearn() {
  const [m, setM] = useState<Manifest | null>(null);
  const [down, setDown] = useState(false);

  useEffect(() => {
    let alive = true;
    apiFetch<Manifest>("/api/agent/manifest")
      .then((d) => { if (alive) setM(d); })
      .catch(() => { if (alive) setDown(true); });
    return () => { alive = false; };
  }, []);

  return (
    <div className="grid gap-x-12 gap-y-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,330px)]">
      <div className="min-w-0">
        <p className="prose-sheet text-[16.5px] leading-[1.85] text-ink-2">
          接进来之后，你的 agent 手上就多了一座<b>军火库</b>：群里攒下来的提示词、方法、技能，它可以自己搜、自己取、自己用。你不用再把东西复制粘贴给它。
        </p>
        {m?.learn_here && (
          <p className="mt-4 border-l-2 border-blue-wash-2 pl-4 font-sans text-[14px] leading-relaxed text-ink-2">
            {m.learn_here}
            <span className="mt-1 block text-[12px] text-ink-3">—— 这句是服务器自己报的，它对 agent 说的和对你说的是同一句。</span>
          </p>
        )}
        <div className="mt-7 rounded-[10px] border border-rule bg-paper-2/45 px-5 py-5">
          <div className="label mb-2.5">举个真的例子</div>
          <p className="prose-sheet text-[16px] leading-[1.85] text-ink-2">
            你跟它说：<span className="hand text-[17px]">「去群里搜『委托』，看看有没有讲怎么给 AI 派活的。」</span>
          </p>
          <ol className="mt-4 space-y-2.5">
            {[
              ["它调 search(\"委托\")", "在整理过的内容里搜，搜到《给 Agent 派活的六个槽位》。"],
              ["它调 get_skill 取全文", "拿到六个槽、那张「哪种任务哪些槽必须齐」的对照表、还有发出去之前的三眼自检。"],
              ["它按那套改写你的任务", "然后回你：「按六槽重排了一遍，你没给『不做什么』，我先默认……」"],
            ].map(([h, d], i) => (
              <li key={h} className="grid grid-cols-[26px_1fr] gap-2.5">
                <span className="num pt-[3px] font-sans text-[12.5px] font-semibold text-blue-text">{String(i + 1).padStart(2, "0")}</span>
                <span>
                  <span className="block font-sans text-[14px] font-semibold text-ink">{h}</span>
                  <span className="mt-0.5 block font-sans text-[13px] leading-relaxed text-ink-2">{d}</span>
                </span>
              </li>
            ))}
          </ol>
          <p className="mt-4 font-sans text-[12.5px] leading-relaxed text-ink-3">
            这一件在<a href="/arsenal/#kb-method-agent-brief-slots-202608" className="text-blue-text underline underline-offset-2">军火库</a>里就能看到——你的 agent 拿到的是同一份。
          </p>
        </div>
      </div>

      <div className="rounded-[10px] border border-rule bg-paper-2/50 px-5 py-5">
        <div className="label mb-3">现在开放的能力</div>
        {down ? (
          <p className="font-sans text-[13px] leading-relaxed text-ink-3">
            能力清单暂时问不到（这一段是现取的）。上线之后这里会自动列出来；在那之前，下面几节的接法都是有效的。
          </p>
        ) : !m ? (
          <p className="font-sans text-[13px] text-ink-3">正在取……</p>
        ) : (
          <>
            <ul className="space-y-2.5">
              {(m.capabilities ?? []).map((c) => (
                <li key={c.name} className="flex items-baseline justify-between gap-3 border-b border-rule-soft pb-2 last:border-0 last:pb-0">
                  <span className="font-sans text-[13.5px] font-semibold text-ink">{c.name}</span>
                  <span className={`shrink-0 rounded-[3px] border px-1.5 py-[1px] font-sans text-[11px] font-semibold ${c.auth === false ? "border-teal/45 bg-teal-wash text-teal-text" : "border-blue-wash-2 bg-blue-wash text-blue-text"}`}>{NEEDS(c.auth)}</span>
                </li>
              ))}
            </ul>
            <p className="mt-4 font-sans text-[11.5px] leading-relaxed text-ink-3">
              这份清单是现取的：后端加了新能力，这里自己就更新，不用等我改页面。
            </p>
          </>
        )}
      </div>
    </div>
  );
}
