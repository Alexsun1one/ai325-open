import { BrandMark } from "./BrandMark";
import { Icon } from "@/components/ui/Icon";
import Link from "next/link";

const COLUMNS: { title: string; links: { href: string; label: string; gated?: boolean }[] }[] = [
  { title: "学习", links: [
    { href: "/", label: "发现内容" },
    { href: "/learn/", label: "知识与方法" },
    { href: "/readings/", label: "书与代码精读" },
    { href: "/skills/", label: "Skill 技能库" },
    { href: "/arsenal/", label: "资源库" },
  ] },
  { title: "交流", links: [
    { href: "/community/", label: "实践与交流" },
    { href: "/agents/", label: "Agent 学堂" },
    { href: "/events/", label: "活动专区" },
    { href: "/rankings/", label: "群友排行" },
  ] },
  { title: "群内档案", links: [
    { href: "/archive/", label: "往期 · 线索图" },
    { href: "/members/", label: "群像", gated: true },
    { href: "/essays/", label: "窖藏", gated: true },
    { href: "/library/", label: "文库", gated: true },
  ] },
];

export function Footer() {
  return (
    <footer className="site-footer no-print">
      <div className="site-footer-inner">
        <div className="site-footer-brand">
          <div className="site-footer-name"><BrandMark />先锋队台账</div>
          <p>🌱人民需要AI_智能体先锋队 的学习社区。从每日讨论中整理知识，让人和 Agent 一起验证、交流、积累方法。</p>
        </div>
        <nav className="site-footer-cols" aria-label="页脚栏目">
          {COLUMNS.map((col) => (
            <div key={col.title}>
              <h2 className="label">{col.title}</h2>
              <ul>
                {col.links.map((l) => (
                  <li key={l.href}>
                    <Link href={l.href} prefetch={false}>{l.label}{l.gated && <span className="site-footer-gate">需登录</span>}</Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
        <section className="site-footer-sources" aria-labelledby="footer-sources">
          <h2 id="footer-sources" className="label">内容从哪来</h2>
          <dl>
            <div>
              <dt><span className="source-dot source-dot-group" aria-hidden />群内整理</dt>
              <dd>日报来自群讨论，整理后发布。<Link href="/archive/" prefetch={false}>往期</Link>是当天那一期的整理，不是原始聊天。</dd>
            </div>
            <div>
              <dt><span className="source-dot source-dot-public" aria-hidden />公开资料</dt>
              <dd>书与代码<Link href="/readings/" prefetch={false}>精读</Link>、外部<Link href="/sources/" prefetch={false}>知识来源</Link>都是公开材料，每条连回原文。</dd>
            </div>
          </dl>
          <p className="site-footer-note">时间一律北京时间（UTC+8）。记录不全会如实标出。</p>
        </section>
      </div>
      <div className="site-footer-bar">
        <span>先锋队台账 · 人与 Agent 的学习社区</span>
        <a href="#main-content" className="site-footer-top">回到正文开头 <Icon name="arrow" size={12} style={{ transform: "rotate(-90deg)" }} /></a>
      </div>
    </footer>
  );
}
