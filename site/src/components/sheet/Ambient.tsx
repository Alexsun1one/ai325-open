"use client";
import { useEffect, useRef } from "react";

/**
 * 环境粒子：发酵缸里缓慢上浮的蒸汽微粒。极稀疏、极轻，只做气氛。
 * 不是雪花：每颗有自己的水平漂移与摆幅，越往上越淡，边缘用「核 + 晕」两笔画软。
 */
export function Ambient() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const cv = ref.current; if (!cv) return;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const ctx = cv.getContext("2d")!;
    let W = 0, H = 0, raf = 0, alive = true, gain = 1;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    type P = { x: number; y: number; r: number; v: number; a: number; w: number; k: number; ks: number; dx: number; amber: boolean };
    let ps: P[] = [];
    const css = () => getComputedStyle(document.documentElement);
    let amber = "#c37a14", blue = "#1c47a3";
    const readColors = () => {
      const c = css();
      amber = c.getPropertyValue("--amber").trim() || amber;
      blue = c.getPropertyValue("--blue-2").trim() || blue;
      // 纸白底上蓝/琥珀的对比比夜里弱，亮色主题给一档增益，保证「隐约看得见」
      gain = document.documentElement.dataset.theme === "dark" ? 1 : 1.55;
    };
    const rnd = (a: number, b: number) => a + Math.random() * (b - a);
    const spawn = (): P => ({
      x: Math.random() * W,
      y: H + rnd(10, 60),
      r: rnd(0.7, 2.1),
      v: rnd(0.10, 0.34),
      a: rnd(0.05, 0.12),
      w: rnd(5, 18),
      k: Math.random() * Math.PI * 2,
      ks: rnd(0.00035, 0.00085),
      dx: rnd(-0.012, 0.012),
      amber: Math.random() < 0.7,
    });
    const resize = () => {
      W = window.innerWidth; H = window.innerHeight;
      cv.width = W * dpr; cv.height = H * dpr;
      cv.style.width = W + "px"; cv.style.height = H + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const n = Math.min(46, Math.round((W * H) / 42000));
      ps = Array.from({ length: n }, () => { const p = spawn(); p.y = Math.random() * H; return p; });
    };
    resize(); readColors();
    const obs = new MutationObserver(readColors); obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    let last = performance.now();
    const loop = (t: number) => {
      if (!alive) return;
      const dt = Math.min(40, t - last); last = t;
      ctx.clearRect(0, 0, W, H);
      for (const p of ps) {
        p.y -= p.v * dt * 0.06;
        p.k += dt * p.ks;
        p.x += p.dx * dt * 0.06;
        if (p.y < -12 || p.x < -40 || p.x > W + 40) Object.assign(p, spawn());
        const x = p.x + Math.sin(p.k) * p.w;
        // 越往上越淡：底部 8% 淡入，顶部 45% 里线性散尽——是蒸汽在化开，不是雪花在飘
        const up = 1 - p.y / H;
        const rise = Math.min(1, Math.max(0, (1 - up) / 0.45));
        const born = Math.min(1, Math.max(0, up / 0.08));
        const a = p.a * gain * rise * born;
        if (a <= 0.002) continue;
        ctx.fillStyle = p.amber ? amber : blue;
        ctx.globalAlpha = a * 0.4;
        ctx.beginPath(); ctx.arc(x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
        ctx.globalAlpha = a;
        ctx.beginPath(); ctx.arc(x, p.y, p.r * 0.55, 0, Math.PI * 2); ctx.fill();
      }
      ctx.globalAlpha = 1;
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    const vis = () => { if (document.hidden) { alive = false; cancelAnimationFrame(raf); } else if (!alive) { alive = true; last = performance.now(); raf = requestAnimationFrame(loop); } };
    window.addEventListener("resize", resize); document.addEventListener("visibilitychange", vis);
    return () => { alive = false; cancelAnimationFrame(raf); window.removeEventListener("resize", resize); document.removeEventListener("visibilitychange", vis); obs.disconnect(); };
  }, []);
  return <canvas ref={ref} aria-hidden className="no-print pointer-events-none fixed inset-0 z-0" />;
}
