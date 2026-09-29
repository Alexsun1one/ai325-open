import Link from "next/link";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PageShell } from "@/components/pages/PageHead";
import { Icon } from "@/components/ui/Icon";
import { readBookNoteIndex } from "@/lib/book-notes";
import styles from "../../books.module.css";

export const dynamicParams = false;
export function generateStaticParams() {
  return Object.keys(readBookNoteIndex().categories).map((cat) => ({ cat }));
}

/** 静态导出时 params.cat 是百分号编码段——统一解码一次再对类别真值；非法编码/未知类别 null。 */
function resolveCat(raw: string): string | null {
  let cat: string;
  try { cat = decodeURIComponent(raw); } catch { return null; }
  return Object.hasOwn(readBookNoteIndex().categories, cat) ? cat : null;
}

export async function generateMetadata({ params }: { params: Promise<{ cat: string }> }): Promise<Metadata> {
  const { cat } = await params;
  const resolved = resolveCat(cat);
  if (!resolved) notFound();
  return { title: `${resolved} · 完整研读书库` };
}

/** 无 JS 可达的分类全量列表页。 */
export default async function BookCategoryPage({ params }: { params: Promise<{ cat: string }> }) {
  const { cat } = await params;
  const resolved = resolveCat(cat);
  if (!resolved) notFound();
  const items = readBookNoteIndex().items.filter((i) => i.category === resolved);
  if (!items.length) notFound();
  return (
    <PageShell>
      <header className={styles.noteHead}>
        <p className={styles.crumb}><Link href="/readings/books/"><Icon name="back" size={15} />完整研读书库</Link></p>
        <h1>{resolved} <span className={styles.count}>{items.length} 本</span></h1>
        <p className={styles.intro}>研读整理笔记，非原书全文。</p>
      </header>
      <ol className={styles.catList}>
        {items.map((i) => (
          <li key={i.id}>
            <Link prefetch={false} href={`/readings/books/${i.id}/`}>{i.title}</Link>
            <span className={styles.fallMeta}> {i.author}{i.year !== "" ? ` · ${i.year}` : ""} · {Math.round(i.chars / 1000)}k字</span>
          </li>
        ))}
      </ol>
    </PageShell>
  );
}
