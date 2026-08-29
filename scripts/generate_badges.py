#!/usr/bin/env python3
"""Generate the 12 commemorative SVG badges from CODEX-VISUAL-SPEC.md."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "assets" / "badges"


@dataclass(frozen=True)
class Badge:
    filename: str
    name: str
    trigger: str
    icon_name: str
    primary: str
    secondary: str
    symbol: str


BADGES = (
    Badge(
        "newcomer.svg",
        "初来乍到",
        "入群",
        "种子发芽",
        "#34d399",
        "#22d3ee",
        """
        <path d="M100 126C99 108 101 88 101 72"/>
        <path d="M100 94C87 93 77 84 76 69c14-1 25 6 27 20"/>
        <path d="M102 79c5-14 16-21 30-18-1 14-11 24-29 25"/>
        <path d="M82 126c4-10 10-15 18-15s14 5 18 15"/>
        <circle cx="100" cy="134" r="4" class="spark-fill"/>
        """,
    ),
    Badge(
        "first-work.svg",
        "首作",
        "第一篇小作文",
        "钢笔",
        "#60a5fa",
        "#a78bfa",
        """
        <path d="M73 124l9-28 39-39 18 18-39 39-27 10z"/>
        <path d="M82 96l18 18M119 59l18 18M74 123l15-8-8-8-7 16z"/>
        <path d="M108 69l18 18M102 91l13 13" opacity=".55"/>
        <circle cx="130" cy="67" r="3" class="spark-fill"/>
        """,
    ),
    Badge(
        "night-owl.svg",
        "夜行者",
        "凌晨 0-5 点发言超过 20 条",
        "月亮与星星",
        "#818cf8",
        "#c084fc",
        """
        <path d="M117 63c-21 5-32 29-21 48 10 18 35 21 50 6-7 3-15 3-22-1-17-9-20-32-7-53z"/>
        <path d="M74 75v12M68 81h12M139 84v14M132 91h14"/>
        <path d="M74 103l2 5 5 2-5 2-2 5-2-5-5-2 5-2 2-5z" class="spark-fill"/>
        """,
    ),
    Badge(
        "hundred-milestone.svg",
        "百条里程碑",
        "累计发言 100 条",
        "火焰",
        "#fb7185",
        "#f59e0b",
        """
        <path d="M101 55c7 19-5 25 4 37 4-10 12-15 17-22 14 13 21 29 16 45-5 17-20 27-38 27-22 0-39-15-39-36 0-17 10-28 22-39-1 14 3 22 10 26 9-12 4-25 8-38z"/>
        <path d="M100 104c10 9 13 18 8 27-3 6-13 6-17 1-8-10 0-19 9-28z" class="spark-fill"/>
        """,
    ),
    Badge(
        "thousand-legend.svg",
        "千条传奇",
        "累计发言 1000 条",
        "钻石",
        "#22d3ee",
        "#c084fc",
        """
        <path d="M61 83l18-23h42l18 23-39 52-39-52z"/>
        <path d="M61 83h78M79 60l-7 23 28 52 28-52-7-23M72 83h56M100 60L88 83l12 52 12-52-12-23z"/>
        <path d="M145 62v12M139 68h12"/>
        """,
    ),
    Badge(
        "brain-certified.svg",
        "换脑认证",
        "被群主点名纳入蒸馏范围",
        "发光大脑",
        "#a78bfa",
        "#38bdf8",
        """
        <path d="M99 68c-7-12-27-8-27 7-13 2-15 20-5 27-9 10-2 27 11 27 4 10 18 10 22 1V68z"/>
        <path d="M101 68c7-12 27-8 27 7 13 2 15 20 5 27 9 10 2 27-11 27-4 10-18 10-22 1V68z"/>
        <path d="M83 78c8 0 12 6 12 13M75 102c10-3 18 3 20 12M117 78c-8 0-12 6-12 13M125 102c-10-3-18 3-20 12"/>
        <circle cx="100" cy="101" r="7" class="spark-fill"/>
        """,
    ),
    Badge(
        "weflow-rescuer.svg",
        "WeFlow救援者",
        "参与 WeFlow fork 救援讨论",
        "火箭",
        "#38bdf8",
        "#8b5cf6",
        """
        <path d="M92 112c-11 5-19 3-26 0 2-10 8-17 17-20M108 112c11 5 19 3 26 0-2-10-8-17-17-20"/>
        <path d="M82 103c1-24 8-42 18-50 10 8 17 26 18 50l-18 18-18-18z"/>
        <circle cx="100" cy="84" r="8"/>
        <path d="M93 121l-3 20 10-7 10 7-3-20"/>
        <path d="M100 126v10" class="spark"/>
        """,
    ),
    Badge(
        "quality-contributor.svg",
        "质量贡献者",
        "消息被引用次数 TOP10",
        "奖杯",
        "#fbbf24",
        "#fb7185",
        """
        <path d="M79 62h42v22c0 17-8 29-21 29S79 101 79 84V62z"/>
        <path d="M79 70H66v10c0 13 8 20 18 20M121 70h13v10c0 13-8 20-18 20"/>
        <path d="M100 113v14M83 138h34M90 127h20v11H90z"/>
        <path d="M100 72l4 8 9 1-7 6 2 9-8-5-8 5 2-9-7-6 9-1 4-8z" class="spark-fill"/>
        """,
    ),
    Badge(
        "question-artist.svg",
        "提问艺术家",
        "问题引发 50+ 条回复",
        "靶心",
        "#f472b6",
        "#60a5fa",
        """
        <circle cx="100" cy="99" r="38"/>
        <circle cx="100" cy="99" r="25"/>
        <circle cx="100" cy="99" r="11" class="spark-fill"/>
        <path d="M100 99l35-35M121 63h15v15M100 52v8M100 138v8M53 99h8M139 99h8"/>
        """,
    ),
    Badge(
        "knowledge-library.svg",
        "知识图书馆",
        "分享文件或链接超过 10 个",
        "书堆",
        "#2dd4bf",
        "#818cf8",
        """
        <path d="M68 111h62v20H68zM75 87h58v19H75zM67 63h59v19H67z"/>
        <path d="M79 63v19M121 87v19M82 111v20"/>
        <path d="M88 70h27M83 94h29M90 118h28" opacity=".6"/>
        <circle cx="134" cy="69" r="4" class="spark-fill"/>
        """,
    ),
    Badge(
        "agent-tamer.svg",
        "Agent 驯兽师",
        "分享 Agent 经验并获群主认可",
        "闪电",
        "#facc15",
        "#22d3ee",
        """
        <path d="M108 53L72 105h26l-6 40 38-57h-26l4-35z" class="spark-fill"/>
        <path d="M67 69l-7-7M133 69l7-7M64 126l-8 6M137 125l8 5" opacity=".8"/>
        """,
    ),
    Badge(
        "founding-member.svg",
        "创始成员",
        "建群 48 小时内入群",
        "星星",
        "#fcd34d",
        "#a78bfa",
        """
        <path d="M100 53l13 28 31 4-23 22 6 31-27-15-27 15 6-31-23-22 31-4 13-28z" class="spark-fill"/>
        <path d="M100 68l8 19 20 2-15 14 4 20-17-10-17 10 4-20-15-14 20-2 8-19z" opacity=".55"/>
        <path d="M145 57v12M139 63h12M57 119v10M52 124h10"/>
        """,
    ),
)


SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200" role="img" aria-labelledby="title desc">
  <title id="title">{name}纪念徽章</title>
  <desc id="desc">达成条件：{trigger}。中心图标：{icon_name}。</desc>
  <defs>
    <radialGradient id="bg" cx="50%" cy="38%" r="72%">
      <stop offset="0" stop-color="{primary}" stop-opacity=".18"/>
      <stop offset=".48" stop-color="#0b1024"/>
      <stop offset="1" stop-color="#030308" class="space-stop"/>
    </radialGradient>
    <linearGradient id="rim" x1="22" y1="28" x2="175" y2="176" gradientUnits="userSpaceOnUse">
      <stop stop-color="{primary}"/><stop offset=".48" stop-color="{secondary}"/><stop offset="1" stop-color="{primary}"/>
    </linearGradient>
    <linearGradient id="ink" x1="70" y1="56" x2="134" y2="140" gradientUnits="userSpaceOnUse">
      <stop stop-color="#f8fbff" class="icon-hi-stop"/><stop offset=".45" stop-color="{primary}"/><stop offset="1" stop-color="{secondary}"/>
    </linearGradient>
    <filter id="glow" x="-80%" y="-80%" width="260%" height="260%" color-interpolation-filters="sRGB">
      <feGaussianBlur stdDeviation="4" result="blur"/>
      <feFlood flood-color="{primary}" flood-opacity=".9" result="color"/>
      <feComposite in="color" in2="blur" operator="in" result="halo"/>
      <feMerge><feMergeNode in="halo"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="soft-glow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="2.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <clipPath id="disc"><circle cx="100" cy="100" r="91"/></clipPath>
    <style>
      .space {{ fill:#030308; }}
      .space-stop {{ stop-color:#030308; }}
      .icon-hi-stop {{ stop-color:#f8fbff; }}
      .grid {{ stroke:#94a3b8; }}
      .spark {{ stroke:#f8fbff; }}
      .label {{ fill:#e6efff; font:700 12px -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif; letter-spacing:.06em; }}
      @media (prefers-color-scheme: light) {{
        .space {{ fill:#eaf2ff; }}
        .space-stop {{ stop-color:#eaf2ff; }}
        .icon-hi-stop {{ stop-color:#ffffff; }}
        .grid {{ stroke:#475569; }}
        .label {{ fill:#172554; }}
      }}
      .icon {{ fill:none; stroke:url(#ink); stroke-width:5; stroke-linecap:round; stroke-linejoin:round; }}
      .spark-fill {{ fill:url(#ink); stroke:url(#ink); }}
    </style>
  </defs>
  <circle cx="100" cy="100" r="96" class="space" stroke="#111a36" stroke-width="2"/>
  <circle cx="100" cy="100" r="91" fill="url(#bg)"/>
  <g clip-path="url(#disc)" opacity=".75">
    <path d="M-8 131C42 92 69 99 105 65s76-26 110-53" fill="none" stroke="url(#rim)" stroke-width="15" opacity=".07" filter="url(#glow)"/>
    <path d="M24 47h152M17 78h166M11 109h178M17 140h166" class="grid" stroke-width=".5" opacity=".08"/>
    <path d="M48 15v145M78 8v157M108 8v157M138 15v145" class="grid" stroke-width=".5" opacity=".07"/>
  </g>
  <circle cx="100" cy="100" r="89" fill="none" stroke="url(#rim)" stroke-width="2.5" filter="url(#glow)"/>
  <circle cx="100" cy="100" r="82" fill="none" stroke="url(#rim)" stroke-width=".8" stroke-dasharray="2 7" opacity=".7"/>
  <path d="M41 151A74 74 0 0 0 159 151" fill="none" stroke="url(#rim)" stroke-width="1" opacity=".4"/>
  <g fill="{primary}" filter="url(#soft-glow)">
    <circle cx="43" cy="50" r="1.4"/><circle cx="155" cy="54" r="1"/><circle cx="164" cy="116" r="1.4"/>
    <circle cx="35" cy="112" r=".9"/><circle cx="72" cy="36" r=".8"/><circle cx="137" cy="145" r=".8"/>
  </g>
  <g class="icon" filter="url(#glow)">{symbol}</g>
  <path d="M60 155h80" stroke="url(#rim)" stroke-width="1" opacity=".45"/>
  <text x="100" y="174" text-anchor="middle" class="label">{name}</text>
  <circle cx="100" cy="100" r="96" fill="none" stroke="url(#rim)" stroke-width="1" opacity=".42"/>
</svg>
"""


def render_badge(badge: Badge) -> str:
    return SVG_TEMPLATE.format(
        name=badge.name,
        trigger=badge.trigger,
        icon_name=badge.icon_name,
        primary=badge.primary,
        secondary=badge.secondary,
        symbol="".join(line.strip() for line in badge.symbol.strip().splitlines()),
    )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "collection": "先锋队群像站纪念徽章",
        "version": 1,
        "format": "SVG",
        "dimensions": {"width": 200, "height": 200},
        "theme": "deep-space neon",
        "colorSchemes": ["dark", "light"],
        "files": [],
    }

    for badge in BADGES:
        destination = OUTPUT_DIR / badge.filename
        destination.write_text(render_badge(badge), encoding="utf-8")
        manifest["files"].append(
            {
                "file": badge.filename,
                "name": badge.name,
                "trigger": badge.trigger,
                "centerIcon": badge.icon_name,
                "colors": [badge.primary, badge.secondary],
            }
        )

    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {len(BADGES)} badges in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
