"use client";
import { useEffect, useState } from "react";
import { AvatarRow, type Face } from "@/components/pages/AvatarRow";
import { loadPeople, type Person } from "./PersonHover";

/** 成员高光上方的头像行：按本期高光顺序叠排，悬停出名牌（Aceternity animated-tooltip 的品鉴单皮，见 pages/AvatarRow）。 */
export function FocusFaces({ names }: { names: string[] }) {
  const [faces, setFaces] = useState<Face[]>([]);
  useEffect(() => {
    loadPeople().then((ps: Person[]) => {
      const fs: Face[] = [];
      for (const n of names) { const p = ps.find((x) => x.name === n || x.aliases.includes(n)); fs.push({ name: p?.name ?? n, role: p?.role ?? "", avatar: p?.avatar ?? undefined }); }
      setFaces(fs);
    });
  }, [names]);
  if (!faces.length) return <div className="mb-6 h-10" aria-hidden />;
  return (
    <div className="mb-6 flex flex-wrap items-center gap-x-5 gap-y-3">
      <AvatarRow faces={faces} />
      <span className="font-sans text-[12.5px] text-ink-3">本期 <span className="num text-ink-2">{faces.length}</span> 位 · 悬停看名牌，点名字看名片</span>
    </div>
  );
}
