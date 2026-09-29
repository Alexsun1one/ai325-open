"use client";

export function nfmt(v: number | null | undefined): string {
  if (v == null) return "—";
  return v.toLocaleString("zh-CN");
}

export function SparkBars({
  points,
  label,
}: {
  points: { date: string; pv: number }[];
  label: string;
}) {
  const W = 640, H = 128, L = 8, R = 8, T = 10, B = 22;
  const innerW = W - L - R, innerH = H - T - B;
  const peak = Math.max(1, ...points.map((p) => p.pv));
  const n = Math.max(1, points.length);
  const gap = 2;
  const barW = Math.max(2, (innerW - gap * (n - 1)) / n);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={label}>
      <line x1={L} x2={W - R} y1={T + innerH} y2={T + innerH} stroke="var(--rule)" strokeWidth="1" />
      {points.map((p, i) => {
        const h = (p.pv / peak) * innerH;
        const x = L + i * (barW + gap);
        const y = T + innerH - h;
        const tick = i % Math.max(1, Math.floor(n / 6)) === 0 || i === n - 1;
        return (
          <g key={p.date}>
            <rect x={x} y={y} width={barW} height={Math.max(h, 1)} fill="var(--amber)" opacity="0.9">
              <title>{`${p.date} · PV ${nfmt(p.pv)}`}</title>
            </rect>
            {tick && (
              <text x={x + barW / 2} y={H - 6} textAnchor="middle" fontFamily="var(--font-sans)" fontSize="9" fill="var(--ink-3)" className="num">
                {p.date.slice(5)}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

export type RankRow = { name: string; pv: number };

export function RankBars({
  items,
  label,
}: {
  items: RankRow[];
  label: string;
}) {
  const W = 520, rowH = 22, H = items.length * rowH + 4, labelW = 78;
  const peak = Math.max(1, ...items.map((i) => i.pv || 0));
  const barMax = W - labelW - 52;
  if (!items.length) return <p className="font-sans text-[13px] text-ink-3">暂无</p>;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={label}>
      {items.map((item, i) => {
        const y = i * rowH;
        const val = item.pv || 0;
        const w = (val / peak) * barMax;
        return (
          <g key={`${item.name}-${i}`}>
            <text x={0} y={y + 14} fontFamily="var(--font-sans)" fontSize="11.5" fill="var(--ink)">{item.name}</text>
            <rect x={labelW} y={y + 6} width={barMax} height={9} fill="var(--paper-2, #e8e6de)" />
            <rect x={labelW} y={y + 6} width={Math.max(w, val ? 2 : 0)} height={9} fill="var(--blue)" />
            <text x={W} y={y + 14} textAnchor="end" fontFamily="var(--font-sans)" fontSize="11.5" fill="var(--ink)" className="num">{nfmt(val)}</text>
          </g>
        );
      })}
    </svg>
  );
}

export function DegreePath({
  points,
}: {
  points: { date: string; degree: number | null }[];
}) {
  const real = points.filter((p): p is { date: string; degree: number } => typeof p.degree === "number");
  if (!real.length) return <p className="font-sans text-[13px] text-ink-3">暂无出刊度数</p>;
  const W = 640, H = 148, L = 30, R = 12, T = 18, B = 26;
  const innerW = W - L - R, innerH = H - T - B;
  const n = real.length;
  const x = (i: number) => L + innerW * (n === 1 ? 0.5 : i / (n - 1));
  const y = (v: number) => T + innerH * (1 - v / 100);
  const d = real.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.degree)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label="出刊度数曲线">
      {[40, 60, 80].map((v) => (
        <g key={v}>
          <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke="var(--rule-soft)" strokeWidth="1" />
          <text x={L - 6} y={y(v) + 3} textAnchor="end" fontFamily="var(--font-sans)" fontSize="9.5" fill="var(--ink-3)" className="num">{v}</text>
        </g>
      ))}
      {n > 1 && <path d={d} fill="none" stroke="var(--amber)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />}
      {real.map((p, i) => (
        <g key={p.date}>
          <circle cx={x(i)} cy={y(p.degree)} r="4.5" fill="var(--amber)" stroke="var(--blue)" strokeWidth="1.2" />
          <text x={x(i)} y={y(p.degree) - 10} textAnchor="middle" fontFamily="var(--font-sans)" fontSize="11" fontWeight="700" fill="var(--amber-text)" className="num">{p.degree}°</text>
          <text x={x(i)} y={H - 6} textAnchor="middle" fontFamily="var(--font-sans)" fontSize="9.5" fill="var(--ink-3)" className="num">{p.date.slice(5)}</text>
        </g>
      ))}
    </svg>
  );
}

export function CommunitySpark({
  points,
}: {
  points: { date: string; messages: number; speakers: number }[];
}) {
  const slice = points.slice(-14);
  if (!slice.length) return <p className="font-sans text-[13px] text-ink-3">暂无社群趋势</p>;
  const W = 640, H = 120, L = 8, R = 8, T = 8, B = 22;
  const innerW = W - L - R, innerH = H - T - B;
  const peak = Math.max(1, ...slice.map((p) => p.messages));
  const n = slice.length;
  const gap = 3;
  const barW = Math.max(2, (innerW - gap * (n - 1)) / n);
  const speakerPeak = Math.max(1, ...slice.map((p) => p.speakers));
  const line = slice.map((p, i) => {
    const x = L + i * (barW + gap) + barW / 2;
    const y = T + innerH * (1 - p.speakers / speakerPeak);
    return `${i ? "L" : "M"}${x},${y}`;
  }).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label="消息量与发言人数">
      <line x1={L} x2={W - R} y1={T + innerH} y2={T + innerH} stroke="var(--rule)" strokeWidth="1" />
      {slice.map((p, i) => {
        const h = (p.messages / peak) * innerH;
        const x = L + i * (barW + gap);
        return (
          <rect key={p.date} x={x} y={T + innerH - h} width={barW} height={Math.max(h, 1)} fill="var(--amber)" opacity="0.75">
            <title>{`${p.date} · 消息 ${nfmt(p.messages)} · 发言 ${nfmt(p.speakers)}`}</title>
          </rect>
        );
      })}
      <path d={line} fill="none" stroke="var(--blue)" strokeWidth="1.8" strokeLinejoin="round" />
      {slice.map((p, i) => {
        const x = L + i * (barW + gap) + barW / 2;
        const y = T + innerH * (1 - p.speakers / speakerPeak);
        const tick = i % 2 === 0 || i === n - 1;
        return (
          <g key={`s-${p.date}`}>
            <circle cx={x} cy={y} r="2.4" fill="var(--blue)" />
            {tick && <text x={x} y={H - 6} textAnchor="middle" fontFamily="var(--font-sans)" fontSize="9" fill="var(--ink-3)" className="num">{p.date.slice(5)}</text>}
          </g>
        );
      })}
    </svg>
  );
}
