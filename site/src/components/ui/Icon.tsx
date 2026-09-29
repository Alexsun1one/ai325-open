import type { SVGProps } from "react";

// Shared 24-unit grid; uniform stroke weight keeps the set consistent at every size.
const paths = {
  discover: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm3.5 5.5-2.3 4.7-4.7 2.3 2.3-4.7 4.7-2.3Z",
  book: "M12 6C9 4 6 4 3 5v14c3-1 6-1 9 1 3-2 6-2 9-1V5c-3-1-6-1-9 1Zm0 0v14",
  chat: "M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-9l-5 3v-3a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Zm2 5h10M7 13h6",
  skill: "m7 6-5 6 5 6m10-12 5 6-5 6M14.5 4.5l-5 15",
  tools: "M18.6 3.4a5 5 0 0 0-7.1 7.1L4 18l2.2 2.2 7.3-7.7a5 5 0 0 0 7.1-7.1l-2.6 2.6-2-2 2.6-2.6Z",
  agent: "M12 3v3M6 6h12a3 3 0 0 1 3 3v9a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V9a3 3 0 0 1 3-3ZM8 10.5v3M16 10.5v3M8 16.5h8",
  archive: "M3 4h18v5H3V4Zm2 5v11h14V9M9 13h6",
  flag: "M5 21V3m0 1c5-3 9 3 14 0v10c-5 3-9-3-14 0",
  people: "M9 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM3.5 20v-.5a5.5 5.5 0 0 1 11 0v.5M16 4.5a3.75 3.75 0 0 1 0 7.5M17.5 15.2a5 5 0 0 1 3.5 4.8",
  quote: "M10 5H3v7h5c0 3-1 5-4 7m17-14h-7v7h5c0 3-1 5-4 7",
  method: "M3 5h4v4H3V5Zm0 10h4v4H3v-4Zm9-9h9m-9 3h6m-6 7h9m-9 3h6",
  principle: "m12 3 8 4v5c0 5-8 9-8 9s-8-4-8-9V7l8-4Zm-4 9 3 3 5-6",
  save: "M6 3h12v18l-6-4-6 4V3Z",
  check: "m4 12 5 5L20 6",
  download: "M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5",
  search: "M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14Zm5 12 6 6",
  arrow: "M4 12h16m-6-6 6 6-6 6",
  info: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM12 8v.01M12 11.5V17",
  spark: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z",
  contents: "M8 6h13M8 12h13M8 18h13M4 6h.01M4 12h.01M4 18h.01",
  external: "M14 3h7v7m0-7L10 14M10 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5",
  back: "M20 12H4m6-6-6 6 6 6",
};

export type IconName = keyof typeof paths;

export function Icon({ name, size = 20, ...props }: SVGProps<SVGSVGElement> & { name: IconName; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true" focusable="false" {...props}>
      <path d={paths[name]} />
    </svg>
  );
}
