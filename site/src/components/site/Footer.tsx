import Link from "next/link";

export function Footer() {
  return (
    <footer className="no-print mt-24 border-t border-rule">
      <div className="mx-auto grid max-w-[1180px] gap-8 px-5 py-12 sm:grid-cols-3 sm:px-8">
        <div>
          <div className="font-serif text-[18px] font-black text-ink">先锋队台账</div>
          <p className="mt-2 max-w-[34ch] font-sans text-[13px] leading-relaxed text-ink-3">
            🌱人民需要AI_智能体先锋队 的每日蒸馏刊。群聊是原料，这里只端出蒸好的那一锅。
          </p>
        </div>
        <div className="font-sans text-[13.5px]">
          <div className="label mb-3">栏目</div>
          <ul className="grid grid-cols-2 gap-y-1.5 text-ink-2">
            <li><Link href="/" className="hover:text-blue-text">本期</Link></li>
            <li><Link href="/archive/" className="hover:text-blue-text">往期 · 线索图</Link></li>
            <li><Link href="/events/" className="hover:text-blue-text">活动专区</Link></li>
            <li><Link href="/quality/" className="hover:text-blue-text">度数</Link></li>
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
