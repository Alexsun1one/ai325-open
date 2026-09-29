"use client";
import { Icon, type IconName } from "@/components/ui/Icon";
import Link from "next/link";
import type { ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import { DISCOVERY_KINDS, type DiscoveryData, type DiscoveryKind } from "@/lib/discovery";
function EntryLink({ href, children }: { href: string; children: ReactNode }) {
  return href.endsWith(".html") ? <a href={href} className="block">{children}</a> : <Link href={href} className="block">{children}</Link>;
}
const kindIcons: Record<string,IconName> = {knowledge:"book",skill:"skill",resource:"tools",ledger:"archive"};
const control="inline-flex items-center justify-center gap-2 min-h-11 rounded-md border border-rule bg-paper px-3 text-[14px] text-ink focus-visible:outline-2 focus-visible:outline-blue";
export function DiscoveryHome({ data }: { data: DiscoveryData }) {
  const params=useSearchParams(); const q=params.get("q")??""; const kind=params.get("kind")??""; const sort=params.get("sort")??"latest";
  const terms=q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const score=(item:DiscoveryData["items"][number])=>terms.reduce((sum,t)=>sum+(item.title.toLowerCase().includes(t)?3:item.tags.some(v=>v.toLowerCase().includes(t))?2:1),0);
  const matches=data.items.filter(e=>(!kind||e.kind===kind)&&terms.every(t=>`${e.title} ${e.summary} ${e.tags.join(" ")}`.toLowerCase().includes(t))).sort((a,b)=>(sort==="relevance"&&terms.length?score(b)-score(a):0)||b.date.localeCompare(a.date)||a.id.localeCompare(b.id));
  const pages=Math.max(1,Math.ceil(matches.length/20)); const parsed=Number(params.get("page")??1); const page=Number.isSafeInteger(parsed)?Math.max(1,Math.min(pages,parsed)):1;const start=(page-1)*20;
  const update=(values:Record<string,string>)=>{const next=new URLSearchParams(params.toString());for(const [k,v] of Object.entries(values)){if(v)next.set(k,v);else next.delete(k);} const query=next.toString();window.history.replaceState(null,"",query?`/?${query}`:"/");};
  return <section aria-label="公开内容发现">
    <div className="flex flex-wrap gap-2 border-y border-rule py-3"><button onClick={()=>update({kind:"",page:""})} aria-pressed={!kind} className={`${control} ${!kind?"border-blue bg-blue-wash text-blue-text":""}`}><Icon name="discover" size={16} />全部 {data.items.length}</button>{Object.entries(DISCOVERY_KINDS).map(([id,label])=><button key={id} onClick={()=>update({kind:id,page:""})} aria-pressed={kind===id} className={`${control} ${kind===id?"border-blue bg-blue-wash text-blue-text":""}`}><Icon name={kindIcons[id]} size={16} />{label} {data.items.filter(e=>e.kind===id).length}</button>)}</div>
    <div className="mt-5 grid gap-3 sm:grid-cols-[minmax(0,1fr)_140px]"><label className="grid gap-2 text-[13px] text-ink-2">找一个问题、一项技能或一个工具<input type="search" className={control} value={q} maxLength={200} onChange={e=>update({q:e.target.value,page:""})} placeholder="搜索知识、技能、资源和日报" /></label><label className="grid gap-2 text-[13px] text-ink-2">排列方式<select className={control} value={sort} onChange={e=>update({sort:e.target.value,page:""})}><option value="latest">最近更新</option><option value="relevance">关键词相关</option></select></label></div>
    <p role="status" className="my-4 text-[13px] text-ink-3">找到 {matches.length} 条{matches.length>0?` · 显示 ${start+1}–${Math.min(start+20,matches.length)}`:""}</p>
    {!matches.length&&<div className="border-y border-rule py-10"><p>还没有匹配的公开内容，换个关键词或分类试试。</p><button className="mt-4 min-h-11 text-blue-text" onClick={()=>update({q:"",kind:"",page:""})}>清除筛选</button></div>}
    <ul className="divide-y divide-rule border-y border-rule">{matches.slice(start,start+20).map(item=><li key={item.id} className="py-5"><div className="mb-2 flex flex-wrap gap-3 text-[12px] text-ink-3"><span className="inline-flex items-center gap-1.5 text-blue-text"><Icon name={kindIcons[item.kind]} size={15}/>{DISCOVERY_KINDS[item.kind as DiscoveryKind]}</span><time className="num">{item.date}</time></div><EntryLink href={item.url}><h2 className="font-serif text-[20px] font-bold leading-snug text-ink hover:text-blue-text">{item.title}</h2><p className="mt-3 line-clamp-2 text-[16px] leading-relaxed text-ink-2">{item.summary}</p></EntryLink><div className="mt-3 flex flex-wrap gap-3 text-[12px] text-ink-3">{item.tags.slice(0,4).map(tag=><span key={tag}>{tag}</span>)}</div></li>)}</ul>
    {matches.length>0&&<nav aria-label="发现分页" className="my-6 flex items-center gap-4"><button className={`${control} disabled:opacity-40`} disabled={page<=1} onClick={()=>update({page:String(page-1)})}>上一页</button><span className="num text-[13px]">{page} / {pages}</span><button className={`${control} disabled:opacity-40`} disabled={page>=pages} onClick={()=>update({page:String(page+1)})}>下一页</button></nav>}
  </section>;
}
