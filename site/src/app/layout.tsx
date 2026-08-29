import type { Metadata, Viewport } from "next";
import "@/styles/noto-serif-sc.css";
import "@/styles/lxgw-wenkai.css";
import "./globals.css";
import { Nav } from "@/components/site/Nav";
import { Footer } from "@/components/site/Footer";

export const metadata: Metadata = {
  title: { default: "先锋队台账 · 每日蒸馏刊", template: "%s · 先锋队台账" },
  description: "🌱人民需要AI_智能体先锋队 的每日蒸馏刊：每期一张品鉴单——进料、蒸馏曲线、品评、逐字摘录、五维度数、行动清单。",
  applicationName: "先锋队台账",
  metadataBase: new URL("https://www.ai325.com"),
  icons: { icon: [{ url: "/icons/favicon-32.png", sizes: "32x32", type: "image/png" }, { url: "/icons/app-icon-192.png", sizes: "192x192", type: "image/png" }], apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }], shortcut: ["/icons/favicon.ico"] },
  openGraph: { type: "website", siteName: "先锋队台账", locale: "zh_CN", images: [{ url: "/art/cover-light-og.jpg", width: 1200, height: 630, alt: "先锋队台账 · 每日蒸馏刊" }] },
  twitter: { card: "summary_large_image", images: ["/art/cover-light-og.jpg"] },
};
export const viewport: Viewport = { themeColor: [{ media: "(prefers-color-scheme: light)", color: "#f2f1ec" }, { media: "(prefers-color-scheme: dark)", color: "#0f1219" }] };

const THEME_BOOT = `(function(){try{var t=localStorage.getItem('xf-theme');if(!t){t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}document.documentElement.dataset.theme=t}catch(e){document.documentElement.dataset.theme='light'}})();`;

const CONTRACT = `<!--
DIRECTION CONTRACT · impeccable seed a668aa13 · 品鉴单 The Tasting Sheet
THESIS: 每期日报是对「当天这一锅」的一张鉴定单，不是摘要页也不是 dashboard；拒绝「大数字+小标签+统计卡片墙+渐变 hero」的社群站默认排法。
OWN-WORLD: 纸白底上蓝墨印刷的表单（蓝=表头/格线/批次章），琥珀=酒液（曲线、分数、液位、度数），朱砂只给鉴定章与「半真」，青给「玩笑」；宋体正文 17px/1.9 约 38 字行，文楷当手写批注，数字用系统字体 tabular。去掉所有内容也能认出来：蓝色格线、左栏印刷标签、琥珀液位管、圆形批次章。
STORY: 读者先看到这一锅的批次与度数，再沿着进料→蒸馏曲线→品评→逐字摘录→五维打分→行动清单读完一锅；理解「治理后的内容才是产品」，带走可打勾的行动。
FIRST VIEWPORT: 左：一行样品信息（批次/日期/截止/鉴定人）+ 大号刊名「创刊号·全量基线」+ 导语；右上：圆形蓝章（第 001 批 · 76°）略倾斜盖下；其下一排六个进料字段框（蓝标签+大数字）；再下是通栏 24 小时蒸馏曲线，琥珀柱，酒心段更深并以括号标出。主要动作：往下读 / 往期。
FORM: 品鉴单（蒸馏厂世界的第 7 号渲染：烈酒品评记录表 × 酒精计 × 掐头去尾），seed a668aa13，assigned index 7。
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md
-->`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body className="sheet-ground min-h-screen antialiased">
        <div hidden dangerouslySetInnerHTML={{ __html: CONTRACT }} />
        <a href="#top" className="skip-link">跳到正文</a>
        <Nav />
        {children}
        <Footer />
      </body>
    </html>
  );
}
