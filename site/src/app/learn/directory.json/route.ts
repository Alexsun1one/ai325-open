import { readKnowledge } from "@/lib/knowledge-content";
export const dynamic = "force-static";
export function GET() { return Response.json(readKnowledge()); }
