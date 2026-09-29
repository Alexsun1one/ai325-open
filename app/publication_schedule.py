"""出刊断更判定的唯一真值源。

日报早上出刊（备料 06:30、兜底 07:15、deadman 08:30 北京时间）。
- 截止前：最新应出刊 = 前天（昨天这期仍在制作窗口，缺它不算断更）。
- 截止及之后：最新应出刊 = 昨天。
- missing_dates 从最新已出刊日之后逐日列到 expected_latest，更早的真实断刊不会被藏掉。

XF_PUBLICATION_DEADLINE 可覆盖截止时刻（"HH:MM"，北京时间），默认 08:30。
"""

from __future__ import annotations

import datetime
import os
import re

CST = datetime.timezone(datetime.timedelta(hours=8))
DEFAULT_DEADLINE = (8, 30)
_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def deadline_hhmm() -> tuple[int, int]:
    raw = (os.environ.get("XF_PUBLICATION_DEADLINE") or "").strip()
    match = _HHMM_RE.match(raw)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    return DEFAULT_DEADLINE


def deadline_for(day: datetime.date) -> datetime.datetime:
    hour, minute = deadline_hhmm()
    return datetime.datetime.combine(
        day, datetime.time(hour, minute), tzinfo=CST
    )


def _as_cst(now: datetime.datetime) -> datetime.datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=CST)
    return now.astimezone(CST)


def expected_latest(now: datetime.datetime) -> datetime.date:
    """给定当前时刻，返回此刻必须已经出刊的最晚日期。"""
    now = _as_cst(now)
    deadline = deadline_for(now.date())
    return now.date() - datetime.timedelta(days=1) if now >= deadline else now.date() - datetime.timedelta(days=2)


def publication_status(now: datetime.datetime, published_dates) -> dict:
    """共用计算：health / expected_latest / missing_dates / pending_date / scheduled_for。

    published_dates：可迭代的 ISO 日期字符串集合（已出刊期）。
    """
    now = _as_cst(now)
    expected = expected_latest(now)
    published = sorted(d for d in published_dates if isinstance(d, str) and d)
    published_set = set(published)
    latest = published[-1] if published else None
    missing: list[str] = []
    # 起点 = published 中 <=expected 的最新一期（trailing gap 语义保持；
    # 提前出刊 latest>expected 时不掩盖当期应交缺口），无则从 expected 起
    due_published = [d for d in published if d <= expected.isoformat()]
    probe = (
        datetime.date.fromisoformat(due_published[-1]) + datetime.timedelta(days=1)
        if due_published
        else expected
    )
    while probe <= expected:
        if probe.isoformat() not in published_set:
            missing.append(probe.isoformat())
        probe += datetime.timedelta(days=1)
    pending = expected + datetime.timedelta(days=1)
    # pending 这期在次日 deadline 到期：09-23 期 → 09-24 08:30
    scheduled_for = deadline_for(pending + datetime.timedelta(days=1))
    hour, minute = deadline_hhmm()
    return {
        "as_of": now.date().isoformat(),
        "now": now.isoformat(timespec="seconds"),
        "deadline": f"{hour:02d}:{minute:02d}",
        "expected_latest": expected.isoformat(),
        "pending_date": pending.isoformat(),
        "scheduled_for": scheduled_for.isoformat(timespec="seconds"),
        "latest_date": latest,
        "missing_dates": missing,
        "health": "gap" if missing else ("ok" if published else "empty"),
    }
