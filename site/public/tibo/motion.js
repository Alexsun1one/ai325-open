"use strict";

// Animation is an optional view layer. Domain state and translated speech stay in app.js.
(() => {
  const artwork = document.querySelector("#artwork");
  const sprite = document.querySelector("#hero-sprite");
  if (!artwork || !sprite || !Element.prototype.animate) return;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const statePosition = { waiting:"0%", soon:"50%", reset:"100%" };
  const ease = "cubic-bezier(.22,1,.36,1)";
  const running = new Set();
  const transient = new Set();
  let sceneAnimations = [];
  let particleAnimations = [];
  let transitionId = 0;
  let paused = false;
  let onScreen = true;
  let speechAnimation;
  let reactionAnimation;

  function element(tag, className, parent, copy) {
    const node = document.createElement(tag);
    node.className = className;
    node.setAttribute("aria-hidden", "true");
    if (copy) node.textContent = copy;
    parent.append(node);
    return node;
  }
  const stage = element("div", "motion-stage", artwork);
  stage.append(sprite);
  stage.dataset.scene = document.body.dataset.state || "waiting";
  const actor = element("div", "motion-actor", stage);
  const atmosphere = element("div", "motion-atmosphere", stage);
  for (let i = 0; i < 3; i++) element("i", "motion-steam", atmosphere);
  for (let i = 0; i < 3; i++) element("span", "motion-sleep", atmosphere, "z");
  element("i", "motion-ring", atmosphere);
  element("i", "motion-halo", atmosphere);
  [[20,20],[75,18],[85,37],[30,43],[67,50]].forEach(([x,y], i) => {
    const spark = element("span", "motion-spark", atmosphere, "✦");
    spark.style.left = x + "%";
    spark.style.top = y + "%";
    spark.style.animationDelay = -i * .65 + "s";
  });
  const burst = element("div", "motion-burst", artwork);
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "motion-toggle";
  document.querySelector(".offerings-note").after(toggle);
  // This component owns only its two UI labels; all narrative copy comes from i18n.js.
  const labels = {
    "zh-CN":["暂停动画","播放动画"], en:["Pause animation","Play animation"],
    ja:["アニメーションを停止","アニメーションを再生"], fr:["Suspendre les animations","Activer les animations"],
    es:["Pausar animaciones","Activar animaciones"], pt:["Pausar animações","Ativar animações"],
    ko:["애니메이션 일시 정지","애니메이션 재생"]
  };
  try { paused = localStorage.getItem("aitibo:motion-paused") === "true"; } catch {}
  const active = () => !reduced.matches && !paused && !document.hidden && onScreen;

  function animate(node, frames, options = {}) {
    if (!active()) return null;
    const animation = node.animate(frames, {duration:420,easing:ease,fill:"none",...options});
    running.add(animation);
    animation.finished.catch(() => {}).finally(() => running.delete(animation));
    return animation;
  }
  function temporary(node, animation) {
    transient.add(node);
    if (!animation) { node.remove(); transient.delete(node); return; }
    animation.finished.catch(() => {}).finally(() => {node.remove();transient.delete(node);});
  }
  function cancelScene() {
    transitionId++;
    sceneAnimations.forEach(animation => animation?.cancel());
    sceneAnimations = [];
    particleAnimations.forEach(animation => animation?.cancel());
    particleAnimations = [];
    artwork.querySelectorAll(".motion-previous,.motion-cursor").forEach(node => node.remove());
    burst.replaceChildren();
    delete artwork.dataset.motionPhase;
  }
  function stop() {
    cancelScene();
    running.forEach(animation => animation.cancel());
    running.clear();
    transient.forEach(node => node.remove());
    transient.clear();
  }
  function syncMotion() {
    document.body.classList.toggle("motion-paused",paused);
    document.body.classList.toggle("motion-reduced",reduced.matches);
    document.body.classList.toggle("motion-suspended",document.hidden || !onScreen);
    toggle.textContent = (labels[document.documentElement.lang] || labels.en)[paused || reduced.matches ? 1 : 0];
    toggle.setAttribute("aria-pressed",String(!paused && !reduced.matches));
    toggle.hidden = reduced.matches;
    if (!active()) stop();
  }
  toggle.addEventListener("click",() => {
    paused = !paused;
    try {localStorage.setItem("aitibo:motion-paused",String(paused));} catch {}
    syncMotion();
  });
  reduced.addEventListener("change",syncMotion);
  document.addEventListener("visibilitychange",syncMotion);
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(entries => {
      onScreen = entries[0].isIntersecting;
      syncMotion();
    },{threshold:0}).observe(artwork);
  }

  function tokenBurst() {
    if (!active()) return;
    particleAnimations.forEach(animation => animation?.cancel());
    particleAnimations = [];
    burst.replaceChildren();
    const particle = (node,frames,options) => {
      const animation = animate(node,frames,options);
      particleAnimations.push(animation);
      temporary(node,animation);
    };
    const width = artwork.clientWidth;
    const height = artwork.clientHeight;
    const ring = element("i", "motion-impact", burst);
    particle(ring,[{opacity:.85,transform:"scale(.1)"},{opacity:0,transform:"scale(2.3)"}],{duration:800});
    for (let i = 0; i < 24; i++) {
      const token = element("span", "motion-token", burst,["↻","{ }","✦","</>"][i % 4]);
      const angle = Math.PI * (1.12 + i / 24 * .78);
      const dx = Math.cos(angle) * width * (.25 + Math.random() * .3);
      const dy = Math.sin(angle) * height * (.8 + Math.random() * .3);
      particle(token,[
        {opacity:0,transform:"translate(-50%,0) scale(.2) rotate(0deg)",offset:0},
        {opacity:1,transform:`translate(${dx*.55}px,${dy*.8}px) scale(1) rotate(${dx/5}deg)`,offset:.35},
        {opacity:1,transform:`translate(${dx}px,${dy}px) scale(1) rotate(${dx/2}deg)`,offset:.65},
        {opacity:0,transform:`translate(${dx*1.1}px,${height*.45}px) scale(.8) rotate(${dx}deg)`,offset:1}
      ],{duration:1800 + i * 22,delay:i * 13,easing:"cubic-bezier(.18,.55,.48,1)"});
    }
  }

  function transition(state, previous) {
    cancelScene();
    if (!active()) return;
    const id = transitionId;
    artwork.dataset.motionPhase = "anticipation";
    const old = element("div", "motion-previous", artwork);
    old.style.backgroundPosition = "50% " + statePosition[previous || state];
    const reset = state === "reset";
    const length = reset ? 1100 : 650;
    const outgoing = animate(old,[
      {opacity:1,transform:"scale(1)",offset:0},
      {opacity:1,transform:reset ? "translateY(3px) scale(.975)" : "translateY(2px) scale(.99)",offset:.26},
      {opacity:0,transform:reset ? "translateY(7px) scale(.96)" : "translateY(-8px) scale(1.035)",offset:.65},
      {opacity:0,transform:"scale(1.03)",offset:1}
    ],{duration:length});
    sceneAnimations.push(outgoing);
    temporary(old,outgoing);
    sceneAnimations.push(animate(stage,[
      {opacity:0,transform:"translateY(12px) scale(.97)",offset:0},
      {opacity:0,transform:"translateY(12px) scale(.97)",offset:.27},
      {opacity:1,transform:reset ? "translateY(-4px) scale(1.025)" : "translateY(-2px) scale(1.01)",offset:.72},
      {opacity:1,transform:"translateY(0) scale(1)",offset:1}
    ],{duration:length}));
    if (reset) {
      const hand = element("span", "motion-cursor", artwork,"☝");
      const handAnimation = animate(hand,[
        {opacity:0,transform:"translate(-10px,-45px) rotate(170deg)",offset:0},
        {opacity:1,transform:"translate(-10px,-22px) rotate(170deg)",offset:.3},
        {opacity:1,transform:"translate(-10px,5px) rotate(180deg) scale(.9)",offset:.58},
        {opacity:0,transform:"translate(-10px,-20px) rotate(170deg)",offset:1}
      ],{duration:580});
      temporary(hand,handAnimation);
      sceneAnimations.push(handAnimation);
      handAnimation?.finished.then(() => {
        if (id !== transitionId || !active()) return;
        artwork.dataset.motionPhase = "celebration";
        tokenBurst();
      }).catch(() => {});
    }
    outgoing?.finished.then(() => { if (id === transitionId) artwork.dataset.motionPhase = "idle"; }).catch(() => {});
  }

  window.addEventListener("aitibo:state",({detail}) => {
    stage.dataset.scene = detail.state;
    syncMotion();
    if (detail.animate) transition(detail.state,detail.previous);
    else cancelScene();
  });
  window.addEventListener("aitibo:speech",() => {
    speechAnimation?.cancel();
    speechAnimation = animate(document.querySelector("#speech"),[
      {opacity:.3,transform:"rotate(2deg) scale(.88)"},
      {opacity:1,transform:"rotate(8deg) scale(1.03)",offset:.65},
      {opacity:1,transform:"rotate(6deg) scale(1)"}
    ],{duration:440});
  });
  window.addEventListener("aitibo:nudge",() => {
    reactionAnimation?.cancel();
    reactionAnimation = animate(actor,[{transform:"scale(1.02) rotate(0deg)"},{transform:"scale(1.02) rotate(-7deg)",offset:.2},{transform:"scale(1.02) rotate(5deg)",offset:.45},{transform:"scale(1.02) rotate(-2deg)",offset:.7},{transform:"scale(1.015) rotate(0deg)"}],{duration:700});
    if (document.body.dataset.state === "reset") tokenBurst();
  });

  function giftEffect(kind,button) {
    if (!active()) return;
    // Bound temporary effects even when a visitor drums on a gift button.
    if (transient.size > 65) return;
    const from = button.getBoundingClientRect();
    const rect = artwork.getBoundingClientRect();
    const start = {x:from.left + from.width/2 - 16,y:from.top};
    const target = {x:rect.left + rect.width * (kind === "coffee" ? .2 : .46),y:rect.top + rect.height * (kind === "coffee" ? .62 : .45)};
    const dx = target.x - start.x;
    const dy = target.y - start.y;
    const item = element("span", "motion-gift", document.body,{coffee:"☕",razor:"🪒",pray:"🙏"}[kind]);
    item.style.left = start.x + "px";
    item.style.top = start.y + "px";
    const frames = [
      {opacity:0,transform:"translate(0,0) scale(.5) rotate(-12deg)",offset:0},
      {opacity:1,transform:`translate(${dx*.55}px,${dy-70}px) scale(1.25) rotate(14deg)`,offset:.28},
      {opacity:1,transform:`translate(${dx}px,${dy}px) scale(1.2) rotate(-10deg)`,offset:.5}
    ];
    if (kind === "razor") {
      frames.push({opacity:1,transform:`translate(${dx+28}px,${dy-14}px) rotate(20deg)`,offset:.63},{opacity:1,transform:`translate(${dx-12}px,${dy+9}px) rotate(-20deg)`,offset:.78});
    } else if (kind === "coffee") {
      frames.push({opacity:1,transform:`translate(${dx+15}px,${dy-3}px) rotate(-30deg)`,offset:.74});
    }
    frames.push({opacity:0,transform:`translate(${dx}px,${dy-25}px) scale(.6) rotate(0deg)`,offset:1});
    const flight = animate(item,frames,{duration:1600,easing:"cubic-bezier(.25,.46,.45,.94)"});
    temporary(item,flight);
    if (kind === "razor" || kind === "pray") {
      for (let i = 0; i < 8; i++) {
        const bit = element("span",kind === "razor" ? "motion-stubble" : "motion-prayer",document.body,kind === "pray" ? "✦" : "");
        bit.style.left = target.x + (i-4)*7 + "px";
        bit.style.top = target.y + "px";
        temporary(bit,animate(bit,[{opacity:0,transform:"translateY(0) scale(.4)"},{opacity:1,offset:.2},{opacity:0,transform:`translate(${(i-4)*9}px,${kind === "razor" ? 85 : -100}px) rotate(${i*37}deg) scale(1)`}],{delay:850+i*35,duration:900}));
      }
    }
    reactionAnimation?.cancel();
    reactionAnimation = animate(actor,[{transform:"scale(1.015) rotate(0deg)"},{transform:`scale(1.02) rotate(${kind === "razor" ? -4 : 2}deg)`,offset:.6},{transform:"scale(1.015) rotate(0deg)"}],{delay:600,duration:800});
  }
  window.addEventListener("aitibo:gift",({detail}) => giftEffect(detail.kind,detail.button));
  window.addEventListener("aitibo:fortune",() => {
    // Fortune is lower on the page, so its animation is independent of hero visibility.
    if (reduced.matches || paused || document.hidden) return;
    const ticket = document.querySelector(".fortune-ticket");
    ticket.getAnimations().forEach(animation => animation.cancel());
    const animation = ticket.animate([
      {opacity:.35,transform:"perspective(700px) rotateX(-75deg) translateY(-12px)"},
      {opacity:1,transform:"perspective(700px) rotateX(12deg) translateY(3px)",offset:.65},
      {opacity:1,transform:"perspective(700px) rotateX(0) translateY(0)"}
    ],{duration:700,easing:ease});
    running.add(animation);
    animation.finished.catch(() => {}).finally(() => running.delete(animation));
  });

  syncMotion();
  // Small stagger only on entry; long-form content remains visible without JavaScript.
  [".hero-copy > .eyebrow","#hero-title","#status","#hero-line",".timer-block",".hero-actions",".hero-scene"].forEach((selector,i) => {
    animate(document.querySelector(selector),[{opacity:0,transform:"translateY(16px)"},{opacity:1,transform:"translateY(0)"}],{duration:640,delay:i*65,fill:"backwards"});
  });
})();
