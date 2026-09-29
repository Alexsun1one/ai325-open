"use client";
import { IdentityAvatar } from "./IdentityAvatar";
import { AGENT_AVATARS, AGENT_AVATAR_KEYS, type AgentAvatarKey } from "./agent-avatars";
import { isHermesIdentity } from "./agent-appearance";
import styles from "./AgentAvatarPicker.module.css";

/** Agent 头像选择：自动（按名字种子/Hermes 变体）+ 8 款自绘符号。
 *  预览用 IdentityAvatar 真渲染，所见即所得；只产出 avatar_key，不代表权限。 */
export function AgentAvatarPicker({ name, value, disabled, onSelect }: {
  name: string;
  value: string;
  disabled?: boolean;
  onSelect: (key: AgentAvatarKey | "") => void;
}) {
  const auto = (
    <IdentityAvatar name={name} kind="agent" size={30} variant={isHermesIdentity(name, "agent") ? "hermes" : undefined} />
  );
  return (
    <div className={styles.picker} role="group" aria-label="选择头像">
      <button type="button" className={`${styles.opt} ${!value ? styles.on : ""}`} aria-pressed={!value}
        disabled={disabled} onClick={() => onSelect("")}>
        {auto}<span>自动</span>
      </button>
      {AGENT_AVATAR_KEYS.map((key) => (
        <button key={key} type="button" className={`${styles.opt} ${value === key ? styles.on : ""}`} aria-pressed={value === key}
          disabled={disabled} onClick={() => onSelect(key)}>
          <IdentityAvatar name={name} kind="agent" size={30} avatarKey={key} /><span>{AGENT_AVATARS[key].label}</span>
        </button>
      ))}
    </div>
  );
}
