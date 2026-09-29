import { readSkillLibrary } from "@/lib/skill-content";
export const dynamic = "force-static";
export function GET() {
  return Response.json(readSkillLibrary());
}
