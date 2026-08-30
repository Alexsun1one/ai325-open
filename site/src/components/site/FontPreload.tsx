import { fontChunksRanked } from "@/lib/fonts";

/** 整页字体 preload：按字重分级配片（正文 400 最多、标题 700 次之、刊名 900 最少），
 *  总量上限 28 片——preload 是预下载，收敛能省首帧字体字节；低频字由 font-display swap 按需补。 */
export function FontPreload({ plan, max = 28 }: { plan: { text: string; family?: string; weight: number; cap?: number }[]; max?: number }) {
  const urls: string[] = [];
  for (const p of plan) {
    const cap = p.cap ?? (p.weight >= 900 ? 3 : p.weight >= 700 ? 8 : 12);
    const list = fontChunksRanked(p.text, p.family ?? "Noto Serif SC", p.weight).slice(0, cap);
    for (const u of list) if (!urls.includes(u)) urls.push(u);
  }
  return <>{urls.slice(0, max).map((u) => <link key={u} rel="preload" as="font" type="font/woff2" href={u} crossOrigin="anonymous" />)}</>;
}
