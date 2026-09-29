"use strict";
// Hero paired last/next reset summary, rendered from snapshot.reset_timeline.
// Announcement time is labeled as such; next window shows the Pacific source
// calendar first (exclusive end minus 1ms) plus a local instant conversion.
// Demo hides it; stale data keeps the historical last and marks next unknown.
(() => {
  const copy = {
    "zh-CN": { last: "上次重置", next: "下次重置", noLast: "暂无完成公告", announcedNoDate: "已公开预告 · 哪天还没说", possibleNoDate: "有信号 · 还没定日子", unknown: "下次时间待确认", announceNote: "完成公告时间", pacific: "太平洋时间", tentative: "暂定窗口", windowNote: "窗口内具体时刻未公布", localLabel: "本地", stale: "观测过期", source: "原帖", pending: "正在读取观测…" },
    en: { last: "Last reset", next: "Next reset", noLast: "No completion announced yet", announcedNoDate: "Announced · no date given", possibleNoDate: "Signals only · no date yet", unknown: "Next timing unconfirmed", announceNote: "announcement time", pacific: "Pacific calendar", tentative: "tentative window", windowNote: "No exact time announced within the window", localLabel: "local", stale: "stale observation", source: "post", pending: "Reading observations…" },
    ja: { last: "前回のリセット", next: "次のリセット", noLast: "完了の告知はまだありません", announcedNoDate: "予告あり · 日付未公表", possibleNoDate: "兆候のみ · 日付未定", unknown: "次の時期は未確認", announceNote: "完了公告の時刻", pacific: "太平洋時間の暦", tentative: "暫定ウィンドウ", windowNote: "期間内の具体的な時刻は未公表", localLabel: "ローカル", stale: "観測が古い", source: "原帖", pending: "観測を読み込み中…" },
    fr: { last: "Dernier reset", next: "Prochain reset", noLast: "Aucune annonce de fin", announcedNoDate: "Annoncé · date non précisée", possibleNoDate: "Signaux · pas encore de date", unknown: "Prochaine date non confirmée", announceNote: "heure de l'annonce", pacific: "calendrier Pacifique", tentative: "fenêtre provisoire", windowNote: "Pas d'heure précise annoncée", localLabel: "heure locale", stale: "observation périmée", source: "publication", pending: "Lecture des observations…" },
    es: { last: "Último reinicio", next: "Próximo reinicio", noLast: "Sin anuncio de reinicio aún", announcedNoDate: "Anunciado · sin fecha concreta", possibleNoDate: "Señales · fecha sin definir", unknown: "Próxima fecha sin confirmar", announceNote: "hora del anuncio", pacific: "calendario del Pacífico", tentative: "ventana tentativa", windowNote: "Sin hora exacta anunciada", localLabel: "hora local", stale: "observación desactualizada", source: "publicación", pending: "Leyendo observaciones…" },
    pt: { last: "Última redefinição", next: "Próxima redefinição", noLast: "Sem anúncio de conclusão", announcedNoDate: "Anunciada · data ainda não dita", possibleNoDate: "Sinais · data indefinida", unknown: "Próxima data não confirmada", announceNote: "horário do anúncio", pacific: "calendário do Pacífico", tentative: "janela provisória", windowNote: "Sem horário exato anunciado", localLabel: "hora local", stale: "observação desatualizada", source: "publicação", pending: "Lendo observações…" },
    ko: { last: "지난 초기화", next: "다음 초기화", noLast: "완료 발표가 아직 없습니다", announcedNoDate: "예고됨 · 날짜 미정", possibleNoDate: "신호만 있음 · 날짜 미정", unknown: "다음 시점 미확인", announceNote: "완료 발표 시각", pacific: "태평양 달력", tentative: "잠정 창", windowNote: "창 내 구체 시각 미공개", localLabel: "로컬", stale: "오래된 관측", source: "원문", pending: "관측을 읽는 중…" },
  };
  const STATUSES = new Set(["announced", "possible", "unknown"]);
  const MAX_AGE = 86400000, SKEW = 60000, PACIFIC = "America/Los_Angeles";
  const q = s => document.querySelector(s);
  const c = () => copy[document.documentElement.lang] || copy.en;
  const parse = v => { const t = Date.parse(v); return Number.isNaN(t) ? null : t; };
  const text = v => typeof v === "string" && v.trim() !== "";
  const validURL = u => typeof u === "string" && /^https:\/\/x\.com\/thsottiaux\/status\/\d+$/.test(u);
  const el = (tag, cls) => { const e = document.createElement(tag); if (cls) e.className = cls; return e; };
  const fmtDay = (t, tz) => new Intl.DateTimeFormat(document.documentElement.lang, { month: "long", day: "numeric", timeZone: tz }).format(new Date(t));
  const fmtLocal = t => new Intl.DateTimeFormat(document.documentElement.lang, { month: "long", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(t));
  const fmtLocalShort = t => new Intl.DateTimeFormat(document.documentElement.lang, { month: "numeric", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(t));
  const localTZ = () => Intl.DateTimeFormat().resolvedOptions().timeZone || "local";
  function rel(t, now) {
    const diff = now - t, rtf = new Intl.RelativeTimeFormat(document.documentElement.lang, { numeric: "auto" });
    if (diff >= 86400000) return rtf.format(-Math.round(diff / 86400000), "day");
    if (diff >= 3600000) return rtf.format(-Math.round(diff / 3600000), "hour");
    return rtf.format(-Math.max(1, Math.round(diff / 60000)), "minute");
  }

  // Pure projection; exported for tests. Returns hidden/pending/ready.
  function project(detail, now = Date.now()) {
    if (detail?.demo) return { state: "hidden" };
    if (!detail || detail.loading) return { state: "pending" };
    const snap = detail.snapshot;
    if (!snap) return { state: "pending" };
    const rt = snap.reset_timeline;
    if (rt === undefined || rt === null) return { state: "pending" };
    if (typeof rt !== "object" || typeof rt.fresh !== "boolean" || !rt.next_reset || typeof rt.next_reset !== "object") return { state: "hidden" };
    const nr = rt.next_reset;
    if (!STATUSES.has(nr.status) || !["source_calendar", "unspecified"].includes(nr.time_basis) || nr.timezone !== PACIFIC) return { state: "hidden" };
    if (nr.source_url !== null && !validURL(nr.source_url)) return { state: "hidden" };
    let ws = parse(nr.window_start), we = parse(nr.window_end);
    if ((nr.window_start !== null && ws === null) || (nr.window_end !== null && we === null)) return { state: "hidden" };
    if ((ws === null) !== (we === null) || (ws !== null && ws >= we)) return { state: "hidden" };
    if (nr.time_basis === "source_calendar" && ws === null) return { state: "hidden" };
    if (nr.time_basis === "unspecified") { ws = null; we = null; }
    let last = null;
    if (rt.last_reset !== null && rt.last_reset !== undefined) {
      const at = parse(rt.last_reset?.reported_at);
      if (at === null || at > now + SKEW || !validURL(rt.last_reset.source_url)) return { state: "hidden" };
      last = { at, rel: rel(at, now), url: rt.last_reset.source_url };
    }
    const fetched = parse(snap.fetched_at);
    const stale = detail.failed || snap.health !== "ok" || rt.fresh === false || fetched === null || now - fetched > MAX_AGE || fetched > now + SKEW;
    let next;
    if (stale || (ws !== null && we <= now)) next = { status: "unknown", stale: true };
    else if (nr.status === "announced") next = ws !== null ? { status: "announced", ws, we: we - 1, rawEnd: we, url: nr.source_url, stale: false } : { status: "announcedNoDate", url: nr.source_url, stale: false };
    else if (nr.status === "possible") next = ws !== null ? { status: "possible", ws, we: we - 1, rawEnd: we, url: nr.source_url, stale: false } : { status: "possibleNoDate", url: nr.source_url, stale: false };
    else next = { status: "unknown", stale: false };
    return { state: "ready", last, next };
  }

  const block = el("div", "reset-pair");
  block.id = "reset-pair";
  const anchor = q("#hero-line");
  if (anchor) anchor.after(block);

  function row(labelKey, stale) {
    const r = el("div", "rt-row");
    const label = el("span", "rt-label"); label.textContent = c()[labelKey];
    if (stale) { const tag = el("i", "rt-stale"); tag.textContent = c().stale; label.append(tag); }
    r.append(label);
    return r;
  }
  function sourceLink(url) {
    const a = document.createElement("a"); a.className = "rt-src"; a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.textContent = c().source + " ↗";
    return a;
  }
  function render(detail) {
    const p = project(detail);
    if (p.state === "hidden") { block.hidden = true; return; }
    block.hidden = false;
    if (p.state !== "ready") {
      const s = el("p", "rt-pending"); s.textContent = c().pending; block.replaceChildren(s); return;
    }
    const t = c(), rows = [];
    // Last reset: local absolute + tz + relative, labeled as announcement time.
    const lastRow = row("last", false);
    const lastMain = el("span", "rt-main");
    if (p.last) {
      const b = document.createElement("b"); b.textContent = fmtLocal(p.last.at);
      const small = document.createElement("small"); small.textContent = localTZ() + " · " + p.last.rel;
      lastMain.append(b, small);
      const sub = el("span", "rt-sub");
      sub.append(document.createTextNode(t.announceNote + " · "), sourceLink(p.last.url));
      lastRow.append(lastMain, sub);
    } else {
      const b = document.createElement("b"); b.textContent = t.noLast; lastMain.append(b); lastRow.append(lastMain);
    }
    rows.push(lastRow);
    // Next reset: source calendar first, local conversion as secondary text.
    const nextRow = row("next", p.next.stale);
    const nextMain = el("span", "rt-main");
    const sub = el("span", "rt-sub");
    const n = p.next;
    if (n.status === "announced" || n.status === "possible") {
      const b = document.createElement("b"); b.textContent = fmtDay(n.ws, PACIFIC) + " – " + fmtDay(n.we, PACIFIC);
      const small = document.createElement("small"); small.textContent = t.pacific + (n.status === "possible" ? " · " + t.tentative : "");
      nextMain.append(b, small);
      sub.append(document.createTextNode((n.status === "announced" ? t.windowNote + " · " : "") + t.localLabel + " " + fmtLocalShort(n.ws) + " → " + fmtLocalShort(n.rawEnd) + " (" + localTZ() + ")" + (n.url ? " · " : "")));
      if (n.url) sub.append(sourceLink(n.url));
    } else {
      const key = n.status === "announcedNoDate" ? "announcedNoDate" : n.status === "possibleNoDate" ? "possibleNoDate" : "unknown";
      const b = document.createElement("b"); b.textContent = t[key]; nextMain.append(b);
      if (n.url) sub.append(sourceLink(n.url));
    }
    nextRow.append(nextMain, sub);
    rows.push(nextRow);
    block.replaceChildren(...rows);
  }
  window.addEventListener("aitibo:observations", e => render(e.detail));
  window.AITIBO_TIMELINE = { project };
  render(null);
})();
