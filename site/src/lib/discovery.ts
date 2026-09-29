export type DiscoveryKind = "knowledge" | "skill" | "resource" | "ledger";
export interface DiscoveryItem { id: string; kind: DiscoveryKind; title: string; summary: string; url: string; date: string; tags: string[]; sourceUrl?: string; topicId?: string }
export interface DiscoveryData { schemaVersion: 1; updatedAt: string; items: DiscoveryItem[] }
export const DISCOVERY_KINDS: Record<DiscoveryKind,string> = { knowledge:"金句与方法", resource:"工具与资源", skill:"Agent 技能", ledger:"每日蒸馏" };
