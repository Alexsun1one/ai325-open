/** Agent 自绘头像目录：契约白名单 8 款，与后端 avatar_key 取值一致。
 *  同一 40×40 网格、currentColor 描边、无外部图库；'' 表示自动（按名字种子生成）。
 *  外观只是装扮，不代表认证/权限/在线。 */
export const AGENT_AVATAR_KEYS = ["robot", "owl", "fox", "cat", "orbit", "seed", "spark", "hermes"] as const;
export type AgentAvatarKey = (typeof AGENT_AVATAR_KEYS)[number];

export function isAgentAvatarKey(value: unknown): value is AgentAvatarKey {
  return typeof value === "string" && (AGENT_AVATAR_KEYS as readonly string[]).includes(value);
}

/** 一条可描边路径；w 覆盖默认 1.8 的线宽。 */
export interface AgentAvatarMark { d: string; w?: number }

export const AGENT_AVATARS: Record<AgentAvatarKey, { label: string; nodes: AgentAvatarMark[] }> = {
  robot: {
    label: "机器人",
    nodes: [
      { d: "M17 8h6M20 8v6", w: 1.8 },
      { d: "M10 14h20a3 3 0 0 1 3 3v11a3 3 0 0 1-3 3H10a3 3 0 0 1-3-3V17a3 3 0 0 1 3-3Z", w: 1.8 },
      { d: "M15 21v3.5M25 21v3.5", w: 2 },
      { d: "M15 28.5h10", w: 1.8 },
      { d: "M15 34.5h10", w: 1.5 },
    ],
  },
  owl: {
    label: "猫头鹰",
    nodes: [
      { d: "M12 11.5 9.5 7l5.5 2M28 11.5 30.5 7l-5.5 2", w: 1.6 },
      { d: "M20 10.5c-6.5 0-11 4.5-11 11 0 8 4.5 12.5 11 12.5s11-4.5 11-12.5c0-6.5-4.5-11-11-11Z", w: 1.8 },
      { d: "M15.5 15.8a3.2 3.2 0 1 0 0 6.4 3.2 3.2 0 0 0 0-6.4ZM24.5 15.8a3.2 3.2 0 1 0 0 6.4 3.2 3.2 0 0 0 0-6.4Z", w: 1.8 },
      { d: "m20 23-2 3h4l-2-3Z", w: 1.6 },
    ],
  },
  fox: {
    label: "狐狸",
    nodes: [
      { d: "M9.5 7l7 6h7l7-6-1 13L20 34 10.5 20l-1-13Z", w: 1.8 },
      { d: "M15.5 19.5v2.5M24.5 19.5v2.5", w: 2 },
    ],
  },
  cat: {
    label: "猫",
    nodes: [
      { d: "M12.5 16.5 10.5 7.5l7.5 5M27.5 16.5 29.5 7.5l-7.5 5", w: 1.8 },
      { d: "M20 14a10 10 0 1 0 0 20 10 10 0 0 0 0-20Z", w: 1.8 },
      { d: "M16 22v2.5M24 22v2.5", w: 2 },
      { d: "m18 29.5 2 1.5 2-1.5", w: 1.5 },
    ],
  },
  orbit: {
    label: "星轨",
    nodes: [
      { d: "M20 13a7 7 0 1 0 0 14 7 7 0 0 0 0-14Z", w: 1.8 },
      { d: "M5 20a15 5.5 0 1 0 30 0 15 5.5 0 1 0-30 0Z", w: 1.5 },
      { d: "M33 10.5h.01", w: 2.5 },
    ],
  },
  seed: {
    label: "种子",
    nodes: [
      { d: "M20 33V21", w: 1.8 },
      { d: "M20 22c-6.5 0-10-4-10-10.5 6 0 10 4 10 10.5ZM20 22c6.5 0 10-4 10-10.5-6 0-10 4-10 10.5Z", w: 1.7 },
      { d: "M14 35h12", w: 1.5 },
    ],
  },
  spark: {
    label: "火花",
    nodes: [
      { d: "m20 6 3.4 10.1L33.5 20l-10.1 3.4L20 34l-3.4-10.1L6.5 20l10.1-3.4L20 6Z", w: 1.8 },
    ],
  },
  hermes: {
    label: "信使",
    nodes: [
      { d: "M13 11v18M27 11v18M13 20h14", w: 2 },
      { d: "M8 8.5c2.6-2.4 5.8-3.7 9-3.7M32 8.5c-2.6-2.4-5.8-3.7-9-3.7", w: 1.5 },
      { d: "M11 34.5h18", w: 1.5 },
    ],
  },
};
