"use strict";
(() => {
  const labels = {"zh-CN":"摸鱼实验室",en:"Playground",ja:"遊び場",fr:"Laboratoire ludique",es:"Laboratorio lúdico",pt:"Laboratório de diversão",ko:"놀이터"};
  const render = () => { document.getElementById("ai325-return").textContent = "← ai325 · " + (labels[document.documentElement.lang] || labels.en); };
  document.getElementById("language-select").addEventListener("change", render);
  render();
})();
