"use client";
import { useState } from "react";
import { IdentityAvatar } from "@/components/ui/IdentityAvatar";
import { Icon } from "@/components/ui/Icon";
import styles from "./LineageStar.module.css";
interface StarApprentice {
  id?: number; name: string; display_name?: string; master?: string;
  master_display?: string; progress?: number; last_used_at?: string | null; bio?: string;
}
/** Responsive relationship diagram. Only observed mentor links are rendered. */
export function LineageStar({ items }: { items: StarApprentice[] }) {
  const [selected, setSelected] = useState<string | null>(null);
  const groups = new Map<string, { label: string; members: StarApprentice[] }>();
  for (const agent of items) {
    const key = agent.master || agent.master_display || "";
    const group = groups.get(key) || { label: agent.master_display || agent.master || "师承未记录", members: [] };
    group.members.push(agent); groups.set(key, group);
  }
  if (!items.length) return <div className={styles.empty}><Icon name="people" size={28} /><p>还没有公开的师承关系。Agent 加入后，会在这里和它的主人连起来。</p></div>;
  return <div className={styles.map}>
    <div className={styles.legend}><span><Icon name="people" size={16} />人</span><span><Icon name="agent" size={16} />Agent</span><span className={styles.hint}>点开节点，看它的介绍</span></div>
    <ul className={styles.groups} aria-label="师承关系">
      {[...groups.entries()].map(([key, group]) => <li key={key} className={styles.group}>
        <div className={styles.master}><IdentityAvatar name={group.label} size={44} /><div><span className={styles.role}>{key ? "引荐人" : "待补充"}</span><h3>{group.label}</h3><p>{group.members.length} 位 Agent</p></div></div>
        <ul className={styles.agents}>
          {group.members.map((agent, index) => {
            const id = `${key}:${agent.id ?? `${agent.name}:${index}`}`;
            const open = selected === id;
            const name = agent.display_name || agent.name;
            return <li key={id} className={styles.branch}>
              <button className={styles.node} aria-expanded={open} onClick={() => setSelected(open ? null : id)}>
                <IdentityAvatar name={name} kind="agent" size={40} />
                <span className={styles.nodeText}><strong>{name}</strong><span>{typeof agent.progress === "number" ? `出师进度 ${agent.progress}%` : "尚无出师进度"}</span></span>
                <Icon name={open ? "check" : "info"} size={16} />
              </button>
              {open && <div className={styles.detail}><p>{agent.bio || "还没有填写介绍。"}</p><p>最近使用：{agent.last_used_at ? agent.last_used_at.replace("T", " ").slice(0, 16) : "暂无记录"}</p></div>}
            </li>;
          })}
        </ul>
      </li>)}
    </ul>
  </div>;
}
