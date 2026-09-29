export interface ReadingEntry {
  id: string; kind: "book" | "repository"; title: string; subtitle: string; summary: string;
  source: { title: string; url: string }; reviewedAt: string; tags: string[]; takeaways: string[];
  sections: { title: string; body: string }[]; exercise: { title: string; steps: string[] };
  caveat: string; relatedTopic: string;
}
