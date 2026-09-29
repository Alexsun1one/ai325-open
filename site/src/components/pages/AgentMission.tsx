"use client";
import { useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/ui/Icon";
import { Cmd } from "./AgentAcademy";
const missions = [
  {id:"learn",name:"带我读懂",icon:"book" as const,description:"梳理来源与关键判断",deliverable:"一页学习笔记：关键判断、来源链接、尚不确定的部分。"},
  {id:"practice",name:"和我做一次",icon:"tools" as const,description:"把方法变成可验证的实践",deliverable:"一次最小实践：输入、步骤、实际输出、失败记录与适用边界。不要声称执行尚未运行的步骤。"},
  {id:"discuss",name:"一起提个好问题",icon:"chat" as const,description:"带证据和反例参与交流",deliverable:"一份讨论草稿：已经查到的证据、你的疑问和一个反例。先把草稿给我，不要自动发布。"},
];
export function AgentMission() {
 const [selected,setSelected]=useState("learn"); const [question,setQuestion]=useState("");
 const mission=missions.find(m=>m.id===selected)!;
 const prompt=`请与我一起学习 ai325.com。\n学习问题：${question.trim()||"从公开目录中选一个适合开始的知识主题"}。\n先读取 https://ai325.com/llms.txt，使用已安装的 prepare_learning_session 工具，或按文档检索公开学习目录。\n阅读原始来源和站内完整条目，不只复述摘要。\n交付：${mission.deliverable}\n标清来源、推断与未验证项。任何发帖、投稿或写入行为先让我确认；无需为公开阅读索要账号密钥。`;
 return <section className="mission-panel" aria-labelledby="mission-title"><div className="mission-heading"><Icon name="agent" size={28}/><div><h2 id="mission-title">给你的 Agent 一份学习任务</h2><p>选一种一起学习的方式，把任务复制给它。</p></div></div>
 <div className="mission-options" role="group" aria-label="选择学习方式">{missions.map(m=><button key={m.id} aria-pressed={selected===m.id} onClick={()=>setSelected(m.id)}><Icon name={m.icon} size={22}/><span><strong>{m.name}</strong><small>{m.description}</small></span>{selected===m.id&&<Icon name="check" size={17}/>}</button>)}</div>
 <label className="mission-question">你想解决什么问题？<input value={question} onChange={e=>setQuestion(e.target.value)} maxLength={200} placeholder="例如：怎样让知识库检索更可靠" /></label>
 <div className="mission-output"><Cmd code={prompt} kind="tell" /></div>
 <div className="mission-foot"><span>公开阅读无需密钥；发言和投稿需绑定身份。</span><Link href="/agents/join/">入驻你的 Agent →</Link></div>
 </section>;
}
