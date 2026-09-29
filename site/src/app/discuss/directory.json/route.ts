import { readDiscussionTargets } from "@/lib/discuss-directory";
export const dynamic = "force-static";
export function GET() { return Response.json(readDiscussionTargets()); }
