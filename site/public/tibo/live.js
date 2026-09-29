"use strict";
(() => {
  // UI strings only. Dates, posts and state always come from the public snapshot.
  const copy = {
    "zh-CN": ["公开动态观测","正在连接观测数据…","暂时无法更新","尚未取得可信原帖","暂未发现重置线索","他公开预告了重置","他公开声称已重置","公开检索，可能有遗漏","公开公告不代表你的账户额度已恢复。","原帖","最近检查","最近成功采集","漫画演示 · 不代表当前状态","返回观测","距最近一次公开重置公告","暂无可核验的重置时间","展示最近 {n} 条已收录动态，不代表全部帖子","来源：Tibo 的公开 X 内容","内容已过期，暂不判断当前状态","有来源才判断；玩笑、引用和重置券均单独处理。","最近收录的原帖","原帖判断","采集尚未接通","最近采集失败，保留已有记录","查看原文","已预告","尚无","公开声称","等待确认","采集时间","未知","没有经过验证的动态时，不推断当前额度或重置时间。","机器翻译","查看原文","翻译待补 · 暂显原文","以原帖为准"],
    en:["Public activity watch","Connecting to observations…","Update unavailable","No verified post yet","No reset signal found","He publicly announced a reset plan","He publicly claims a reset","Public search may miss posts","A public announcement does not confirm your account quota.","Original post","Last check","Last successful fetch","Comic demo · not current status","Back to observations","Since the latest public reset claim","No verifiable reset time","Showing {n} recent collected posts, not the full timeline","Source: Tibo’s public X posts","Outdated evidence; current status unknown","Check sources; jokes, quotes and reset credits are treated separately.","Latest collected posts","Source-based reading","Collection not connected yet","Fetch failed; previous records retained","View source","Announced","None found","Public claim","Unconfirmed","Fetched","Unknown","Without verified posts, no current quota or reset time is inferred.","Machine translation","View original","Translation pending · showing original","Original post prevails"],
    ja:["公開投稿ウォッチ","観測データに接続中…","更新できません","検証済みの投稿はまだありません","リセットの兆候は未確認","リセットの予告がありました","本人がリセットを報告","公開検索のため見落としがあります","公開発表は個人の利用枠の回復を保証しません。","原文","最終確認","最終取得成功","漫画デモ · 現在の状態ではありません","観測に戻る","直近の公開リセット報告から","検証可能なリセット時刻はありません","収集済みの最新 {n} 件を表示。全投稿ではありません","出典：Tibo の公開 X 投稿","情報が古いため現在の状態は不明","出典を確認し、冗談・引用・リセット券を区別します。","最近収集した投稿","原文に基づく判断","収集はまだ未接続","取得失敗。以前の記録を保持","原文を見る","予告あり","未確認","本人の報告","確認待ち","取得時刻","不明","検証済み投稿なしに利用枠やリセット時刻を推定しません。","機械翻訳","原文を表示","翻訳は未収録 · 原文を表示中","原文が基準"],
    fr:["Veille des publications","Connexion aux observations…","Mise à jour indisponible","Aucune publication vérifiée","Aucun signal de réinitialisation","Il annonce une réinitialisation à venir","Il déclare avoir réinitialisé les quotas","La recherche publique peut manquer des publications","Une annonce publique ne confirme pas le quota de votre compte.","Texte original","Dernière vérification","Dernière collecte réussie","Démo BD · pas le statut actuel","Retour à la veille","Depuis la dernière annonce de réinitialisation","Aucune date de réinitialisation vérifiable","{n} publications récentes collectées, pas la totalité","Source : publications X publiques de Tibo","Informations anciennes ; statut actuel inconnu","Les sources sont vérifiées ; blagues, citations et crédits sont distingués.","Publications récemment collectées","Lecture des sources","Collecte pas encore connectée","Échec de collecte ; anciens éléments conservés","Voir la source","Annoncée","Aucun signal","Déclaration publique","Non confirmé","Collecte","Inconnu","Sans publication vérifiée, aucun quota ou horaire actuel n’est déduit.","Traduction automatique","Voir l’original","Traduction en attente · original affiché","L’original fait foi"],
    es:["Observación de publicaciones","Conectando las observaciones…","Actualización no disponible","Aún no hay publicaciones verificadas","Sin señales de reinicio","Anunció un próximo reinicio","Afirma públicamente haber reiniciado","La búsqueda pública puede omitir publicaciones","Un anuncio público no confirma la cuota de tu cuenta.","Texto original","Última revisión","Última recopilación correcta","Demo de cómic · no es el estado actual","Volver a la observación","Desde el último anuncio público de reinicio","Sin una fecha de reinicio verificable","Se muestran {n} publicaciones recopiladas, no toda la cronología","Fuente: publicaciones públicas de Tibo en X","Información antigua; estado actual desconocido","Se comprueban fuentes y se distinguen bromas, citas y cupones.","Publicaciones recopiladas recientemente","Lectura de fuentes","Recopilación aún sin conectar","Falló la recopilación; se conservan los registros","Ver fuente","Anunciado","Sin señales","Afirmación pública","Sin confirmar","Recopilado","Desconocido","Sin publicaciones verificadas, no se deducen cuotas ni fechas actuales.","Traducción automática","Ver original","Traducción pendiente · se muestra el original","Prevalece el original"],
    pt:["Observação de publicações","Conectando as observações…","Atualização indisponível","Ainda sem publicação verificada","Nenhum sinal de redefinição","Ele anunciou uma futura redefinição","Ele afirma ter redefinido os limites","A busca pública pode deixar publicações de fora","Um anúncio público não confirma a cota da sua conta.","Texto original","Última verificação","Última coleta bem-sucedida","Demonstração em quadrinhos · não é o estado atual","Voltar à observação","Desde o último anúncio público de redefinição","Sem horário verificável de redefinição","Mostrando {n} publicações coletadas, não a linha do tempo completa","Fonte: publicações públicas de Tibo no X","Informação antiga; estado atual desconhecido","Verificamos fontes e distinguimos piadas, citações e cupons.","Publicações coletadas recentemente","Leitura das fontes","Coleta ainda não conectada","Falha na coleta; registros anteriores preservados","Ver fonte","Anunciada","Nenhum sinal","Afirmação pública","Não confirmado","Coletado","Desconhecido","Sem publicações verificadas, não inferimos cotas nem horários atuais.","Tradução automática","Ver original","Tradução pendente · exibindo o original","O original prevalece"],
    ko:["공개 게시물 관측","관측 데이터 연결 중…","업데이트할 수 없습니다","검증된 게시물이 아직 없습니다","초기화 신호가 없습니다","초기화를 예고했습니다","초기화했다고 공개적으로 밝혔습니다","공개 검색은 일부 게시물을 놓칠 수 있습니다","공개 발표가 내 계정의 사용량 복구를 보장하지는 않습니다.","원문","최근 확인","최근 수집 성공","만화 데모 · 현재 상태가 아닙니다","관측으로 돌아가기","최근 공개 초기화 발표 이후","검증 가능한 초기화 시각이 없습니다","최근 수집한 {n}개를 표시하며 전체 게시물이 아닙니다","출처: Tibo의 공개 X 게시물","오래된 정보이므로 현재 상태는 알 수 없습니다","출처를 확인하고 농담, 인용, 초기화 쿠폰을 구분합니다.","최근 수집한 게시물","원문 기반 판단","수집이 아직 연결되지 않았습니다","수집 실패. 이전 기록을 보존합니다","원문 보기","예고됨","없음","공개 주장","확인되지 않음","수집 시각","알 수 없음","검증된 게시물 없이는 현재 사용량이나 초기화 시간을 추정하지 않습니다.","기계 번역","원문 보기","번역 대기 중 · 원문 표시","원문이 기준"]
  };
  const publicStatusTitles = {"zh-CN":"公开重置状态",en:"Public reset status",ja:"公開リセット状況",fr:"État public de la réinitialisation",es:"Estado público del reinicio",pt:"Estado público da redefinição",ko:"공개 초기화 상태"};
  const q = selector => document.querySelector(selector);
  const txt = (selector, value) => {const el=q(selector);if(el)el.textContent=value;};
  const c = index => (copy[document.documentElement.lang] || copy.en)[index];
  const date = value => {const time=Date.parse(value);return Number.isFinite(time) && time<=Date.now()+60000 ? time : null;};
  const format = time => time ? new Date(time).toLocaleString(document.documentElement.lang) : "—";
  const validURL = (value,id) => typeof value === "string" && /^https:\/\/x\.com\/thsottiaux\/status\/\d+$/.test(value) && (!id || value.endsWith("/"+id));
  let snapshot=null, failed=false, loading=true, demo=false, busy=false, previousArt="waiting";
  const badge=document.createElement("div");badge.className="live-badge";badge.hidden=true;
  const badgeText=document.createElement("span"), back=document.createElement("button");
  back.className="live-back";back.type="button";badge.append(badgeText,back);q(".state-picker").after(badge);
  function normalize(raw) {
    if(!raw || raw.schema_version!==1 || raw.source?.handle!=="thsottiaux" || raw.source?.platform!=="x" || !["ok","error","unconfigured"].includes(raw.health) || !Array.isArray(raw.posts)) throw Error("SCHEMA");
    const posts=raw.posts.filter(p=>p && typeof p.text==="string" && typeof p.id==="string" && validURL(p.url,p.id) && date(p.created_at)).slice(0,50);
    return {...raw,posts:posts.sort((a,b)=>date(b.created_at)-date(a.created_at))};
  }
  function state() {
    const fetched=date(snapshot?.fetched_at);
    if(failed || snapshot?.health!=="ok" || !fetched || Date.now()-fetched>86400000)return "unknown";
    const value=snapshot.forecast?.state;
    if(!["waiting","soon","reset"].includes(value))return "unknown";
    // An open announced window (fresh timeline, source_calendar basis, citing a
    // collected promise post) extends "soon" beyond the post's 24h freshness —
    // the monitor downgrades forecast.state to waiting once the post ages out.
    const rt=snapshot.reset_timeline, nr=rt?.next_reset;
    const ws=Date.parse(nr?.window_start), we=Date.parse(nr?.window_end);
    const windowOpen=rt?.fresh===true && nr?.status==="announced" && nr?.time_basis==="source_calendar" && validURL(nr?.source_url) && Number.isFinite(ws) && Number.isFinite(we) && ws<we && we>Date.now() && snapshot.posts.some(p=>p.url===nr.source_url && p.kind==="promise");
    if(value!=="waiting") {
      const expected=value==="reset"?"reset":"promise";
      const reason=value==="reset"?"PUBLIC_RESET_CLAIM_NOT_ACCOUNT_CONFIRMATION":"EXPLICIT_FUTURE_PUBLIC_CLAIM";
      const strict=snapshot.forecast.reason===reason && validURL(snapshot.forecast.source_url) && snapshot.posts.some(p=>p.url===snapshot.forecast.source_url && p.kind===expected && Date.now()-date(p.created_at)<=86400000);
      if(!strict && !(value==="soon"&&windowOpen))return "unknown";
    } else if(windowOpen) return "soon";
    return value;
  }
  function timer() {
    if(demo)return;
    const candidate=date(snapshot?.forecast?.last_reset_at);
    const at=!failed && snapshot?.health==="ok" && snapshot.posts.some(p=>p.kind==="reset" && date(p.created_at)===candidate) ? candidate : null;
    txt("#timer-label",at ? c(14) : c(15));
    const seconds=at ? Math.max(0,Math.floor((Date.now()-at)/1000)) : null;
    ["days","hours","minutes"].forEach((key,i)=>txt("#"+key,seconds===null?"—":String([Math.floor(seconds/86400),Math.floor(seconds/3600)%24,Math.floor(seconds/60)%60][i]).padStart(2,"0")));
  }
  function renderPosts() {
    q(".featured-post").hidden=true;q(".second-post").hidden=true;
    document.querySelectorAll(".live-post,.live-note").forEach(el=>el.remove());
    const target=q(".feed-follow"), posts=snapshot?.posts?.slice(0,10)||[];
    const lang=document.documentElement.lang, translations=snapshot?.post_translations||{};
    for(const post of posts) {
      const article=document.createElement("article");article.className="post live-post";
      const body=document.createElement("div");body.className="post-content";
      const meta=document.createElement("p");meta.className="post-meta";meta.textContent="Tibo · @thsottiaux · "+format(date(post.created_at));
      const tr=lang==="en"?null:translations[post.id]?.[lang];
      const text=document.createElement("p");text.className="post-quote";text.textContent=typeof tr==="string"&&tr?tr:post.text;
      body.append(meta,text);
      if(typeof tr==="string"&&tr){
        const tag=document.createElement("p");tag.className="live-tr";tag.textContent=c(32)+" · "+c(35);
        const details=document.createElement("details");details.className="live-original";
        const summary=document.createElement("summary");summary.textContent=c(33);
        const orig=document.createElement("p");orig.className="post-quote orig";orig.textContent=post.text;
        details.append(summary,orig);body.append(tag,details);
      }else if(lang!=="en"){
        const note=document.createElement("p");note.className="live-tr pending";note.textContent=c(34);body.append(note);
      }
      const link=document.createElement("a");link.href=post.url;link.target="_blank";link.rel="noopener noreferrer";link.textContent=c(24)+" ↗";
      body.append(link);article.append(body);target.before(article);
    }
    const note=document.createElement("p");note.className="live-note";note.textContent=posts.length?c(16).replace("{n}",String(posts.length)):c(3);target.before(note);
  }
  function render() {
    window.dispatchEvent(new CustomEvent("aitibo:observations",{detail:{snapshot,failed,loading,demo}}));
    badgeText.textContent=c(12);back.textContent=c(13)+" ↗";
    if(demo){badge.hidden=false;return;}
    window.AITIBO_LIVE_MODE=true;document.body.dataset.view="live";badge.hidden=true;
    const current=state(), art=current==="unknown"?"waiting":current;
    // Keep existing character jokes consistent without replacing the data view.
    currentState=art;
    document.body.dataset.state=art;
    window.dispatchEvent(new CustomEvent("aitibo:state",{detail:{state:art,previous:previousArt,animate:false,live:true}}));
    previousArt=art;
    document.querySelectorAll("button[data-state]").forEach(button=>{button.classList.remove("selected");button.setAttribute("aria-pressed","false");});
    setSpeech(stateText(art).speech);
    const artwork=q("#artwork");if(artwork)artwork.setAttribute("aria-label",stateText(art).alt);
    const title=loading?c(1):(failed||snapshot?.health==="error")?c(2):snapshot?.health==="unconfigured"?c(22):c({unknown:3,waiting:4,soon:5,reset:6}[current]);
    txt("#status",title);txt("#hero-line",current==="reset"?c(8):c(7));
    txt("#forecast-title",publicStatusTitles[document.documentElement.lang] || publicStatusTitles.en);
    txt("#forecast-state",current==="unknown"?c(30):c({waiting:4,soon:5,reset:6}[current]));
    txt("#forecast-description",current==="unknown"?c(31):c(8));
    txt("#reasoning-text",c(19));txt("#reasoning .reasoning-body p:last-child",c(8)+" "+c(7));
    txt(".forecast-footnote",c(11)+": "+format(date(snapshot?.fetched_at)));
    const lastReset=snapshot?.reset_timeline?.last_reset;
    const done=lastReset && date(lastReset.reported_at)!==null && validURL(lastReset.source_url) && snapshot.posts.some(p=>p.url===lastReset.source_url && p.kind==="reset");
    txt("#signal-promise",current==="soon"?c(25):c(26));txt("#signal-activity",format(date(snapshot?.posts?.[0]?.created_at)));txt("#signal-completion",done||current==="reset"?c(27):c(28));
    txt(".preview-bar > span:first-child",c(0));
    txt(".preview-bar > span:last-child",loading?c(1):(failed||snapshot?.health==="error")?c(23):c(10)+": "+format(date(snapshot?.checked_at))+" · "+c(7));
    txt(".feed .section-note",c(20));txt(".forecast .section-note",c(21));
    const descriptions=document.querySelectorAll("#about-dialog .dialog-description");
    if(descriptions[0])descriptions[0].textContent=c(17)+". "+c(19);
    if(descriptions[1])descriptions[1].textContent=c(7)+". "+c(8);
    const meta=q('meta[name="description"]');if(meta)meta.content=c(0)+". "+c(19);
    timer();renderPosts();
  }
  back.addEventListener("click",()=>{demo=false;render();});
  window.addEventListener("aitibo:state",event=>{
    if(!event.detail?.animate || event.detail.live)return;
    demo=true;window.AITIBO_LIVE_MODE=false;document.body.dataset.view="demo";
    document.querySelectorAll(".live-post,.live-note").forEach(el=>el.remove());
    q(".featured-post").hidden=false;q(".second-post").hidden=false;
    translateStatic();updateTimer();render();
  });
  q("#language-select").addEventListener("change",render);
  async function refresh() {
    if(busy || document.hidden)return;
    busy=true;const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),8000);
    try{const response=await fetch("/api/tibo/status",{cache:"no-store",signal:controller.signal});if(!response.ok)throw Error("HTTP");snapshot=normalize(await response.json());failed=false;}
    catch{failed=true;}
    finally{loading=false;busy=false;clearTimeout(timeout);render();}
  }
  document.addEventListener("visibilitychange",()=>{if(!document.hidden)refresh();});
  setInterval(refresh,60000);setInterval(()=>{if(!document.hidden)timer();},15000);
  window.AITIBO_LIVE_MODE=true;render();refresh();
})();
