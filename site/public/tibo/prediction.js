"use strict";
// Next-reset signal index card inside #forecast.
// Renders snapshot.prediction (kind "signal_index"), never fabricates a score.
// Fail-closed like intent.js: any malformed field hides the card.
(() => {
  const copy = {
    "zh-CN": { title: "下一次重置 · 信号指数", tag: "机器分析", pending: "暂无有效的下次预测", expired: "预测已过期", error: "预测暂不可用", index: "信号指数", window: "观察窗口", signals: "信号来源", uncertainty: "不确定度", source: "原帖", note: "指数是公开帖信号的确定性打分，不是重置概率；今日已完成重置不计入。" },
    en: { title: "Next reset · signal index", tag: "Machine analysis", pending: "No valid next-reset forecast yet", expired: "Forecast expired", error: "Forecast unavailable", index: "Signal index", window: "Window", signals: "Signals", uncertainty: "Uncertainty", source: "Source", note: "A deterministic score of public-post signals, not a reset probability; today's completed reset adds nothing." },
    ja: { title: "次のリセット · シグナル指数", tag: "機械分析", pending: "有効な次回予測はまだありません", expired: "予測は期限切れです", error: "予測を利用できません", index: "シグナル指数", window: "観測ウィンドウ", signals: "シグナル", uncertainty: "不確実性", source: "原帖", note: "指数は公開投稿のシグナル評価であり、リセット確率ではありません。本日完了したリセットは加点されません。" },
    fr: { title: "Prochain reset · indice de signal", tag: "Analyse machine", pending: "Pas de prévision valide pour l'instant", expired: "Prévision expirée", error: "Prévision indisponible", index: "Indice de signal", window: "Fenêtre", signals: "Signaux", uncertainty: "Incertitude", source: "Publication", note: "Un score déterministe de signaux publics, pas une probabilité de reset ; le reset d'aujourd'hui ne compte pas." },
    es: { title: "Próximo reinicio · índice de señales", tag: "Análisis automático", pending: "Aún no hay una previsión válida", expired: "Previsión caducada", error: "Previsión no disponible", index: "Índice de señales", window: "Ventana", signals: "Señales", uncertainty: "Incertidumbre", source: "Publicación", note: "Una puntuación determinista de señales públicas, no una probabilidad de reinicio; el reinicio de hoy no suma." },
    pt: { title: "Próxima redefinição · índice de sinais", tag: "Análise automática", pending: "Ainda sem previsão válida", expired: "Previsão expirada", error: "Previsão indisponível", index: "Índice de sinais", window: "Janela", signals: "Sinais", uncertainty: "Incerteza", source: "Publicação", note: "Uma pontuação determinista de sinais públicos, não uma probabilidade de redefinição; a redefinição de hoje não conta." },
    ko: { title: "다음 초기화 · 신호 지수", tag: "기계 분석", pending: "유효한 다음 예측이 아직 없습니다", expired: "예측이 만료되었습니다", error: "예측을 사용할 수 없습니다", index: "신호 지수", window: "관측 창", signals: "신호", uncertainty: "불확실성", source: "원문", note: "공개 게시물 신호의 결정적 점수이며 초기화 확률이 아닙니다. 오늘 완료된 초기화는 반영되지 않습니다." },
  };
  const codes = {
    "zh-CN": { explicit_reset_plan: "明确预告", tentative_reset: "含糊预告", dated_window: "点明时间窗", launch_context: "发布会背景", incident_context: "故障背景", cancellation: "取消信号" },
    en: { explicit_reset_plan: "Explicit plan", tentative_reset: "Tentative hint", dated_window: "Dated window", launch_context: "Launch context", incident_context: "Incident context", cancellation: "Cancellation" },
    ja: { explicit_reset_plan: "明示的な予告", tentative_reset: "示唆", dated_window: "期間指定", launch_context: "イベント背景", incident_context: "障害背景", cancellation: "取り消し" },
    fr: { explicit_reset_plan: "Annonce explicite", tentative_reset: "Indice", dated_window: "Fenêtre datée", launch_context: "Contexte de lancement", incident_context: "Contexte d'incident", cancellation: "Annulation" },
    es: { explicit_reset_plan: "Plan explícito", tentative_reset: "Indicio", dated_window: "Ventana fechada", launch_context: "Contexto de lanzamiento", incident_context: "Contexto de incidencia", cancellation: "Cancelación" },
    pt: { explicit_reset_plan: "Plano explícito", tentative_reset: "Indício", dated_window: "Janela datada", launch_context: "Contexto de lançamento", incident_context: "Contexto de incidente", cancellation: "Cancelamento" },
    ko: { explicit_reset_plan: "명시된 계획", tentative_reset: "예고 시사", dated_window: "날짜 지정", launch_context: "출시 맥락", incident_context: "장애 맥락", cancellation: "취소 신호" },
  };
  const CODE_SET = new Set(["explicit_reset_plan", "tentative_reset", "dated_window", "launch_context", "incident_context", "cancellation"]);
  const MAX_AGE = 86400000, SKEW = 60000;
  const q = s => document.querySelector(s);
  const c = () => copy[document.documentElement.lang] || copy.en;
  const cc = () => codes[document.documentElement.lang] || codes.en;
  const parse = v => { const t = Date.parse(v); return Number.isNaN(t) ? null : t; };
  const text = v => typeof v === "string" && v.trim() !== "";
  const validURL = u => { try { const x = new URL(u); return x.protocol === "https:" && x.hostname === "x.com" && /^\/thsottiaux\/status\/\d+$/.test(x.pathname); } catch { return false; } };
  const el = (tag, cls) => { const e = document.createElement(tag); if (cls) e.className = cls; return e; };

  // Pure assessment; exported for tests.
  function assess(detail, now = Date.now(), lang = document.documentElement.lang) {
    if (detail?.demo) return { state: "hidden" };
    if (!detail || detail.loading) return { state: "pending" };
    const snap = detail.snapshot;
    if (detail.failed || !snap || snap.health === "error") return { state: "error" };
    if (snap.health !== "ok") return { state: "pending" };
    const p = snap.prediction;
    if (p === null || p === undefined) return { state: "pending" };
    const bad = () => ({ state: "error" });
    if (p.schema_version !== 1 || p.kind !== "signal_index" || p.methodology_version !== "signals-v1") return bad();
    if (typeof p.score !== "number" || !Number.isFinite(p.score) || p.score < 0 || p.score > 95) return bad();
    if (p.scale !== 100 || p.timezone !== "America/Los_Angeles" || typeof p.locales !== "object" || !p.locales || !Array.isArray(p.signals)) return bad();
    const generated = parse(p.generated_at), fetched = parse(p.source_fetched_at), snapFetched = parse(snap.fetched_at);
    if (generated === null || fetched === null || snapFetched === null) return bad();
    if (generated > now + SKEW || fetched > now + SKEW || generated < fetched) return bad();
    if (fetched !== snapFetched || now - fetched > MAX_AGE || now - generated > MAX_AGE) return { state: "expired" };
    const ws = parse(p.window_start), we = parse(p.window_end);
    if (ws === null || we === null || ws < generated - MAX_AGE || ws >= we || we > generated + 14 * MAX_AGE) return bad();
    if (we <= now) return { state: "expired" };
    const loc = p.locales[lang];
    if (!loc || !text(loc.summary) || !text(loc.uncertainty)) return bad();
    const posts = Array.isArray(snap.posts) ? snap.posts : [];
    const items = [];
    for (const s of p.signals) {
      if (!s || !CODE_SET.has(s.code) || !text(s.post_id) || !text(s.quote) || typeof s.points !== "number" || !Number.isFinite(s.points)) return bad();
      const post = posts.find(x => x.id === s.post_id);
      if (!post || !validURL(post.url) || !post.url.includes("/status/" + post.id) || !String(post.text || "").includes(s.quote)) return bad();
      items.push({ code: s.code, quote: s.quote, points: s.points, url: post.url, at: post.created_at });
    }
    return { state: "ready", score: p.score, window: [p.window_start, p.window_end], summary: loc.summary, uncertainty: loc.uncertainty, signals: items };
  }

  const block = el("div", "pred");
  block.id = "prediction";
  const anchor = q("#forecast .signals");
  if (anchor) anchor.after(block);

  function fmtRange(a, b) {
    const f = new Intl.DateTimeFormat(document.documentElement.lang, { month: "short", day: "numeric", timeZone: "America/Los_Angeles" });
    return f.format(new Date(a)) + " – " + f.format(new Date(b)) + " · America/Los_Angeles";
  }
  function status(key) { const p = el("p", "pred-status"); p.textContent = c()[key]; block.replaceChildren(p); }
  function render(detail) {
    const r = assess(detail);
    if (r.state === "hidden") { block.hidden = true; return; }
    block.hidden = false;
    if (r.state !== "ready") { status(r.state); return; }
    const t = c(), ct = cc();
    const head = el("p", "pred-title");
    const strong = document.createElement("strong"); strong.textContent = t.title;
    const tag = el("span", "pred-tag"); tag.textContent = t.tag;
    head.append(strong, tag);
    const score = el("div", "pred-score");
    const num = document.createElement("b"); num.textContent = String(Math.round(r.score));
    const scale = el("span", "pred-scale"); scale.textContent = "/100 · " + t.index;
    score.append(num, scale);
    const meter = el("div", "pred-meter");
    meter.setAttribute("aria-hidden", "true");
    const fill = el("i"); fill.style.width = Math.max(0, Math.min(100, r.score)) + "%";
    meter.append(fill);
    const sum = el("p", "pred-sum"); sum.textContent = r.summary;
    const win = el("p", "pred-win"); win.textContent = t.window + " · " + fmtRange(r.window[0], r.window[1]);
    const list = el("ul", "pred-sigs");
    for (const s of r.signals) {
      const li = document.createElement("li");
      const chip = el("span", "pred-chip"); chip.dataset.code = s.code; chip.textContent = ct[s.code] || s.code;
      const pts = el("b", "pred-pts"); pts.textContent = (s.points > 0 ? "+" : "") + Math.round(s.points);
      const quote = el("q", "pred-quote"); quote.textContent = s.quote;
      const src = document.createElement("a"); src.className = "pred-src"; src.href = s.url; src.target = "_blank"; src.rel = "noopener noreferrer"; src.textContent = t.source + " ↗";
      li.append(chip, pts, quote, src); list.append(li);
    }
    const unc = el("p", "pred-unc"); const ub = document.createElement("b"); ub.textContent = t.uncertainty + " · "; unc.append(ub, document.createTextNode(r.uncertainty));
    const note = el("p", "pred-note"); note.textContent = t.note;
    block.replaceChildren(head, score, meter, sum, win, list, unc, note);
  }
  window.addEventListener("aitibo:observations", e => render(e.detail));
  window.AITIBO_PREDICT = { assess };
  render(null);
})();
