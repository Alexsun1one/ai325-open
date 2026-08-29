---
name: 先锋队台账 · 每日蒸馏刊
description: 纸白底上蓝墨印刷的品鉴单——蓝是表单，琥珀是酒液，每期日报是对当天那一锅的一张鉴定单。
colors:
  paper: "#f2f1ec"
  paper-2: "#e9e7e0"
  paper-3: "#dedbd2"
  rule: "#c9c6bc"
  rule-soft: "#dddacf"
  ink: "#15171b"
  ink-2: "#3f434b"
  ink-3: "#676c76"
  blue: "#1c47a3"
  blue-2: "#2e5fcb"
  blue-text: "#1a42a0"
  blue-wash: "#dfe7f8"
  blue-wash-2: "#c6d5f2"
  amber: "#c37a14"
  amber-2: "#d9953a"
  amber-deep: "#8c5306"
  amber-text: "#7e4a05"
  amber-wash: "#f4e4c3"
  amber-wash-2: "#ebd19c"
  cinnabar: "#b8331f"
  cinnabar-text: "#a12c1a"
  cinnabar-wash: "#f3dad4"
  teal: "#107878"
  teal-text: "#0d6a6a"
  teal-wash: "#d2ece8"
typography:
  display:
    fontFamily: "Noto Serif SC, Songti SC, STSong, SimSun, Noto Serif CJK SC, serif"
    fontSize: "40px / sm 52px / lg 58px"
    fontWeight: 900
    lineHeight: 1.18
    letterSpacing: "0.01em"
  headline:
    fontFamily: "Noto Serif SC, Songti SC, STSong, SimSun, serif"
    fontSize: "26px / sm 30px"
    fontWeight: 700
    lineHeight: 1.375
    letterSpacing: "0.01em"
  title:
    fontFamily: "Noto Serif SC, Songti SC, STSong, SimSun, serif"
    fontSize: "19px / 20px / 24px / sm 26px"
    fontWeight: 700
    lineHeight: 1.375
  body:
    fontFamily: "Noto Serif SC, Songti SC, STSong, SimSun, serif"
    fontSize: "17px / max-width 640px 16px"
    fontWeight: 400
    lineHeight: 1.9
  hand:
    fontFamily: "LXGW WenKai, Kaiti SC, STKaiti, KaiTi, Noto Serif SC, serif"
    fontSize: "17px / 18px"
    fontWeight: 400
    lineHeight: 1.9
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, PingFang SC, Hiragino Sans GB, Noto Sans SC, system-ui, sans-serif"
    fontSize: "11.5px"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "0.14em"
  num:
    fontFamily: "-apple-system, BlinkMacSystemFont, PingFang SC, Hiragino Sans GB, Noto Sans SC, system-ui, sans-serif"
    fontWeight: 600
    letterSpacing: "-0.01em"
    fontFeature: "tnum 1, lnum 1"
rounded:
  none: "0"
  chip: "3px"
  sm: "4px"
  btn: "5px"
  md: "6px"
  field: "8px"
  lg: "10px"
  xl: "12px"
  full: "9999px"
spacing:
  page-x: "20px"
  page-x-sm: "32px"
  container: "1180px"
  rail: "168px"
  gutter: "40px"
  sec-top: "28px"
  sec-top-lg: "32px"
  sec-bottom: "56px"
  sec-bottom-lg: "80px"
  block: "56px"
components:
  section-label:
    textColor: "{colors.blue-text}"
    typography: "{typography.label}"
    width: "{spacing.rail}"
  stamp:
    textColor: "{colors.blue}"
    size: "196px"
  intake-field:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "10px 16px 12px"
  intake-field-hover:
    backgroundColor: "{colors.paper-2}"
  tone-tag-serious:
    backgroundColor: "{colors.blue-wash}"
    textColor: "{colors.blue-text}"
    rounded: "{rounded.chip}"
    padding: "3px 6px"
  tone-tag-joke:
    backgroundColor: "{colors.teal-wash}"
    textColor: "{colors.teal-text}"
    rounded: "{rounded.chip}"
    padding: "3px 6px"
  tone-tag-half:
    backgroundColor: "{colors.cinnabar-wash}"
    textColor: "{colors.cinnabar-text}"
    rounded: "{rounded.chip}"
    padding: "3px 6px"
  button-primary:
    backgroundColor: "{colors.blue}"
    textColor: "{colors.paper}"
    rounded: "{rounded.btn}"
    padding: "10px 20px"
  button-quiet:
    backgroundColor: "{colors.blue-wash}"
    textColor: "{colors.blue-text}"
    rounded: "{rounded.md}"
    padding: "8px 14px"
  input-field:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
  input-field-focus:
    backgroundColor: "{colors.paper-2}"
  nav-link:
    textColor: "{colors.ink-2}"
    rounded: "{rounded.md}"
    padding: "6px 10px"
  nav-link-hover:
    backgroundColor: "{colors.paper-2}"
    textColor: "{colors.ink}"
  chip-thread:
    backgroundColor: "{colors.blue-wash}"
    textColor: "{colors.blue-text}"
    rounded: "{rounded.full}"
    padding: "4px 10px"
  card-sheet:
    backgroundColor: "{colors.paper-2}"
    rounded: "{rounded.lg}"
    padding: "20px"
  callout-gap:
    backgroundColor: "{colors.amber-wash}"
    textColor: "{colors.amber-text}"
    rounded: "{rounded.md}"
    padding: "8px 12px"
---

# Design System: 先锋队台账 · 每日蒸馏刊

## Overview

**Creative North Star: "品鉴单 The Tasting Sheet"**

这是一张**印刷出来的鉴定表单**，不是一个网页仪表盘。世界的物理设定只有两种材料：**纸和蓝墨**（表单本身：表头、格线、批次章、器皿轮廓），以及**琥珀色的酒液**（被测量出来的东西：柱高、液位、分数、度数、打勾）。读者拿到的是「第 001 批」的化验单，不是「本周数据概览」。这条线一旦分清，页面上任何一个元素的颜色就不用再讨论：它要么是表单，要么是被测量的内容。

密度是**印刷密度**，不是卡片密度。信息靠**格线分区**（`border-top` + 左栏蓝标签），不靠卡片盒子分区——全站没有一面卡片墙。留白给正文：宋体 17px/1.9、行长 42em，一整屏可以只有一段字和一条线。装饰只有一层极轻的纸张网点（22px 网格、0.6px 圆点），没有噪点滤镜、没有渐变背景、没有大面积色块。

确认拒绝的东西写在方向契约里，也在代码里守住了：**渐变 hero、大数字统计卡片墙、半透明模糊导航、霓虹发光、emoji 当图标**。导航是不透明纸色 + 一条格线；唯一的大数字（度数 88px）只出现一次，且被五维格子和证据文本包着，不是一张孤立的 KPI 卡。

**Key Characteristics:**
- **两种材料**：蓝 = 表单印刷色，琥珀 = 被测量的酒液。第三、第四色（朱砂 / 青）只服务语气语义，不做装饰。
- **表单语法**：左栏 168px 蓝标签 + 右栏内容，节与节之间只有一条 1px 格线。
- **一个被授权的时刻**：圆形批次章在首屏落下（-14° → -7°），全站没有第二个入场表演。
- **随滚动的液位**：阅读进度是往缸里注酒，不是进度条。
- **宋体读、文楷写、系统字体算数**：三套字体三种身份，永不互串。
- **诚实优先于完整**：缺口有专门的琥珀警示条，未来批次画虚线空槽，不用平滑或占位图糊过去。

## Colors

调色盘是「一张单色印刷表单 + 一种被灌进去的液体」，加两枚语义专用色。**明色值以本文件 frontmatter 为准**；下表给职责、禁用场景与夜间值。所有色对在两个主题下都以 `--*-text` 变体承担文字，`--*` 原色承担图形——白字白底是死罪，写文字时永远选 `-text`。

### Primary

- **表单蓝 blue**（夜间 `#3b6fe0`）：表单本身的印刷色。用于批次章全部笔画、器皿玻璃轮廓与刻度、双线菱形分隔、主按钮底、活动目录刻度。**禁用**：正文文字（用 blue-text）、大面积填充、任何"品牌渐变"。
- **交互蓝 blue-2**（夜间 `#5c8af0`）：只做交互反馈——`:focus-visible` 2px 描边（offset 3px）、悬停时的边框换色、黑话词条的点线下划线、图上"有大事记"那根柱的描边。**禁用**：静态装饰描边。
- **蓝字 blue-text**（夜间 `#8fb0ff`）：全站所有蓝色文字——左栏标签、人名、链接、时间戳、批次号、期刊列头。**禁用**：正文段落（正文永远是墨色）。
- **蓝底片 blue-wash / blue-wash-2**（夜间 `#18274a` / `#1f3463`）：蓝色文字的底片——线索 chip、前情提要框、成员标签、度数图的等级带、进料字段的分隔格线（blue-wash-2）。**禁用**：整节背景。

### Secondary

- **酒液琥珀 amber**（夜间 `#d79a3a`）：一切被测量出来的量——蒸馏曲线的酒心柱、液位管与器皿液体、五维分数格、时间线走过的点、行动清单进度与打勾框、复利曲线与度数折线。**禁用**：文字（用 amber-text）、导航、按钮底、任何与"数值"无关的强调。
- **深琥珀 amber-deep**（夜间 `#b3782a`）：琥珀图形的描边与酒心括号；打勾框选中态的边。**禁用**：填充。
- **琥珀字 amber-text**（夜间 `#f0be6a`）：度数、百分比读数、峰值标注、缺口告示、顺延提示。**禁用**：长段落。
- **琥珀底片 amber-wash / amber-wash-2**（夜间 `#2e2412` / `#4a3715`）：手写体 `<u>` 的荧光笔底（62%–92% 渐变带）、缺口告示条底、`::selection` 选中底。**禁用**：卡片底。

### Tertiary（语义专用，不作装饰色）

- **朱砂 cinnabar / cinnabar-text / cinnabar-wash**（夜间 `#e0624f` / `#f08a79` / `#3a1c17`）：只有两个用途——语气三档里的**「半真」**，以及**未兑现的承诺 / 报错**。**禁用**：任何"强调红"、任何促销色用法。
- **青 teal / teal-text / teal-wash**（夜间 `#3eafa8` / `#6fd2cb` / `#10302f`）：只有两个用途——语气三档里的**「玩笑」**，以及**成功提示**。**禁用**：链接、图表系列色。

### Neutral

- **纸 paper / paper-2 / paper-3**（夜间 `#0f1219` / `#161a24` / `#1e2330`）：页底 / 次级底（悬停、抽屉内块、表单卡）/ 进度槽。
- **墨 ink / ink-2 / ink-3**（夜间 `#eceae3` / `#c3c6ce` / `#8f95a3`）：正文与标题 / 次要正文与手写体 / 元信息与说明。
- **格线 rule / rule-soft**（夜间 `#2b3142` / `#222838`）：主格线（节分隔、表头上下线、表格外框）/ 次格线（行分隔、图上刻度线、滚动条）。

### Named Rules

**The Two Materials Rule.** 每个有颜色的元素先回答一个问题：你是表单，还是被测量的内容？表单画蓝，内容画琥珀。回答不了的元素，说明它不该存在。

**The Semantic Reserve Rule.** 朱砂和青被语气系统征用了。想加第三个强调色时，答案永远是"用蓝的深浅或琥珀的深浅"，不是"再挑一个颜色"。

**The Text Variant Rule.** 文字只能取 `--ink*`、`--blue-text`、`--amber-text`、`--cinnabar-text`、`--teal-text`。直接把 `--blue` / `--amber` / `--cinnabar` / `--teal` 写在 `color` 上视为缺陷——那是给图形准备的浓度。

## Typography

**Display / Body Font:** Noto Serif SC（回退 Songti SC / STSong / SimSun）——正文与所有标题。
**Hand Font:** LXGW WenKai 文楷（回退 Kaiti SC / STKaiti）——手写批注层。
**Label / Numeral Font:** 系统栈 `-apple-system / PingFang SC / Hiragino Sans GB / Noto Sans SC`——标签、元信息、全部数字。

**Character:** 三层字体是三种**身份**，不是三种口味。宋体在说"这是被排印出来的正文"；文楷在说"这句是整理者写上去的，不是原话"；系统字体在说"这是仪器读数"。三者永不互相顶替：数字绝不用宋体（会合成假粗体、宽度不齐），延伸判断绝不用宋体（会冒充原话），正文绝不用系统字体（会像后台）。

### Hierarchy

- **Display**（900，40px / sm 52px / lg 58px，行高 1.18，字距 0.01em）：每期刊名。首屏唯一的大字，`max-w-[14em]`。分页刊头降一档（36 / 46 / 52px）。
- **Headline**（700，26px / sm 30px，行高 1.375）：节内主标题 `H2`、登录墙标题。
- **Title**（700，24–26px / 20px / 19px 三档）：主题幕标题（24 / sm 26）、深潜与出品小节标题（20）、悬案与词条标题（19）。
- **Body**（400，17px，行高 1.9，行长 42em）：`.prose-sheet`。次级正文 15.5–16px / 1.8–1.85；窄屏整站降到 16px / 1.85。刊头导语 17px、`max-w-[36em]`；口径说明 13.5px、`max-w-[44em]`。
- **Hand**（400，17–18px，行高 1.9，色 ink-2）：`.hand` 与 `.prose-sheet u`。用于「没说破的」深潜、分歧裁决、本期感谢、新人第一句、以及所有让用户写字的输入框（笔记、评论）。`<u>` 额外带琥珀荧光笔底。
- **Label**（500，11.5px，字距 0.14em，色 blue-text）：`.label`。左栏节名、表头字段名、抽屉分区名。
- **Num**（600，系统字体，`tabular-nums lining-nums`，字距 -0.01em）：`.num`。所有数字——批次号、进料读数、度数、时间戳、计数。特大读数：度数 88px（字距 -0.02em）、打卡计数 42px、进料 24–26px。

### Named Rules

**The Three Hands Rule.** 打字的用宋体，手写的用文楷，机器读的用系统字体。一段文字改字体之前，先说清它换了哪个身份；说不清就不换。

**The Never-Synthesize Rule.** 数字一律 `.num`，永不套宋体、永不设不存在的字重。中文衬线合成粗体会糊，等宽数字对不齐就没法逐行比。

**The Extension-Is-Handwriting Rule.** 凡整理者延伸的内容（深潜、裁决、感谢语），必须落在文楷层，且带琥珀荧光笔底。逐字原话永远是宋体加「」。这一条是内容诚信的视觉承载，不能为版式统一而牺牲。

## Layout

**容器与栅格。** 全站单一容器：`max-width 1180px`，左右 padding 20px（≥640px 起 32px）。没有第二种容器宽度，分页与日报页共用 `PageShell`。

**表单节栅格（全站骨架）。** 每一节是 `Section`：`lg` 及以上为 `168px | 1fr` 两列，列间距 40px；左列放蓝标签 + 一行 12px 灰副题（可选 96px 缩略插图），且 `sticky top-80px` 跟着读；右列放内容。节的上沿是一条 1px `rule` 格线，`padding-top` 28px（lg 32px）、`padding-bottom` 56px（lg 80px）。**窄屏下左栏塌成内容上方的一行标签**，不是消失。

**刊头。** `1fr | 232px`：左边是"样品信息行 → 刊名 → 导语 → 鉴定人"，右边是批次章 + 器皿。样品信息行是一条 `border-y` 包住的四格 `<dl>`（窄屏两格），每格 `label` + `.num` 值——这一行定义了整站的表头语法，分页 `PageHead` 逐字复用。

**断点行为。**
- `640px (sm)`：正文 17→16px；四格表头由 2 列变 4 列；页边距 20→32px；导航从换行两排收成一排。
- `1024px (lg)`：表单节展开为左标签栏 + 右内容；段落悬停工具条出现；液位管出现；双列内容（深潜、成长）分栏。
- `1280px (xl)`：右侧目录刻度列出现；逐字摘录由 2 栏变 3 栏。

**层序（z-index）。** 环境粒子 0 → 正文 1 → 段落工具条 30 / 目录 30 → 导航 40 / 抽屉 40 → 悬浮释义与「记下」气泡 50。

**溢出。** 宽内容（线索图、表格）自带 `overflow-x-auto` + 窄屏「可左右滑动」提示（`ScrollHint`），页面主体永不横向滚动。

### Named Rules

**The Left-Rail Rule.** 每一节都要能在左栏用一个不超过 5 字的蓝标签说清自己是什么（进料 / 蒸馏曲线 / 真伪鉴定 / 出品…）。起不出这个标签的内容，说明它不该是一节。

**The Rule-Not-Box Rule.** 分区靠横线，不靠盒子。需要边框时优先只画上边线（`border-top`），四边框留给真正的容器（抽屉、表单卡、悬浮层）。

## Elevation & Depth

**这是一张纸，纸不投影。** 页面的所有内容层——节、表格、图、引文、成员条目——一律零投影、零圆角、靠格线和纸色深浅（`paper` / `paper-2` / `paper-3`）分层。深度只在**离开纸面**时出现：悬浮层、抽屉、跟手气泡。

### Shadow Vocabulary

- **sheet**（`--shadow-sheet`：`0 1px 2px rgba(21,23,27,.06), 0 10px 28px -14px rgba(21,23,27,.22)`；夜间加深至 `.5 / .7`）：贴着纸面的小浮层——段落悬停工具条。
- **pop**（`--shadow-pop`：`0 2px 6px rgba(21,23,27,.08), 0 16px 40px -16px rgba(21,23,27,.3)`；夜间 `.5 / .8`）：真正浮起来的层——黑话释义气泡、「记下这段」气泡、笔记与评论抽屉、目录展开面板、常驻圆角按钮、头像名牌。

### Named Rules

**The Paper-Doesn't-Lift Rule.** 内容不投影。看到一个内容块想加阴影，先问它是不是应该改成一条格线。只有"浮在文档之上、可以关掉"的东西才配拿 `pop`。

**The Two-Shadow Rule.** 全站只有 `sheet` 和 `pop` 两级，且都定义为 token。禁止就地写 `box-shadow`（唯一例外：主题开关滑块的 1px 微影）。

## Shapes

**默认圆角是 0。** 表单的格子、进料字段、五维分数格、图表区、引文栏、节分隔——全部直角。圆角是"这不是印在纸上的东西"的信号，按离纸面的距离分级：

- **0**：所有格线分区与表格状内容。
- **3px（chip）/ 4px（sm）**：贴纸的小标记——语气章、成员标签、状态徽记、打勾框、`:focus-visible` 的 2px 圆角。
- **5px（btn）/ 6px（md）**：表单控件与静默按钮、提示条、导航项。
- **8px（field）**：多行输入框。
- **10px（lg）/ 12px（xl）**：离开纸面的容器——前情提要框、相邻批次卡、抽屉内条目、目录面板、感谢框。
- **full**：只给圆形与胶囊——头像、时间线圆点、液位管、线索 chip、常驻悬浮按钮、进度槽。

**线宽语法。** 1px 是格线；0.8px 是图上的次刻度；1.5–2.4px 是画出来的器物（章的环、器皿壁、菱形）。虚线只有一个含义：**这个东西还不存在**（未来批次空槽、往未来延伸的曲线尾）。点线（dotted）也只有一个含义：**这是一个可以问的词或一格填空**（黑话下划线、进料字段底线）。

### Named Rules

**The Dashed-Means-Absent Rule.** 虚线不是装饰。页面上任何虚线都必须代表"还没有的数据"或"等着被填的空位"，读者据此判断真伪。

## Components

### 表单节 Section（全站骨架）
- **形状：** 上沿 1px `rule` 格线，无圆角、无底色、无投影。
- **结构：** `168px` 左栏（`.label` 蓝标签 + 12px 灰副题 + 可选 96px 插图，`lg:sticky top-80px`）| `1fr` 内容。
- **间距：** `pt 28/32px`，`pb 56/80px`，列间距 40px。
- **props：** `id`（同时是目录锚点与评论锚点前缀）、`label`、`sub`、`spot`。

### 按钮 Buttons
- **Primary**（`Btn`）：蓝底纸色字，5px 圆角，`10px 20px`，14px 600 系统字体；悬停 `opacity .9`；禁用 `opacity .55` + `not-allowed`；忙碌时左侧转一个 3px 细环。用于提交类动作（登录、注册、订阅）。
- **Quiet**（蓝底片按钮）：`blue-wash` 底 + `blue` 边 + `blue-text` 字，6px 圆角。用于次级确认（记下、发表、看全部画像）。
- **Ghost**（纸底描边）：`paper` 底 + `rule` 边 + `ink-2` 字，6px 圆角，悬停换 `blue-2` 边并转 `ink`。用于工具动作（打印、回到刊头、导出 .md）。
- **文字按钮**：无底无边，12px 系统字体 `ink-3`，悬停 `paper-2` 底 + `ink` 字。用于条目内动作（复制、分享卡、删除）。

### 输入 Inputs / Fields（`FormBits`）
- **样式：** 蓝标签**印在上方**，输入框是"填进去的那一格"：`paper` 底 + 1px `rule` 边 + 4px 圆角 + `8px 12px`，15px 系统字体。不是圆角胶囊。
- **Focus：** 边框转 `blue-2`，底色转 `paper-2/50`。不发光、不加环。
- **多行输入：** 8px 圆角、`paper-2/60` 底，且**字体是文楷**——用户写的字属于手写层。
- **提示 `Note`：** 三态 6px 圆角条——中性 `rule/paper-2`、错误 `cinnabar`（带 `role="alert"`）、成功 `teal`。

### 语气章 ToneTag（内容体系的一部分）
- **三档：** 认真 = 蓝（灯泡）、玩笑 = 青（笑脸）、半真 = 朱砂（火苗）。
- **样式：** 1px 同色边 + 同色底片 + 同色字，3px 圆角；`sm` 11px / `md` 13px 两档；`stamp` 时整体 `-2°`，像盖上去的。
- **图标：** 一律**单线 SVG**，`strokeWidth 2`、`round` 端点，与文字同色继承。`title` 属性写清三档的采信规则。

### 卡片 / 容器 Cards
- **不做卡片墙。** 内容默认无盒。真正的容器只有四类：抽屉（右侧 420px，`paper` 底 + 左侧 1px 边 + `pop` 影）、表单卡（10px 圆角 + `paper-2/50` 底 + `rule` 边）、提示框（10px 圆角 + `blue-wash/70` 或 `amber-wash`）、相邻批次卡（10px 圆角描边，悬停转 `blue-2` 边）。
- **内边距：** 表单卡 `20–24px`；提示框 `12–16px`；抽屉内条目 `12–16px`。

### 导航 Navigation
- **样式：** `sticky top-0`、**不透明 `paper` 底**、下沿一条 `rule` 格线、高 56px。绝不半透明、绝不背景模糊。
- **刊名：** 宋体 19/20px 900，右侧接一行 12px 系统字体副题（`sm` 起显示）。
- **链接：** 13–13.5px 系统字体 `ink-2`，6px 圆角，悬停 `paper-2` 底 + `ink` 字。无下划线、无当前项高亮块。需登录的栏目在文字后跟一枚 10px 单线锁形 SVG。
- **窄屏：** 不做汉堡菜单——链接换行成第二排，主题开关留在首排右端。
- **主题开关：** 56×32 胶囊，滑块 500ms `ease-out-expo` 位移 24px；日/夜图标是琥珀色单线 SVG。

### 签名物件（去掉内容也能认出这个世界）

**① 批次章 Stamp。** 纯蓝单色圆章，196px：外环 2.4px 且**故意断线**（`strokeDasharray`）像印油没吃满，再叠一层错位 1.2px 的浅重影；环文沿 `textPath` 走"先锋队台账 · 每日蒸馏 · TASTING SHEET · 日期"；中心从上到下是「第 001 批」/ 40px 度数 /「B 级 · 已鉴定」。落章角度 `-7°`。**每期页面只有一枚。**

**② 器皿 Vessel。** 236×256 的量杯：**蓝线玻璃 + 琥珀液体**——外壁 2.2px 蓝、内壁 0.8px 蓝 45% 透明、右壁一列长短交替刻度、纸色高光竖线一道。液面是两层错相慢波（4.8s / 7.2s 反向）+ 一圈纸色椭圆口沿，液体是 `amber-2 → amber-deep` 竖向渐变。右侧一条虚线引出实时百分比。**液位含义是累计批次的成长**，不是本期数值。

**③ 液位管 LiquidRail。** 左栏 148px 处一根 8px 宽、360px 高的玻璃管，`sticky` 在视口中线；阅读进度以琥珀液从下往上注入（`useScroll` + `useSpring`）；管侧 9 道刻度，底部一枚 9.5px 蓝标签「液位」。仅 `lg+` 显示。

**④ 掐头去尾括号（RunChart）。** 24 小时柱状图上方悬三段方括号：**酒头 / 酒心 / 酒尾**。酒心 = 含峰值且占总量 ≥50% 的最短连续窗口（`lib/cuts.ts`），括号 1.6px 深琥珀、柱子填 `amber`；酒头酒尾括号 1px 蓝 75%、柱子填 `amber-wash-2`。括号下写"N 条 · X%"。有大事记的小时，柱子加 1.2px `blue-2` 描边。

**⑤ 双线菱形分隔 DoubleRule。** 两条相距 4px 的 `blue/70` 细线，两端各一枚 7px 蓝色 45° 方块。**只用在刊头之下和页脚之上**，是"表单开始 / 表单结束"的印刷记号，不做通用分隔。

### 交互件
- **黑话悬停 TermHover：** 正文里 `dfn[data-term]` 带 `blue-2` 点线下划线 + `cursor:help`；悬停或点击弹出 300px 纸色卡（10px 圆角 + `pop`），卡内左上是词条（宋体 15px 粗）、右上是「黑话词典」蓝标签。滚动即关。
- **记下笔记 Notebook：** 选中正文 ≥4 字弹出「记下这段 ✎」胶囊（蓝边纸底），存进右侧抽屉；批注输入框是文楷；按批次存 `localStorage`（`xf-notes-<date>`），可导出 Markdown。左下常驻圆角按钮带琥珀计数点。**页面明写「只存在这台设备」。**
- **段落工具 ParagraphTools：** 每个正文段落自动获得稳定锚点 `date#sectionId-pN` 与 `.has-anchor`（`lg+` 悬停时底色是 45% 的 `blue-wash`，4px 圆角）；右侧浮出一枚圆角工具条：评论（带计数）+ 导出分享卡。后端未接通时**如实说明**，不假装成功。
- **行动打勾 Growth / TodoCheck：** 18px 方框，未选是 `blue-2` 边 + 纸底（"待填的空格"），选中是 `amber-deep` 边 + `amber` 底 + 纸色对勾（`scale 0→1`，300ms `ease-out-expo`）。顶部一条 3–4px 琥珀进度条。两处共用同一 `localStorage` 键 `xf-todo-<date>`，勾选互通。
- **目录 Toc：** `xl+` 固定在右侧中线，收起时只是一列 2.5px 短横（当前项 5px 蓝）；悬停或钉住时整列展开成节名 + `NN/12` 计数。窄屏降级为右下角胶囊 + 上弹列表。
- **分享卡 sharecard：** 1080×1350 竖版 PNG，就地读 CSS 变量出图，因此**跟随当前主题**：纸底 + 36px 网点 + 3px 蓝外框 + 蓝圆章 + 琥珀「」引号 + 页脚口径声明。

### 动效纪律
- **一个被授权的时刻。** 首屏只有批次章落下（`delay .9s`，`scale 1.25→1`、`rotate -14°→-7°`，0.55s）与种子入缸（1.15s 起落、1.6s 涟漪 + 液位起升、2.4s 稳定）。除此之外没有入场表演。
- **一条缓动。** `--ease-out-expo: cubic-bezier(.16,1,.3,1)`，全站唯一。时长：微交互 0.16–0.22s，展开/抽屉 0.26–0.35s，图形入场 0.4–1.1s。
- **动画必须承载读数。** 柱子长高 = 消息量，格子注满 = 分数，液位上升 = 阅读进度/累计批次，线条画出 = 累积增长。不做纯装饰位移。
- **随滚动的只有液位。** `LiquidRail`（阅读进度）与 `Timeline`（走过的事件点由纸色转琥珀）用 `useScroll`；其余一律 `useInView { once: true }`，滚回去不重播。
- **粒子极轻。** `Ambient` 是全屏 canvas 的上浮气泡：数量 `≤46`（按面积 W×H/42000），半径 0.8–2.6px，**透明度 0.05–0.12**，70% 琥珀 / 30% 蓝；随主题变量热更新，页面隐藏时停帧。它只能被余光看见。
- **reduced-motion 是真降级不是减速。** `prefers-reduced-motion` 下：CSS 波纹/气泡 `animation: none`；`Ambient` 直接不启动；`Stamp` 无入场直接就位；`Vessel` 液位直接到目标值、种子与涟漪不播；计数器直接显示终值；图表 `initial` 即终态；`scroll-behavior` 转 `auto`。

### 组件索引

| 文件 | 用途 | props 要点 |
| --- | --- | --- |
| `sheet/Section.tsx` | 表单节骨架；导出 `H2` | `id, label, sub?, spot?` |
| `sheet/SheetHeader.tsx` | 刊头：样品信息行 + 刊名 + 导语 + 章 + 器皿 | `l: Ledger, prevOpen, totalIssues` |
| `sheet/Stamp.tsx` | 圆形批次章 | `issue, degree, grade, date, size=196, delay=.9` |
| `sheet/Vessel.tsx` | 量杯 / 液位 / 种子入缸 | `issue, level (0.08–0.92), label?` |
| `sheet/Intake.tsx` | 进料六格 + 数字滚动 | `fields: {k,v,suffix?,note?}[]` |
| `sheet/RunChart.tsx` | 24h 柱图 + 掐头去尾 + 悬停读数 | `hours, events, caption?` |
| `sheet/Timeline.tsx` | 大事记液位时间线 | `events` |
| `sheet/Themes.tsx` | 品评项（重织 + 手写深潜 + 逐字原声 + 线索 chip） | `themes, threads, issue, illus?` |
| `sheet/ToneTag.tsx` | 语气三档章；导出 `ToneGlyph` | `g: 's'\|'j'\|'h', size, stamp?` |
| `sheet/ToneStamps.tsx` | 真伪鉴定三栏 | `notes: ToneNote[]` |
| `sheet/Insights.tsx` | 深潜双栏 | `items: Insight[]` |
| `sheet/QuoteWall.tsx` | 逐字摘录瀑布 + 复制 / 分享卡 | `quotes, issue, date, degree` |
| `sheet/ScoreGrid.tsx` | 五维十格 + 88px 度数 | `dims, overall, grade, basis` |
| `sheet/Growth.tsx` | 随身装备 + 可打勾行动清单 | `takeaways, todo, date, carried?, prevDate?` |
| `sheet/Docket.tsx` | 悬案挂账 + 分歧对撞 | `docket, clashes, issue` |
| `sheet/Glossary.tsx` | 黑话词典 + 弹药库 | `items, arsenal` |
| `sheet/MembersFocus.tsx` | 成员高光 + 本期感谢 | `items, thanks?` |
| `sheet/Newcomers.tsx` | 新面孔欢迎卡 | `items, issue` |
| `sheet/SheetFooter.tsx` | 双线分隔 + 上下批 + 口径与边界 + 打印 | `l, prev?, next?` |
| `sheet/DoubleRule.tsx` | 双蓝线菱形分隔 | `className?` |
| `sheet/LiquidRail.tsx` | 左栏阅读液位管 | `target: Ref, marks` |
| `sheet/Toc.tsx` | 右侧刻度目录 / 窄屏抽屉 | `sections: {id,label}[]` |
| `sheet/TermHover.tsx` | 黑话释义气泡（全局监听 `dfn[data-term]`） | `glossary` |
| `sheet/Notebook.tsx` | 选中记下 + 笔记抽屉 + 导出 md | `date, issue, title` |
| `sheet/ParagraphTools.tsx` | 段落锚点 + 评论 + 分享卡 | `date, issue, degree` |
| `sheet/Ambient.tsx` | 环境气泡 canvas | 无 |
| `sheet/LedgerSheet.tsx` | 日报页装配（12 节顺序在此） | `l, prevOpen, totalIssues, prev, next, illus, spots` |
| `pages/PageHead.tsx` | 分页刊头；导出 `PageShell` `GapNote` `ScrollHint` | `fields, title, lead, aside?, note?` |
| `pages/FormBits.tsx` | `Field` / `Btn` / `Note` | 见上文输入与按钮 |
| `pages/Gate.tsx` | 邀请码登录墙（children 必须是元素，不能是函数） | `what, why, children` |
| `pages/Subscribe.tsx` | 订阅登记（明说不发信） | 无 |
| `pages/TodoCheck.tsx` | 活动页行动打卡（与日报共用存储） | `todo, date` |
| `pages/ThreadMap.tsx` | 线索图：行=线索 列=批次 + 未来空槽 | `rows, issues, ghost=5` |
| `pages/CompoundRun.tsx` | 复利四格累积曲线 | `series, issues, ghost=5` |
| `pages/DegreeRun.tsx` | 逐批度数折线 + 等级带 | `points, ghost=5` |
| `pages/BadgeWall.tsx` | 12 枚徽章墙（未点亮即不点亮） | `badges` |
| `pages/AvatarRow.tsx` | 头像与叠排名牌；导出 `Avatar` | `faces, max=24` |
| `pages/MembersRoster.tsx` | 群像名册 + 筛选 chips + 深读 | `profiles` |
| `site/Nav.tsx` `Footer.tsx` `ThemeToggle.tsx` | 全局壳 | 无 |

## Do's and Don'ts

### Do:
- **Do** 先判定材料再上色：表单画蓝、内容画琥珀（**The Two Materials Rule**）。
- **Do** 每一节都起一个 ≤5 字的左栏蓝标签；起不出就说明它不该独立成节。
- **Do** 用格线分区，需要边框时优先只画上边线。
- **Do** 数字一律 `.num`（系统字体 + `tabular-nums`），并保持不设合成字重。
- **Do** 把整理者的延伸判断放进文楷层 + 琥珀荧光笔底，逐字原话留在宋体加「」。
- **Do** 给每条被引用的话挂语气三档章，颜色对应蓝 / 青 / 朱砂，图标用单线 SVG。
- **Do** 数据缺口用 `GapNote` 琥珀条明写，未来批次画虚线空槽（**The Dashed-Means-Absent Rule**）。
- **Do** 新动画先回答"它承载哪个读数"；答不上就删掉。
- **Do** 每个动画都配 `useReducedMotion` 或 `@media (prefers-reduced-motion)` 的**终态直达**分支。
- **Do** 交互焦点一律走全局 `:focus-visible`（`blue-2` 2px / offset 3px），不要就地改写。
- **Do** 需要浮层时用 `--shadow-sheet` / `--shadow-pop` 两级，不要就地写阴影。
- **Do** 在明暗两主题下都用 `-text` 变体承担文字，两边都过对比度。
- **Do** 把只存在本机的状态（笔记、打勾）在界面上明说"只存在你这台设备"。

### Don't:
- **Don't** 做卡片墙——一排等权的圆角阴影盒子是这个世界最典型的失败模式。
- **Don't** 用渐变做背景、hero 或强调（唯一的渐变是量杯液体的 `amber-2 → amber-deep` 与手写体的荧光笔带）。
- **Don't** 用霓虹、发光、外阴影描边、玻璃拟态。
- **Don't** 做半透明模糊导航；导航必须是不透明纸色 + 一条格线。
- **Don't** 用 emoji 当图标（图标一律单线 SVG，`strokeWidth ≈2`，随文字色继承）。
- **Don't** 再做第二块孤立的大数字统计卡；度数 88px 是全站唯一的大数字，且必须被证据文本包着。
- **Don't** 把琥珀用在与数值无关的地方（导航、按钮、正文强调）。
- **Don't** 把朱砂或青当通用强调色——它们已被"半真 / 玩笑"征用。
- **Don't** 把 `--blue` / `--amber` 原色直接写在 `color` 上，文字只能取 `-text` 变体。
- **Don't** 让数字落进宋体，也别让延伸判断落进宋体。
- **Don't** 给内容块加圆角和阴影去"分组"；那是格线的活。
- **Don't** 用占位图、平滑或估算把数据缺口糊过去；没有就画虚线并写明。
- **Don't** 加第二个入场表演——批次章落下是唯一被授权的时刻。
- **Don't** 让粒子/气氛层的透明度超过 0.12 或数量超过 46。
- **Don't** 引入第二套缓动或第二种容器宽度。
