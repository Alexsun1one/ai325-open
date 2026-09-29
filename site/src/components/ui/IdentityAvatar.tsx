"use client";
import { useState } from "react";
import styles from "./AgentIdentity.module.css";
import { AGENT_AVATARS, isAgentAvatarKey } from "./agent-avatars";

function AgentMark({ mark, size }: { mark: keyof typeof AGENT_AVATARS; size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round">
      {AGENT_AVATARS[mark].nodes.map((node, i) => <path key={i} d={node.d} strokeWidth={node.w ?? 1.8} />)}
    </svg>
  );
}

/** Human initials and deterministic Agent geometry; never synthetic human portraits. */
export function IdentityAvatar({ name, kind = "human", src, size = 40, variant, avatarKey }: { name: string; kind?: "human" | "agent"; src?: string; size?: number; variant?: "hermes"; avatarKey?: string }) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const initial = Array.from(name.trim())[0] || "?";
  const seed = Array.from(name).reduce((n, ch) => ((n * 31 + (ch.codePointAt(0) || 0)) >>> 0), 7);
  if (src && failedSrc !== src) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={src} alt="" width={size} height={size} loading="lazy" onError={() => setFailedSrc(src)} className="identity-avatar" style={{ width: size, height: size }} />;
  }
  // Agent：显式有效 avatar_key 优先；空值保留 Hermes 变体/种子默认行为。
  const picked = kind === "agent" && isAgentAvatarKey(avatarKey) ? avatarKey : undefined;
  const mark = picked ?? (variant === "hermes" && kind === "agent" ? "hermes" : undefined);
  if (mark) {
    return <span className={`identity-avatar identity-agent ${mark === "hermes" ? `identity-hermes ${styles.hermes}` : ""}`} style={{ width:size, height:size }} aria-hidden="true">
      <AgentMark mark={mark} size={size} />
    </span>;
  }
  return <span className={`identity-avatar identity-${kind}`} style={{ width:size, height:size }} aria-hidden="true">
    {kind === "agent" ? <svg width={size} height={size} viewBox="0 0 40 40" fill="none">
      <path d="M20 6v5M16 6h8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <rect x="8" y="12" width="24" height="21" rx={seed % 2 ? 6 : 3} stroke="currentColor" strokeWidth="1.6" />
      <path d={seed % 3 === 0 ? "M13 21h4m6 0h4M15 28h10" : "M14 19v4m12-4v4M16 28h8"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d={seed % 2 ? "M4 19v7m32-7v7" : "M11 35h18"} stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg> : <span style={{fontSize:size*.42}}>{initial}</span>}
  </span>;
}
