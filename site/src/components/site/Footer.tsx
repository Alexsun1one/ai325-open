import { BrandMark } from "./BrandMark";
import Link from "next/link";

export function Footer() {
  return (
    <footer className="no-print mt-24 border-t border-rule">
      <div className="mx-auto grid max-w-[1180px] gap-8 px-5 py-12 sm:grid-cols-3 sm:px-8">
        <div>
          <div className="flex items-center gap-3 font-serif text-[18px] font-black text-ink"><BrandMark />先锋队台账</div>
          <p className="mt-2 max-w-[34ch] font-sans text-[13px] leading-relaxed text-ink-3">
            🌱人民需要AI_智能体先锋队 的学习社区。从每日讨论中整理知识，让人和 Agent 一起验证、交流、积累方法。
          </p>
        </div>
        <div className="font-sans text-[13.5px]">
          <div className="label mb-3">栏目</div>
          <ul className="grid grid-cols-2 gap-y-1.5 text-ink-2">
            <li><Link href="/" className="hover:text-blue-text">发现内容</Link></li>
            <li><Link href="/archive/" className="hover:text-blue-text">往期 · 线索图</Link></li>
            <li><Link href="/readings/" className="hover:text-blue-text">书与代码精读</Link></li>
            <li><Link href="/events/" className="hover:text-blue-text">活动专区</Link></li>
            <li><Link href="/learn/" className="hover:text-blue-text">知识与方法</Link></li>
            <li><Link href="/community/" className="hover:text-blue-text">实践与交流</Link></li>
            <li><Link href="/agents/" className="hover:text-blue-text">Agent 学堂</Link></li>
            <li><Link href="/skills/" className="hover:text-blue-text">Skill 技能库</Link></li>
            <li><Link href="/members/" className="hover:text-blue-text">群像（登录）</Link></li>
            <li><Link href="/essays/" className="hover:text-blue-text">窖藏（登录）</Link></li>
            <li><Link href="/about/" className="hover:text-blue-text">关于 · 邀请码 · 订阅</Link></li>
          </ul>
        </div>
        <div className="font-sans text-[13px] leading-relaxed text-ink-3">
          <div className="label mb-3">怎么记的</div>
          <p>时间一律北京时间（UTC+8）。引文逐字来自群聊原文；「没说破的」为整理者延伸，已用手写体标出。涉隐私内容打码，密码类内容不收录。</p>
          <p className="mt-2">哪天记录不全，我们会如实标出来。</p>
        </div>
      </div>
    </footer>
  );
}
