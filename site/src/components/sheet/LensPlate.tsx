"use client";
import { useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";

/** 放大镜插页（Aceternity Lens 的品鉴单皮）：悬停出一枚圆形放大镜看蚀刻细节；纸色边 + 蓝发丝环。 */
export function LensPlate({ src, alt = "", zoom = 1.8, size = 180, className = "" }: { src: string; alt?: string; zoom?: number; size?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const [on, setOn] = useState(false);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const [geo, setGeo] = useState({ w: 1, h: 1, nw: 1, nh: 1 });
  const move = (e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const img = imgRef.current;
    setPos({ x: e.clientX - r.left, y: e.clientY - r.top });
    setGeo({ w: r.width, h: r.height, nw: img?.naturalWidth || r.width, nh: img?.naturalHeight || r.height });
  };
  // 还原 object-cover 的实际绘制几何，再放大 zoom 倍：镜片中心始终对准光标下那一点
  const cover = Math.max(geo.w / geo.nw, geo.h / geo.nh);
  const drawnW = geo.nw * cover, drawnH = geo.nh * cover;
  const ox = (drawnW - geo.w) / 2, oy = (drawnH - geo.h) / 2;
  return (
    <div ref={ref} className={`relative overflow-hidden ${className}`} onMouseEnter={() => setOn(true)} onMouseLeave={() => setOn(false)} onMouseMove={move}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img ref={imgRef} src={src} alt={alt} loading="lazy" decoding="async" className="block aspect-[16/9] w-full object-cover sm:aspect-[2/1]" />
      <AnimatePresence>
        {on && (
          <motion.div key="lens" initial={{ opacity: 0, scale: 0.7 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.7 }} transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            className="pointer-events-none absolute z-10 rounded-full border-[1.5px] border-blue shadow-[0_8px_24px_-10px_rgba(21,23,27,.45),inset_0_0_0_4px_var(--paper)]"
            style={{ width: size, height: size, left: pos.x - size / 2, top: pos.y - size / 2, backgroundImage: `url(${src})`, backgroundSize: `${drawnW * zoom}px ${drawnH * zoom}px`, backgroundPosition: `${size / 2 - (pos.x + ox) * zoom}px ${size / 2 - (pos.y + oy) * zoom}px`, backgroundRepeat: "no-repeat" }} aria-hidden />
        )}
      </AnimatePresence>
      <span className={`pointer-events-none absolute bottom-2 right-2 rounded-[3px] bg-paper/85 px-1.5 py-[2px] font-sans text-[10.5px] text-ink-3 transition-opacity ${on ? "opacity-0" : "opacity-80"}`}>悬停放大</span>
    </div>
  );
}
