import type { Metadata } from "next";
import Link from "next/link";
import { getAllLedgers, fmtInt, pad3 } from "@/lib/content";
import { Section } from "@/components/sheet/Section";
import { ToneTag } from "@/components/sheet/ToneTag";
import { PageHead, PageShell, GapNote, byName } from "@/components/pages/PageHead";

export const metadata: Metadata = {
  title: "关于 · 邀请码 · 订阅",
  description: "先锋队台账是什么、我们守着哪几条、邀请码怎么用、留了邮箱会发生什么、内容从哪来又是怎么整理的。",
};

const BOUNDS = [
  {
    k: "原始聊天不上站",
    body: "群聊是原料，不是成品。这里只放整理过的东西：蒸出来的主题、标好的语气、逐字的金句、五维打分、能带走的行动。原来那个能翻聊天记录的入口已经拆掉了——登录也翻不到，不是藏起来，是没有了。",
  },
  {
    k: "语气分三档",
    body: "每一条被引用的话都标了语气：认真 / 玩笑 / 半真。把段子当宣言是事故——所以宁可多标一档，也不让读者自己猜。",
  },
  {
    k: "记不全就说记不全",
    body: "哪天没记全，我们会在那一期开头就说，并写清楚为什么。往期列表里也会标出来。我们不拿平均值、不拿估算、不拿「大概是这样」去把窟窿补上——补上了你就再也看不出它曾经是个窟窿。",
  },
  {
    k: "隐私打码",
    body: "涉隐私内容打码；密码、密钥、连接串一类内容不收录。引文逐字来自群聊原文，「没说破的」是整理者延伸，一律用手写体标出，不混进原话。",
  },
];

export default function AboutPage() {
  const ledgers = getAllLedgers();
  const l = ledgers[0];
  const totalMsgs = ledgers.reduce((s, x) => s + x.stats.msgs, 0);

  return (
    <PageShell>
      <PageHead
        title="关于 · 邀请码 · 订阅"
        lead="先锋队台账是「🌱人民需要AI_智能体先锋队」的每日蒸馏刊：每天把群里聊的东西整理成一期，一天一批，一批一张品鉴单。这一页说清楚我们守着哪几条、你怎么参与。"
        fields={[
          { k: "已出批次", v: `${ledgers.length} 批` },
          { k: "最新批次", v: `第 ${pad3(l.issue)} 批 · ${l.date}` },
          { k: "累计进料", v: `${fmtInt(totalMsgs)} 条` },
          { k: "时间", v: "北京时间 UTC+8" },
        ]}
      />

      <Section id="what" label="是什么" sub="一句话 + 一段话">
        <p className="prose-sheet text-[19px] font-bold leading-[1.8] text-ink sm:text-[21px]">
          每天把一个 AI 群的聊天，蒸成一张能读完、能带走、能跨期承接的鉴定单。
        </p>
        <p className="prose-sheet mt-5 text-[16.5px] leading-[1.85] text-ink-2">
          群聊的问题不是信息少，是信息以碎片形态存在——今天吵完的架，三天后没人记得结论；一个人写的千字自述，隔天沉到两百条以下。台账做的事是把这些碎片<b>重新组织成一锅</b>：谁在说什么、这话是认真还是玩笑、哪几条值得逐字保留、这一天的内容值多少度、读完能带走哪些可执行的动作，以及——<span className="hand">哪些线索会在明天继续。</span>
        </p>
        <p className="prose-sheet mt-4 text-[16.5px] leading-[1.85] text-ink-2">
          隐喻是蒸馏厂：每一期是一个<b>批次</b>，质量分叫<b>度数</b>，一天的消息分成酒头 / 酒心 / 酒尾三段。这不只是修辞——它逼着我们承认，原料和成品不是一回事，而中间那道工序需要被公开检查。
        </p>
      </Section>

      <Section id="bounds" label="我们守的四条" sub="不会因为哪天方便就改">
        <div className="divide-y divide-rule border-y border-rule">
          {BOUNDS.map((b, i) => (
            <div key={b.k} className="grid gap-x-8 gap-y-2 py-6 lg:grid-cols-[minmax(0,200px)_minmax(0,1fr)]">
              <h3 className="flex items-baseline gap-3 font-serif text-[19px] font-bold text-ink">
                <span className="num font-sans text-[12.5px] font-semibold text-blue-text">{String(i + 1).padStart(2, "0")}</span>
                {b.k}
              </h3>
              <p className="prose-sheet text-[16px] leading-[1.85] text-ink-2">{b.body}</p>
            </div>
          ))}
        </div>
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <span className="font-sans text-[13px] text-ink-3">语气三档长这样：</span>
          <ToneTag g="s" size="md" /><ToneTag g="j" size="md" /><ToneTag g="h" size="md" />
        </div>
      </Section>

      <Section id="invite" label="邀请码" sub="群像与窖藏的门">
        <div className="grid gap-x-12 gap-y-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,320px)]">
          <div className="min-w-0">
            <p className="prose-sheet text-[16.5px] leading-[1.85] text-ink-2">
              日报是公开的，谁都能读。<Link href="/members/" className="text-blue-text no-underline hover:underline">群像</Link>和<Link href="/essays/" className="text-blue-text no-underline hover:underline">窖藏</Link>不是——那是 51 个人的画像和几十篇自述，写的时候没打算给公开互联网看。所以这两栏加了一道门。
            </p>
            <ol className="mt-7 space-y-5 border-t border-rule pt-6">
              {[
                ["拿到邀请码", "群内向 Sun 索取。群主在后台逐个生成，一人一码、可撤销；没有自助申请入口，也不存在公开通用码。"],
                ["注册", "打开群像或窖藏，切到「用邀请码注册」，选群昵称、填密码、邀请码。码错了、或已被撤销、或已被人用过，都会直接挡下，不会建号。"],
                ["登录 90 天有效", "票据存在你这台设备的浏览器里，常来会自动续期，基本不用重复登录。退出登录会立刻作废；改密码会作废其他设备上的登录。"],
              ].map(([h, d], i) => (
                <li key={h} className="grid grid-cols-[32px_1fr] gap-4">
                  <span className="num pt-[3px] font-sans text-[13px] font-semibold text-blue-text">{String(i + 1).padStart(2, "0")}</span>
                  <div>
                    <div className="font-sans text-[15px] font-semibold text-ink">{h}</div>
                    <p className="mt-1 font-sans text-[14px] leading-relaxed text-ink-2">{d}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
          <div className="rounded-[10px] border border-blue-wash-2 bg-blue-wash/60 px-5 py-6">
            <div className="label">怎么拿到邀请码</div>
            <p className="prose-sheet mt-2.5 text-[17px] font-bold leading-[1.7] text-ink">
              邀请码由群主发放，群内向 Sun 索取。
            </p>
            <p className="mt-3 font-sans text-[12.5px] leading-relaxed text-ink-2">
              <b>一人一码，可随时撤销</b>——所以这一页不会印出任何邀请码，站上任何地方都不会。看到有人在别处贴「通用邀请码」，那是过期信息。
            </p>
            <p className="mt-3 font-sans text-[12.5px] leading-relaxed text-ink-2">
              区分大小写。填错只会被挡下，不会创建账号，可以直接重填。
            </p>
            <p className="mt-3 font-sans text-[12.5px] leading-relaxed text-ink-3">
              这道门挡的是搜索引擎和路人，不是保密级别的隔离——请不要把群友的小作文原样转发出去。
            </p>
            <details className="mt-4 border-t border-blue-wash-2 pt-3">
              <summary className="cursor-pointer font-sans text-[12.5px] font-semibold text-blue-text">登录到底存了什么（技术细节）</summary>
              <ul className="mt-2.5 space-y-1.5 font-sans text-[12px] leading-relaxed text-ink-2">
                <li>· 服务器上只有：用户名、密码的 SHA-256 哈希、登录票据。<b>没有密码明文。</b></li>
                <li>· 凭证存在你浏览器的 <span className="num">localStorage</span>，键名 <span className="num">xf-token</span>，<span className="num">72</span> 小时后失效。</li>
                <li>· 点「退出」会同时删掉服务器上那张票据和本机这一份。</li>
                <li>· 打勾进度另存一份，键名 <span className="num">xf-todo-日期</span>，只在本机，从不上传。</li>
              </ul>
            </details>
          </div>
        </div>
      </Section>

      <Section id="subscribe" label="订阅" sub="登记邮箱 · 目前不发信">
        <div className="grid gap-x-12 gap-y-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,340px)]">
          <div className="min-w-0">
            <p className="prose-sheet text-[16.5px] leading-[1.85] text-ink-2">
              留个邮箱，等发信通道通了，<b>每天早上 07:45</b> 把当批品鉴单寄给你。
            </p>
            <div className="mt-6">
              <GapNote>
                <b>发信通道还没通，所以现在填了也收不到信。</b>邮箱会好好存着，通道一通就从这份名单开始寄——先说清楚，不让你等一封不会来的信。
              </GapNote>
            </div>
            <dl className="mt-7 space-y-4 border-t border-rule pt-5">
              <div><dt className="label">存了什么</dt><dd className="mt-1 font-sans text-[14px] leading-relaxed text-ink-2">邮箱、称呼、登记时间。就这三样。</dd></div>
              <div><dt className="label">给谁</dt><dd className="mt-1 font-sans text-[14px] leading-relaxed text-ink-2">不给任何第三方，不做画像，不做投放。</dd></div>
              <div><dt className="label">怎么退</dt><dd className="mt-1 font-sans text-[14px] leading-relaxed text-ink-2">在用户中心把开关关掉就行，邮箱还留着，随时能再打开。</dd></div>
            </dl>
          </div>
          <div className="h-max rounded-[10px] border border-rule bg-paper-2/50 px-5 py-6 sm:px-6">
            <div className="label">怎么订</div>
            <p className="prose-sheet mt-2.5 text-[17px] font-bold leading-[1.7] text-ink">
              登录后在<Link href="/me/" className="text-blue-text no-underline hover:underline">用户中心</Link>填邮箱、开开关。
            </p>
            <p className="mt-3 font-sans text-[12.5px] leading-relaxed text-ink-2">
              这样邮箱是挂在你账号下的：换邮箱、退订、再订回来，都在同一个地方，不用再找我们。
            </p>
            <p className="mt-3 font-sans text-[12.5px] leading-relaxed text-ink-3">
              还没有账号？注册要一个邀请码，群内向 Sun 索取。
            </p>
            <Link href="/me/" className="mt-5 inline-flex min-h-11 items-center justify-center gap-2 rounded-[5px] border border-blue bg-blue px-5 py-2.5 font-sans text-[14px] font-semibold text-paper no-underline transition-opacity hover:opacity-90">
              去用户中心
            </Link>
          </div>
        </div>
      </Section>

      <Section id="method" label="东西是怎么来的" sub="从群聊到这张单子">
        <ol className="grid gap-y-7 sm:grid-cols-2 sm:gap-x-10 lg:grid-cols-4">
          {[
            ["收", "群里的消息一条条存下来。有些是压缩的，得先还原（这一批还原了 " + fmtInt(l.stats.decoded) + " 条）。"],
            ["蒸", "把当天的消息蒸成一期：分出主题、标好语气、挑出金句、打五维分、列出能带走的行动、记下没吵完的账。这一批是 " + byName(l.credits.distilled_by) + " 做的。"],
            ["核", "人再看一遍才发出来。这一批：" + byName(l.credits.reviewed_by) + "。"],
            ["排版", "整理好的内容排成你现在看到的这张品鉴单。这一步只碰整理过的东西，碰不到原始记录。"],
          ].map(([h, d], i) => (
            <li key={h}>
              <div className="num font-sans text-[12.5px] font-semibold text-blue-text">{String(i + 1).padStart(2, "0")}</div>
              <div className="mt-1.5 font-serif text-[18px] font-bold text-ink">{h}</div>
              <p className="mt-2 font-sans text-[13.5px] leading-relaxed text-ink-2">{d}</p>
            </li>
          ))}
        </ol>

        <div className="mt-10 border-t border-rule pt-6">
          <div className="label mb-3">有几件事我们还没做到</div>
          <ul className="prose-sheet space-y-2.5 text-[16px] leading-[1.8] text-ink-2">
            <li>· 微信隔三个小时会掉一次线，<b>掉线那阵子的消息补不回来</b>。</li>
            <li>· 建群那天（{l.coverage.from}）的内容是从《群聊精华整理》回溯的，不如后面几天记得细，两者不能直接比。</li>
            <li>· 度数只评内容，不评人；五维定义见<Link href="/quality/#mapping" className="text-blue-text no-underline hover:underline">度数 · 稳定映射</Link>。</li>
            <li>· 徽章的达成条件都定好了，但「谁拿到了哪一枚」还没开始算，见<Link href="/events/badge-wall/" className="inline-flex min-h-11 items-center text-blue-text no-underline hover:underline sm:min-h-0">纪念徽章墙</Link>。</li>
          </ul>
        </div>

        <p className="mt-8 font-sans text-[12.5px] leading-relaxed text-ink-3">
          时间一律北京时间（UTC+8）。这一页上的数字都是从最新那一批现读的，不是写死的——出了新的一批，这里跟着变。
        </p>
      </Section>
    </PageShell>
  );
}
