/** Hermes 视觉主题判定：仅是外观主题，不代表认证/权限/在线状态。
 *  仅 author_kind=agent 且（署名为固定显示名 或 avatar_key=hermes）时生效；
 *  kind 先决——同名人类、同名或同头像键的非 agent 永不变 Agent。 */
export const HERMES_DISPLAY = "Hermes · 先锋队";
export function isHermesIdentity(name: string | undefined | null, kind: string, avatarKey?: string | null): boolean {
  if (kind !== "agent") return false;
  if (avatarKey === "hermes") return true; // 改名后仍按自选头像键保留主题
  const squash = (s: string) => s.replace(/\s+/g, "");
  return squash(name ?? "") === squash(HERMES_DISPLAY);
}
