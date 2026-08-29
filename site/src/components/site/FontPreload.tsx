import { fontChunksRanked } from "@/lib/fonts";

/** 整页字体 preload：把页面正文/标题/手写层用到的分片按命中频次预载（上限 48 片），React 会提升到 <head>。 */
export function FontPreload({ plan, max = 48 }: { plan: { text: string; family?: string; weight: number; cap?: number }[]; max?: number }) {
  const urls: string[] = [];
  for (const p of plan) {
    const list = fontChunksRanked(p.text, p.family ?? "Noto Serif SC", p.weight).slice(0, p.cap ?? 24);
    for (const u of list) if (!urls.includes(u)) urls.push(u);
  }
  return <>{urls.slice(0, max).map((u) => <link key={u} rel="preload" as="font" type="font/woff2" href={u} crossOrigin="anonymous" />)}</>;
}
