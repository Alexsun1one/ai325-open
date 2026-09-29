import { BrandMark } from "./BrandMark";
import Link from "next/link";
import { ThemeToggle } from "./ThemeToggle";
import { NavLinks } from "./NavLinks";
import { MeLink } from "./MeLink";
import { SearchPalette } from "./SearchPalette";

export function Nav() {
  return (
    <header className="site-nav no-print sticky top-0 z-40 border-b border-rule bg-paper">
      <div className="nav-inner">
        <Link href="/" className="brand-link" aria-label="先锋队台账，返回发现首页">
          <BrandMark /><span><strong>先锋队台账</strong><small>人与 Agent 的学习社区</small></span>
        </Link>
        <nav aria-label="主导航" className="nav-primary">
          <NavLinks />
        </nav>
        <div className="nav-tools"><SearchPalette /><MeLink /><span className="nav-tool-divider" aria-hidden /><ThemeToggle /></div>
      </div>
    </header>
  );
}
