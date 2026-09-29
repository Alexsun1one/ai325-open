"use strict";

// aitibo.cn i18n — no framework, one global: window.AITIBO_I18N
// 7 locales: zh-CN (source), en, ja, fr, es, pt, ko
window.AITIBO_I18N = (() => {
  const LANGS = [
    { code: "zh-CN", label: "中文" },
    { code: "en", label: "English" },
    { code: "ja", label: "日本語" },
    { code: "fr", label: "Français" },
    { code: "es", label: "Español" },
    { code: "pt", label: "Português" },
    { code: "ko", label: "한국어" }
  ];

  const dicts = {
    "zh-CN": {
      meta: {
        title: "Tibo，今天按了吗？ · aitibo.cn",
        hiddenTitle: "还在等他吗？ · aitibo.cn",
        description: "Tibo，今天按了吗？一个有点着急的重置观测站。本地交互原型。"
      },
      skip: "跳到主要内容",
      brandAria: "aitibo 首页",
      navAria: "主导航",
      langAria: "选择语言",
      nav: { radar: "重置雷达", feed: "他的动态", history: "重置日历", about: "关于", subscribe: "订阅提醒" },
      preview: { badge: "本地交互原型", note: "X 尚未接入 · 切换下方状态体验" },
      hero: {
        eyebrow: "一个有点着急的重置观测站", title: "今天按了吗", mark: "?",
        cta: "重置了叫我", evidence: "查看预测依据", note: "你负责创造，剩下的等他按。"
      },
      speechTag: "本站配文",
      nudge: { label: "戳一下他", hint: "只是玩梗，不会触发重置", speech: "收到，再给我一口咖啡。", speechReset: "按过了，快去开工！" },
      picker: {
        aria: "预览角色状态",
        waiting: "苦等中", waitingSub: "按钮还没动",
        soon: "准备按", soonSub: "他有话说",
        reset: "封神了", resetSub: "重置，开工！"
      },
      sceneCaption: "同一个 Tibo，不同的精神状态。",
      offerings: { aria: "和漫画 Tibo 互动", coffee: "续一杯", razor: "该刮胡子了", pray: "义父救我", note: "纯属玩梗，义父收不到。" },
      feed: { title: "他刚刚说了什么", note: "历史内容演示", follow: "去 X 看 Tibo 的最新动态" },
      post: { disclaimer: "公开发言，不代表当前状态", source: "查看出处" },
      post2: {
        meta: "采访摘意", badge: "背景资料",
        quote: "有时是为体验问题补偿，有时是想和大家一起庆祝。",
        context: "重置按钮是真的。期待，也是真的。",
        source: "Matthew Berman 采访 · 23:37 起", link: "听他说"
      },
      forecast: {
        title: "下一次，有戏吗？", note: "演示判断",
        signals: { promise: "明确预告", activity: "近期动态", completion: "完成公告" },
        reasoningSummary: "看看是怎么判断的",
        reasoningStatic: "正式版本将结合原帖、回复上文、时间和适用范围判断；本页尚未运行自动采集或预测模型。",
        footnote: "有来源才有依据，有承诺也要等确认。"
      },
      history: { title: "每一次，重新开工", sub: "把惊喜记下来，也把不同的重置分清楚。" },
      filters: { aria: "筛选历史类型", all: "全部", reset: "直接重置", banked: "重置券" },
      events: [
        { label: "历史类型示意 · 01", title: "故障补偿", desc: "修好问题，也让大家重新开始。", source: "来源：采访" },
        { label: "历史类型示意 · 02", title: "发放重置券", desc: "留到需要的时候，自己选择使用。", source: "来源：历史索引" },
        { label: "历史类型示意 · 03", title: "庆祝重置", desc: "好日子，值得多写一点代码。", source: "来源：社区转载" }
      ],
      fortune: {
        eyebrow: "等待期间 · 自娱自乐", title: "今日求重置签", sub: "代码可以等，仪式感不能少。",
        pending: "待抽签", initial: "心诚则灵，额度另说。", disclaimer: "本站娱乐文案，与真实重置无关",
        draw: "抽一签", redraw: "再抽一签", copy: "复制我的签文", suffix: " · 纯属娱乐",
        copyTpl: "【今日求重置签 · {rank}】\n{line}\n{detail}\naitibo.cn · 社区二创，纯属娱乐"
      },
      bottom: { note: "愿你的灵感，<br><b>永远比额度多一点。</b>", cta: "下次重置，叫上我" },
      footer: { note: "独立社区二创，与 OpenAI 无隶属关系", tag: "保持热爱，多点耐心。" },
      dialog: { close: "关闭" },
      sub: {
        eyebrow: "下次重置，叫上我", title: "把期待留在这里。",
        desc: "这是提醒功能的交互预览。偏好仅保存在当前浏览器，尚未接入通知服务，不会发送邮件或推送。",
        promise: "他明确预告时", promiseSub: "先听到风声",
        reset: "他宣布重置时", resetSub: "该开工了",
        save: "保存本机偏好",
        readError: "无法读取已有偏好，可以重新选择。", saveError: "浏览器不允许本地存储，偏好未保存。"
      },
      about: {
        eyebrow: "关于这个小站", title: "等一个按钮，<br>也等一点惊喜。",
        desc1: "aitibo.cn 是围绕 Tibo 公开重置动态构思的独立社区项目。这一版是可交互的本地原型：人物状态、计时和判断均为演示，历史资料附出处。",
        desc2: "下一步是接入他的公开 X 动态，区分调侃、预告、直接重置与重置券，让每个判断都能回到原文。漫画台词属于本站二创。",
        ok: "知道了"
      },
      units: { day: "天", hour: "时", min: "分" },
      timer: { demoTag: "演示计时" },
      stateNames: { waiting: "苦等中", soon: "准备按", reset: "重置封神" },
      states: {
        waiting: {
          status: "还在等他", line: "胡子又长了，按钮还没动。", speech: "别急，我就刷会儿 X",
          alt: "胡子拉碴的漫画 Tibo 趴在重置按钮旁，等待重置",
          forecast: "暂无线索…", description: "当前示例内容没有构成明确的重置承诺。别急，先把想做的事记下来。",
          signals: ["未发现", "日常互动", "待确认"], badge: "调侃",
          quote: "“你以为我要宣布重置？我只是来刷刷推。”", context: "历史帖意译 · 2026 年 7 月 15 日",
          semantic: "语义判断：调侃，未承诺重置",
          reasoning: "示例中虽然出现了“重置”，但句子明确否定了重置预告。关键词命中不等于承诺。",
          timerLabel: "距离上次重置"
        },
        soon: {
          status: "他预告了 · 演示", line: "手已经抬起来了，再等一下。", speech: "好好好，手已经抬了。",
          alt: "漫画 Tibo 挑眉微笑，手指悬在红色重置按钮上",
          forecast: "有明确预告", description: "示例发言包含“下午会重置”的承诺。具体范围和实际完成仍需后续确认。",
          signals: ["下午会重置", "明确时间窗口", "等待完成"], badge: "预告",
          quote: "“不用叫我宝贝，下午会重置。”", context: "历史回复意译 · 2026 年 7 月 9 日",
          semantic: "语义判断：未来承诺，尚未宣布完成",
          reasoning: "“下午会重置”含有未来时间与明确动作，因此比泛泛的庆祝消息更强。但原帖没有精确时刻，不生成精确倒计时；历史回复也不作为今天的新公告。",
          timerLabel: "距离上次重置"
        },
        reset: {
          status: "重置封神 · 演示", line: "按钮一按，世界又有了光。", speech: "去吧，做点了不起的。",
          alt: "漫画 Tibo 身披白袍头顶金色光环，按下重置按钮，金色 token 飘落",
          forecast: "宣布重置了！", description: "示例公告使用已完成语气。具体账号是否恢复，仍以产品内的实际额度为准。",
          signals: ["已成为公告", "庆祝新体验", "已宣布完成"], badge: "已宣布",
          quote: "“为庆祝美好的一周，我已重置所有付费套餐的 Codex 额度。”", context: "历史公告意译 · 2026 年 4 月 28 日",
          semantic: "语义判断：已完成公告，范围为 Codex 付费套餐",
          reasoning: "该历史公告使用已完成语气，并说明适用套餐。公告是公共信息，不能直接证明每个账户已经到账；也不能把一次直接重置与发放重置券混为一谈。",
          timerLabel: "本次重置已经过去"
        }
      },
      toasts: {
        preview: "正在预览：{state} · 非实时状态",
        nudge: "只是戳了一下漫画人物，不会影响真实额度。",
        savedOn: "偏好已保存在本机 · 当前不会发送通知",
        savedOff: "已关闭本机提醒偏好",
        gift: "漫画 Tibo 已回应 · 娱乐互动，不会发给本人",
        fortune: "签文已出炉，愿望先替你留着。",
        copied: "签文已复制，可以发给一起等重置的人。",
        copyFail: "浏览器未允许复制，请直接选中签文复制。"
      },
      giftLines: {
        coffee: {
          waiting: ["咖啡续上了，额度还没续。", "这杯算你的，下次重置算我的。", "先别加糖，需求已经够甜了。"],
          soon: ["咖啡放下，别碰我按钮。", "这一口喝完，我再看看。"],
          reset: ["神也需要咖啡因。", "咖啡敬创作者，token 敬理想。"]
        },
        razor: {
          waiting: ["这是胡子，也是你等待的进度条。", "别催了，再催胡子要长出分支了。", "等我重置，连胡子一起 reset。"],
          soon: ["刮完这边，就按那边。", "先重置，后理容。"],
          reset: ["刚封神，别动我的神圣胡茬。", "光环开了美颜，不用刮。"]
        },
        pray: {
          waiting: ["你这一声义父，我的鼠标都抖了。", "不要叫我宝贝……义父也先别叫。", "你的愿望已加入宇宙队列。"],
          soon: ["手都举起来了，你再等等。", "仪式感到位，等公告。"],
          reset: ["额度给你了，别拿去问我帅不帅。", "散会！去把那个项目做出来。"]
        }
      },
      fortunes: [
        { rank: "上上签", line: "义父手一抖，项目全都有。", detail: "宜：把需求写清楚。忌：额度满了却没想法。" },
        { rank: "摸鱼签", line: "额度归零，终于有理由下班。", detail: "宜：起身喝水。忌：对着用量页反复刷新。" },
        { rank: "工程签", line: "重置靠义父，回滚靠自己。", detail: "宜：留好备份。忌：把希望全押在按钮上。" },
        { rank: "胡须签", line: "他的胡子在长，你的需求也在长。", detail: "宜：砍掉一个功能。忌：再加一个小需求。" },
        { rank: "封神签", line: "天降 token 雨，接着写下去。", detail: "宜：完成那个小项目。忌：一次开十个新坑。" },
        { rank: "耐心签", line: "他在刷推，你在刷新。", detail: "宜：看看窗外。忌：把玩笑当作重置预告。" }
      ]
    },

    en: {
      meta: {
        title: "Did Tibo press it today? · aitibo.cn",
        hiddenTitle: "Still waiting for him? · aitibo.cn",
        description: "Did Tibo press it today? A mildly anxious reset observatory. Local interactive prototype."
      },
      skip: "Skip to main content",
      brandAria: "aitibo home",
      navAria: "Main navigation",
      langAria: "Choose language",
      nav: { radar: "Reset Radar", feed: "His Posts", history: "Reset Calendar", about: "About", subscribe: "Get Notified" },
      preview: { badge: "Local interactive prototype", note: "X not connected yet · try the states below" },
      hero: {
        eyebrow: "A mildly anxious reset observatory", title: "did you press it", mark: "?",
        cta: "Ping me when he resets", evidence: "See the reasoning", note: "You build. He presses. Eventually."
      },
      speechTag: "our caption",
      nudge: { label: "Poke him", hint: "just a joke, won't trigger a reset", speech: "Heard. One more coffee first.", speechReset: "Already pressed. Go build!" },
      picker: {
        aria: "Preview character states",
        waiting: "Waiting it out", waitingSub: "button untouched",
        soon: "Warming up", soonSub: "he has something to say",
        reset: "Ascended", resetSub: "reset. let's build!"
      },
      sceneCaption: "Same Tibo, different states of mind.",
      offerings: { aria: "Interact with cartoon Tibo", coffee: "One more coffee", razor: "Time for a shave", pray: "Godfather, save me", note: "Just for laughs. The godfather can't hear you." },
      feed: { title: "What he just said", note: "Past posts, demo only", follow: "See Tibo's latest on X" },
      post: { disclaimer: "Public remarks, not a live status", source: "See source" },
      post2: {
        meta: "Interview excerpt", badge: "Background",
        quote: "Sometimes it's compensation for a rough patch; sometimes he just wants to celebrate with everyone.",
        context: "The reset button is real. So is the anticipation.",
        source: "Matthew Berman interview · from 23:37", link: "Hear him"
      },
      forecast: {
        title: "Next reset — any chance?", note: "Demo verdict",
        signals: { promise: "Clear promise", activity: "Recent activity", completion: "Done notice" },
        reasoningSummary: "See how we read it",
        reasoningStatic: "The full version will weigh the original post, reply context, timing and scope. This page runs no scraper and no prediction model yet.",
        footnote: "No source, no case. And even a promise needs a confirmation."
      },
      history: { title: "Every reset, a fresh start", sub: "Record the surprises — and tell one kind of reset from another." },
      filters: { aria: "Filter history types", all: "All", reset: "Direct reset", banked: "Reset credits" },
      events: [
        { label: "Sample type · 01", title: "Apology reset", desc: "Fixed the bug, then let everyone start over.", source: "Source: interview" },
        { label: "Sample type · 02", title: "Reset credits", desc: "Banked for later — use them when you need them.", source: "Source: history index" },
        { label: "Sample type · 03", title: "Celebration reset", desc: "A good day deserves a few more lines of code.", source: "Source: community repost" }
      ],
      fortune: {
        eyebrow: "While we wait · self-amusement", title: "Today's reset fortune", sub: "Code can wait. Rituals can't.",
        pending: "Not drawn", initial: "Faith helps. Quotas may differ.", disclaimer: "Just-for-fun copy, unrelated to real resets",
        draw: "Draw one", redraw: "Draw again", copy: "Copy my fortune", suffix: " · just for fun",
        copyTpl: "[Today's Reset Fortune · {rank}]\n{line}\n{detail}\naitibo.cn · fan-made, just for fun"
      },
      bottom: { note: "May your inspiration<br><b>always outlast your quota.</b>", cta: "Next reset, count me in" },
      footer: { note: "Independent fan project, not affiliated with OpenAI", tag: "Stay curious. Stay patient." },
      dialog: { close: "Close" },
      sub: {
        eyebrow: "Next reset, count me in", title: "Leave the hoping here.",
        desc: "This is a preview of the reminder feature. Preferences are saved in this browser only — no notification service is connected, and nothing is emailed or pushed.",
        promise: "When he clearly teases it", promiseSub: "hear it first",
        reset: "When he announces it", resetSub: "time to build",
        save: "Save on this device",
        readError: "Couldn't read saved preferences — pick again.", saveError: "This browser blocked local storage. Preferences not saved."
      },
      about: {
        eyebrow: "About this little site", title: "Waiting on a button,<br>and a little surprise.",
        desc1: "aitibo.cn is an independent community project built around Tibo's public reset moves. This version is a local interactive prototype: states, timer and verdicts are all demo; historical material comes with sources.",
        desc2: "Next step is wiring in his public X feed and telling teasing, teasers, direct resets and reset credits apart — every verdict traceable to the source. Cartoon lines are our own fan work.",
        ok: "Got it"
      },
      units: { day: "d", hour: "h", min: "m" },
      timer: { demoTag: "demo timer" },
      stateNames: { waiting: "Waiting it out", soon: "Warming up", reset: "Ascended" },
      states: {
        waiting: {
          status: "Still waiting on him", line: "The beard grows. The button stays put.", speech: "Chill — I'm just scrolling X.",
          alt: "A stubbly cartoon Tibo slumped beside the reset button, still waiting",
          forecast: "No leads yet…", description: "The sample post doesn't add up to a real reset promise. Hang tight — jot down what you'll build first.",
          signals: ["None found", "Everyday chatter", "Unconfirmed"], badge: "Teasing",
          quote: "“You thought I was announcing a reset? I just came to scroll.”", context: "Paraphrased past post · July 15, 2026",
          semantic: "Read: teasing, no reset promised",
          reasoning: "The sample mentions “reset”, but the sentence clearly denies a reset announcement. A keyword hit isn't a promise.",
          timerLabel: "Since the last reset"
        },
        soon: {
          status: "He teased it · demo", line: "Hand's up. Give him a second.", speech: "Fine, fine — hand's already up.",
          alt: "Cartoon Tibo smirks, finger hovering over the red reset button",
          forecast: "Clear promise on record", description: "The sample line includes a promise to “reset this afternoon”. Scope and actual completion still need confirmation.",
          signals: ["“This afternoon”", "Clear time window", "Awaiting completion"], badge: "Teaser",
          quote: "“Don't call me baby — the reset lands this afternoon.”", context: "Paraphrased past reply · July 9, 2026",
          semantic: "Read: future promise, completion not yet announced",
          reasoning: "“Reset this afternoon” carries a time and a clear action, so it outweighs vague celebration. But the original reply has no exact minute, so no precise countdown — and an old reply isn't today's news.",
          timerLabel: "Since the last reset"
        },
        reset: {
          status: "Ascended · demo", line: "One press, and the world has light again.", speech: "Go. Build something great.",
          alt: "Cartoon Tibo in a white robe with a golden halo pressing the reset button as golden tokens rain down",
          forecast: "Reset announced!", description: "The sample announcement speaks in past tense. Whether your own quota came back still depends on what the product shows.",
          signals: ["It's official", "Celebrating the new", "Marked complete"], badge: "Announced",
          quote: "“To celebrate a wonderful week, I've reset Codex rate limits for all paid plans.”", context: "Paraphrased past announcement · April 28, 2026",
          semantic: "Read: completed announcement, Codex paid plans only",
          reasoning: "The past announcement uses completed-action phrasing and names the plans it covers. A public post can't prove every account got it — and a direct reset is not the same as handing out reset credits.",
          timerLabel: "Since this reset"
        }
      },
      toasts: {
        preview: "Previewing: {state} · not live",
        nudge: "You poked a cartoon character. Real quotas are unaffected.",
        savedOn: "Preference saved on this device · nothing will be sent",
        savedOff: "Local reminder preference turned off",
        gift: "Cartoon Tibo responded · for fun, never sent to him",
        fortune: "Fortune drawn. Your wish is safe with us.",
        copied: "Fortune copied — send it to a fellow waiter.",
        copyFail: "Clipboard blocked — select the text and copy it yourself."
      },
      giftLines: {
        coffee: {
          waiting: ["Coffee's refilled. The quota isn't.", "This cup's on you — the next reset's on me.", "Hold the sugar; the requirements are sweet enough."],
          soon: ["Put the coffee down. Hands off my button.", "Let me finish this sip, then we'll see."],
          reset: ["Even a legend runs on caffeine.", "Coffee to the builders, tokens to the dreamers."]
        },
        razor: {
          waiting: ["It's not a beard, it's your waiting progress bar.", "Stop nagging — the beard is about to fork.", "When I reset, the beard gets a reset too."],
          soon: ["Shave this side, press that side.", "Reset first, grooming second."],
          reset: ["Freshly ascended — hands off the sacred stubble.", "The halo has a beauty filter. No shave needed."]
        },
        pray: {
          waiting: ["That “godfather” made my mouse shake.", "Don't call me baby… and let's skip “godfather” too.", "Your wish has joined the cosmic queue."],
          soon: ["The hand is up. Two more minutes.", "The vibe is right — wait for the announcement."],
          reset: ["Quota granted. Don't waste it asking if I'm handsome.", "Meeting adjourned! Go ship that project."]
        }
      },
      fortunes: [
        { rank: "Jackpot", line: "One flick of the godfather's wrist, and every project ships.", detail: "Do: write crisp requirements. Avoid: a full quota with zero ideas." },
        { rank: "Slacker", line: "Quota zero — finally an excuse to clock out.", detail: "Do: drink water. Avoid: refreshing the usage page on loop." },
        { rank: "Engineer's", line: "Resets come from the godfather; rollbacks come from you.", detail: "Do: keep backups. Avoid: betting everything on one button." },
        { rank: "Beard", line: "His beard grows. So does your requirements list.", detail: "Do: cut one feature. Avoid: adding one more tiny ask." },
        { rank: "Ascension", line: "Tokens rain from the sky. Keep writing.", detail: "Do: finish that little project. Avoid: opening ten new tabs of ambition." },
        { rank: "Patience", line: "He's scrolling. You're refreshing.", detail: "Do: look out the window. Avoid: reading a joke as a reset teaser." }
      ]
    },

    ja: {
      meta: {
        title: "Tibo、今日は押した？ · aitibo.cn",
        hiddenTitle: "まだ待ってる？ · aitibo.cn",
        description: "Tibo、今日は押した？ちょっとソワソワするリセット観測所。ローカル・インタラクティブ原型。"
      },
      skip: "本文へスキップ",
      brandAria: "aitibo ホーム",
      navAria: "メインナビゲーション",
      langAria: "言語を選択",
      nav: { radar: "リセットレーダー", feed: "あの人の動向", history: "リセットカレンダー", about: "概要", subscribe: "通知を受ける" },
      preview: { badge: "ローカル・インタラクティブ原型", note: "X は未接続 · 下の状態を切り替えて体験" },
      hero: {
        eyebrow: "ちょっとソワソワするリセット観測所", title: "今日は押した", mark: "？",
        cta: "リセットされたら教えて", evidence: "予測の根拠を見る", note: "作るのは君。押すのは彼。"
      },
      speechTag: "当サイトのセリフ",
      nudge: { label: "つついてみる", hint: "ネタです。リセットは発動しません", speech: "了解、まずコーヒーをもう一口。", speechReset: "もう押したよ。さあ作ろう！" },
      picker: {
        aria: "キャラクター状態のプレビュー",
        waiting: "待ちぼうけ", waitingSub: "ボタンはまだ",
        soon: "押す気満々", soonSub: "何か言いたげ",
        reset: "神になった", resetSub: "リセット、開工！"
      },
      sceneCaption: "同じ Tibo、違う精神状態。",
      offerings: { aria: "マンガの Tibo と遊ぶ", coffee: "おかわりどうぞ", razor: "そろそろヒゲ剃りを", pray: "神様お願い", note: "全部ネタ。神様には届きません。" },
      feed: { title: "さっきの発言", note: "過去の内容・デモ", follow: "X で Tibo の最新を見る" },
      post: { disclaimer: "公開発言であり、現在の状態ではありません", source: "出典を見る" },
      post2: {
        meta: "インタビュー要旨", badge: "背景資料",
        quote: "体験トラブルの埋め合わせの時もあれば、みんなと祝いたい時もある。",
        context: "リセットボタンは本物。期待も本物。",
        source: "Matthew Berman インタビュー · 23:37 から", link: "本人の声を聴く"
      },
      forecast: {
        title: "次回、あるか？", note: "デモ判定",
        signals: { promise: "明確な予告", activity: "最近の動き", completion: "完了告知" },
        reasoningSummary: "判定の中身を見る",
        reasoningStatic: "正式版は原帖・返信文脈・時刻・適用範囲を総合して判断します。本ページは自動収集も予測モデルも未稼働です。",
        footnote: "出典あっての根拠。予告あっても確定待ち。"
      },
      history: { title: "毎回、仕切り直し", sub: "サプライズを記録し、リセットの種類も分けておく。" },
      filters: { aria: "履歴タイプの絞り込み", all: "全部", reset: "直接リセット", banked: "リセット券" },
      events: [
        { label: "タイプ例 · 01", title: "障害のお詫び", desc: "直して、みんなでやり直し。", source: "出典：インタビュー" },
        { label: "タイプ例 · 02", title: "リセット券の配布", desc: "必要な時に、自分で使える。", source: "出典：履歴インデックス" },
        { label: "タイプ例 · 03", title: "祝いのリセット", desc: "良い日には、もう少しコードを。", source: "出典：コミュニティ転載" }
      ],
      fortune: {
        eyebrow: "待ち時間の · お遊び", title: "今日のリセットみくじ", sub: "コードは待てる。儀式は待てない。",
        pending: "未抽選", initial: "心を込めれば届く、枠は別の話。", disclaimer: "当サイトの遊び文句。実際のリセットとは無関係",
        draw: "一枚引く", redraw: "もう一度引く", copy: "おみくじをコピー", suffix: " · あくまで遊び",
        copyTpl: "【今日のリセットみくじ · {rank}】\n{line}\n{detail}\naitibo.cn · ファン二次創作、あくまで遊び"
      },
      bottom: { note: "君のひらめきが、<br><b>いつも枠より少し多めでありますように。</b>", cta: "次のリセット、私にも教えて" },
      footer: { note: "独立コミュニティ二次創作。OpenAI とは無関係", tag: "好きを保ち、気長に待つ。" },
      dialog: { close: "閉じる" },
      sub: {
        eyebrow: "次のリセット、私にも教えて", title: "期待はここに置いて。",
        desc: "これは通知機能のインタラクション・プレビューです。設定はこのブラウザにのみ保存され、通知サービスには未接続。メールもプッシュも送りません。",
        promise: "明確な予告が出た時", promiseSub: "いち早く知る",
        reset: "リセット発表の時", resetSub: "開工の時間だ",
        save: "この端末に保存",
        readError: "保存済みの設定を読めません。選び直してください。", saveError: "ブラウザがローカル保存を拒否。設定は未保存です。"
      },
      about: {
        eyebrow: "この小さなサイトについて", title: "ボタンを待ち、<br>小さな驚きを待つ。",
        desc1: "aitibo.cn は Tibo の公開リセット動向をめぐる独立コミュニティ企画。この版はローカル・インタラクティブ原型で、状態・計時・判定はすべてデモ。過去資料には出典付き。",
        desc2: "次は彼の公開 X を取り込み、冗談・予告・直接リセット・リセット券を見分け、すべての判定を原文に辿れるようにします。マンガのセリフは当サイトの二次創作です。",
        ok: "了解"
      },
      units: { day: "日", hour: "時間", min: "分" },
      timer: { demoTag: "デモ計時" },
      stateNames: { waiting: "待ちぼうけ", soon: "押す気満々", reset: "リセット封神" },
      states: {
        waiting: {
          status: "まだ彼待ち", line: "ヒゲは伸びる。ボタンは動かない。", speech: "焦るな、ちょっと X を見てるだけ",
          alt: "無精ヒゲのマンガ Tibo がリセットボタンのそばで待ちくたびれている",
          forecast: "手がかりなし…", description: "今の例文は明確なリセット約束になっていません。焦らず、作りたいものをメモしておこう。",
          signals: ["見つからず", "日常のやり取り", "確認待ち"], badge: "冗談",
          quote: "「リセット発表だと思った？ただ X を見に来ただけ。」", context: "過去帖の意訳 · 2026年7月15日",
          semantic: "意味判定：冗談。リセットは約束されていない",
          reasoning: "例文には「リセット」が出るが、文は明確にリセット予告を否定している。キーワード一致は約束ではない。",
          timerLabel: "前回のリセットから"
        },
        soon: {
          status: "予告あり · デモ", line: "手はもう上がってる。あと少し。", speech: "よしよし、手は上げた。",
          alt: "マンガの Tibo が眉を上げて微笑み、赤いリセットボタンに指をかざしている",
          forecast: "明確な予告あり", description: "例文に「午後にリセット」の約束が含まれます。範囲と実際の完了は引き続き確認待ち。",
          signals: ["「午後にリセット」", "明確な時間幅", "完了待ち"], badge: "予告",
          quote: "「ベイビー呼びはやめて。午後にリセットするよ。」", context: "過去返信の意訳 · 2026年7月9日",
          semantic: "意味判定：未来の約束。完了は未発表",
          reasoning: "「午後にリセット」は未来の時間と明確な動作を含み、漠然とした祝いより強い。ただし正確な時刻はなく、精密なカウントダウンは出せない。過去返信を今日の新発表にもしない。",
          timerLabel: "前回のリセットから"
        },
        reset: {
          status: "リセット封神 · デモ", line: "ボタン一発、世界に光が戻った。", speech: "行け。すごいものを作れ。",
          alt: "白い衣に金色の後光をまとったマンガ Tibo がリセットボタンを押し、金色のトークンが舞う",
          forecast: "リセット発表！", description: "例文の公告は完了形の言い方。自分の枠が戻ったかは、プロダクト内の実際の表示で確認を。",
          signals: ["公告化", "新体験を祝う", "完了を発表"], badge: "発表済み",
          quote: "「素晴らしい一週間を祝して、全有料プランの Codex 枠をリセットしました。」", context: "過去公告の意訳 · 2026年4月28日",
          semantic: "意味判定：完了公告。範囲は Codex 有料プラン",
          reasoning: "過去の公告は完了形で、対象プランも明記。公告は公開情報で、各アカウントへの着弾を証明しない。直接リセットとリセット券配布を混同してはいけない。",
          timerLabel: "このリセットから"
        }
      },
      toasts: {
        preview: "プレビュー中：{state} · 実況ではありません",
        nudge: "マンガをつついただけ。実際の枠は変わりません。",
        savedOn: "この端末に保存 · 通知は飛びません",
        savedOff: "端末の通知設定をオフにしました",
        gift: "マンガの Tibo が応答 · 遊びです、本人には届きません",
        fortune: "おみくじ完成。願いは預かっておく。",
        copied: "コピー完了。リセット待ちの仲間に送ろう。",
        copyFail: "コピーがブロックされました。本文を選択してコピーしてね。"
      },
      giftLines: {
        coffee: {
          waiting: ["コーヒーはおかわり、枠はまだ。", "この一杯は君のおごり。次のリセットは俺が出す。", "砂糖はいらない。要件がもう甘い。"],
          soon: ["コーヒーは置け、ボタンに触るな。", "この一口を飲んだら考える。"],
          reset: ["神もカフェインが要る。", "コーヒーは作る人に、トークンは夢見る人に。"]
        },
        razor: {
          waiting: ["これはヒゲ、君の待機プログレスバー。", "急かすな、ヒゲが分岐する。", "俺がリセットする時、ヒゲもリセット。"],
          soon: ["こっちを剃ったら、あっちを押す。", "リセットが先、身だしなみは後。"],
          reset: ["封神直後だ、聖なるヒゲに触るな。", "後光は美肌フィルター付き。剃らなくていい。"]
        },
        pray: {
          waiting: ["その「神様」でマウスが震えた。", "ベイビーはやめて……神様も待って。", "君の願いは宇宙のキューに入った。"],
          soon: ["手は上げてる。もう少し待て。", "儀式は十分、公告を待て。"],
          reset: ["枠はやった。俺がイケてるか聞くな。", "解散！そのプロジェクトを作ってこい。"]
        }
      },
      fortunes: [
        { rank: "大吉", line: "神の手が震えれば、プロジェクトは全部完成。", detail: "吉：要件をはっきり書く。凶：枠だけあってアイデアなし。" },
        { rank: "サボり吉", line: "枠がゼロ。やっと帰る理由ができた。", detail: "吉：水を飲む。凶：使用量ページを連打。" },
        { rank: "エンジニア吉", line: "リセットは神頼み、ロールバックは自前。", detail: "吉：バックアップを取る。凶：ボタンに全賭け。" },
        { rank: "ヒゲ吉", line: "彼のヒゲは伸びる、君の要件も伸びる。", detail: "吉：機能を一つ削る。凶：小さなお願いを追加。" },
        { rank: "封神吉", line: "トークンの雨が降る。書き続けろ。", detail: "吉：小さなプロジェクトを完成。凶：新坑を十個掘る。" },
        { rank: "忍耐吉", line: "彼はスクロール、君はリロード。", detail: "吉：窓の外を見る。凶：冗談を予告と読む。" }
      ]
    },

    fr: {
      meta: {
        title: "Tibo a-t-il appuyé aujourd'hui ? · aitibo.cn",
        hiddenTitle: "Toujours en train de l'attendre ? · aitibo.cn",
        description: "Tibo a-t-il appuyé aujourd'hui ? Un observatoire du reset, un rien impatient. Prototype interactif local."
      },
      skip: "Aller au contenu principal",
      brandAria: "Accueil aitibo",
      navAria: "Navigation principale",
      langAria: "Choisir la langue",
      nav: { radar: "Radar reset", feed: "Ses posts", history: "Calendrier", about: "À propos", subscribe: "Me prévenir" },
      preview: { badge: "Prototype interactif local", note: "X pas encore branché · essayez les états ci-dessous" },
      hero: {
        eyebrow: "Un observatoire du reset, un rien impatient", title: "tu as appuyé", mark: " ?",
        cta: "Prévenez-moi au reset", evidence: "Voir le raisonnement", note: "Toi, tu crées. Lui, il appuie."
      },
      speechTag: "légende du site",
      nudge: { label: "Le pousser du coude", hint: "juste une blague, ça ne déclenche rien", speech: "Reçu. D'abord une gorgée de café.", speechReset: "C'est déjà fait. Au boulot !" },
      picker: {
        aria: "Aperçu des états du personnage",
        waiting: "En attente", waitingSub: "bouton intact",
        soon: "Prêt à appuyer", soonSub: "il a quelque chose à dire",
        reset: "Divinisé", resetSub: "reset, au boulot !"
      },
      sceneCaption: "Le même Tibo, d'autres états d'esprit.",
      offerings: { aria: "Interagir avec le Tibo BD", coffee: "Encore un café", razor: "Il est temps de se raser", pray: "Parrain, sauve-moi", note: "Pur délire. Le parrain n'entend rien." },
      feed: { title: "Ce qu'il vient de dire", note: "Contenus passés, démo", follow: "Voir les derniers posts de Tibo sur X" },
      post: { disclaimer: "Propos publics, pas un état actuel", source: "Voir la source" },
      post2: {
        meta: "Extrait d'interview", badge: "Contexte",
        quote: "Parfois c'est un dédommagement pour un souci d'expérience, parfois juste l'envie de fêter ça ensemble.",
        context: "Le bouton reset existe. L'attente aussi.",
        source: "Interview Matthew Berman · à partir de 23:37", link: "L'écouter"
      },
      forecast: {
        title: "La prochaine, ça se dessine ?", note: "Verdict démo",
        signals: { promise: "Annonce claire", activity: "Activité récente", completion: "Avis de fin" },
        reasoningSummary: "Voir comment c'est jugé",
        reasoningStatic: "La version finale croisera post original, contexte de réponse, date et périmètre. Cette page ne lance ni collecte automatique ni modèle de prédiction.",
        footnote: "Pas de source, pas de verdict. Et même une promesse attend confirmation."
      },
      history: { title: "À chaque reset, on repart", sub: "Notez les surprises — et distinguez les types de reset." },
      filters: { aria: "Filtrer les types d'historique", all: "Tout", reset: "Reset direct", banked: "Coupons reset" },
      events: [
        { label: "Exemple de type · 01", title: "Reset dédommagement", desc: "Panne réparée, et tout le monde repart.", source: "Source : interview" },
        { label: "Exemple de type · 02", title: "Coupons reset", desc: "À garder pour plus tard, à utiliser quand on veut.", source: "Source : index historique" },
        { label: "Exemple de type · 03", title: "Reset de fête", desc: "Les beaux jours méritent quelques lignes de code en plus.", source: "Source : repost communauté" }
      ],
      fortune: {
        eyebrow: "En attendant · on s'occupe", title: "Oracle reset du jour", sub: "Le code peut attendre. Pas le rituel.",
        pending: "Pas encore tiré", initial: "La foi aide. Le quota, c'est autre chose.", disclaimer: "Texte pour rire, sans lien avec les vrais resets",
        draw: "Tirer un oracle", redraw: "Retirer", copy: "Copier mon oracle", suffix: " · juste pour rire",
        copyTpl: "[Oracle reset du jour · {rank}]\n{line}\n{detail}\naitibo.cn · création de fan, juste pour rire"
      },
      bottom: { note: "Que ton inspiration<br><b>dépasse toujours ton quota.</b>", cta: "Au prochain reset, préviens-moi" },
      footer: { note: "Projet communautaire indépendant, sans lien avec OpenAI", tag: "Garder la passion. Et un peu de patience." },
      dialog: { close: "Fermer" },
      sub: {
        eyebrow: "Au prochain reset, préviens-moi", title: "Dépose l'espoir ici.",
        desc: "Ceci est un aperçu interactif des rappels. Les préférences ne sont enregistrées que dans ce navigateur — aucun service de notification n'est branché, rien n'est envoyé par mail ou push.",
        promise: "Quand il annonce clairement", promiseSub: "entendre le vent tourner",
        reset: "Quand il déclare le reset", resetSub: "l'heure de coder",
        save: "Enregistrer sur cet appareil",
        readError: "Impossible de lire les préférences. Choisis à nouveau.", saveError: "Le navigateur refuse le stockage local. Préférences non enregistrées."
      },
      about: {
        eyebrow: "À propos de ce petit site", title: "Attendre un bouton,<br>et une petite surprise.",
        desc1: "aitibo.cn est un projet communautaire indépendant autour des resets publics de Tibo. Cette version est un prototype interactif local : états, chronomètre et verdicts sont des démos ; les sources historiques sont citées.",
        desc2: "La suite : brancher son flux X public, distinguer blagues, annonces, resets directs et coupons, et rendre chaque verdict traçable jusqu'au post. Les répliques du personnage sont notre propre création.",
        ok: "Compris"
      },
      units: { day: "j", hour: "h", min: "min" },
      timer: { demoTag: "chrono démo" },
      stateNames: { waiting: "En attente", soon: "Prêt à appuyer", reset: "Reset divin" },
      states: {
        waiting: {
          status: "On l'attend encore", line: "La barbe pousse. Le bouton, non.", speech: "Doucement, je scrolle juste X.",
          alt: "Tibo BD mal rasé, affalé près du bouton reset, en attente",
          forecast: "Aucune piste…", description: "L'exemple actuel ne constitue pas une promesse claire de reset. Patience — notez déjà ce que vous ferez.",
          signals: ["Rien trouvé", "Petits échanges", "À confirmer"], badge: "Vanne",
          quote: "« Vous pensiez que j'allais annoncer un reset ? Je venais juste scroller. »", context: "Post passé paraphrasé · 15 juillet 2026",
          semantic: "Lecture : vanne, aucun reset promis",
          reasoning: "L'exemple mentionne « reset », mais la phrase nie clairement toute annonce. Un mot-clé repéré n'est pas une promesse.",
          timerLabel: "Depuis le dernier reset"
        },
        soon: {
          status: "Il a teasé · démo", line: "La main est levée. Encore une seconde.", speech: "Ça va, ça va — la main est levée.",
          alt: "Tibo BD sourit en coin, doigt au-dessus du bouton reset rouge",
          forecast: "Annonce claire", description: "L'exemple contient la promesse « reset cet après-midi ». La portée et la concrétisation restent à confirmer.",
          signals: ["« Cet après-midi »", "Fenêtre claire", "En attente"], badge: "Teaser",
          quote: "« Ne m'appelez pas bébé — reset cet après-midi. »", context: "Réponse passée paraphrasée · 9 juillet 2026",
          semantic: "Lecture : promesse future, fin non annoncée",
          reasoning: "« Reset cet après-midi » porte un moment et une action clairs, donc plus fort qu'une vague célébration. Mais pas d'heure précise : pas de compte à rebours exact. Et une vieille réponse n'est pas une annonce d'aujourd'hui.",
          timerLabel: "Depuis le dernier reset"
        },
        reset: {
          status: "Reset divin · démo", line: "Un clic, et la lumière revient au monde.", speech: "Va. Fais quelque chose de grand.",
          alt: "Tibo BD en toge blanche, auréole dorée, appuyant sur le bouton reset sous une pluie de tokens dorés",
          forecast: "Reset annoncé !", description: "L'annonce d'exemple est au passé. Pour savoir si ton propre quota est revenu, regarde le produit lui-même.",
          signals: ["Annonce faite", "On fête le nouveau", "Fini, annoncé"], badge: "Annoncé",
          quote: "« Pour fêter une belle semaine, j'ai réinitialisé les quotas Codex de tous les forfaits payants. »", context: "Annonce passée paraphrasée · 28 avril 2026",
          semantic: "Lecture : annonce accomplie, forfaits Codex payants",
          reasoning: "L'annonce historique emploie l'accompli et nomme les forfaits couverts. Un post public ne prouve pas que chaque compte a été crédité — et un reset direct n'est pas une distribution de coupons.",
          timerLabel: "Depuis ce reset"
        }
      },
      toasts: {
        preview: "Aperçu : {state} · pas en direct",
        nudge: "Tu as poussé un personnage de BD. Le vrai quota ne bouge pas.",
        savedOn: "Préférences enregistrées ici · rien ne sera envoyé",
        savedOff: "Rappels locaux désactivés",
        gift: "Le Tibo BD a répondu · pour rire, jamais envoyé",
        fortune: "Oracle tiré. Ton vœu est gardé.",
        copied: "Oracle copié — envoie-le à un autre impatient.",
        copyFail: "Copie bloquée — sélectionne le texte toi-même."
      },
      giftLines: {
        coffee: {
          waiting: ["Café resservi. Le quota, non.", "Cette tasse est pour toi — le prochain reset, pour moi.", "Sans sucre : les specs sont déjà assez douces."],
          soon: ["Pose ce café. Pas touche à mon bouton.", "Laisse-moi finir cette gorgée, on verra."],
          reset: ["Même les dieux boivent du café.", "Café aux bâtisseurs, tokens aux rêveurs."]
        },
        razor: {
          waiting: ["Ce n'est pas une barbe, c'est ta barre de progression.", "Arrête de presser, la barbe va fourcher.", "Quand je resette, la barbe resette aussi."],
          soon: ["Je rase ce côté, j'appuie de l'autre.", "D'abord le reset, la toilette après."],
          reset: ["Fraîchement divinisé — pas touche au duvet sacré.", "L'auréole a un filtre beauté. Pas besoin de raser."]
        },
        pray: {
          waiting: ["Ce « parrain » a fait trembler ma souris.", "Pas de « bébé »… et « parrain », on verra plus tard.", "Ton vœu a rejoint la file cosmique."],
          soon: ["La main est levée. Encore deux minutes.", "Le rituel est parfait — attends l'annonce."],
          reset: ["Quota livré. Ne le gaspille pas à me demander si je suis beau.", "Séance levée ! Va finir ce projet."]
        }
      },
      fortunes: [
        { rank: "Grand oracle", line: "Un tic du parrain, et tous les projets se bouclent.", detail: "Faire : écrire des specs nettes. Éviter : un quota plein sans idée." },
        { rank: "Oracle glandouille", line: "Quota à zéro — enfin une excuse pour débaucher.", detail: "Faire : boire de l'eau. Éviter : rafraîchir la page de quota en boucle." },
        { rank: "Oracle ingénieur", line: "Le reset vient du parrain, le rollback vient de toi.", detail: "Faire : des backups. Éviter : tout miser sur un bouton." },
        { rank: "Oracle barbu", line: "Sa barbe pousse. Ta liste de specs aussi.", detail: "Faire : couper une feature. Éviter : ajouter une « petite » demande." },
        { rank: "Oracle divin", line: "Il pleut des tokens. Continue d'écrire.", detail: "Faire : finir ce petit projet. Éviter : ouvrir dix nouveaux chantiers." },
        { rank: "Oracle patience", line: "Il scrolle. Tu rafraîchis.", detail: "Faire : regarder par la fenêtre. Éviter : lire une blague comme un teaser." }
      ]
    },

    es: {
      meta: {
        title: "¿Tibo ya lo pulsó hoy? · aitibo.cn",
        hiddenTitle: "¿Sigues esperándolo? · aitibo.cn",
        description: "¿Tibo ya lo pulsó hoy? Un observatorio del reset algo impaciente. Prototipo interactivo local."
      },
      skip: "Saltar al contenido",
      brandAria: "Inicio de aitibo",
      navAria: "Navegación principal",
      langAria: "Elegir idioma",
      nav: { radar: "Radar de reset", feed: "Sus posts", history: "Calendario", about: "Acerca de", subscribe: "Avísame" },
      preview: { badge: "Prototipo interactivo local", note: "X aún no conectado · prueba los estados de abajo" },
      hero: {
        eyebrow: "Un observatorio del reset algo impaciente", title: "¿ya lo pulsaste hoy", mark: "?",
        cta: "Avísame cuando resetee", evidence: "Ver el razonamiento", note: "Tú creas. Él pulsa. Algún día."
      },
      speechTag: "frase del sitio",
      nudge: { label: "Dale un toque", hint: "es broma, no dispara ningún reset", speech: "Anotado. Primero otro sorbo de café.", speechReset: "Ya pulsé. ¡A construir!" },
      picker: {
        aria: "Vista previa de estados",
        waiting: "En la espera", waitingSub: "botón intacto",
        soon: "Calentando", soonSub: "tiene algo que decir",
        reset: "Consagrado", resetSub: "reset, ¡a trabajar!"
      },
      sceneCaption: "El mismo Tibo, distintos estados de ánimo.",
      offerings: { aria: "Interactuar con el Tibo de cómic", coffee: "Otro café", razor: "Hora de afeitarse", pray: "Padrino, sálvame", note: "Puro chiste. El padrino no te escucha." },
      feed: { title: "Lo que acaba de decir", note: "Contenido pasado, demo", follow: "Ver lo último de Tibo en X" },
      post: { disclaimer: "Declaración pública, no un estado actual", source: "Ver la fuente" },
      post2: {
        meta: "Extracto de entrevista", badge: "Contexto",
        quote: "A veces compensa un problema de experiencia; a veces solo quiere celebrarlo con todos.",
        context: "El botón de reset es real. La expectativa también.",
        source: "Entrevista Matthew Berman · desde 23:37", link: "Escúchalo"
      },
      forecast: {
        title: "El próximo, ¿tiene pinta?", note: "Veredicto demo",
        signals: { promise: "Promesa clara", activity: "Actividad reciente", completion: "Aviso de fin" },
        reasoningSummary: "Mira cómo lo juzgamos",
        reasoningStatic: "La versión final cruzará el post original, el contexto de la respuesta, la fecha y el alcance. Esta página no ejecuta recolección automática ni modelo de predicción.",
        footnote: "Sin fuente no hay veredicto. Y hasta una promesa necesita confirmación."
      },
      history: { title: "Cada reset, un nuevo comienzo", sub: "Anota las sorpresas — y distingue unos resets de otros." },
      filters: { aria: "Filtrar tipos de historial", all: "Todo", reset: "Reset directo", banked: "Cupones reset" },
      events: [
        { label: "Tipo de ejemplo · 01", title: "Reset de compensación", desc: "Arreglado el fallo, todos vuelven a empezar.", source: "Fuente: entrevista" },
        { label: "Tipo de ejemplo · 02", title: "Cupones de reset", desc: "Guardados para cuando los necesites.", source: "Fuente: índice histórico" },
        { label: "Tipo de ejemplo · 03", title: "Reset de fiesta", desc: "Los buenos días merecen unas líneas más de código.", source: "Fuente: repost de la comunidad" }
      ],
      fortune: {
        eyebrow: "Mientras esperamos · diversión", title: "Fortuna de reset del día", sub: "El código espera. El ritual no.",
        pending: "Sin tirar", initial: "La fe ayuda. La cuota es otro tema.", disclaimer: "Texto de broma, sin relación con resets reales",
        draw: "Tirar una", redraw: "Tirar otra", copy: "Copiar mi fortuna", suffix: " · solo por diversión",
        copyTpl: "[Fortuna de reset del día · {rank}]\n{line}\n{detail}\naitibo.cn · obra de fans, solo por diversión"
      },
      bottom: { note: "Que tu inspiración<br><b>dure siempre un poco más que tu cuota.</b>", cta: "En el próximo reset, avísame" },
      footer: { note: "Proyecto comunitario independiente, sin afiliación con OpenAI", tag: "Sigue creando. Con paciencia." },
      dialog: { close: "Cerrar" },
      sub: {
        eyebrow: "En el próximo reset, avísame", title: "Deja aquí la esperanza.",
        desc: "Esto es una vista previa de los recordatorios. Las preferencias solo se guardan en este navegador — no hay servicio de notificaciones conectado, ni se envían correos ni push.",
        promise: "Cuando lo anuncie claramente", promiseSub: "oirlo primero",
        reset: "Cuando declare el reset", resetSub: "hora de trabajar",
        save: "Guardar en este dispositivo",
        readError: "No se pudieron leer las preferencias. Elige otra vez.", saveError: "El navegador bloqueó el almacenamiento. Preferencias no guardadas."
      },
      about: {
        eyebrow: "Sobre este sitio", title: "Esperando un botón,<br>y una pequeña sorpresa.",
        desc1: "aitibo.cn es un proyecto comunitario independiente en torno a los resets públicos de Tibo. Esta versión es un prototipo interactivo local: estados, cronómetro y veredictos son de demo; el material histórico incluye fuentes.",
        desc2: "El siguiente paso es conectar su feed público de X y distinguir bromas, promesas, resets directos y cupones, con cada veredicto trazable al post original. Las frases del cómic son creación nuestra.",
        ok: "Entendido"
      },
      units: { day: "d", hour: "h", min: "min" },
      timer: { demoTag: "cronómetro demo" },
      stateNames: { waiting: "En la espera", soon: "Calentando", reset: "Reset divino" },
      states: {
        waiting: {
          status: "Aún lo esperamos", line: "La barba crece. El botón no.", speech: "Calma, solo estoy viendo X.",
          alt: "Un Tibo de cómic con barba, apoyado junto al botón de reset, esperando",
          forecast: "Sin pistas…", description: "El ejemplo actual no equivale a una promesa clara de reset. Tranquilo — apunta lo que harás primero.",
          signals: ["Nada hallado", "Charla de cada día", "Por confirmar"], badge: "Broma",
          quote: "“¿Creías que anunciaba un reset? Solo vine a ver el timeline.”", context: "Post pasado parafraseado · 15 de julio de 2026",
          semantic: "Lectura: broma, sin reset prometido",
          reasoning: "El ejemplo menciona «reset», pero la frase niega claramente un anuncio. Una palabra clave no es una promesa.",
          timerLabel: "Desde el último reset"
        },
        soon: {
          status: "Lo anticipó · demo", line: "La mano ya está arriba. Un segundo.", speech: "Vale, vale — la mano ya está arriba.",
          alt: "El Tibo de cómic sonríe con el dedo sobre el botón rojo de reset",
          forecast: "Promesa clara", description: "El ejemplo incluye la promesa de «reset esta tarde». El alcance y la ejecución real siguen por confirmar.",
          signals: ["«Esta tarde»", "Ventana clara", "A la espera"], badge: "Anuncio",
          quote: "“No me llames bebé — esta tarde hay reset.”", context: "Respuesta pasada parafraseada · 9 de julio de 2026",
          semantic: "Lectura: promesa futura, fin no anunciado",
          reasoning: "«Reset esta tarde» tiene momento y acción claros, más fuerte que una celebración vaga. Pero sin hora exacta no hay cuenta atrás precisa, y una respuesta vieja no es un anuncio de hoy.",
          timerLabel: "Desde el último reset"
        },
        reset: {
          status: "Reset divino · demo", line: "Un clic y el mundo vuelve a tener luz.", speech: "Ve. Crea algo grande.",
          alt: "Tibo de cómic con túnica blanca y halo dorado pulsando el botón de reset bajo una lluvia de tokens",
          forecast: "¡Reset anunciado!", description: "El anuncio de ejemplo habla en pasado. Si tu cuota volvió o no, míralo en el propio producto.",
          signals: ["Ya es anuncio", "Celebrando lo nuevo", "Fin anunciado"], badge: "Anunciado",
          quote: "“Para celebrar una gran semana, he reseteado las cuotas de Codex de todos los planes de pago.”", context: "Anuncio pasado parafraseado · 28 de abril de 2026",
          semantic: "Lectura: anuncio cumplido, solo planes Codex de pago",
          reasoning: "El anuncio histórico usa forma de acción cumplida y nombra los planes cubiertos. Un post público no prueba que cada cuenta lo recibiera, y un reset directo no es reparto de cupones.",
          timerLabel: "Desde este reset"
        }
      },
      toasts: {
        preview: "Vista previa: {state} · no es en vivo",
        nudge: "Le diste un toque a un cómic. La cuota real ni se entera.",
        savedOn: "Preferencias guardadas aquí · no se enviará nada",
        savedOff: "Recordatorios locales desactivados",
        gift: "El Tibo de cómic respondió · por diversión, nunca le llega",
        fortune: "Fortuna lista. Tu deseo queda guardado.",
        copied: "Fortuna copiada — mándasela a otro que espera.",
        copyFail: "Copia bloqueada — selecciona el texto y cópialo tú."
      },
      giftLines: {
        coffee: {
          waiting: ["Café servido. La cuota, no.", "Esta taza la pagas tú — el próximo reset lo pago yo.", "Sin azúcar: los requisitos ya son bastante dulces."],
          soon: ["Deja el café. Quita las manos de mi botón.", "Déjame terminar este sorbo y vemos."],
          reset: ["Hasta los dioses toman café.", "Café para los que crean, tokens para los que sueñan."]
        },
        razor: {
          waiting: ["No es barba, es tu barra de progreso de espera.", "Deja de presionar, que la barba va a bifurcar.", "Cuando resetee, la barba se resetea conmigo."],
          soon: ["Afeito este lado, pulso el otro.", "Primero el reset, luego el aseo."],
          reset: ["Recién consagrado — no toques la barba sagrada.", "El halo tiene filtro de belleza. No hace falta afeitar."]
        },
        pray: {
          waiting: ["Ese «padrino» hizo temblar mi ratón.", "No me llames bebé… y padrino, ya veremos.", "Tu deseo entró en la cola cósmica."],
          soon: ["La mano está arriba. Dos minutos más.", "El ritual está perfecto — espera el anuncio."],
          reset: ["Cuota entregada. No la gastes preguntando si soy guapo.", "¡Se acabó la reunión! Ve a terminar ese proyecto."]
        }
      },
      fortunes: [
        { rank: "Suerte mayor", line: "Un temblor del padrino y todos los proyectos salen.", detail: "Haz: requisitos claros. Evita: cuota llena y cero ideas." },
        { rank: "Fortuna vaga", line: "Cuota a cero — por fin excusa para salir.", detail: "Haz: bebe agua. Evita: refrescar la página de uso sin parar." },
        { rank: "Fortuna ingenieril", line: "El reset viene del padrino; el rollback, de ti.", detail: "Haz: copias de seguridad. Evita: apostarlo todo a un botón." },
        { rank: "Fortuna barbuda", line: "Su barba crece. Tu lista de requisitos también.", detail: "Haz: corta una función. Evita: añadir «una cosita más»." },
        { rank: "Fortuna divina", line: "Llueven tokens. Sigue escribiendo.", detail: "Haz: termina ese mini proyecto. Evita: abrir diez frentes nuevos." },
        { rank: "Fortuna paciente", line: "Él hace scroll. Tú haces refresh.", detail: "Haz: mira por la ventana. Evita: leer un chiste como anuncio." }
      ]
    },

    pt: {
      meta: {
        title: "O Tibo já apertou hoje? · aitibo.cn",
        hiddenTitle: "Ainda esperando por ele? · aitibo.cn",
        description: "O Tibo já apertou hoje? Um observatório de reset meio impaciente. Protótipo interativo local."
      },
      skip: "Pular para o conteúdo",
      brandAria: "Início do aitibo",
      navAria: "Navegação principal",
      langAria: "Escolher idioma",
      nav: { radar: "Radar de reset", feed: "Posts dele", history: "Calendário", about: "Sobre", subscribe: "Me avisa" },
      preview: { badge: "Protótipo interativo local", note: "X ainda não conectado · experimente os estados abaixo" },
      hero: {
        eyebrow: "Um observatório de reset meio impaciente", title: "já apertou hoje", mark: "?",
        cta: "Me avisa quando resetar", evidence: "Ver o raciocínio", note: "Você cria. Ele aperta. Uma hora."
      },
      speechTag: "legenda do site",
      nudge: { label: "Cutuca ele", hint: "só brincadeira, não dispara reset", speech: "Anotado. Antes, mais um gole de café.", speechReset: "Já apertei. Vai construir!" },
      picker: {
        aria: "Prévia dos estados do personagem",
        waiting: "Na espera", waitingSub: "botão intacto",
        soon: "Quase lá", soonSub: "ele tem algo a dizer",
        reset: "Consagrado", resetSub: "reset, bora codar!"
      },
      sceneCaption: "O mesmo Tibo, outros estados de espírito.",
      offerings: { aria: "Interagir com o Tibo de quadrinhos", coffee: "Mais um café", razor: "Hora de se barbear", pray: "Padrinho, me salva", note: "Pura brincadeira. O padrinho não te ouve." },
      feed: { title: "O que ele acabou de dizer", note: "Conteúdo passado, demo", follow: "Ver os posts recentes do Tibo no X" },
      post: { disclaimer: "Fala pública, não é status atual", source: "Ver a fonte" },
      post2: {
        meta: "Trecho de entrevista", badge: "Contexto",
        quote: "Às vezes é compensação por um problema de experiência; às vezes é só vontade de comemorar com todo mundo.",
        context: "O botão de reset existe. A expectativa também.",
        source: "Entrevista Matthew Berman · a partir de 23:37", link: "Ouça ele"
      },
      forecast: {
        title: "O próximo, tem chance?", note: "Veredito demo",
        signals: { promise: "Promessa clara", activity: "Atividade recente", completion: "Aviso de fim" },
        reasoningSummary: "Veja como julgamos",
        reasoningStatic: "A versão final vai cruzar post original, contexto da resposta, data e abrangência. Esta página não roda coleta automática nem modelo de previsão.",
        footnote: "Sem fonte, sem veredito. E até promessa precisa de confirmação."
      },
      history: { title: "Cada reset, um recomeço", sub: "Anote as surpresas — e diferencie um tipo de reset do outro." },
      filters: { aria: "Filtrar tipos de histórico", all: "Tudo", reset: "Reset direto", banked: "Cupons de reset" },
      events: [
        { label: "Tipo de exemplo · 01", title: "Reset de desculpas", desc: "Bug resolvido e todo mundo recomeça.", source: "Fonte: entrevista" },
        { label: "Tipo de exemplo · 02", title: "Cupons de reset", desc: "Guardados para usar quando precisar.", source: "Fonte: índice histórico" },
        { label: "Tipo de exemplo · 03", title: "Reset de festa", desc: "Dia bom merece mais umas linhas de código.", source: "Fonte: repost da comunidade" }
      ],
      fortune: {
        eyebrow: "Enquanto esperamos · diversão", title: "Sorte de reset do dia", sub: "O código espera. O ritual não.",
        pending: "Não sorteado", initial: "Fé ajuda. Cota é outra história.", disclaimer: "Texto de brincadeira, sem relação com resets de verdade",
        draw: "Sortear", redraw: "Sortear de novo", copy: "Copiar minha sorte", suffix: " · só brincadeira",
        copyTpl: "[Sorte de reset do dia · {rank}]\n{line}\n{detail}\naitibo.cn · obra de fã, só brincadeira"
      },
      bottom: { note: "Que sua inspiração<br><b>dure sempre um pouco mais que a cota.</b>", cta: "No próximo reset, me chama" },
      footer: { note: "Projeto comunitário independente, sem vínculo com a OpenAI", tag: "Continue criando. Com paciência." },
      dialog: { close: "Fechar" },
      sub: {
        eyebrow: "No próximo reset, me chama", title: "Deixa a esperança aqui.",
        desc: "Isto é uma prévia interativa dos lembretes. As preferências ficam salvas só neste navegador — nenhum serviço de notificação conectado, nada de e-mail ou push.",
        promise: "Quando ele anunciar claramente", promiseSub: "saber primeiro",
        reset: "Quando ele declarar o reset", resetSub: "hora de codar",
        save: "Salvar neste dispositivo",
        readError: "Não foi possível ler as preferências. Escolha de novo.", saveError: "O navegador bloqueou o armazenamento. Preferências não salvas."
      },
      about: {
        eyebrow: "Sobre este sitezinho", title: "Esperando um botão,<br>e uma surpresinha.",
        desc1: "aitibo.cn é um projeto comunitário independente sobre os resets públicos do Tibo. Esta versão é um protótipo interativo local: estados, cronômetro e vereditos são demo; o material histórico tem fontes.",
        desc2: "O próximo passo é plugar o feed público dele no X, separando piadas, promessas, resets diretos e cupons — cada veredito rastreável até o post. As falas do personagem são criação nossa.",
        ok: "Entendi"
      },
      units: { day: "d", hour: "h", min: "min" },
      timer: { demoTag: "cronômetro demo" },
      stateNames: { waiting: "Na espera", soon: "Quase lá", reset: "Reset divino" },
      states: {
        waiting: {
          status: "Ainda esperando ele", line: "A barba cresce. O botão não.", speech: "Calma, só tô rolando o X.",
          alt: "Tibo de quadrinhos barbudo, caído ao lado do botão de reset, esperando",
          forecast: "Sem pistas…", description: "O exemplo atual não configura uma promessa clara de reset. Calma — anota o que você vai fazer primeiro.",
          signals: ["Nada achado", "Papo do dia a dia", "A confirmar"], badge: "Zoação",
          quote: "“Achou que eu ia anunciar reset? Só vim rolar o feed.”", context: "Post antigo parafraseado · 15 de julho de 2026",
          semantic: "Leitura: zoação, nenhum reset prometido",
          reasoning: "O exemplo menciona “reset”, mas a frase nega claramente um anúncio. Palavra-chave encontrada não é promessa.",
          timerLabel: "Desde o último reset"
        },
        soon: {
          status: "Ele prometeu · demo", line: "A mão já tá levantada. Só um segundo.", speech: "Tá bom, tá bom — a mão já tá lá.",
          alt: "Tibo de quadrinhos sorrindo de canto, dedo sobre o botão vermelho de reset",
          forecast: "Promessa clara", description: "O exemplo inclui a promessa de “reset à tarde”. Escopo e conclusão real ainda precisam de confirmação.",
          signals: ["“À tarde”", "Janela clara", "Aguardando"], badge: "Promessa",
          quote: "“Não me chama de bebê — reset à tarde.”", context: "Resposta antiga parafraseada · 9 de julho de 2026",
          semantic: "Leitura: promessa futura, conclusão não anunciada",
          reasoning: "“Reset à tarde” traz horário e ação claros, mais forte que uma comemoração vaga. Mas sem hora exata, sem contagem regressiva precisa — e uma resposta antiga não é anúncio de hoje.",
          timerLabel: "Desde o último reset"
        },
        reset: {
          status: "Reset divino · demo", line: "Um clique e o mundo tem luz de novo.", speech: "Vai. Cria algo grande.",
          alt: "Tibo de quadrinhos de túnica branca e auréola dourada apertando o botão de reset sob chuva de tokens",
          forecast: "Reset anunciado!", description: "O anúncio de exemplo fala em passado. Se a sua cota voltou mesmo, confira no próprio produto.",
          signals: ["Já é anúncio", "Festejando o novo", "Fim anunciado"], badge: "Anunciado",
          quote: "“Pra celebrar uma semana linda, resetei as cotas de Codex de todos os planos pagos.”", context: "Anúncio antigo parafraseado · 28 de abril de 2026",
          semantic: "Leitura: anúncio concluído, só planos Codex pagos",
          reasoning: "O anúncio histórico usa forma concluída e cita os planos cobertos. Um post público não prova que cada conta recebeu — e um reset direto não é distribuição de cupons.",
          timerLabel: "Desde este reset"
        }
      },
      toasts: {
        preview: "Prévia: {state} · não é ao vivo",
        nudge: "Você cutucou um personagem de quadrinhos. A cota real nem liga.",
        savedOn: "Preferências salvas aqui · nada será enviado",
        savedOff: "Lembretes locais desligados",
        gift: "O Tibo de quadrinhos respondeu · por brincadeira, nunca chega nele",
        fortune: "Sorte pronta. Seu pedido fica com a gente.",
        copied: "Sorte copiada — manda pra outro ansioso.",
        copyFail: "Cópia bloqueada — selecione o texto e copie você."
      },
      giftLines: {
        coffee: {
          waiting: ["Café servido. A cota, não.", "Este café é por sua conta — o próximo reset é por minha.", "Sem açúcar: os requisitos já estão doces demais."],
          soon: ["Larga o café. Tira a mão do meu botão.", "Deixa eu terminar esse gole e a gente vê."],
          reset: ["Até os deuses tomam café.", "Café pra quem constrói, token pra quem sonha."]
        },
        razor: {
          waiting: ["Não é barba, é sua barra de progresso da espera.", "Para de apressar, a barba vai bifurcar.", "Quando eu resetar, a barba reseta junto."],
          soon: ["Aparo deste lado, aperto do outro.", "Primeiro o reset, depois a barba."],
          reset: ["Recém-consagrado — não toque na barba sagrada.", "A auréola tem filtro de beleza. Nem precisa barbear."]
        },
        pray: {
          waiting: ["Esse «padrinho» fez meu mouse tremer.", "Não me chama de bebê… e padrinho, segura aí.", "Seu pedido entrou na fila cósmica."],
          soon: ["A mão tá levantada. Mais dois minutos.", "O ritual tá pronto — espera o anúncio."],
          reset: ["Cota entregue. Não gasta perguntando se eu sou bonito.", "Reunião encerrada! Vai terminar aquele projeto."]
        }
      },
      fortunes: [
        { rank: "Sorte grande", line: "Um tremor do padrinho e todo projeto sai.", detail: "Faça: requisitos claros. Evite: cota cheia e zero ideias." },
        { rank: "Sorte preguiçosa", line: "Cota zerada — enfim desculpa pra sair.", detail: "Faça: beba água. Evite: ficar dando refresh na página de uso." },
        { rank: "Sorte engenheira", line: "Reset vem do padrinho; rollback vem de você.", detail: "Faça: backups. Evite: apostar tudo num botão." },
        { rank: "Sorte barbuda", line: "A barba dele cresce. Sua lista de requisitos também.", detail: "Faça: corte uma feature. Evite: mais «um pedidinho»." },
        { rank: "Sorte divina", line: "Chove token. Continue escrevendo.", detail: "Faça: termine aquele mini projeto. Evite: abrir dez frentes novas." },
        { rank: "Sorte paciente", line: "Ele rola o feed. Você dá refresh.", detail: "Faça: olhe pela janela. Evite: ler piada como promessa." }
      ]
    },

    ko: {
      meta: {
        title: "Tibo, 오늘은 눌렀을까? · aitibo.cn",
        hiddenTitle: "아직 기다리는 중? · aitibo.cn",
        description: "Tibo, 오늘은 눌렀을까? 조금 초조한 리셋 관측소. 로컬 인터랙티브 프로토타입."
      },
      skip: "본문으로 건너뛰기",
      brandAria: "aitibo 홈",
      navAria: "주 내비게이션",
      langAria: "언어 선택",
      nav: { radar: "리셋 레이더", feed: "그의 소식", history: "리셋 달력", about: "소개", subscribe: "알림 받기" },
      preview: { badge: "로컬 인터랙티브 프로토타입", note: "X 미연결 · 아래 상태를 바꿔 체험" },
      hero: {
        eyebrow: "조금 초조한 리셋 관측소", title: "오늘 눌렀어", mark: "?",
        cta: "리셋되면 알려줘", evidence: "예측 근거 보기", note: "만드는 건 너. 누르는 건 그."
      },
      speechTag: "사이트 대사",
      nudge: { label: "쿡 찔러보기", hint: "장난일 뿐, 리셋 안 됨", speech: "알겠어, 커피 한 모금만 더.", speechReset: "이미 눌렀어. 어서 만들어!" },
      picker: {
        aria: "캐릭터 상태 미리보기",
        waiting: "기다리는 중", waitingSub: "버튼은 아직",
        soon: "누를 준비", soonSub: "할 말 있는 듯",
        reset: "신이 됨", resetSub: "리셋, 개시!"
      },
      sceneCaption: "같은 Tibo, 다른 정신 상태.",
      offerings: { aria: "만화 Tibo와 놀기", coffee: "한 잔 더", razor: "면도할 시간", pray: "대부님, 살려주세요", note: "전부 장난. 대부님에겐 안 닿아요." },
      feed: { title: "방금 한 말", note: "지난 내용 · 데모", follow: "X에서 Tibo 최신 소식 보기" },
      post: { disclaimer: "공개 발언일 뿐, 현재 상태 아님", source: "출처 보기" },
      post2: {
        meta: "인터뷰 요지", badge: "배경 자료",
        quote: "어떤 때는 사용성 문제의 보상이고, 어떤 때는 그냥 다 함께 축하하고 싶은 거죠.",
        context: "리셋 버튼은 진짜다. 기대도 진짜다.",
        source: "Matthew Berman 인터뷰 · 23:37부터", link: "직접 들어보기"
      },
      forecast: {
        title: "다음 리셋, 가능성은?", note: "데모 판정",
        signals: { promise: "명확한 예고", activity: "최근 움직임", completion: "완료 공지" },
        reasoningSummary: "판정 방식 보기",
        reasoningStatic: "정식 버전은 원문, 답글 맥락, 시각, 적용 범위를 종합합니다. 이 페이지는 자동 수집도 예측 모델도 돌리지 않습니다.",
        footnote: "출처가 있어야 근거가 된다. 예고도 확정까지 기다려야 한다."
      },
      history: { title: "매번, 새로 시작", sub: "서프라이즈를 기록하고, 리셋 종류도 구분해 두자." },
      filters: { aria: "히스토리 유형 필터", all: "전체", reset: "직접 리셋", banked: "리셋 쿠폰" },
      events: [
        { label: "유형 예시 · 01", title: "장애 보상", desc: "고치고, 모두가 다시 시작.", source: "출처: 인터뷰" },
        { label: "유형 예시 · 02", title: "리셋 쿠폰 지급", desc: "필요할 때 골라서 사용.", source: "출처: 히스토리 인덱스" },
        { label: "유형 예시 · 03", title: "축하 리셋", desc: "좋은 날엔 코드를 조금 더.", source: "출처: 커뮤니티 재공유" }
      ],
      fortune: {
        eyebrow: "기다리는 동안 · 소소한 놀이", title: "오늘의 리셋 운세", sub: "코드는 기다려도 의식은 못 기다려.",
        pending: "미추첨", initial: "정성이면 통한다, 쿼터는 별개.", disclaimer: "사이트 재미 문구. 실제 리셋과 무관",
        draw: "한 장 뽑기", redraw: "다시 뽑기", copy: "내 운세 복사", suffix: " · 그저 재미",
        copyTpl: "[오늘의 리셋 운세 · {rank}]\n{line}\n{detail}\naitibo.cn · 팬 2차 창작, 그저 재미"
      },
      bottom: { note: "당신의 영감이<br><b>늘 쿼터보다 조금 많기를.</b>", cta: "다음 리셋, 나도 불러줘" },
      footer: { note: "독립 커뮤니티 2차 창작, OpenAI와 무관", tag: "열정은 유지, 마음은 여유롭게." },
      dialog: { close: "닫기" },
      sub: {
        eyebrow: "다음 리셋, 나도 불러줘", title: "기대는 여기에 두고 가세요.",
        desc: "알림 기능의 인터랙션 미리보기입니다. 설정은 이 브라우저에만 저장되며, 알림 서비스는 미연결 — 이메일이나 푸시는 보내지 않습니다.",
        promise: "명확한 예고가 뜨면", promiseSub: "남들보다 먼저",
        reset: "리셋을 발표하면", resetSub: "작업할 시간",
        save: "이 기기에 저장",
        readError: "저장된 설정을 읽지 못했습니다. 다시 선택해 주세요.", saveError: "브라우저가 로컬 저장을 거부했습니다. 설정 미저장."
      },
      about: {
        eyebrow: "이 작은 사이트에 대해", title: "버튼 하나를 기다리며,<br>작은 놀라움도 기다리며.",
        desc1: "aitibo.cn은 Tibo의 공개 리셋 동향을 중심으로 만든 독립 커뮤니티 프로젝트입니다. 이 버전은 로컬 인터랙티브 프로토타입으로 상태·타이머·판정은 모두 데모이며, 자료에는 출처를 달았습니다.",
        desc2: "다음 단계는 그의 공개 X 피드를 연결해 농담·예고·직접 리셋·쿠폰을 구분하고, 모든 판정이 원문으로 돌아가게 하는 것. 만화 대사는 이 사이트의 2차 창작입니다.",
        ok: "알겠어요"
      },
      units: { day: "일", hour: "시간", min: "분" },
      timer: { demoTag: "데모 타이머" },
      stateNames: { waiting: "기다리는 중", soon: "누를 준비", reset: "리셋 봉신" },
      states: {
        waiting: {
          status: "아직 그를 기다리는 중", line: "수염은 자라는데 버튼은 안 눌려.", speech: "급할 거 없어, X 좀 보는 중",
          alt: "수염 난 만화 Tibo가 리셋 버튼 옆에 엎드려 기다리는 모습",
          forecast: "단서 없음…", description: "현재 예시는 명확한 리셋 약속이 아닙니다. 서두르지 말고 하고 싶은 것부터 메모해 두세요.",
          signals: ["발견 못 함", "일상 소통", "확인 대기"], badge: "농담",
          quote: "“리셋 발표인 줄 알았어? 그냥 피드 보러 온 건데.”", context: "지난 글 의역 · 2026년 7월 15일",
          semantic: "의미 판정: 농담, 리셋 약속 없음",
          reasoning: "예시에 '리셋'이 나오지만 문장은 명확히 리셋 예고를 부정한다. 키워드 매칭은 약속이 아니다.",
          timerLabel: "지난 리셋으로부터"
        },
        soon: {
          status: "예고함 · 데모", line: "손은 이미 들었다. 조금만 더.", speech: "그래그래, 손 들었어.",
          alt: "만화 Tibo가 눈썹을 치켜 올리며 빨간 리셋 버튼 위에 손가락을 댄 모습",
          forecast: "명확한 예고 있음", description: "예시에 '오후에 리셋' 약속이 포함됩니다. 범위와 실제 완료는 계속 확인 필요.",
          signals: ["'오후에 리셋'", "명확한 시간대", "완료 대기"], badge: "예고",
          quote: "“자기야라고 부르지 마 — 오후에 리셋할게.”", context: "지난 답글 의역 · 2026년 7월 9일",
          semantic: "의미 판정: 미래 약속, 완료 미발표",
          reasoning: "'오후에 리셋'은 미래 시점과 명확한 동작을 담아 막연한 축하보다 강하다. 다만 정확한 시각이 없어 정밀 카운트다운은 안 나오고, 지난 답글을 오늘의 새 공지로도 보지 않는다.",
          timerLabel: "지난 리셋으로부터"
        },
        reset: {
          status: "리셋 봉신 · 데모", line: "버튼 하나에 세상에 다시 빛이.", speech: "가라. 대단한 걸 만들어라.",
          alt: "흰 옷에 금빛 후광을 두른 만화 Tibo가 리셋 버튼을 누르고 황금 토큰이 흩날리는 모습",
          forecast: "리셋 발표!", description: "예시 공지는 완료형 어조. 내 쿼터가 돌아왔는지는 제품 안의 실제 표시로 확인하세요.",
          signals: ["공지가 됨", "새 경험 축하", "완료 발표"], badge: "발표됨",
          quote: "“멋진 한 주를 기념해 모든 유료 플랜의 Codex 쿼터를 리셋했습니다.”", context: "지난 공지 의역 · 2026년 4월 28일",
          semantic: "의미 판정: 완료 공지, 범위는 Codex 유료 플랜",
          reasoning: "지난 공지는 완료형 어조에 대상 플랜도 명시. 공지는 공개 정보일 뿐 계정별 도달을 증명하지 못하고, 직접 리셋과 쿠폰 지급을 혼동해선 안 된다.",
          timerLabel: "이번 리셋으로부터"
        }
      },
      toasts: {
        preview: "미리보기: {state} · 실시간 아님",
        nudge: "만화 캐릭터를 찔렀을 뿐. 실제 쿼터는 그대로.",
        savedOn: "이 기기에 저장됨 · 알림은 발송되지 않음",
        savedOff: "기기 알림 설정 해제됨",
        gift: "만화 Tibo가 응답 · 장난이며 본인에겐 안 감",
        fortune: "운세 완성. 소원은 맡아둘게.",
        copied: "운세 복사 완료 — 같이 기다리는 사람에게 보내봐.",
        copyFail: "복사가 차단됨 — 직접 선택해서 복사해줘."
      },
      giftLines: {
        coffee: {
          waiting: ["커피는 리필됐는데 쿼터는 아직.", "이 잔은 네가 사고, 다음 리셋은 내가 쏠게.", "설탕은 됐어. 요구사항이 이미 달잖아."],
          soon: ["커피 내려놔. 내 버튼 건들지 마.", "이 한 모금 마시고 생각해볼게."],
          reset: ["신도 카페인이 필요하다.", "커피는 만드는 자에게, 토큰은 꿈꾸는 자에게."]
        },
        razor: {
          waiting: ["이건 수염이자 네 기다림의 진행 바.", "재촉 마라, 수염이 갈라진다.", "내가 리셋할 때 수염도 같이 리셋."],
          soon: ["이쪽 밀고, 저쪽 누른다.", "리셋 먼저, 단장은 나중."],
          reset: ["갓 봉신했다, 신성한 수염에 손대지 마.", "후광이 미백 필터라 면도 필요 없어."]
        },
        pray: {
          waiting: ["그 '대부님' 소리에 마우스가 떨렸다.", "자기야는 안 돼…… 대부님도 잠깐만.", "네 소원은 우주 큐에 들어갔다."],
          soon: ["손은 들었으니 조금만 더.", "의식은 충분, 공지를 기다려."],
          reset: ["쿼터 줬으니 잘생겼냐고 묻지 마.", "해산! 가서 그 프로젝트 완성해."]
        }
      },
      fortunes: [
        { rank: "대길", line: "대부 손끝 한 번이면 프로젝트 전부 완성.", detail: "길: 요구사항 깔끔하게. 흉: 쿼터만 넘치고 아이디어 제로." },
        { rank: "뺀질운", line: "쿼터 제로, 드디어 퇴근할 명분.", detail: "길: 물 마시기. 흉: 사용량 페이지 새로고침 연타." },
        { rank: "엔지니어운", line: "리셋은 대부님께, 롤백은 내 손으로.", detail: "길: 백업해두기. 흉: 버튼 하나에 올인." },
        { rank: "수염운", line: "그의 수염이 자라듯 네 요구사항도 자란다.", detail: "길: 기능 하나 덜기. 흉: '작은 것' 하나 더." },
        { rank: "봉신운", line: "토큰 비가 내린다. 계속 써라.", detail: "길: 그 소형 프로젝트 완성. 흉: 새 구덩이 열 개." },
        { rank: "인내운", line: "그는 스크롤, 너는 새로고침.", detail: "길: 창밖 보기. 흉: 농담을 예고로 읽기." }
      ]
    }
  };

  let current = "zh-CN";
  const dig = (obj, path) => path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
  const t = (key, vars) => {
    let v = dig(dicts[current], key);
    if (v === undefined) v = dig(dicts.en, key);
    if (v === undefined) v = dig(dicts["zh-CN"], key);
    if (v === undefined) return key;
    if (vars && typeof v === "string") for (const [k, val] of Object.entries(vars)) v = v.replaceAll("{" + k + "}", val);
    return v;
  };
  const match = (raw) => {
    const v = (raw || "").toLowerCase().trim();
    if (!v) return null;
    if (v.startsWith("zh")) return "zh-CN";
    for (const { code } of LANGS) if (code !== "zh-CN" && (v === code || v.startsWith(code + "-"))) return code;
    return null;
  };
  const detect = () => {
    const fromUrl = match(new URLSearchParams(location.search).get("lang"));
    if (fromUrl) return fromUrl;
    try {
      const saved = localStorage.getItem("aitibo:lang");
      if (saved && dicts[saved]) return saved;
    } catch {}
    return match(navigator.language) || "en";
  };
  return {
    LANGS, dicts, t, detect,
    get lang() { return current; },
    set lang(v) { if (dicts[v]) current = v; }
  };
})();
