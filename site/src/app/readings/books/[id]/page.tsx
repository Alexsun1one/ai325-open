import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { PageShell } from "@/components/pages/PageHead";
import BookNoteBody, { bookNoteHeadings } from "@/components/pages/BookNoteBody";
import { ReadingActions } from "@/components/pages/ReadingActions";
import { ContentEngagement } from "@/components/pages/ContentEngagement";
import { ArticleComments } from "@/components/pages/ArticleComments";
import { Icon } from "@/components/ui/Icon";
import { readBookNote, readBookNoteIndex } from "@/lib/book-notes";
import styles from "../books.module.css";

export const dynamicParams = false;
export function generateStaticParams() {
  return readBookNoteIndex().items.map((e) => ({ id: e.id }));
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const entry = readBookNoteIndex().items.find((e) => e.id === id);
  return { title: entry ? `${entry.title} — 研读笔记` : "研读笔记未找到", description: entry ? `${entry.author}《${entry.title}》研读整理笔记` : undefined };
}

export default async function BookNotePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const note = readBookNote(id);
  if (!note) notFound();
  const toc = bookNoteHeadings(note.markdown).filter((h: { level: number }) => h.level <= 3);
  // 评论日期取笔记 updated 里的合法日；不合法不造日期
  const upd = (note.updated ?? "").slice(0, 10);
  const commentDate = /^\d{4}-\d{2}-\d{2}$/.test(upd) ? upd : "";
  return (
    <PageShell>
      <header className={styles.noteHead}>
        <p className={styles.crumb}><Link href="/readings/books/"><Icon name="back" size={15} />完整研读书库</Link></p>
        <p className={styles.noteKicker}>研读笔记 · {note.category}</p>
        <h1>{note.title}</h1>
        <p className={styles.noteMeta}>
          {note.author && <span>{note.author}</span>}
          {note.year !== "" && <span>{note.year}</span>}
          <span>{note.chars.toLocaleString()} 字</span>
        </p>
        <p className={styles.noteNotice}>研读整理笔记，非原书全文，未逐页核对原书。内容为整理者归纳与批注，不代表原书目录；引文类段落因未经原文核验已从略。</p>
      </header>
      <div className={styles.noteLayout}>
        {toc.length > 1 && (
          <aside className={styles.toc} aria-label="本篇目录">
            <nav className={styles.tocSticky}>
              <p className={styles.tocTitle}>本篇目录</p>
              {toc.map((h: { id: string; title: string; level: number }) => (
                <a key={h.id} href={`#${h.id}`} className={h.level >= 3 ? styles.tocSub : styles.tocLink}>{h.title}</a>
              ))}
            </nav>
          </aside>
        )}
        <div className={styles.noteBody}>
          {toc.length > 1 && (
            <details className={styles.tocMobile}>
              <summary>本篇目录（{toc.length} 节）</summary>
              {toc.map((h: { id: string; title: string; level: number }) => <a key={h.id} href={`#${h.id}`}>{h.title}</a>)}
            </details>
          )}
          <ContentEngagement kind="book_note" resourceId={note.id} commentHref="#article-comments-title" />
          <ReadingActions kind="book_note" resourceId={note.id} />
          <BookNoteBody markdown={note.markdown} />
          <p className={styles.backlink}><Link href="/readings/books/">← 返回完整研读书库</Link></p>
          <ArticleComments anchor={`article:book_note:${note.id}`} date={commentDate} />
        </div>
      </div>
    </PageShell>
  );
}
