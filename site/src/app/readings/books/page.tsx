import Link from "next/link";
import type { Metadata } from "next";
import { Suspense } from "react";
import { PageShell } from "@/components/pages/PageHead";
import { Icon } from "@/components/ui/Icon";
import { BookLibrary } from "@/components/pages/BookLibrary";
import { readBookNoteIndex } from "@/lib/book-notes";
import styles from "./books.module.css";

export const metadata: Metadata = {
  title: "完整研读书库",
  description: "本地研读笔记全量书库：按分类浏览、按书名作者搜索。研读整理非原书全文。",
};

/** 无 JS 兜底：分类入口 + 少量真实条目链接。 */
function LibraryFallback({ byCat }: { byCat: [string, CatItem[]][] }) {
  return (
    <div className={styles.fallback}>
      <nav className={styles.fallCats} aria-label="按分类浏览">
        {byCat.map(([cat, items]) => (
          <Link key={cat} href={`/readings/books/c/${encodeURIComponent(cat)}/`}>{cat} <span>{items.length}</span></Link>
        ))}
      </nav>
      <ol className={styles.catList}>
        {byCat.flatMap(([, items]) => items).slice(0, 24).map((i) => (
          <li key={i.id}>
            <Link prefetch={false} href={`/readings/books/${i.id}/`}>{i.title}</Link>
            <span className={styles.fallMeta}> {i.author}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

type CatItem = { id: string; title: string; author: string };

export default function BooksPage() {
  const index = readBookNoteIndex();
  const byCat: [string, CatItem[]][] = Object.keys(index.categories).map((cat) => [
    cat,
    index.items.filter((i) => i.category === cat).map((i) => ({ id: i.id, title: i.title, author: i.author })),
  ]);
  return (
    <PageShell>
      <header className={styles.head}>
        <p className={styles.kicker}><Icon name="book" size={18} />完整研读书库</p>
        <h1>研读笔记全库 <span className={styles.count}>{index.total} 本</span></h1>
        <p className={styles.intro}>本地研读材料逐本整理成笔记：可分类浏览、可搜书名作者。研读整理非原书全文，未逐页核对原书；与上方的编辑导读是两个层次。</p>
      </header>
      <Suspense fallback={<LibraryFallback byCat={byCat} />}>
        <BookLibrary fallback={<LibraryFallback byCat={byCat} />} />
      </Suspense>
      <p className={styles.notice}>大部头建议先看目录跳读；每篇开头有「适用边界」类段落时先读它，判断这本书的讲法适不适合你手上的问题。</p>
    </PageShell>
  );
}
