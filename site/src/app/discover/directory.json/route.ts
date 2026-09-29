import { readDiscovery } from "@/lib/discovery-content";
export const dynamic = "force-static";
export function GET() { return Response.json(readDiscovery()); }
