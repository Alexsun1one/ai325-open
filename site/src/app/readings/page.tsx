import Link from "next/link";
import type { Metadata } from "next";
import fs from "node:fs";
import path from "node:path";
import { Suspense } from "react";
import { PageShell } from "@/components/pages/PageHead";
import { Icon } from "@/components/ui/Icon";
import { readReadings } from "@/lib/reading-content";
import { readBookNoteIndex } from "@/lib/book-notes";
import type { ShelfCatalogue, ShelfEntry } from "@/lib/reading-shelf";
import { ReadingShelf } from "@/components/pages/ReadingShelf";
import styles from "./readings.module.css";

export const metadata: Metadata = {
  title: "书与代码精读",
  description: "把已经读过的书和开源仓库，整理成可理解、可验证、可实践的阅读专题。",
};

function readCatalogue(): ShelfCatalogue {
  const file = path.join(process.cwd(), "content/readings/catalogue.json");
  const data = JSON.parse(fs.readFileSync(file, "utf8")) as ShelfCatalogue;
  if (!Array.isArray(data.topics) || typeof data.assignments !== "object" || !data.assignments) {
    throw new Error("Invalid readings catalogue");
  }
  return data;
}

/** 静态导出下 useSearchParams 使书架为 CSR：fallback 输出真实目录链接，无 JS 也可读可达 */
function ShelfFallback({ entries }: { entries: ShelfEntry[] }) {
  const groups: { id: string; label: string; items: ShelfEntry[] }[] = [
    { id: "books", label: "书与长文", items: entries.filter((e) => e.kind === "book") },
    { id: "repositories", label: "仓库拆解", items: entries.filter((e) => e.kind === "repository") },
  ];
  return (
    <div className={styles.fallback}>
      {groups.map((g) => (
        <details key={g.id} id={g.id} open={g.id === "books"}>
          <summary>{g.label} <span>{g.items.length} 条</span></summary>
          <ol>
            {g.items.map((e) => (
              <li key={e.id}><Link href={`/readings/${e.id}/`}>{e.title}</Link></li>
            ))}
          </ol>
        </details>
      ))}
    </div>
  );
}

export default function ReadingsPage() {
  const entries = readReadings();
  const catalogue = readCatalogue();
  const bookTotal = readBookNoteIndex().total;
  // 只把书架需要的元数据传进客户端，绝不打包 sections/exercise 全文
  const shelf: ShelfEntry[] = entries.map((e) => ({
    id: e.id, kind: e.kind, title: e.title, subtitle: e.subtitle, summary: e.summary,
    tags: e.tags, sourceTitle: e.source.title, sourceUrl: e.source.url,
  }));
  return (
    <PageShell>
      <header className={styles.heading}>
        <p className={styles.kicker}><Icon name="book" size={18} />书与代码精读</p>
        <h1>读进去，<br />也带出来一点东西。</h1>
        <p className={styles.intro}>从一本书理解一种思考方式，从一个仓库拆解一种实现。拨动书架选一本，每篇都有阅读导引、核心观点和动手练习。</p>
        <nav className={styles.index} aria-label="精读分类">
          <a href="?kind=book#shelf">书与长文 <span>{entries.filter(e => e.kind === "book").length}</span></a>
          <a href="?kind=repository#shelf">仓库拆解 <span>{entries.filter(e => e.kind === "repository").length}</span></a>
          <Link href="/library/">群内原件档案 <Icon name="arrow" size={16} /></Link>
          <Link href="/readings/books/">完整研读书库 <span>{bookTotal}</span> <Icon name="arrow" size={16} /></Link>
        </nav>
      </header>
      <Suspense fallback={<ShelfFallback entries={shelf} />}>
        <ReadingShelf entries={shelf} catalogue={catalogue} />
      </Suspense>
      <p className={styles.notice}>这里是基于本地研读材料整理的编辑导读，不是原书或仓库全文。判断保留适用边界，来源链接可供核对。</p>
    </PageShell>
  );
}
