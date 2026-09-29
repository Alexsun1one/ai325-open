/* 先锋队表情（“先锋小蓝”）manifest 与文本分段。
   契约固定：8 个 id、token 形如 :xf-{id}:、图片 /brand/stickers/pioneer-{id}.webp。
   图片由根内置 Image Gen 生成后落位；本文件只认白名单 id，绝不接受任意 URL/外链图。 */

export type PioneerStickerId =
  | "ready" | "start" | "learned" | "evidence"
  | "retry" | "together" | "distilled" | "salute";

export interface PioneerSticker {
  id: PioneerStickerId;
  /** 中文名，图旁展示；也是图片 alt 与超额退化的 [名称] */
  name: string;
  /** 序列化 token :xf-{id}: */
  token: string;
  /** 固定站内路径，不拼接用户输入 */
  src: string;
}

const DEFS: ReadonlyArray<readonly [PioneerStickerId, string]> = [
  ["ready", "收到"],
  ["start", "开干"],
  ["learned", "学到了"],
  ["evidence", "求证据"],
  ["retry", "再试一次"],
  ["together", "一起向前"],
  ["distilled", "蒸馏好了"],
  ["salute", "向实干者致敬"],
];

export const PIONEER_STICKERS: readonly PioneerSticker[] = DEFS.map(([id, name]) => ({
  id,
  name,
  token: `:xf-${id}:`,
  src: `/brand/stickers/pioneer-${id}.webp`,
}));

/** 整套下载包，根接好后才在 UI 出现链接 */
export const PIONEER_STICKER_PACK_URL = "/brand/stickers/pioneer-stickers.zip";

/** 单条消息最多渲染为图片的数量；超出的 token 退化为 [名称] 文本 */
export const STICKER_IMAGE_LIMIT = 8;

export const STICKER_BY_TOKEN: ReadonlyMap<string, PioneerSticker> = new Map(
  PIONEER_STICKERS.map((s) => [s.token, s]),
);

/** token 的 regex source，供调用方嵌进更大的行内匹配器 */
export const STICKER_TOKEN_SRC = `:xf-(?:${DEFS.map(([id]) => id).join("|")}):`;

/** 白名单 token 匹配：只认 manifest 八个，未知 :xf-xxx: 保持纯文本 */
export const STICKER_TOKEN_RE = new RegExp(STICKER_TOKEN_SRC, "g");

/** 整行（段）仅由表情 token 与空白组成——用于放大渲染 */
export const STICKER_SOLO_RE = new RegExp(`^(?:\\s*${STICKER_TOKEN_SRC}\\s*)+$`);

/**
 * 纯文本摘录场景：已知 token 换成 [名称]，未知 token 原样保留——
 * 列表/引用/预览摘要里不裸显 :xf-…:。
 */
export function pioneerStickerText(src: string): string {
  return (src || "").replace(STICKER_TOKEN_RE, (t) => `[${STICKER_BY_TOKEN.get(t)!.name}]`);
}

export type StickerPart =
  | { kind: "text"; text: string }
  | { kind: "sticker"; sticker: PioneerSticker; asImage: boolean };

/**
 * 把一段（单行）文本按表情 token 切成有序片段。
 * budget 为可变计数：每产出一个图片片段 budget.left--，耗尽后 token 退化为
 * {kind:"sticker", asImage:false}——由渲染层显示 [名称]，不画假图。
 * 本函数不处理 Markdown 结构；代码块/行内码的豁免由调用方在进入本函数前保证。
 */
export function splitStickerParts(
  src: string,
  budget: { left: number },
): StickerPart[] {
  const parts: StickerPart[] = [];
  let last = 0;
  // matchAll 独立迭代器：调用方若嵌套使用也不会共享 lastIndex
  for (const m of src.matchAll(STICKER_TOKEN_RE)) {
    if (m.index > last) parts.push({ kind: "text", text: src.slice(last, m.index) });
    const sticker = STICKER_BY_TOKEN.get(m[0]);
    if (sticker) {
      const asImage = budget.left > 0;
      if (asImage) budget.left -= 1;
      parts.push({ kind: "sticker", sticker, asImage });
    } else {
      parts.push({ kind: "text", text: m[0] }); // 理论到不了：正则只放行白名单
    }
    last = m.index + m[0].length;
  }
  if (last < src.length) parts.push({ kind: "text", text: src.slice(last) });
  return parts;
}
