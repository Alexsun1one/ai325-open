import { TONE_META, type Tone } from "@/lib/shared";

/**
 * 三档语气的单线图标：认真=灯泡 / 玩笑=笑弧 / 半真=火苗。
 * 三枚共用 24 网格、strokeWidth 2、圆端点，且视觉高度都落在 y≈3–19，
 * 这样 11–13px 行内排版时三档的墨量与重心一致（灯泡原本多一道底座线，偏重）。
 */
export function ToneGlyph({ g, size = 12 }: { g: Tone; size?: number }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className: "shrink-0",
    "aria-hidden": true,
  };
  if (g === "s") return <svg {...common}><path d="M9.25 18.5h5.5M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3Z"/></svg>;
  if (g === "j") return <svg {...common}><circle cx="12" cy="11.5" r="8"/><path d="M8.8 14.2a4.2 4.2 0 0 0 6.4 0M9.4 9.6h.01M14.6 9.6h.01"/></svg>;
  return <svg {...common}><path d="M12 3s-5 5-5 10a5 5 0 0 0 10 0c0-2.5-1.5-4.5-2.5-5.5-.3 1.5-1 2.5-2 3-.3-2.5-.5-5-.5-7.5Z"/></svg>;
}

/**
 * 语气章。`align-middle` 是为了让它嵌在 14–16px 正文里时不撑高行盒、
 * 也不掉到基线以下（成员高光、黑话词条都会把它排进句子里）。
 */
export function ToneTag({ g, size = "sm", stamp = false }: { g: Tone; size?: "sm" | "md"; stamp?: boolean }) {
  // 数据里语气可能缺席（新成员还没被鉴定过）：没有就不打章，别让整页跟着崩
  const m = TONE_META[g];
  if (!m) return null;
  return (
    <span
      className={`inline-flex select-none items-center whitespace-nowrap rounded-[3px] border align-middle font-sans font-semibold leading-none ${size === "sm" ? "gap-[3px] px-1.5 py-[3px] text-[11px]" : "gap-1.5 px-2.5 py-1.5 text-[13px]"}${stamp ? " -rotate-2" : ""}`}
      style={{ color: m.color, borderColor: m.color, background: m.wash }}
      title={g === "s" ? "认真：可直接引用为观点" : g === "j" ? "玩笑：段子/复读/自嘲，不得当观点采信" : "半真：玩笑壳认真芯"}
    >
      <ToneGlyph g={g} size={size === "sm" ? 11 : 13} />
      {m.label}
    </span>
  );
}
