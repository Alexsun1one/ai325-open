import type { Arsenal, Glossary as G, Tone } from "@/lib/shared";
import { TONE_META } from "@/lib/shared";
import { ToneGlyph } from "./ToneTag";

const TONE_BY_EMOJI: Record<string, Tone> = { "\u{1F4A1}": "s", "\u{1F604}": "j", "\u{1F525}": "h" };
const SUFFIX = /(?:\s|→|\u{1F4A1}|\u{1F604}|\u{1F525})+$/u;

/**
 * 词条名在数据里带着 💡/😄/🔥 后缀当语气标注（且 dfn[data-term] 用整串做键，不能改数据）。
 * 这里只在**显示**时把后缀摘下来，换成与语气章同源的单线图标——本站不拿 emoji 当图标。
 */
function parseTerm(term: string) {
  const m = term.match(SUFFIX);
  if (!m || m.index === undefined) return { text: term, tones: [] as Tone[], arrow: false };
  const tones = [...m[0]].map((c) => TONE_BY_EMOJI[c]).filter(Boolean);
  if (!tones.length) return { text: term, tones: [] as Tone[], arrow: false };
  return { text: term.slice(0, m.index), tones, arrow: m[0].includes("→") };
}

function ToneMarks({ tones, arrow }: { tones: Tone[]; arrow: boolean }) {
  return (
    <span className="inline-flex shrink-0 items-center gap-1 align-middle">
      {tones.map((t, i) => (
        <span key={i} className="inline-flex items-center gap-1" style={{ color: TONE_META[t].color }} title={TONE_META[t].label}>
          {i > 0 && arrow && <span aria-hidden className="font-sans text-[11px] text-ink-3">→</span>}
          <ToneGlyph g={t} size={13} />
          <span className="sr-only">{TONE_META[t].label}</span>
        </span>
      ))}
    </span>
  );
}

export function Glossary({ items, arsenal }: { items: G[]; arsenal: Arsenal[] }) {
  return (
    <div className="space-y-12">
      <dl className="grid gap-x-10 gap-y-4 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((g, i) => {
          const { text, tones, arrow } = parseTerm(g.term);
          return (
            <div key={i} id={`term-${i}`} className="min-w-0 border-t border-rule-soft pt-3.5">
              <dt className="flex flex-wrap items-center gap-x-2 gap-y-1 font-serif text-[17px] font-bold leading-[1.5] text-ink">
                <span className="min-w-0">{text}</span>
                {tones.length > 0 && <ToneMarks tones={tones} arrow={arrow} />}
              </dt>
              <dd className="prose-sheet mt-1.5 text-[15px] leading-[1.8] text-ink-2" dangerouslySetInnerHTML={{ __html: g.def }} />
            </div>
          );
        })}
      </dl>
      <div>
        <h3 className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1 font-serif text-[19px] font-bold text-ink">
          资源弹药库
          <span className="font-sans text-[13px] font-medium text-ink-3">按贡献人鸣谢</span>
        </h3>
        <div className="mt-5 grid gap-x-10 gap-y-7 md:grid-cols-3">
          {arsenal.map((a, i) => (
            <div key={i} className="min-w-0 border-t border-rule-soft pt-3.5">
              <div className="font-sans text-[13.5px] font-semibold text-blue-text">{a.h}</div>
              <p className="prose-sheet mt-2 text-[14.5px] leading-[1.8] text-ink-2" dangerouslySetInnerHTML={{ __html: a.body }} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
