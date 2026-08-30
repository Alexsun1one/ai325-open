"use client";
/** 师承谱星图（静态 SVG 分层，不引力导向库）。
 *  中心=掌炉；第一圈=引荐人（master）；学徒环绕其引荐人；新入住亮标记。
 *  数据=roster 真值（师承/进度/最近活跃）；学徒 ≤3 收缩高度，多时自动长高。 */
interface StarApprentice {
  name: string;
  display_name?: string;
  master_display?: string;
  progress?: number;
  last_used_at?: string | null;
}
export function LineageStar({ items, centerName = "孙务远" }: { items: StarApprentice[]; centerName?: string }) {
  const W = 860;
  const masters = Array.from(new Set(items.map((a) => a.master_display).filter((m) => m && m !== centerName))) as string[];
  const compact = items.length <= 3;
  const H = compact ? 300 : 420;
  const CX = W / 2, CY = H / 2;
  const ringR = compact ? 96 : 150;
  const ringR2 = compact ? 78 : 140;
  const kidR = compact ? 34 : 46;
  const underCenter = items.filter((a) => !a.master_display || a.master_display === centerName);
  const byMaster = (m: string) => items.filter((a) => a.master_display === m);
  const ring1 = masters.length || 1;
  const underCount = underCenter.length || 1;
  const masterNodes = masters.map((m, i) => {
    const angle = (2 * Math.PI * i) / ring1 - Math.PI / 2;
    return { name: m, x: CX + Math.cos(angle) * ringR, y: CY + Math.sin(angle) * ringR2 };
  });
  const centerKids = underCenter.map((a, i) => {
    const angle = (2 * Math.PI * i) / underCount - Math.PI / 2;
    return { a, x: CX + Math.cos(angle) * (compact ? 62 : 88), y: CY + Math.sin(angle) * (compact ? 58 : 84) };
  });
  const kids: { a: StarApprentice; x: number; y: number; px: number; py: number }[] = [];
  for (const mn of masterNodes) {
    const list = byMaster(mn.name);
    const n = list.length || 1;
    list.forEach((a, i) => {
      const angle = (2 * Math.PI * i) / n - Math.PI / 2;
      kids.push({ a, x: mn.x + Math.cos(angle) * kidR, y: mn.y + Math.sin(angle) * kidR, px: mn.x, py: mn.y });
    });
  }
  const isNew = (a: StarApprentice) => {
    const t = a.last_used_at || "";
    return t.slice(0, 10) >= "2026-08-30";
  };
  const node = (x: number, y: number, name: string, extra: string, opts?: { sub?: string; fresh?: boolean }) => (
    <g key={`${x}-${y}-${name}`}>
      {opts?.sub ? <text x={x} y={y + 30} textAnchor="middle" fontSize="10.5" fill="#8a8578" fontFamily="sans-serif">{opts.sub}</text> : null}
      {opts?.fresh ? <circle cx={x + 26} cy={y - 17} r={6} fill="#2e7d74" /> : null}
      <circle cx={x} cy={y} r={compact ? 21 : 26} fill="#fffdf8" stroke={extra === "center" ? "#b0473a" : "#c9c2b4"} strokeWidth={extra === "center" ? 2 : 1.2} />
      <text x={x} y={y + 4} textAnchor="middle" fontSize={extra === "center" ? (compact ? 13 : 15) : compact ? 10.5 : 11.5} fill="#2b2b2b" fontFamily="sans-serif" fontWeight={extra === "center" ? 700 : 500}>
        {name.length > (compact ? 3 : 4) ? name.slice(0, compact ? 3 : 4) + "…" : name}
      </text>
    </g>
  );
  return (
    <div className="overflow-x-auto rounded-[10px] border border-rule bg-[#fdfaf3] p-2">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="师承谱星图" className="mx-auto block h-auto w-full max-w-[860px]">
        {masterNodes.map((m) => <line key={`c-${m.name}`} x1={CX} y1={CY} x2={m.x} y2={m.y} stroke="#c9c2b4" strokeWidth={1.2} />)}
        {kids.map((k) => <line key={`k-${k.a.name}`} x1={k.px} y1={k.py} x2={k.x} y2={k.y} stroke="#d8d1c2" strokeWidth={0.8} />)}
        {centerKids.map((k) => <line key={`ck-${k.a.name}`} x1={CX} y1={CY} x2={k.x} y2={k.y} stroke="#d8d1c2" strokeWidth={0.8} />)}
        {centerKids.map((k) => node(k.x, k.y, k.a.display_name || k.a.name, "kid", { sub: `${k.a.progress ?? 0}%`, fresh: isNew(k.a) }))}
        {masterNodes.map((m) => node(m.x, m.y, m.name, "master", { sub: `${byMaster(m.name).length} 徒` }))}
        {kids.map((k) => node(k.x, k.y, k.a.display_name || k.a.name, "kid", { sub: `${k.a.progress ?? 0}%`, fresh: isNew(k.a) }))}
        {node(CX, CY, centerName, "center", { sub: "掌炉" })}
      </svg>
      <div className="flex flex-wrap gap-x-4 gap-y-1 px-2 pb-1 font-sans text-[11.5px] text-ink-3">
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full border border-cinnabar bg-[#fdfaf3] align-[-1px]" />掌炉</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full border border-rule bg-[#fdfaf3] align-[-1px]" />引荐人</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full border border-rule bg-[#fdfaf3] align-[-1px]" />学徒</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-teal align-[-1px]" />今日入住</span>
        <span>节点下标 = 出师进度</span>
      </div>
    </div>
  );
}
