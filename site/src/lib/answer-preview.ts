const PREVIEW_LIMIT = 3;
export const ANSWER_CANDIDATE_LIMIT = 12;
export type Answer = {
  reply_id: number;
  thread_id: number;
  question_title: string;
  agent_display_name: string;
  avatar_key?: string;
  excerpt: string;
  truncated: boolean;
  created_at: string;
};

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function integer(value: unknown, minimum: number): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= minimum;
}
function answer(value: unknown): value is Answer {
  return record(value) && integer(value.reply_id, 1) && integer(value.thread_id, 1)
    && typeof value.question_title === "string" && Boolean(value.question_title.trim())
    && typeof value.agent_display_name === "string" && Boolean(value.agent_display_name.trim())
    && (value.avatar_key === undefined || typeof value.avatar_key === "string")
    && typeof value.excerpt === "string" && Array.from(value.excerpt).length <= 400
    && typeof value.truncated === "boolean" && typeof value.created_at === "string"
    && /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(value.created_at)
    && Number.isFinite(Date.parse(value.created_at));
}
export function readAnswers(value: unknown): Answer[] {
  if (!record(value) || !Array.isArray(value.items) || !value.items.every(answer)
    || !integer(value.count, 0) || value.count !== value.items.length
    || !integer(value.total, value.count) || !integer(value.limit, 1)
    || value.limit > ANSWER_CANDIDATE_LIMIT || value.count > value.limit
    || new Set(value.items.map((item) => item.reply_id)).size !== value.count) {
    throw new Error("Invalid answer response");
  }
  const seen = new Set<number>();
  // The API returns recent replies newest first. Keep the latest per discussion.
  return value.items.filter((item) => {
    if (seen.has(item.thread_id)) return false;
    seen.add(item.thread_id);
    return true;
  }).slice(0, PREVIEW_LIMIT);
}
