import { Fragment } from "react";
import { segment, type SegmentOptions } from "./segment";

interface ProseProps extends SegmentOptions {
  html: string;
  className?: string;
  /** 每隔几段给一次呼吸（一条极轻的格线）。0 = 不给。长文（小作文）才需要。 */
  breathe?: number;
  as?: "div" | "blockquote";
  /** 首段首字下沉两行（印刷开篇记号）。只给每幕重织正文这类「开篇」。 */
  dropcap?: boolean;
}

/**
 * 长文正文：按句读把「一整坨」切成段落再渲染。只影响显示，数据一个字没动。
 * 段间距交给 `.prose-sheet p + p`（globals.css），这里不重复定义。
 */
export function Prose({ html, className = "", breathe = 0, as = "div", dropcap = false, min, per }: ProseProps) {
  const paras = segment(html, { min, per });
  if (!paras.length) return null;
  const Tag = as;
  // 段首是标签（人名/加粗等标记，别拆开）或标点（「 等会跟着一起下沉）时不下沉
  const canDrop = dropcap && /^[\p{Script=Han}A-Za-z0-9]/u.test(paras[0].trimStart());
  return (
    <Tag className={`prose-sheet ${canDrop ? "prose-drop" : ""} ${className}`}>
      {paras.map((p, i) => (
        <Fragment key={i}>
          {breathe > 0 && i > 0 && i % breathe === 0 && (
            <span aria-hidden className="my-9 block h-px w-16 bg-rule" />
          )}
          <p dangerouslySetInnerHTML={{ __html: p }} />
        </Fragment>
      ))}
    </Tag>
  );
}
