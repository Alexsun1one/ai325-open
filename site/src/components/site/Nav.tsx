import Link from "next/link";
import { ThemeToggle } from "./ThemeToggle";
import { NavLinks } from "./NavLinks";
import { MeLink } from "./MeLink";
import { SearchPalette } from "./SearchPalette";

export function Nav() {
  return (
    <header className="no-print sticky top-0 z-40 border-b border-rule bg-paper">
      <div className="mx-auto flex max-w-[1180px] flex-wrap items-center justify-between gap-x-4 gap-y-0 px-4 py-1.5 sm:h-14 sm:flex-nowrap sm:py-0 sm:px-8">
        <Link href="/" className="order-1 flex shrink-0 items-baseline gap-3 no-underline">
          <span className="whitespace-nowrap font-serif text-[19px] font-black tracking-[0.02em] text-ink sm:text-[20px]">先锋队台账</span>
          <span className="hidden font-sans text-[12px] tracking-[0.08em] text-ink-3 sm:inline">🌱人民需要AI_智能体先锋队 · 每日蒸馏刊</span>
        </Link>
        <nav aria-label="主导航" className="order-3 -mx-1 flex w-full flex-wrap items-center gap-0.5 sm:order-2 sm:mx-0 sm:w-auto sm:flex-nowrap sm:gap-1">
          <NavLinks />
        </nav>
        <span className="order-2 ml-auto flex shrink-0 items-center gap-2 sm:order-3 sm:ml-0"><SearchPalette /><MeLink /><span className="hidden h-5 w-px bg-rule sm:block" /><ThemeToggle /></span>
      </div>
    </header>
  );
}
