import { readReadings } from "@/lib/reading-content";
import type { PracticeIndex, PracticeIndexEntry } from "@/lib/reading-practice";

export const dynamic = "force-static";

/** 阅读→练习预填索引：白名单条目 id → 可编辑预填字段。
 *  只出标题/完成标准/第一步/回链——不带正文、不带外部私密路径；
 *  字段都从现行 readReadings 派生，新书晋升自动纳入。 */
export function GET() {
  const entries: Record<string, PracticeIndexEntry> = {};
  for (const e of readReadings()) {
    const steps = e.exercise.steps.map((s) => s.trim()).filter(Boolean);
    const outcome = [e.exercise.title.trim(), ...steps.map((s) => `· ${s}`)]
      .filter(Boolean).join("\n").slice(0, 1000);
    entries[e.id] = {
      title: e.title.slice(0, 120),
      outcome,
      next_step: (steps[0] ?? e.exercise.title).slice(0, 1000),
      source_url: `/readings/${e.id}/`,
      source_title: e.title.slice(0, 240),
    };
  }
  const payload: PracticeIndex = { version: 1, entries };
  return Response.json(payload);
}
