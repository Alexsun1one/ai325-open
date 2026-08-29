/** 蒸馏的「掐头去尾」：找出包含峰值小时、占总量 ≥50% 的最短连续窗口 = 酒心；前为酒头，后为酒尾。 */
export interface Cuts {
  hours: { h: number; n: number }[];
  total: number;
  peak: { h: number; n: number };
  head: { from: number; to: number; n: number };
  heart: { from: number; to: number; n: number };
  tail: { from: number; to: number; n: number };
}

export function computeCuts(hoursMap: Record<string, number>): Cuts {
  const hours = Array.from({ length: 24 }, (_, h) => ({ h, n: hoursMap[String(h).padStart(2, "0")] ?? 0 }));
  const total = hours.reduce((s, x) => s + x.n, 0);
  let peak = hours[0];
  for (const x of hours) if (x.n > peak.n) peak = x;
  let lo = peak.h, hi = peak.h, sum = peak.n;
  while (sum < total * 0.5 && (lo > 0 || hi < 23)) {
    const left = lo > 0 ? hours[lo - 1].n : -1;
    const right = hi < 23 ? hours[hi + 1].n : -1;
    if (right >= left) { hi += 1; sum += hours[hi].n; } else { lo -= 1; sum += hours[lo].n; }
  }
  const seg = (from: number, to: number) => ({ from, to, n: hours.slice(from, to + 1).reduce((s, x) => s + x.n, 0) });
  return {
    hours, total, peak,
    head: seg(0, Math.max(0, lo - 1)),
    heart: seg(lo, hi),
    tail: seg(Math.min(23, hi + 1), 23),
  };
}

export const hh = (h: number) => String(h).padStart(2, "0");
