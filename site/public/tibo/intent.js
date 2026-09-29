"use strict";
(() => {
  // Intent analysis section — reads snapshot.intent_analysis pushed via the
  // aitibo:observations event (fired by live.js at the top of every render,
  // including language switches). UI strings only; all claims come from data.
  const copy = {
    "zh-CN": {
      title: "他在盘算什么？", note: "机器解读 · 公开帖子", tag: "机器解读",
      pending: "正在解读他的公开帖子…", expired: "解读已过期，等下一次采集", error: "解读暂不可用",
      outlook: { reset_reported: "他声称已重置", reset_signals: "出现重置信号", product_teasing: "更像产品预热", no_reset_signal: "暂无重置信号", unclear: "意图不明" },
      confidence: "解读置信度", levels: { low: "低", medium: "中", high: "高" },
      confidenceNote: "置信度指解读把握，不是重置概率",
      evidence: "帖子依据", rationale: "判断理由", counter: "反向线索", watch: "接下来盯",
      scope: "只读公开帖子，不是读心", source: "原帖",
      fetched: "采集", generated: "生成",
      intents: { completion: "宣布完成", promise: "预告", compensation: "补偿", promotion: "推广", humor: "玩梗", unrelated: "无关", ambiguous: "存疑" },
      strengths: { direct: "直接", indirect: "间接" }
    },
    en: {
      title: "What is he up to?", note: "Machine reading · public posts", tag: "Machine reading",
      pending: "Reading his public posts…", expired: "Reading expired; waiting for the next fetch", error: "Reading unavailable",
      outlook: { reset_reported: "He claims a reset", reset_signals: "Reset signals spotted", product_teasing: "More like product teasing", no_reset_signal: "No reset signal", unclear: "Intent unclear" },
      confidence: "Reading confidence", levels: { low: "Low", medium: "Medium", high: "High" },
      confidenceNote: "Confidence is about the reading, not the odds of a reset",
      evidence: "Post evidence", rationale: "Why", counter: "Counter-evidence", watch: "Watch next",
      scope: "Public posts only — not mind reading", source: "Source",
      fetched: "Fetched", generated: "Generated",
      intents: { completion: "Completion", promise: "Promise", compensation: "Compensation", promotion: "Promotion", humor: "Humor", unrelated: "Unrelated", ambiguous: "Ambiguous" },
      strengths: { direct: "Direct", indirect: "Indirect" }
    },
    ja: {
      title: "彼の本音は？", note: "機械解読 · 公開投稿", tag: "機械解読",
      pending: "公開投稿を解読中…", expired: "解読は期限切れ。次の収集を待機中", error: "解読は現在利用できません",
      outlook: { reset_reported: "本人がリセットを報告", reset_signals: "リセットの兆候あり", product_teasing: "製品ティザーの可能性", no_reset_signal: "リセットの兆候なし", unclear: "意図不明" },
      confidence: "解読の確度", levels: { low: "低", medium: "中", high: "高" },
      confidenceNote: "確度は解読の自信であり、リセット確率ではありません",
      evidence: "根拠となった投稿", rationale: "判断理由", counter: "反証", watch: "次の注目点",
      scope: "公開投稿のみ。心を読むものではありません", source: "原文",
      fetched: "収集", generated: "生成",
      intents: { completion: "完了報告", promise: "予告", compensation: "補償", promotion: "宣伝", humor: "冗談", unrelated: "無関係", ambiguous: "曖昧" },
      strengths: { direct: "直接", indirect: "間接" }
    },
    fr: {
      title: "Que mijote-t-il ?", note: "Lecture machine · posts publics", tag: "Lecture machine",
      pending: "Lecture de ses posts publics…", expired: "Lecture expirée, en attente de la prochaine collecte", error: "Lecture indisponible",
      outlook: { reset_reported: "Il déclare un reset", reset_signals: "Signaux de reset", product_teasing: "Plutôt du teasing produit", no_reset_signal: "Aucun signal de reset", unclear: "Intention floue" },
      confidence: "Confiance de lecture", levels: { low: "Faible", medium: "Moyenne", high: "Élevée" },
      confidenceNote: "La confiance concerne la lecture, pas la probabilité d'un reset",
      evidence: "Posts à l'appui", rationale: "Pourquoi", counter: "Contre-indices", watch: "À surveiller",
      scope: "Posts publics uniquement — pas de lecture de pensée", source: "Source",
      fetched: "Collecté", generated: "Généré",
      intents: { completion: "Annonce de fin", promise: "Annonce", compensation: "Compensation", promotion: "Promotion", humor: "Humour", unrelated: "Sans rapport", ambiguous: "Ambigu" },
      strengths: { direct: "Direct", indirect: "Indirect" }
    },
    es: {
      title: "¿Qué trama?", note: "Lectura automática · publicaciones públicas", tag: "Lectura automática",
      pending: "Leyendo sus publicaciones públicas…", expired: "Lectura caducada; esperando la próxima recopilación", error: "Lectura no disponible",
      outlook: { reset_reported: "Afirma haber reiniciado", reset_signals: "Señales de reinicio", product_teasing: "Más bien promoción", no_reset_signal: "Sin señales de reinicio", unclear: "Intención poco clara" },
      confidence: "Confianza de la lectura", levels: { low: "Baja", medium: "Media", high: "Alta" },
      confidenceNote: "La confianza es sobre la lectura, no sobre la probabilidad de reinicio",
      evidence: "Publicaciones de apoyo", rationale: "Por qué", counter: "Contrapruebas", watch: "A vigilar",
      scope: "Solo publicaciones públicas, no lectura de mente", source: "Fuente",
      fetched: "Recopilado", generated: "Generado",
      intents: { completion: "Completado", promise: "Promesa", compensation: "Compensación", promotion: "Promoción", humor: "Broma", unrelated: "Sin relación", ambiguous: "Ambiguo" },
      strengths: { direct: "Directa", indirect: "Indirecta" }
    },
    pt: {
      title: "O que ele trama?", note: "Leitura automática · posts públicos", tag: "Leitura automática",
      pending: "Lendo os posts públicos…", expired: "Leitura expirada; aguardando a próxima coleta", error: "Leitura indisponível",
      outlook: { reset_reported: "Ele diz que redefiniu", reset_signals: "Sinais de redefinição", product_teasing: "Parece divulgação", no_reset_signal: "Sem sinal de redefinição", unclear: "Intenção incerta" },
      confidence: "Confiança da leitura", levels: { low: "Baixa", medium: "Média", high: "Alta" },
      confidenceNote: "A confiança é sobre a leitura, não sobre a chance de redefinição",
      evidence: "Posts de apoio", rationale: "Por quê", counter: "Contraprovas", watch: "A seguir",
      scope: "Apenas posts públicos — não é leitura de mente", source: "Fonte",
      fetched: "Coletado", generated: "Gerado",
      intents: { completion: "Concluído", promise: "Promessa", compensation: "Compensação", promotion: "Promoção", humor: "Piada", unrelated: "Sem relação", ambiguous: "Ambíguo" },
      strengths: { direct: "Direta", indirect: "Indireta" }
    },
    ko: {
      title: "그의 공개 발언 해석", note: "기계 해석 · 공개 게시물", tag: "기계 해석",
      pending: "공개 게시물을 해석하는 중…", expired: "해석이 만료되었습니다. 다음 수집을 기다립니다", error: "해석을 사용할 수 없습니다",
      outlook: { reset_reported: "초기화했다고 주장", reset_signals: "초기화 신호 포착", product_teasing: "제품 티징에 가까움", no_reset_signal: "초기화 신호 없음", unclear: "의도 불분명" },
      confidence: "해석 신뢰도", levels: { low: "낮음", medium: "보통", high: "높음" },
      confidenceNote: "신뢰도는 해석의 확신이지 초기화 확률이 아닙니다",
      evidence: "근거 게시물", rationale: "판단 근거", counter: "반대 단서", watch: "다음 주시점",
      scope: "공개 게시물만 — 독심술이 아닙니다", source: "원문",
      fetched: "수집", generated: "생성",
      intents: { completion: "완료 보고", promise: "예고", compensation: "보상", promotion: "홍보", humor: "농담", unrelated: "무관", ambiguous: "모호" },
      strengths: { direct: "직접", indirect: "간접" }
    }
  };
  const OUTLOOKS = ["reset_reported", "reset_signals", "product_teasing", "no_reset_signal", "unclear"];
  const INTENTS = ["completion", "promise", "compensation", "promotion", "humor", "unrelated", "ambiguous"];
  const LEVELS = ["low", "medium", "high"];
  const FIELDS = ["summary", "rationale", "counter_evidence", "watch_next"];
  const MAX_AGE = 86400000, SKEW = 60000, MAX_EVIDENCE = 6;
  const q = selector => document.querySelector(selector);
  const c = () => copy[document.documentElement.lang] || copy.en;
  const parse = value => { const time = Date.parse(value); return Number.isFinite(time) ? time : null; };
  const format = time => time === null ? "—" : new Date(time).toLocaleString(document.documentElement.lang);
  const validURL = (value, id) => typeof value === "string" && /^https:\/\/x\.com\/thsottiaux\/status\/\d+$/.test(value) && (!id || value.endsWith("/" + id));
  const hasText = value => typeof value === "string" && value.length > 0;
  const el = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; };

  // Pure gate: decide what the section may show. Fails closed — any invalid
  // evidence or missing locale field hides the whole reading, not just part.
  // Exposed for node tests: assess(detail, now?, lang?).
  function assess(detail, now, lang) {
    now = now === undefined ? Date.now() : now;
    lang = lang || (copy[document.documentElement.lang] ? document.documentElement.lang : "en");
    const snapshot = detail && detail.snapshot;
    if (detail && detail.demo) return { state: "hidden" };
    if (!detail || detail.loading) return { state: "pending" };
    if (detail.failed || !snapshot || snapshot.health === "error") return { state: "error" };
    if (snapshot.health !== "ok") return { state: "pending" };
    const a = snapshot.intent_analysis;
    if (!a) return { state: "pending" };
    if (a.schema_version !== 1 || a.scope !== "public_posts_not_private_intent" || !OUTLOOKS.includes(a.outlook) || !LEVELS.includes(a.confidence) || !a.locales || typeof a.locales !== "object" || !Array.isArray(a.evidence)) return { state: "error" };
    const generated = parse(a.generated_at), fetched = parse(a.source_fetched_at);
    if (generated === null || fetched === null || generated > now + SKEW || fetched > now + SKEW || generated < fetched) return { state: "error" };
    if (a.source_fetched_at !== snapshot.fetched_at) return { state: "expired" };
    if (now - generated > MAX_AGE || now - fetched > MAX_AGE) return { state: "expired" };
    const loc = a.locales[lang];
    if (!loc || FIELDS.some(k => !hasText(loc[k]))) return { state: "error" };
    const posts = (Array.isArray(snapshot.posts) ? snapshot.posts : []).filter(p => p && hasText(p.id) && hasText(p.text));
    if (!posts.length || !a.evidence.length || a.evidence.length > MAX_EVIDENCE) return { state: "error" };
    const latest = posts.reduce((m, p) => { const t = parse(p.created_at); return t !== null && (m === null || t > parse(m.created_at)) ? p : m; }, null);
    const entries = [];
    for (const item of a.evidence) {
      if (!item || !hasText(item.post_id) || !hasText(item.quote) || !INTENTS.includes(item.intent) || (item.strength !== "direct" && item.strength !== "indirect")) return { state: "error" };
      const reading = item.locales && item.locales[lang];
      if (!reading || !hasText(reading.reading) || !hasText(reading.reset_relevance)) return { state: "error" };
      const post = posts.find(p => p.id === item.post_id && validURL(p.url, p.id) && p.text.includes(item.quote));
      if (!post) return { state: "error" };
      entries.push({ item, url: post.url, reading, at: parse(post.created_at) });
    }
    if (latest && !entries.some(e => e.item.post_id === latest.id)) return { state: "error" };
    return { state: "ready", analysis: a, entries, loc, lang };
  }
  window.AITIBO_INTENT = { assess };

  const section = el("section", "intent");
  section.id = "intent";
  section.setAttribute("aria-labelledby", "intent-title");
  const heading = el("div", "section-heading");
  heading.append(el("h2", null, " "), el("span", "section-note"));
  heading.firstChild.id = "intent-title";
  const statusLine = el("p", "intent-state");
  statusLine.setAttribute("role", "status");
  const body = el("div", "intent-body");
  section.append(heading, statusLine, body);
  const grid = q(".info-grid");
  if (grid) grid.before(section); else q(".page").append(section);

  function render(detail) {
    const t = c(), verdict = assess(detail);
    section.dataset.state = verdict.state;
    section.hidden = verdict.state === "hidden";
    heading.firstChild.textContent = t.title;
    heading.lastChild.textContent = t.note;
    body.replaceChildren();
    if (verdict.state !== "ready") {
      statusLine.hidden = false;
      statusLine.textContent = verdict.state === "pending" ? t.pending : verdict.state === "expired" ? t.expired : t.error;
      return;
    }
    statusLine.hidden = true;
    const a = verdict.analysis, loc = verdict.loc;

    const lead = el("div", "intent-lead");
    const outlook = el("p", "intent-outlook", t.outlook[a.outlook]);
    outlook.dataset.outlook = a.outlook;
    const meta = el("p", "intent-confidence");
    meta.append(el("span", "intent-tag", t.tag), document.createTextNode(" " + t.confidence + ": "), el("b", null, t.levels[a.confidence]), el("small", null, t.confidenceNote));
    lead.append(outlook, el("p", "intent-summary", loc.summary), meta);

    const cols = el("div", "intent-cols");
    const evBox = el("div", "intent-evidence");
    evBox.append(el("h3", null, t.evidence));
    const list = el("ol", "intent-list");
    for (const { item, url, reading, at } of verdict.entries) {
      const li = el("li", "intent-item");
      const top = el("p", "intent-item-top");
      top.append(el("span", "intent-chip", t.intents[item.intent]), el("span", "intent-chip subtle", t.strengths[item.strength]));
      li.append(top, el("p", "intent-quote", "“" + item.quote + "”"), el("p", "intent-reading", reading.reading), el("p", "intent-relevance", reading.reset_relevance));
      const footRow = el("p", "intent-item-foot");
      const link = el("a", "intent-source", t.source + " ↗");
      link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer";
      footRow.append(link);
      if (at !== null) {
        const time = el("time", "intent-time", format(at));
        time.dateTime = new Date(at).toISOString();
        footRow.append(time);
      }
      li.append(footRow);
      list.append(li);
    }
    evBox.append(list);

    const aside = el("aside", "intent-aside");
    for (const [label, text] of [[t.rationale, loc.rationale], [t.counter, loc.counter_evidence], [t.watch, loc.watch_next]]) {
      const group = el("div", "intent-block");
      group.append(el("h3", null, label), el("p", null, text));
      aside.append(group);
    }
    cols.append(evBox, aside);

    const foot = el("p", "intent-foot");
    foot.textContent = t.scope + " · " + t.fetched + " " + format(parse(a.source_fetched_at)) + " · " + t.generated + " " + format(parse(a.generated_at));

    body.append(lead, cols, foot);
  }

  let last = null;
  window.addEventListener("aitibo:observations", event => { last = event.detail || null; render(last); });
  render(null);
})();
