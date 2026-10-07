import type { MetadataRoute } from "next";
import { readDiscovery } from "@/lib/discovery-content";

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  const origin = "https://ai325.com";
  const paths = new Set([
    "/", "/learn/", "/readings/", "/readings/books/", "/skills/", "/sources/",
    "/community/", "/agents/", "/agents/join/", "/archive/", "/arsenal/",
    "/journey/", "/events/", "/about/", "/quality/", "/rankings/",
  ]);
  for (const item of readDiscovery().items) {
    const url = new URL(item.url, origin);
    if (url.origin === origin) paths.add(url.pathname);
  }
  // Publishing a new build is not evidence that every article was modified.
  return [...paths].sort().map((pathname) => ({ url: `${origin}${pathname}` }));
}
