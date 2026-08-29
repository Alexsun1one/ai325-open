/**
 * 印刷品鉴单的通栏分隔：双蓝线 + 菱形端点。只用在刊头之下与页脚之上。
 * 几何：两条 1px 线占 y 0–1 / 3–4（间距 3px，视觉中线 y=2）；
 * 菱形 6×6 旋转 45°、top -1px，中心正落在 y=2；右顶点 x=7.24 恰好压住线头 x=7。
 */
export function DoubleRule({ className = "" }: { className?: string }) {
  return (
    <div aria-hidden className={`relative mb-6 mt-6 h-[7px] ${className}`}>
      <div className="absolute inset-x-[7px] top-0 h-px bg-blue/70" />
      <div className="absolute inset-x-[7px] top-[3px] h-px bg-blue/70" />
      <span className="absolute left-0 top-[-1px] h-[6px] w-[6px] rotate-45 bg-blue" />
      <span className="absolute right-0 top-[-1px] h-[6px] w-[6px] rotate-45 bg-blue" />
    </div>
  );
}
