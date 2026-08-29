/** 治理产物里的轻量富文本（仅 b/i/br/u），来源是我们自己的 JSON。 */
export function Rich({ html, className, as: Tag = "p" }: { html: string; className?: string; as?: "p" | "span" | "div" }) {
  return <Tag className={className} dangerouslySetInnerHTML={{ __html: html }} />;
}
