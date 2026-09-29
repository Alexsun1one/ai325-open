"use strict";

const $ = (selector) => document.querySelector(selector);
const I18N = window.AITIBO_I18N;

if (!I18N) throw new Error("AITIBO_I18N must load before app.js");

const stateMeta = {
  waiting: { index: 0, duration: 2 * 86400 + 14 * 3600 + 36 * 60, source: "https://x.com/thsottiaux/status/2077212009071075330" },
  soon: { index: 1, duration: 2 * 86400 + 14 * 3600 + 36 * 60, source: "https://technews.tw/2026/07/21/who-is-tibo/" },
  reset: { index: 2, duration: 3 * 60, source: "https://community.openai.com/t/codex-rate-limits-reset-for-all-paid-plans-april-28-2026/1379921" }
};

let currentState = "waiting";
let stateStarted = Date.now();
let activeFilter = "all";
let lastFortune = -1;
let toastTimeout;
let speechTimeout;

const t = (key, vars) => I18N.t(key, vars);
const text = (selector, key) => { const element = $(selector); if (element) element.textContent = t(key); };
const aria = (selector, key) => { const element = $(selector); if (element) element.setAttribute("aria-label", t(key)); };
const nodeText = (element, value) => { if (element && element.firstChild) element.firstChild.nodeValue = value; };
const nodeValue = (node, value) => { if (node) node.nodeValue = value; };

function stateText(key) {
  const base = "states." + key;
  return {
    status: t(base + ".status"),
    line: t(base + ".line"),
    speech: t(base + ".speech"),
    alt: t(base + ".alt"),
    forecast: t(base + ".forecast"),
    description: t(base + ".description"),
    signals: t(base + ".signals"),
    badge: t(base + ".badge"),
    quote: t(base + ".quote"),
    context: t(base + ".context"),
    semantic: t(base + ".semantic"),
    reasoning: t(base + ".reasoning"),
    timerLabel: t(base + ".timerLabel")
  };
}

function renderEvents() {
  const events = t("events");
  if (!Array.isArray(events)) return;
  document.querySelectorAll("[data-event]").forEach((article) => {
    const event = events[Number(article.dataset.event)];
    if (!event) return;
    textIn(article, ".event-label", event.label);
    textIn(article, "h3", event.title);
    textIn(article, "p", event.desc);
    textIn(article, "a", event.source + " ↗");
  });
}

function textIn(parent, selector, value) {
  const element = parent.querySelector(selector);
  if (element) element.textContent = value;
}

function translateStatic() {
  text(".skip", "skip");
  aria(".brand", "brandAria");
  aria("nav", "navAria");
  ["nav.radar", "nav.feed", "nav.history"].forEach((key, index) => text("nav a:nth-of-type(" + (index + 1) + ")", key));
  text("[data-about]", "nav.about");
  aria("#language-select", "langAria");
  text(".subscribe.outline span:last-child", "nav.subscribe");

  const preview = document.querySelectorAll(".preview-bar > span");
  if (preview[0]) nodeText(preview[0], "");
  if (preview[0]) {
    const label = preview[0].lastChild;
    if (label) label.nodeValue = " " + t("preview.badge");
  }
  if (preview[1]) preview[1].textContent = t("preview.note");
  text(".hero-copy > .eyebrow", "hero.eyebrow");
  nodeValue($("#hero-title").childNodes[2], t("hero.title"));
  text("#hero-title .question", "hero.mark");
  document.querySelectorAll(".timer small").forEach((unit, index) => unit.textContent = t(["units.day", "units.hour", "units.min"][index]));
  nodeText(document.querySelector(".hero-actions button[data-subscribe]"), t("hero.cta") + " ");
  nodeText($("#evidence-link"), t("hero.evidence") + " ");
  text(".hero-note", "hero.note");
  nodeText($("#nudge"), t("nudge.label") + " ");
  text("#nudge small", "nudge.hint");
  aria(".state-picker", "picker.aria");
  ["waiting", "soon", "reset"].forEach((state) => {
    const button = document.querySelector("button[data-state=" + state + "]");
    if (!button) return;
    const spans = button.querySelectorAll("span");
    if (spans[1]) spans[1].textContent = t("picker." + state);
    textIn(button, "small", t("picker." + state + "Sub"));
  });
  nodeText(document.querySelector(".scene-caption"), t("sceneCaption") + " ");
  aria(".offerings", "offerings.aria");
  ["coffee", "razor", "pray"].forEach((kind, index) => {
    const button = document.querySelector("[data-gift=" + kind + "]");
    if (button) nodeText(button, ["☕ ", "🪒 ", "🙏 "][index] + t("offerings." + kind));
  });
  text(".offerings-note", "offerings.note");

  nodeText($("#feed-title"), t("feed.title") + " ");
  text(".feed .section-note", "feed.note");
  text("#post-disclaimer", "post.disclaimer");
  $("#post-source").textContent = t("post.source") + " ↗";
  const secondPost = document.querySelector(".second-post");
  if (secondPost) {
    const meta = secondPost.querySelectorAll(".post-meta > span");
    if (meta[0]) meta[0].textContent = t("post2.meta");
    if (meta[1]) meta[1].textContent = t("post2.badge");
    textIn(secondPost, ".post-quote", t("post2.quote"));
    textIn(secondPost, ".post-context", t("post2.context"));
    textIn(secondPost, ".post-bottom > span", t("post2.source"));
    textIn(secondPost, ".post-bottom a", t("post2.link") + " ↗");
  }
  $(".feed-follow").textContent = t("feed.follow") + " ↗";

  text("#forecast-title", "forecast.title");
  text(".forecast .section-note", "forecast.note");
  ["promise", "activity", "completion"].forEach((signal) => {
    const label = document.querySelector("#signal-" + signal).previousElementSibling;
    if (label) nodeValue(label.lastChild, " " + t("forecast.signals." + signal));
  });
  nodeText($("#reasoning summary"), t("forecast.reasoningSummary") + " ");
  text("#reasoning .reasoning-body p:last-child", "forecast.reasoningStatic");
  text(".forecast-footnote", "forecast.footnote");

  text("#history-title", "history.title");
  text(".history-heading > div:first-child p", "history.sub");
  aria(".filters", "filters.aria");
  ["all", "reset", "banked"].forEach((filter) => text("[data-filter=" + filter + "]", "filters." + filter));
  renderEvents();

  text(".fortune-section .eyebrow", "fortune.eyebrow");
  text("#fortune-title", "fortune.title");
  text(".fortune-section > div:first-child > p:last-child", "fortune.sub");
  $("#bottom-note").innerHTML = t("bottom.note");
  document.querySelectorAll("[data-subscribe]:not(.subscribe.outline)").forEach((button) => {
    if (button.closest(".hero-actions")) return;
    nodeText(button, t("bottom.cta") + " ");
  });
  text("footer > p", "footer.note");
  nodeText($("footer > span"), t("footer.tag"));

  document.querySelectorAll("[data-close]").forEach((button) => ariaButton(button, "dialog.close"));
  const subscribeDialog = $("#subscribe-dialog");
  textIn(subscribeDialog, ".eyebrow", t("sub.eyebrow"));
  textIn(subscribeDialog, "h2", t("sub.title"));
  textIn(subscribeDialog, ".dialog-description", t("sub.desc"));
  ["promise", "reset"].forEach((notice) => {
    const label = $("#notice-" + notice).closest("label");
    if (!label) return;
    const copy = label.querySelector("span");
    nodeText(copy, t("sub." + notice));
    textIn(copy, "small", t("sub." + notice + "Sub"));
  });
  nodeText(subscribeDialog.querySelector("[type=submit]"), t("sub.save") + " ");

  const aboutDialog = $("#about-dialog");
  textIn(aboutDialog, ".eyebrow", t("about.eyebrow"));
  const aboutTitle = $("#about-dialog h2");
  if (aboutTitle) aboutTitle.innerHTML = t("about.title");
  const descriptions = aboutDialog.querySelectorAll(".dialog-description");
  if (descriptions[0]) descriptions[0].textContent = t("about.desc1");
  if (descriptions[1]) descriptions[1].textContent = t("about.desc2");
  nodeText(aboutDialog.querySelector(".primary"), t("about.ok") + " ");
}

function ariaButton(button, key) {
  button.setAttribute("aria-label", t(key));
}

function setSpeech(copy) {
  $("#speech").replaceChildren(document.createTextNode(copy));
  const label = document.createElement("span");
  label.textContent = t("speechTag");
  $("#speech").append(label);
  window.dispatchEvent(new CustomEvent("aitibo:speech", { detail: { animate: true } }));
}

function updateTimer() {
  if (window.AITIBO_LIVE_MODE) return;
  const elapsed = stateMeta[currentState].duration + Math.floor((Date.now() - stateStarted) / 1000);
  $("#days").textContent = String(Math.floor(elapsed / 86400)).padStart(2, "0");
  $("#hours").textContent = String(Math.floor(elapsed / 3600) % 24).padStart(2, "0");
  $("#minutes").textContent = String(Math.floor(elapsed / 60) % 60).padStart(2, "0");
}

function selectState(key, announce = true, resetClock = true) {
  if (!Object.hasOwn(stateMeta, key)) return;
  const previousState = currentState;
  currentState = key;
  if (resetClock) stateStarted = Date.now();
  clearTimeout(speechTimeout);
  const state = stateText(key);
  document.body.dataset.state = key;
  $("#status").textContent = state.status;
  $("#hero-line").textContent = state.line;
  setSpeech(state.speech);
  $("#artwork").setAttribute("aria-label", state.alt);
  $("#hero-sprite").style.backgroundPosition = "50% " + (stateMeta[key].index * 50) + "%";
  $("#forecast-state").textContent = state.forecast;
  $("#forecast-description").textContent = state.description;
  ["promise", "activity", "completion"].forEach((name, index) => { $("#signal-" + name).textContent = state.signals[index]; });
  $("#post-badge").textContent = state.badge;
  $("#post-quote").textContent = state.quote;
  $("#post-context").textContent = state.context;
  $("#post-source").href = stateMeta[key].source;
  $("#semantic-text").textContent = state.semantic;
  $("#reasoning-text").textContent = state.reasoning;
  $("#timer-label").replaceChildren(document.createTextNode(state.timerLabel + " "));
  const tag = document.createElement("span");
  tag.className = "demo-tag";
  tag.textContent = t("timer.demoTag");
  $("#timer-label").append(tag);
  document.querySelectorAll("button[data-state]").forEach((button) => {
    const selected = button.dataset.state === key;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  updateTimer();
  window.dispatchEvent(new CustomEvent("aitibo:state", {
    detail: { state: key, previous: previousState, animate: announce }
  }));
  if (announce) toast(t("toasts.preview", { state: t("stateNames." + key) }));
}

function toast(message) {
  clearTimeout(toastTimeout);
  $("#toast").textContent = message;
  $("#toast").classList.add("visible");
  toastTimeout = setTimeout(() => $("#toast").classList.remove("visible"), 3200);
}

function applyFilter(filter) {
  activeFilter = filter;
  document.querySelectorAll("[data-kind]").forEach((item) => { item.hidden = filter !== "all" && item.dataset.kind !== filter; });
  document.querySelectorAll("[data-filter]").forEach((item) => {
    const selected = item.dataset.filter === filter;
    item.classList.toggle("selected", selected);
    item.setAttribute("aria-pressed", String(selected));
  });
}

function fortunes() {
  const values = t("fortunes");
  return Array.isArray(values) ? values : [];
}

function renderFortune() {
  const all = fortunes();
  const drawn = lastFortune >= 0 && all[lastFortune];
  $("#fortune-rank").textContent = drawn ? all[lastFortune].rank : t("fortune.pending");
  $("#fortune-line").textContent = drawn ? all[lastFortune].line : t("fortune.initial");
  $("#fortune-detail").textContent = drawn ? all[lastFortune].detail + t("fortune.suffix") : t("fortune.disclaimer");
  $("#copy-fortune").hidden = !drawn;
  nodeText($("#draw-fortune"), (drawn ? t("fortune.redraw") : t("fortune.draw")) + " ");
  $("#copy-fortune").textContent = t("fortune.copy") + " ↗";
}

function updateDocumentLanguage() {
  document.documentElement.lang = I18N.lang;
  document.title = t("meta.title");
  const description = document.querySelector('meta[name="description"]');
  if (description) description.content = t("meta.description");
}

function applyLanguage() {
  updateDocumentLanguage();
  translateStatic();
  selectState(currentState, false, false);
  renderFortune();
  applyFilter(activeFilter);
}

function isSupportedLanguage(code) {
  return I18N.LANGS.some((language) => language.code === code);
}

function setLanguageUrl(code) {
  try { localStorage.setItem("aitibo:lang", code); } catch {}
  const url = new URL(window.location.href);
  url.searchParams.set("lang", code);
  history.replaceState(history.state, "", url);
}

function initLanguagePicker() {
  const picker = $("#language-select");
  const requested = new URL(window.location.href).searchParams.get("lang");
  I18N.lang = isSupportedLanguage(requested) ? requested : I18N.detect();
  if (isSupportedLanguage(requested)) {
    try { localStorage.setItem("aitibo:lang", I18N.lang); } catch {}
  }
  I18N.LANGS.forEach((language) => picker.add(new Option(language.label, language.code)));
  picker.value = I18N.lang;
  picker.addEventListener("change", () => {
    if (!isSupportedLanguage(picker.value)) return;
    I18N.lang = picker.value;
    setLanguageUrl(picker.value);
    applyLanguage();
  });
}

document.querySelectorAll("button[data-state]").forEach((button) => button.addEventListener("click", () => selectState(button.dataset.state)));
document.querySelectorAll("[data-subscribe]").forEach((button) => button.addEventListener("click", () => {
  $("#form-message").textContent = "";
  try {
    const saved = JSON.parse(localStorage.getItem("aitibo:notice-demo") || "null");
    if (saved && typeof saved.promise === "boolean" && typeof saved.reset === "boolean") {
      $("#notice-promise").checked = saved.promise;
      $("#notice-reset").checked = saved.reset;
    }
  } catch { $("#form-message").textContent = t("sub.readError"); }
  $("#subscribe-dialog").showModal();
}));
document.querySelectorAll("[data-about]").forEach((button) => button.addEventListener("click", () => $("#about-dialog").showModal()));
document.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => button.closest("dialog").close()));
document.querySelectorAll("dialog").forEach((dialog) => dialog.addEventListener("click", (event) => {
  if (event.target !== dialog) return;
  const rect = dialog.getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
}));
$("#subscribe-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const preference = { promise: $("#notice-promise").checked, reset: $("#notice-reset").checked };
  try { localStorage.setItem("aitibo:notice-demo", JSON.stringify(preference)); }
  catch { $("#form-message").textContent = t("sub.saveError"); return; }
  $("#subscribe-dialog").close();
  toast(preference.promise || preference.reset ? t("toasts.savedOn") : t("toasts.savedOff"));
});
$("#nudge").addEventListener("click", () => {
  clearTimeout(speechTimeout);
  setSpeech(currentState === "reset" ? t("nudge.speechReset") : t("nudge.speech"));
  toast(t("toasts.nudge"));
  window.dispatchEvent(new CustomEvent("aitibo:nudge"));
  speechTimeout = setTimeout(() => setSpeech(stateText(currentState).speech), 4000);
});
$("#evidence-link").addEventListener("click", () => { $("#reasoning").open = true; });
document.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => applyFilter(button.dataset.filter)));
document.querySelectorAll("nav a").forEach((link) => link.addEventListener("click", () => {
  document.querySelectorAll("nav a").forEach((item) => item.classList.toggle("active", item === link));
}));
document.addEventListener("visibilitychange", () => {
  document.title = document.hidden ? t("meta.hiddenTitle") : t("meta.title");
  updateTimer();
});
document.querySelectorAll("[data-gift]").forEach((button) => button.addEventListener("click", () => {
  const kind = button.dataset.gift;
  const lines = t("giftLines." + kind + "." + currentState);
  if (!Array.isArray(lines) || !lines.length) return;
  const count = Number(button.dataset.count || 0);
  button.dataset.count = String(count + 1);
  setSpeech(lines[count % lines.length]);
  clearTimeout(speechTimeout);
  speechTimeout = setTimeout(() => setSpeech(stateText(currentState).speech), 6500);
  toast(t("toasts.gift"));
  window.dispatchEvent(new CustomEvent("aitibo:gift", { detail: { kind, button } }));
}));

$("#draw-fortune").addEventListener("click", () => {
  const all = fortunes();
  if (!all.length) return;
  lastFortune = (lastFortune + 1 + Math.floor(Math.random() * (all.length - 1))) % all.length;
  renderFortune();
  window.dispatchEvent(new CustomEvent("aitibo:fortune"));
  toast(t("toasts.fortune"));
});
$("#copy-fortune").addEventListener("click", async () => {
  const all = fortunes();
  if (lastFortune < 0 || !all[lastFortune]) return;
  const fortune = all[lastFortune];
  const copy = t("fortune.copyTpl", fortune);
  try { await navigator.clipboard.writeText(copy); toast(t("toasts.copied")); }
  catch { toast(t("toasts.copyFail")); }
});

initLanguagePicker();
applyLanguage();
setInterval(updateTimer, 15000);
