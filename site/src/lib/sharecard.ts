/** 金句分享卡：1080×1350 竖版 PNG，纸白/蓝格线/琥珀章，只含治理产物。 */
import { TONE_META, type Tone, pad3 } from "@/lib/shared";

export interface CardInput { text: string; author: string; tone?: Tone; issue: number; date: string; degree: number; url: string; kicker?: string }

const SANS = '-apple-system, "PingFang SC", sans-serif';
const SERIF = '"Noto Serif SC", serif';

const NO_HEAD = "，。、：；！？」』”）】…％%°，,.;:!?)";
const NO_TAIL = "「『“（【(";

function wrap(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string[] {
  // Latin/数字串当一个整体，不拦腰截断
  const units = text.match(/[A-Za-z0-9@_.\-]+|[\s\S]/gu) ?? [];
  const lines: string[] = []; let cur = "";
  for (const u of units) {
    const test = cur + u;
    if (ctx.measureText(test).width > maxWidth && cur) { lines.push(cur); cur = u; } else cur = test;
  }
  if (cur) lines.push(cur);
  // 避头点：行首标点上提；避尾点：行尾开引号下放
  for (let k = 1; k < lines.length; k++) {
    while (lines[k] && NO_HEAD.includes(Array.from(lines[k])[0])) {
      lines[k - 1] += Array.from(lines[k])[0];
      lines[k] = Array.from(lines[k]).slice(1).join("");
    }
    const prev = Array.from(lines[k - 1]);
    if (prev.length && NO_TAIL.includes(prev[prev.length - 1])) {
      lines[k] = prev.pop()! + lines[k];
      lines[k - 1] = prev.join("");
    }
  }
  return lines.filter((l) => l.length > 0);
}

/** 字距版标题：canvas letterSpacing 在部分 WebView 不生效，逐字画最稳。 */
function spacedText(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, gap: number) {
  let cx = x;
  for (const ch of Array.from(text)) { ctx.fillText(ch, cx, y); cx += ctx.measureText(ch).width + gap; }
  return cx - gap;
}

export async function renderShareCard(i: CardInput): Promise<Blob> {
  const W = 1080, H = 1350;
  const c = document.createElement("canvas"); c.width = W; c.height = H;
  const ctx = c.getContext("2d")!;
  const dark = document.documentElement.dataset.theme === "dark";
  const css = getComputedStyle(document.documentElement);
  const v = (n: string) => css.getPropertyValue(n).trim();
  const paper = v("--paper"), ink = v("--ink"), ink3 = v("--ink-3"), blue = v("--blue"), blueText = v("--blue-text"), amber = v("--amber"), amber2 = v("--amber-2"), amberDeep = v("--amber-deep"), amberText = v("--amber-text"), rule = v("--rule"), ruleStrong = v("--rule-strong");
  // 带上实际文本：分包(unicode-range)字体只有指明字符才会把对应 CJK 子包拉下来，否则首次渲染回退黑体
  try {
    await Promise.all([
      document.fonts.load(`900 64px ${SERIF}`, "先锋队台账「」"),
      document.fonts.load(`700 64px ${SERIF}`, i.text + i.author),
    ]);
  } catch {}

  // ── 纸面：底色 + 网点 + 边缘晕影（给卡一点「纸」的厚度）
  ctx.fillStyle = paper; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = dark ? "rgba(255,255,255,.06)" : "rgba(0,0,0,.06)";
  for (let y = 40; y < H; y += 36) for (let x = 40; x < W; x += 36) ctx.fillRect(x, y, 2, 2);
  const vg = ctx.createRadialGradient(W / 2, H / 2, H * 0.32, W / 2, H / 2, H * 0.74);
  vg.addColorStop(0, "rgba(0,0,0,0)");
  vg.addColorStop(1, dark ? "rgba(0,0,0,.22)" : "rgba(56,48,28,.055)");
  ctx.fillStyle = vg; ctx.fillRect(0, 0, W, H);

  // ── 外粗内细双道框 + 四角线稿角花
  ctx.strokeStyle = blue;
  ctx.lineWidth = 4; ctx.strokeRect(44, 44, W - 88, H - 88);
  ctx.lineWidth = 1; ctx.strokeRect(58, 58, W - 116, H - 116);
  ctx.lineWidth = 1.5;
  for (const [cx2, sx] of [[58, 1], [W - 58, -1]] as const) for (const [cy, sy] of [[58, 1], [H - 58, -1]] as const) {
    ctx.beginPath();
    ctx.moveTo(cx2 + 14 * sx, cy + 36 * sy); ctx.lineTo(cx2 + 14 * sx, cy + 14 * sy); ctx.lineTo(cx2 + 36 * sx, cy + 14 * sy);
    ctx.stroke();
    ctx.beginPath(); ctx.arc(cx2 + 25 * sx, cy + 25 * sy, 2.5, 0, Math.PI * 2); ctx.fillStyle = blue; ctx.fill();
  }

  // ── 刊头：字距拉开的刊名 + 层级压低的副题
  ctx.fillStyle = ink; ctx.font = `900 46px ${SERIF}`; ctx.textBaseline = "alphabetic";
  spacedText(ctx, "先锋队台账", 100, 150, 12);
  ctx.fillStyle = amber; ctx.fillRect(100, 170, 46, 3);
  ctx.fillStyle = ink3; ctx.font = `500 19px ${SANS}`;
  ctx.fillText(i.kicker ?? "🌱人民需要AI_智能体先锋队 · 每日蒸馏刊 · 逐字摘录", 100, 204);
  ctx.strokeStyle = blue; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(58, 236); ctx.lineTo(W - 58, 236); ctx.stroke();

  // ── 双环琥珀批次章：度数大字 + 批次/日期小字，微旋转盖章感
  ctx.save(); ctx.translate(W - 196, 147); ctx.rotate(-0.09); ctx.globalAlpha = 0.95;
  ctx.strokeStyle = amber; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(0, 0, 74, 0, Math.PI * 2); ctx.stroke();
  ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(0, 0, 64, 0, Math.PI * 2); ctx.stroke();
  ctx.fillStyle = amber; ctx.textAlign = "center";
  ctx.font = `600 15px ${SANS}`; ctx.fillText(`第 ${pad3(i.issue)} 批`, 0, -30);
  ctx.beginPath(); ctx.moveTo(-26, -22); ctx.lineTo(26, -22); ctx.lineWidth = 1; ctx.stroke();
  ctx.font = `800 44px ${SANS}`; ctx.fillText(`${i.degree}°`, 0, 18);
  ctx.font = `600 12.5px ${SANS}`; ctx.fillText(i.date, 0, 44);
  ctx.restore(); ctx.textAlign = "left"; ctx.globalAlpha = 1;

  // ── 正文：按字数分级字号，垂直居中，引号「」压角
  const chars = Array.from(i.text).length;
  const size = chars <= 40 ? 64 : chars <= 80 ? 54 : chars <= 120 ? 48 : 42;
  const lh = Math.round(size * 1.62);
  ctx.font = `700 ${size}px ${SERIF}`;
  const bodyTop = 262, bodyBottom = 958, zoneH = bodyBottom - bodyTop;
  const maxLines = Math.floor(zoneH / lh);
  let lines = wrap(ctx, i.text, W - 300);
  if (lines.length > maxLines) { lines = lines.slice(0, maxLines); lines[lines.length - 1] += "…"; }
  const blockH = lines.length * lh;
  const startY = bodyTop + (zoneH - blockH) / 2 + size * 0.82;
  const qs = Math.round(size * 2.3);
  ctx.fillStyle = amber; ctx.globalAlpha = 0.9; ctx.font = `900 ${qs}px ${SERIF}`;
  ctx.fillText("「", 82, startY - lh * 0.34);
  ctx.textAlign = "right"; ctx.fillText("」", W - 82, startY + (lines.length - 1) * lh + lh * 0.62);
  ctx.textAlign = "left"; ctx.globalAlpha = 1;
  ctx.fillStyle = ink; ctx.font = `700 ${size}px ${SERIF}`;
  lines.forEach((ln, k) => ctx.fillText(ln, 150, startY + k * lh));

  // ── 署名区：圆形姓氏章 + 作者名，语气章排右侧
  const sigCy = 1042;
  const initial = Array.from(i.author)[0] ?? "佚";
  ctx.strokeStyle = blue; ctx.lineWidth = 2.5;
  ctx.beginPath(); ctx.arc(162, sigCy, 30, 0, Math.PI * 2); ctx.stroke();
  ctx.fillStyle = blue; ctx.font = `700 30px ${SERIF}`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(initial, 162, sigCy + 2);
  ctx.textAlign = "left";
  ctx.fillStyle = blueText; ctx.font = `500 31px ${SANS}`;
  ctx.fillText(i.author, 212, sigCy + 1);
  if (i.tone) {
    const m = TONE_META[i.tone];
    ctx.save(); ctx.translate(W - 210, sigCy); ctx.rotate(-0.05); ctx.globalAlpha = 0.92;
    ctx.strokeStyle = amberText; ctx.lineWidth = 2;
    const bw = 196, bh = 54;
    if (ctx.roundRect) { ctx.beginPath(); ctx.roundRect(-bw / 2, -bh / 2, bw, bh, 8); ctx.stroke(); }
    else ctx.strokeRect(-bw / 2, -bh / 2, bw, bh);
    ctx.fillStyle = amberText; ctx.font = `600 23px ${SANS}`; ctx.textAlign = "center";
    ctx.fillText(`语气鉴定 · ${m.label}`, 0, 2);
    ctx.restore(); ctx.textAlign = "left"; ctx.globalAlpha = 1;
  }
  ctx.textBaseline = "alphabetic";

  // ── 底部：液位刻度小条（0 → 本期度数）+ 网址与治理小字
  ctx.strokeStyle = blue; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(58, 1122); ctx.lineTo(W - 58, 1122); ctx.stroke();
  const barY = 1206, x0 = 104, x1 = 560, deg = Math.max(0, Math.min(100, i.degree));
  ctx.strokeStyle = ruleStrong; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(x0, barY); ctx.lineTo(x1, barY); ctx.stroke();
  ctx.lineWidth = 1;
  for (let d = 0; d <= 100; d += 10) {
    const tx = x0 + (x1 - x0) * d / 100;
    ctx.beginPath(); ctx.moveTo(tx, barY); ctx.lineTo(tx, barY + (d % 50 === 0 ? 11 : 7)); ctx.stroke();
  }
  const fillEnd = x0 + (x1 - x0) * deg / 100;
  const fg = ctx.createLinearGradient(x0, 0, fillEnd, 0);
  fg.addColorStop(0, amber2); fg.addColorStop(1, amber);
  ctx.fillStyle = fg; ctx.globalAlpha = 0.9; ctx.fillRect(x0, barY - 9, fillEnd - x0, 9); ctx.globalAlpha = 1;
  ctx.strokeStyle = amberDeep; ctx.lineWidth = 2.5;
  ctx.beginPath(); ctx.moveTo(fillEnd, barY - 15); ctx.lineTo(fillEnd, barY + 4); ctx.stroke();
  ctx.fillStyle = amberDeep; ctx.font = `700 22px ${SANS}`; ctx.textAlign = "center";
  ctx.fillText(`${i.degree}°`, fillEnd, barY - 24);
  ctx.fillStyle = ink3; ctx.font = `400 15px ${SANS}`;
  ctx.fillText("0", x0, barY + 32); ctx.fillText("100", x1, barY + 32);
  ctx.textAlign = "right";
  ctx.fillStyle = blueText; ctx.font = `600 24px ${SANS}`; ctx.fillText(i.url, W - 104, 1196);
  ctx.fillStyle = ink3; ctx.font = `400 17px ${SANS}`; ctx.fillText("蒸好的 · 原始聊天不上站", W - 104, 1230);
  ctx.textAlign = "left";
  return await new Promise((res) => c.toBlob((b) => res(b!), "image/png"));
}
