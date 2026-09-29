import styles from "./BookCover.module.css";

export type BookCoverKind = "book" | "repository";
export type BookCoverSize = "shelf" | "library";

export function bookCoverVariant(id: string): number {
  let hash = 2166136261;
  for (const char of id) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
  return Math.abs(hash) % 6;
}

function repoParts(title: string): { owner?: string; project: string } {
  const slash = title.indexOf("/");
  if (slash <= 0 || slash === title.length - 1) return { project: title };
  return { owner: title.slice(0, slash), project: title.slice(slash + 1) };
}

export function BookCover({
  id, title, author, kind = "book", size = "library", active = false,
  category,
}: { id: string; title: string; author?: string; kind?: BookCoverKind; size?: BookCoverSize; active?: boolean; category?: string }) {
  const variant = bookCoverVariant(id);
  const repo = kind === "repository" ? repoParts(title) : undefined;
  const length = title.length > 34 ? "long" : title.length > 18 ? "medium" : "short";
  return (
    <div className={`${styles.cover} ${styles[size]}`} data-variant={variant} data-kind={kind} data-active={active || undefined}>
      <span className={styles.spine} aria-hidden="true" />
      <span className={styles.pages} aria-hidden="true" />
      <span className={styles.face}>
        <span className={styles.kicker}>{kind === "repository" ? "源码导读" : "阅读笔记"}</span>
        <span className={styles.title} data-length={length}>
          {size === "library"
            ? <span className={styles.titleText}>{repo ? <><span className={styles.owner}>{repo.owner}</span><span>{repo.project}</span></> : title}</span>
            : (repo ? <><span className={styles.owner}>{repo.owner}</span><span>{repo.project}</span></> : title)}
        </span>
        {category && <span className={styles.category}>{category}</span>}
        {author && <span className={styles.byline}>{author}</span>}
        <span className={styles.signal} aria-hidden="true" />
      </span>
    </div>
  );
}
