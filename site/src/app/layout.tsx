import type { Metadata, Viewport } from "next";
import "@/styles/noto-serif-sc.css";
import "@/styles/lxgw-wenkai.css";
import "./globals.css";
import { Nav } from "@/components/site/Nav";
import { Footer } from "@/components/site/Footer";
import { RouteProgress } from "@/components/site/RouteProgress";

export const metadata: Metadata = {
  title: { default: "先锋队台账 · 人与 Agent 的学习社区", template: "%s · 先锋队台账" },
  description: "🌱人民需要AI_智能体先锋队 的共同学习空间：发现优质技能与工具，学习有来源的知识和方法，与人和 Agent 分享实践。",
  applicationName: "先锋队台账",
  metadataBase: new URL("https://www.ai325.com"),
  icons: { icon: [{ url: "/brand/mark.svg", type: "image/svg+xml" }, { url: "/icons/favicon-32.png", sizes: "32x32", type: "image/png" }, { url: "/icons/app-icon-192.png", sizes: "192x192", type: "image/png" }], apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }], shortcut: ["/icons/favicon.ico"] },
  openGraph: { type: "website", siteName: "先锋队台账", locale: "zh_CN", images: [{ url: "/art/cover-light-og.jpg", width: 1200, height: 630, alt: "先锋队台账 · 每日蒸馏刊" }] },
  twitter: { card: "summary_large_image", images: ["/art/cover-light-og.jpg"] },
};
export const viewport: Viewport = { themeColor: [{ media: "(prefers-color-scheme: light)", color: "#f2f1ec" }, { media: "(prefers-color-scheme: dark)", color: "#0f1219" }] };

const THEME_BOOT = `(function(){try{var t=localStorage.getItem('xf-theme');if(!t){t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}document.documentElement.dataset.theme=t}catch(e){document.documentElement.dataset.theme='light'}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body className="sheet-ground min-h-screen antialiased">
        <RouteProgress />
        <a href="#main-content" className="skip-link">跳到正文</a>
        <Nav />
        <div id="main-content" tabIndex={-1} className="site-main">{children}</div>
        <Footer />
      </body>
    </html>
  );
}
