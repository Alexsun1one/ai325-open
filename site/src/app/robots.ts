import type { MetadataRoute } from "next";

export const dynamic = "force-static";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/admin/", "/me/", "/claim/", "/members/", "/essays/", "/cellar/", "/library/"],
    },
    sitemap: "https://ai325.com/sitemap.xml",
  };
}
