/** REPOSITORY-FINDER R1 · 按问题找已拆仓库与源码入口。
 *  纯函数、强类型、浏览器本地检索：问题同义词(透明概念词典)扩展 + 多字段加权召回。
 *  不是向量检索、不声称语义理解；分数只用于排序，不对外显示为置信度。 */

export interface CapabilityRef { label: string; path: string; url: string; note: string; verifiedAt: string; ref: string }
export interface CapabilityEntry {
  entryId: string; tasks: string[]; aliases: string[]; prerequisites: string[]; notFor: string;
  codeRefs: CapabilityRef[];
}
export interface IndexDoc {
  id: string; title: string; subtitle: string; summary: string; href: string;
  tags: string[]; takeaways: string[];
  sectionTitles: string[]; sectionExcerpts: string[];
  tasks: string[]; aliases: string[]; prerequisites: string[]; notFor: string;
  codeRefs: CapabilityRef[];
}
export interface SearchHit {
  doc: IndexDoc; score: number;
  matchedFields: string[];        // 命中字段名（标题/任务/别名/标签/简介/正文）
  matchedTerms: string[];         // 命中的查询词（供高亮，React 节点渲染）
  concepts: string[];             // 命中的概念（可解释，不是置信度）
  excerpt: string;                // 正文证据片段（命中时）
}

/* ---------- 规范化与分词 ---------- */

const CJK = /[一-鿿㐀-䶿]/;
const EN_TOKEN = /[a-z0-9][a-z0-9+#.+-]*/g;

/** 中英停用词：问句里的虚词/客套/泛指词。保持小而透明，可维护。 */
const STOP = new Set([
  "的", "了", "在", "是", "我", "你", "他", "她", "它", "们", "和", "与", "或", "及", "把", "被", "让", "给", "对", "向", "从", "到", "于", "就", "都", "也", "还", "又", "再", "呢", "吗", "啊", "吧", "嘛", "么", "之", "其", "这", "那", "有", "没", "不", "会", "能", "要", "想", "做", "用", "一个", "什么", "怎么", "如何", "怎样", "有没有", "可以", "一下", "一下下", "帮忙", "帮我", "我想", "请问", "实现", "东西", "功能", "程序", "工具", "项目", "仓库",
  "the", "a", "an", "to", "of", "in", "on", "for", "and", "or", "is", "are", "be", "i", "we", "my", "me", "how", "what", "can", "do", "does", "with", "want", "need", "make", "build", "use", "using", "get", "into", "from", "that", "this", "it", "as", "at", "by", "some", "any", "please", "help", "tool", "library", "project", "repo", "repository",
]);

export function normalizeText(s: string): string {
  // 统一小写，剥掉一切非字母数字（保留 . _ + # - 给 llama.cpp / c++ / faster-whisper 类名字）
  return s.toLowerCase().replace(/[^\p{L}\p{N}_.+#-]+/gu, " ").replace(/\s+/g, " ").trim();
}

/** 问句填充词：在分词前整词剥掉——否则「不知道」会碎成 不知/知道 命中正文。长的排前面防半截吞。 */
const FILLERS = [
  "不知道怎么", "不知道该", "不知道说", "不知道", "怎么说", "怎么想", "怎么做", "怎么办", "怎么样",
  "哪个", "哪些", "哪家", "有没有", "是不是", "能不能", "会不会", "要不要", "要不要用",
  "我想要", "我想", "我要", "我想问", "请问", "帮我", "帮忙", "推荐一下", "推荐",
  "的话", "感觉", "好像", "似乎", "可能", "应该", "比较", "有点", "那种", "这种", "一个", "一些", "某个",
].sort((a, b) => b.length - a.length);

function stripFillers(s: string): string {
  let out = s;
  for (const f of FILLERS) out = out.split(f).join(" ");
  return out;
}

const CJK_RUN = /[一-鿿㐀-䶿]+/g;

/** 分词：英文按整词 token，中文按连续 CJK 段做 2gram（≤8 字整段也留作候选）。中英混排先各自切开。 */
export function tokenize(input: string): string[] {
  const s = stripFillers(normalizeText(input));
  if (!s) return [];
  const out = new Set<string>();
  for (const m of s.matchAll(EN_TOKEN)) {
    const t = m[0];
    if (t.length > 1 && !STOP.has(t)) out.add(t);
  }
  const allStop = (w: string) => [...w].every((c) => STOP.has(c));
  for (const m of s.matchAll(CJK_RUN)) {
    const run = m[0];
    if (run.length === 1) { if (!STOP.has(run)) out.add(run); continue; }
    for (let i = 0; i < run.length - 1; i++) {
      const g = run.slice(i, i + 2);
      if (!allStop(g)) out.add(g);
    }
    if (run.length <= 8 && !allStop(run)) out.add(run);
  }
  return [...out];
}

/* ---------- 透明概念词典：输入命中概念词 → 扩展同义/相关说法 ---------- */
/** 只收录有真实对照材料的能力域；terms 里放中英常见叫法与典型项目名（仅作查询扩展，不加分）。 */
/** detect：判概念命中（含产品名——用户直接点名要认得）；expand：只放能力/同义说法，
 *  不放产品名——否则任意概念命中都给那些项目标题加分，排出不相关二三名。 */
export const CONCEPTS: Record<string, { detect: string[]; expand: string[] }> = {
  "PDF与文档解析": {
    detect: ["pdf", "文档解析", "表格提取", "扫描件", "扫描", "ocr", "docling", "unstructured", "版面", "解析文档", "文档转结构化", "pdf表格", "extract", "table", "tables", "parse", "document", "word", "excel", "图片文字", "图片转文字"],
    expand: ["pdf", "文档解析", "表格提取", "扫描件", "ocr", "版面", "解析文档", "文档转结构化", "extract", "parse", "图片文字"],
  },
  "语音转文字": {
    detect: ["语音转文字", "asr", "语音识别", "转写", "whisper", "faster-whisper", "会议录音", "录音转文字", "字幕", "speech", "transcribe", "transcription", "audio", "meeting", "语音", "录音"],
    expand: ["语音转文字", "asr", "语音识别", "转写", "录音转文字", "字幕", "speech", "transcribe", "transcription", "语音", "录音"],
  },
  "长任务断点续跑": {
    detect: ["断点", "续跑", "长任务", "暂停恢复", "checkpoint", "langgraph", "状态机", "工作流恢复", "中断", "恢复执行", "resume", "durable", "long-running", "继续跑", "断点续跑"],
    expand: ["断点", "续跑", "长任务", "暂停恢复", "checkpoint", "状态机", "工作流恢复", "中断", "恢复执行", "resume", "durable", "断点续跑"],
  },
  "知识检索RAG": {
    detect: ["rag", "知识检索", "检索", "知识库", "向量", "embedding", "召回", "ragflow", "llama-index", "llamaindex", "dify", "问答", "出处", "引用来源", "retrieval", "citation", "语义搜索"],
    expand: ["rag", "知识检索", "检索", "知识库", "向量", "embedding", "召回", "问答", "出处", "引用来源", "retrieval", "citation", "语义搜索"],
  },
  "评测与评估": {
    detect: ["评测", "评估", "eval", "benchmark", "评分", "dspy", "基准", "evaluate", "evaluation", "打分"],
    expand: ["评测", "评估", "eval", "benchmark", "评分", "基准", "evaluate", "evaluation", "打分"],
  },
  "可观测性追踪": {
    detect: ["可观测", "追踪", "trace", "tracing", "jaeger", "otel", "opentelemetry", "慢调用", "链路", "监控", "latency", "spans", "slow", "很慢", "耗时", "卡顿", "性能", "延迟", "哪个环节", "环节慢", "瓶颈"],
    expand: ["可观测", "追踪", "trace", "tracing", "慢调用", "链路", "监控", "latency", "耗时", "性能", "延迟", "瓶颈"],
  },
  "可视化与动画": {
    detect: ["可视化", "图表", "动画", "演示", "manim", "manimgl", "mermaid", "recharts", "绘图", "图形", "chart", "animation", "diagram", "流程图"],
    expand: ["可视化", "图表", "动画", "演示", "绘图", "图形", "chart", "animation", "diagram", "流程图"],
  },
  "包管理与环境": {
    detect: ["包管理", "依赖", "uv", "pip", "环境", "venv", "装包", "python环境", "poetry", "python", "dependency", "dependencies", "ruff", "lint"],
    expand: ["包管理", "依赖", "pip", "环境", "venv", "装包", "python环境", "python", "dependency", "dependencies", "lint"],
  },
  "本地推理": {
    detect: ["本地推理", "本地跑", "本地模型", "离线", "ollama", "llama.cpp", "llamacpp", "vllm", "本地大模型", "不联网", "offline", "on-device", "local-llm", "内网"],
    expand: ["本地推理", "本地跑", "本地模型", "离线", "本地大模型", "不联网", "offline", "on-device", "内网"],
  },
  "Agent协作与编码": {
    detect: ["agent", "智能体", "协作", "mcp", "codex", "openhands", "编码", "写代码", "结对", "工具调用", "tool-call", "助手"],
    expand: ["agent", "智能体", "协作", "编码", "写代码", "结对", "工具调用", "tool-call", "助手"],
  },
  "浏览器自动化": {
    detect: ["浏览器", "自动化测试", "e2e", "playwright", "crawl4ai", "点击", "截图", "爬", "爬虫", "网页自动化", "ui测试", "browser", "scrape", "抓取"],
    expand: ["浏览器", "自动化测试", "e2e", "点击", "截图", "爬虫", "网页自动化", "ui测试", "browser", "scrape", "抓取"],
  },
  "流程自动化": {
    detect: ["流程自动化", "n8n", "定时任务", "自动化流程", "连接服务", "编排", "集成", "automation", "integrate", "自动化"],
    expand: ["流程自动化", "定时任务", "自动化流程", "连接服务", "编排", "集成", "automation", "integrate", "自动化"],
  },
};

/** 概念命中判定：只看原始 query/base——扩展词不回流触发新概念（防级联漂移）。
 *  中文词子串命中即可；英文词必须是整词 token（防 uv⊂luv 类误命中）。 */
export function expandQuery(terms: string[], rawQuery: string): { terms: string[]; concepts: string[] } {
  const concepts: string[] = [];
  const expanded = new Set(terms);
  const base = new Set(terms);
  const raw = normalizeText(rawQuery);
  const rawTokens = new Set(raw.match(EN_TOKEN) ?? []);
  for (const [name, def] of Object.entries(CONCEPTS)) {
    const hit = def.detect.some((w) => {
      const t = normalizeText(w);
      if (!t) return false;
      return base.has(t) || (CJK.test(t) ? raw.includes(t) : rawTokens.has(t));
    });
    if (hit) {
      concepts.push(name);
      for (const w of def.expand) {
        const t = normalizeText(w);
        if (t && !STOP.has(t)) expanded.add(t);
      }
    }
  }
  return { terms: [...expanded], concepts };
}

/* ---------- 建索引文档 ---------- */
export interface ReadingLike {
  id: string; kind: string; title: string; subtitle: string; summary: string;
  source: { title: string; url: string }; tags: string[]; takeaways: string[];
  sections: { title: string; body: string }[];
}

export function buildIndexDocs(
  readings: ReadingLike[],
  capabilities: CapabilityEntry[] = [],
): IndexDoc[] {
  const capById = new Map(capabilities.map((c) => [c.entryId, c]));
  return readings
    .filter((e) => e.kind === "repository")
    .map((e) => {
      const cap = capById.get(e.id);
      return {
        id: e.id,
        title: e.title,
        subtitle: e.subtitle,
        summary: e.summary,
        href: `/readings/${e.id}/`,
        tags: e.tags ?? [],
        takeaways: e.takeaways ?? [],
        sectionTitles: (e.sections ?? []).map((s) => s.title),
        sectionExcerpts: (e.sections ?? []).map((s) => s.body.slice(0, 500)),
        tasks: cap?.tasks ?? [],
        aliases: cap?.aliases ?? [],
        prerequisites: cap?.prerequisites ?? [],
        notFor: cap?.notFor ?? "",
        codeRefs: cap?.codeRefs ?? [],
      };
    });
}

/* ---------- 检索 ---------- */

interface FieldDoc { tokens: Set<string>; raw: string }
interface DocTerms { title: FieldDoc; task: FieldDoc; alias: FieldDoc; tag: FieldDoc; summary: FieldDoc; body: FieldDoc }

function fieldOf(texts: string[]): FieldDoc {
  return { tokens: new Set(texts.flatMap(tokenize)), raw: texts.map(normalizeText).join(" ") };
}

function docTerms(doc: IndexDoc): DocTerms {
  return {
    title: fieldOf([doc.title, doc.subtitle]),
    task: fieldOf(doc.tasks),
    alias: fieldOf(doc.aliases),
    tag: fieldOf(doc.tags),
    summary: fieldOf([doc.summary]),
    body: fieldOf(doc.sectionTitles.concat(doc.sectionExcerpts)),
  };
}

/** 字段命中：token 集合相等；中文词（≥2字）退化为规范化原文子串命中；英文词只认整词。 */
function fieldHit(f: FieldDoc, term: string): boolean {
  if (f.tokens.has(term)) return true;
  return CJK.test(term) && term.length >= 2 && f.raw.includes(term);
}

const FIELD_WEIGHT: Record<keyof DocTerms, number> = { title: 6, task: 8, alias: 8, tag: 5, summary: 3, body: 1 };
const FIELD_LABEL: Record<keyof DocTerms, string> = { title: "标题", task: "可做的事", alias: "常见叫法", tag: "标签", summary: "简介", body: "正文" };

/** 文档分词缓存：索引对象在整个会话内稳定，按对象缓存，不每次查询重切。 */
const dtCache = new WeakMap<IndexDoc, DocTerms>();
function getDocTerms(doc: IndexDoc): DocTerms {
  const hit = dtCache.get(doc);
  if (hit) return hit;
  const d = docTerms(doc);
  dtCache.set(doc, d);
  return d;
}

function findExcerpt(doc: IndexDoc, terms: Set<string>): string {
  for (const s of doc.sectionExcerpts) {
    const toks = tokenize(s);
    if (toks.some((t) => terms.has(t))) {
      // 找到第一个命中词位置取前后片段
      const norm = normalizeText(s);
      let pos = norm.length;
      for (const t of terms) { const i = norm.indexOf(t); if (i >= 0 && i < pos) pos = i; }
      const start = Math.max(0, pos - 30);
      return (start > 0 ? "…" : "") + s.slice(start, start + 120) + (start + 120 < s.length ? "…" : "");
    }
  }
  return "";
}

/** 检索：返回按分数排序的结果；分数只作排序。空/纯停用词/过短查询返回 []，不兜底返前几条。 */
export function search(docs: IndexDoc[], query: string, limit = 20): SearchHit[] {
  const base = tokenize(query);
  if (!base.length) return [];
  const { terms, concepts } = expandQuery(base, query);
  const termSet = new Set(terms);
  const out: SearchHit[] = [];

  for (const doc of docs) {
    const dt = getDocTerms(doc);
    const matchedFields: string[] = [];
    const matchedTerms = new Set<string>();
    let score = 0;
    let highFieldHits = 0;
    for (const [field, weight] of Object.entries(FIELD_WEIGHT) as [keyof DocTerms, number][]) {
      const hits = dt[field].tokens.size ? [...termSet].filter((t) => fieldHit(dt[field], t)) : [];
      if (hits.length) {
        matchedFields.push(FIELD_LABEL[field]);
        hits.forEach((h) => matchedTerms.add(h));
        score += weight * Math.min(hits.length, 3);
        if (field === "title" || field === "task" || field === "alias") highFieldHits += hits.length;
      }
    }
    // 门槛：高信号字段（标题/任务/别名）至少命中一次；或标签+简介同时命中（非仅正文单词相同）
    const tagSummaryHits = matchedFields.includes("标签") && matchedFields.includes("简介");
    if (highFieldHits === 0 && !tagSummaryHits) continue;
    const excerpt = findExcerpt(doc, termSet);
    out.push({ doc, score, matchedFields, matchedTerms: [...matchedTerms], concepts, excerpt });
  }
  out.sort((a, b) => b.score - a.score || a.doc.id.localeCompare(b.doc.id));
  return out.slice(0, Math.max(1, Math.min(limit, 50)));
}
