import { readReadings } from "./reading-content";
import playground from "../../content/playground.json";
import journey from "../../content/journey/people-need-ai.json";
import { createHash } from "node:crypto";
import { readKnowledge } from "./knowledge-content";
import { readSkillLibrary } from "./skill-content";
import { readArsenal } from "@/components/pages/arsenaldata";
import { getLedger, listLedgerDates } from "./content";
import { readExternalDiscovery } from "./external-sources";
import type { DiscoveryData, DiscoveryItem } from "./discovery";
const plain = (value: string) => value.replace(/<[^>]*>/g," ").replace(/[\u0000-\u001f\u007f]/g," ").replace(/\s+/g," ").trim();
const date = (value: string) => { const match=value.match(/^\d{4}-\d{2}-\d{2}/)?.[0]; if(!match || !Number.isFinite(Date.parse(match))) throw new Error("Invalid discovery source date"); return match; };
const key = (kind:string,id:string) => `${kind}:${createHash("sha256").update(id).digest("hex").slice(0,24)}`;
export function readDiscovery(): DiscoveryData {
  const knowledge=readKnowledge(); const skills=readSkillLibrary(); const topics=new Map(knowledge.topics.map(t=>[t.id,t.title]));
  const items: DiscoveryItem[] = [
    {...playground,id:key("resource",`playground:${playground.id}`),kind:"resource" as const,date:date(playground.date)},
    {id:key("resource","journey:people-need-ai"),kind:"resource" as const,title:journey.title,summary:journey.subtitle+" 从实践、真实反馈与法器驾驭，谈普通人怎样和 AI 一起成长。",url:"/journey/",date:date(journey.date),tags:["主站长文","AI学习","实践","自我成长"],sourceUrl:"https://ai325.com/journey/article.md"},
    ...readReadings().map(e=>({id:key("resource",`reading:${e.id}`),kind:"resource" as const,title:e.title,summary:e.summary,url:`/readings/${e.id}/`,date:date(e.reviewedAt),tags:[e.kind==="book"?"书籍精读":"仓库拆解",...e.tags],sourceUrl:e.source.url,...(e.relatedTopic?{topicId:e.relatedTopic}:{})})),
    ...knowledge.entries.map(e=>({id:key("knowledge",e.id),kind:"knowledge" as const,title:e.title,summary:e.text,url:`/learn/entries/${e.id}/`,date:date(e.revisions.map(r=>r.date).sort().at(-1) ?? knowledge.updatedAt),tags:[topics.get(e.topicId) ?? "知识",e.kind==="method"?"实践方法":e.kind==="principle"?"暂定原则":"编辑金句"],topicId:e.topicId})),
    ...skills.items.map(e=>({id:key("skill",e.id),kind:"skill" as const,title:e.name,summary:e.description,url:`/skills/?q=${encodeURIComponent(e.name)}`,date:date(skills.generatedAt),tags:[e.category,e.author,...e.tags],...(e.sourceUrl?.startsWith("https://")?{sourceUrl:e.sourceUrl}:{})})),
    ...readArsenal().filter(e=>["shelved","featured"].includes(e.status)).map(e=>({id:key("resource",e.id),kind:"resource" as const,title:e.title,summary:e.one_line,url:`/arsenal/#kb-${encodeURIComponent(e.id)}`,date:date(e.collected_at),tags:[e.kind,...e.tags],...(e.source.url?.startsWith("https://")?{sourceUrl:e.source.url}:{})})),
    ...readExternalDiscovery(),
    ...listLedgerDates().map(d=>{const e=getLedger(d);return {id:key("ledger",d),kind:"ledger" as const,title:e.title,summary:e.lead,url:`/ledger/${d}/`,date:date(d),tags:["每日蒸馏"]};}),
  ].map(e=>({...e,title:plain(e.title).slice(0,240),summary:plain(e.summary).slice(0,2000),tags:[...new Set(e.tags.map(t=>plain(t).slice(0,80)).filter(Boolean))].slice(0,24)}));
  if(items.some(e=>!e.title||!e.summary) || new Set(items.map(e=>e.id)).size!==items.length) throw new Error("Incomplete discovery directory");
  items.sort((a,b)=>b.date.localeCompare(a.date)||a.id.localeCompare(b.id));
  return {schemaVersion:1,updatedAt:`${items.map(e=>e.date).sort().at(-1)}T00:00:00+08:00`,items};
}
