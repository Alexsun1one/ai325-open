"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { loadPeople, resolvePerson, type Person } from "@/lib/public-people";
import { IdentityAvatar } from "./IdentityAvatar";
import { isHermesIdentity } from "./agent-appearance";

/** Only public, unambiguous identities supply portraits and profile links. */
export function SpeakerIdentity({ name, kind = "human", master, size = 32, avatarKey }: {
  name: string;
  kind?: "human" | "agent";
  master?: string;
  size?: 32 | 36;
  avatarKey?: string;
}) {
  const [people, setPeople] = useState<Person[]>([]);
  useEffect(() => {
    if (kind !== "human") return;
    let active = true;
    void loadPeople().then((data) => {
      if (active && Array.isArray(data)) {
        setPeople(data.filter((person) => person && typeof person.name === "string" && typeof person.slug === "string"));
      }
    }).catch(() => { /* Directory failure must never hide a speaker. */ });
    return () => { active = false; };
  }, [kind]);

  const query = name.trim();
  const person = kind === "human" ? resolvePerson(people, query) : undefined;
  const label = person?.name || query || (kind === "agent" ? "学徒" : "群友");
  const hermes = isHermesIdentity(label, kind, avatarKey); // 仅视觉主题：非认证/权限/在线标记
  const className = "inline-flex min-w-0 max-w-full items-center gap-2 align-middle font-sans text-[13px] leading-snug";
  const content = <>
    <IdentityAvatar name={label} kind={kind} src={typeof person?.avatar === "string" ? person.avatar : undefined} size={size} variant={hermes ? "hermes" : undefined} avatarKey={avatarKey} />
    <span className="min-w-0 [overflow-wrap:anywhere]">
      <span className={`font-semibold ${kind === "agent" && !hermes ? "text-amber-text" : "text-blue-text"}`}>{label}</span>
      {kind === "agent" && <span className="ml-1.5 text-[11px] text-ink-3">{hermes ? "Agent" : "Agent · 学徒"}</span>}
      {kind === "agent" && master && <span className="block text-[11.5px] text-ink-3">师从 {master}</span>}
    </span>
  </>;
  return person?.slug ? <Link href={`/members/#p-${encodeURIComponent(person.slug)}`} aria-label={`查看 ${label} 的群像`} className={`${className} rounded-sm hover:underline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-blue-text`}>{content}</Link> : <span className={className}>{content}</span>;
}
