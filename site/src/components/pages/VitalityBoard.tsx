"use client";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, useAuth } from "@/lib/auth";
import { IdentityAvatar } from "@/components/ui/IdentityAvatar";
import { loadPeople, type Person } from "@/components/sheet/PersonHover";
import styles from "./VitalityBoard.module.css";

interface BoardItem { name: string; rank: number; band: string; gain7: number }
interface Board { scope: string; scope_label: string; month: string; last_month_top?: string | null; month_progress?: number; month_my?: number | null; items: BoardItem[]; count: number; my_rank?: number | null; my_gap?: number | null }
const bands: Record<string, string> = { 掌酒师: "text-cinnabar-text", 资深品鉴师: "text-amber-text", 品鉴师: "text-blue-text", 见习: "text-ink-3" };

export function VitalityBoard({ compact = false }: { compact?: boolean }) {
  const { status, user } = useAuth(); const [board, setBoard] = useState<Board | null>(null); const [people, setPeople] = useState<Person[]>([]); const [error, setError] = useState(""); const [loading, setLoading] = useState(true);
  const load = useCallback(async () => { setLoading(true); const [next, faces] = await Promise.allSettled([apiFetch<Board>("/api/vitality/leaderboard"), loadPeople()]); if (faces.status === "fulfilled") setPeople(faces.value); else setPeople([]); if (next.status === "fulfilled") { setBoard(next.value); setError(""); } else setError("榜单暂时没能读取"); setLoading(false); }, []);
  useEffect(() => { if (status === "loading") return; const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load, status]);
  const index = useMemo(() => new Map<string, Person>(people.flatMap(p => [[p.name, p] as const, ...p.aliases.map(alias => [alias, p] as const)])), [people]);
  const me = user?.display_name || user?.username || "";
  if (loading && !board) return <div className={styles.state}>正在核对酒力榜……</div>;
  if (error && !board) return <div className={styles.state}>{error}<button type="button" onClick={() => void load()}>重试</button></div>;
  if (!board) return null;
  const shown = compact ? board.items.slice(0, 6) : board.items;
  return <section className={`${styles.board} ${compact ? styles.compact : ""}`} aria-label="酒力排行榜">
    <header className={styles.head}><div><p className={styles.kicker}>{board.scope === "all" ? "全期参与榜" : "近 30 天参与榜"}</p><h2>{compact ? "酒力榜" : "谁正在把讨论做下去"}</h2><p>{board.scope_label}，共 {board.count} 位参与者{board.count > shown.length ? `，展示前 ${shown.length} 位` : ""}。近 7 天增量不等于总分。</p></div>{!compact && <button type="button" className={styles.reload} onClick={() => void load()} disabled={loading}>{loading ? "刷新中" : "刷新"}</button>}</header>
    {error && <p className={styles.notice}>{error}，显示上次结果。<button type="button" onClick={() => void load()}>重试</button></p>}
    {!shown.length ? <div className={styles.state}>当前还没有可上榜的参与记录。</div> : <ol className={styles.rows}>{shown.map(item => { const person = index.get(item.name); const mine = !!me && item.name === me; const top = item.rank <= 3; const gain = item.gain7 > 0 ? `+${item.gain7}` : item.gain7 === 0 ? "持平" : `${item.gain7}`; const content = <><span className={`${styles.rank} ${item.rank === 1 ? styles.first : ""}`}>{item.rank}</span><IdentityAvatar name={item.name} src={person?.avatar || undefined} size={top ? 42 : 36} /><span className={styles.person}><strong>{item.name}{mine && <em>你</em>}</strong><small className={bands[item.band] || "text-ink-3"}>{item.band}</small></span><span className={`${styles.gain} ${item.gain7 > 0 ? styles.up : item.gain7 < 0 ? styles.down : ""}`}>{gain}<small>近7日</small></span></>; return <li key={item.rank} className={`${top ? styles.top : ""} ${mine ? styles.mine : ""}`}>{person ? <Link href={`/members/#p-${person.slug}`} aria-label={`查看 ${item.name} 的群像`}>{content}</Link> : <div>{content}</div>}</li>; })}</ol>}
    {status === "in" && board.my_rank && board.my_rank > board.items.length && <p className={styles.mineNote}>你当前第 {board.my_rank}，距离前十还差 {board.my_gap ?? "…"} 酒力。</p>}
    {!compact && <footer>{board.last_month_top ? <>上月榜首是 {board.last_month_top}。 </> : ""}本月已有 {board.month_progress ?? 0} 人参与。</footer>}
  </section>;
}
