import type { ToneNote } from "@/lib/shared";
import { ToneTag } from "./ToneTag";

/** 真伪鉴定：三档语气各一栏，栏头是盖上去的章。 */
export function ToneStamps({ notes }: { notes: ToneNote[] }) {
  return (
    <div className="grid gap-x-10 gap-y-9 md:grid-cols-3">
      {notes.map((n, i) => (
        <div key={i} className="border-t border-rule pt-5">
          <div className="flex items-center gap-3">
            <ToneTag g={n.cls} size="md" stamp />
            <span className="font-sans text-[13px] font-medium leading-tight text-ink-2">{n.h.replace(/^[^\s]+\s/, "")}</span>
          </div>
          <p className="prose-sheet mt-5 text-[15.5px] leading-[1.85] text-ink-2" dangerouslySetInnerHTML={{ __html: n.body }} />
        </div>
      ))}
    </div>
  );
}
