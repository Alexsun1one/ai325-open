/** Open pages become a growing shoot: the community's learning mark. */
export function BrandMark({ className = "" }: { className?: string }) {
  return <svg className={className} width="36" height="36" viewBox="0 0 48 48" fill="none" aria-hidden="true">
    <path d="M6 18C13 18 19 21 24 25C29 21 35 18 42 18V36C35 36 29 39 24 43C19 39 13 36 6 36V18Z" fill="var(--blue-wash)" stroke="var(--blue-text)" strokeWidth="2.5" strokeLinejoin="round" />
    <path d="M24 25V43M12 27L18 30M36 27L30 30" stroke="var(--blue-text)" strokeWidth="2.5" strokeLinecap="round" />
    <path d="M24 22V13M24 15C18 15 15 11 15 6C21 6 24 10 24 15ZM24 18C24 11 28 7 34 7C34 13 30 18 24 18Z" fill="var(--amber-wash)" stroke="var(--amber-text)" strokeWidth="2.5" strokeLinejoin="round" />
  </svg>;
}
