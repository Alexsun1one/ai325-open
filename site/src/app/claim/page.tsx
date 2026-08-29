import type { Metadata } from "next";
import ClaimView from "./ClaimView";

export const metadata: Metadata = {
  title: "认领你的账号",
  description: "孙哥发的认领链接：点开即进站。",
  robots: { index: false, follow: false },
};

export default function ClaimPage() {
  return <ClaimView />;
}
