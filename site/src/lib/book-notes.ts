import fs from "node:fs";
import path from "node:path";

export interface BookNoteIndexEntry {
  id: string; title: string; author: string; category: string;
  tags: string[]; chars: number; updated: string; year: string | number;
}
interface BookNoteIndex { generated: string; total: number; categories: Record<string, number>; items: BookNoteIndexEntry[] }

const DIR = () => path.join(process.cwd(), "content/book-notes");

let cache: BookNoteIndex | null = null;
export function readBookNoteIndex(): BookNoteIndex {
  if (!cache) {
    const file = path.join(DIR(), "index.json");
    const data = JSON.parse(fs.readFileSync(file, "utf8")) as BookNoteIndex;
    if (!Array.isArray(data.items)) throw new Error("Invalid book-notes index");
    cache = data;
  }
  return cache;
}

export interface BookNote extends BookNoteIndexEntry { markdown: string }

/** 服务端按条目读单篇正文——绝不把全部正文打包进目录或客户端。 */
export function readBookNote(id: string): BookNote | null {
  const entry = readBookNoteIndex().items.find((i) => i.id === id);
  if (!entry) return null;
  const file = path.join(DIR(), `${id}.md`);
  if (!fs.existsSync(file)) return null;
  const raw = fs.readFileSync(file, "utf8");
  const m = /^---[ \t]*\n[\s\S]*?\n---[ \t]*\n?/.exec(raw);
  const markdown = m ? raw.slice(m[0].length).trim() : raw;
  return { ...entry, markdown };
}
