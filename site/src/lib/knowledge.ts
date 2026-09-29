export interface KnowledgeSource { date: string; themeTitle: string }
export interface KnowledgeEntry {
  id: string; kind: "insight" | "method" | "principle";
  title: string; text: string; topicId: string; status: "working";
  sources: KnowledgeSource[]; relatedIds: string[]; steps: string[];
  counterpoint: string; question: string; revisions: { date: string; note: string }[];
}
export interface KnowledgeData {
  schemaVersion: 1; updatedAt: string;
  topics: { id: string; title: string; description: string }[];
  entries: KnowledgeEntry[];
}
export const KNOWLEDGE_KINDS = { insight: "编辑金句", method: "实践方法", principle: "暂定原则" };
