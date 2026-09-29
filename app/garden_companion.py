"""家园护法 / 作物图鉴 / 种植成就与足迹（GARDEN-COMPANION R1）。

契约：.fleet/growth-content-20260924/garden-companion-contract.md
- 真人 session only：匿名 401、Agent 403；只读写本人，所有响应 no-store。
- 只统计本人 plant/harvest 事件；偷菜不算种植/收获/图鉴/成就；成就时间取真实事件时间。
- 作物真值继承 garden.RULES；护法/成就配置在 garden_companion_rules.json。
- 唯一新表 garden_companion_preferences，只存本人所选护法，不动收成/作物/积分。
"""

import datetime
import json
import sqlite3
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

try:
    from . import garden
except ImportError:  # Docker 以 ``main:app`` 平铺运行
    import garden

RULES_PATH = Path(__file__).with_name("garden_companion_rules.json")
KINDS = {"plant_count", "harvest_count", "harvest_total", "distinct_crops", "active_days"}
TIP_KINDS = ("no_garden", "ripe", "empty", "waiting")

_db: Callable[[], Any] | None = None
_clock: Callable[[], datetime.datetime] | None = None


def configure(*, db: Callable[[], Any], clock: Callable[[], datetime.datetime] | None = None) -> None:
    """由 main 注入 db()；clock 缺省沿用 garden 的服务端时钟（测试可注入）。"""
    global _db, _clock
    _db = db
    if clock is not None:
        _clock = clock


def _load_rules() -> dict:
    data = json.loads(RULES_PATH.read_text("utf-8"))
    if not isinstance(data.get("recent_days"), int) or not 1 <= data["recent_days"] <= 31:
        raise ValueError("garden_companion_rules.json: recent_days 必须在 1..31")
    guardians = data.get("guardians")
    if not isinstance(guardians, list) or not 1 <= len(guardians) <= 3:
        raise ValueError("garden_companion_rules.json: guardians 需要 1..3 款")
    if len({g.get("id") for g in guardians}) != len(guardians):
        raise ValueError("garden_companion_rules.json: guardian id 重复")
    for g in guardians:
        if not all(g.get(k) for k in ("id", "name", "species", "tagline", "sprite")):
            raise ValueError("garden_companion_rules.json: guardian 字段不全")
        if any(not (g.get("tips") or {}).get(k) for k in TIP_KINDS):
            raise ValueError("garden_companion_rules.json: guardian.tips 缺少 " + "/".join(TIP_KINDS))
    seen = set()
    for m in data.get("milestones", []):
        if m["id"] in seen or m["kind"] not in KINDS or int(m["target"]) < 1:
            raise ValueError("garden_companion_rules.json: milestone 非法 " + str(m.get("id")))
        seen.add(m["id"])
    return data


RULES = _load_rules()


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["garden-companion"], dependencies=[Depends(_no_store)])


def ensure_schema(connection) -> None:
    garden.ensure_schema(connection)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS garden_companion_preferences(
          owner_id INTEGER PRIMARY KEY,
          guardian_id TEXT,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS garden_events_actor_created
          ON garden_events(actor_id, created_at);
        """
    )


def _now() -> datetime.datetime:
    return (_clock or garden._now_dt)()


def _crop_id_by_name(name: str | None) -> str | None:
    return next((c["id"] for c in garden.RULES["crops"] if c["name"] == name), None)


# ── 聚合 ──

def _events(c, user_id: int) -> list[dict]:
    """本人 plant/harvest 事件，时间升序；偷菜事件的 actor 是访客，只有 steal，被排除。"""
    rows = c.execute(
        "SELECT kind,cycle_id,crop_name,amount,created_at FROM garden_events "
        "WHERE actor_id=? AND kind IN('plant','harvest') ORDER BY created_at ASC, id ASC",
        (user_id,),
    ).fetchall()
    out = []
    for r in rows:
        at = garden._parse(r["created_at"])
        out.append({
            "kind": r["kind"], "cycle_id": r["cycle_id"], "crop_name": r["crop_name"],
            "amount": int(r["amount"]), "at": at, "created_at": r["created_at"],
            "day": at.astimezone(garden.CST).date(),
        })
    return out


def _codex(events: list[dict]) -> dict:
    plant_crop = {e["cycle_id"]: _crop_id_by_name(e["crop_name"])
                  for e in events if e["kind"] == "plant" and e["cycle_id"]}
    stat = {c["id"]: {"planted": 0, "harvested": 0, "amount": 0, "first": None}
            for c in garden.RULES["crops"]}
    for e in events:
        cid = plant_crop.get(e["cycle_id"]) if e["kind"] == "harvest" else None
        cid = cid or _crop_id_by_name(e["crop_name"])
        if cid not in stat:
            continue
        s = stat[cid]
        if e["kind"] == "plant":
            s["planted"] += 1
            s["first"] = s["first"] or e["created_at"]
        else:
            s["harvested"] += 1
            s["amount"] += e["amount"]
    crops = []
    for c in garden.RULES["crops"]:
        s = stat[c["id"]]
        crops.append({
            "id": c["id"], "name": c["name"],
            "duration_seconds": c["duration_seconds"], "yield": c["yield"],
            "status": "harvested" if s["harvested"] else "planted" if s["planted"] else "locked",
            "planted": s["planted"], "harvested": s["harvested"],
            "harvested_amount": s["amount"], "first_planted_at": s["first"],
        })
    return {
        "unlocked": sum(1 for x in crops if x["status"] != "locked"),
        "total": len(crops),
        "crops": crops,
    }


def _progress(events: list[dict]) -> dict[str, list[tuple[str, int]]]:
    """每个 kind 的（事件时间, 达到后的累计值）序列，用于取真实解锁事件时间。"""
    seq: dict[str, list[tuple[str, int]]] = {k: [] for k in KINDS}
    plants = harvests = amount = 0
    crops: set[str] = set()
    days: set[datetime.date] = set()
    for e in events:
        if e["day"] not in days:
            days.add(e["day"])
            seq["active_days"].append((e["created_at"], len(days)))
        if e["kind"] == "plant":
            plants += 1
            seq["plant_count"].append((e["created_at"], plants))
            cid = _crop_id_by_name(e["crop_name"])
            if cid and cid not in crops:
                crops.add(cid)
                seq["distinct_crops"].append((e["created_at"], len(crops)))
        else:
            harvests += 1
            amount += e["amount"]
            seq["harvest_count"].append((e["created_at"], harvests))
            seq["harvest_total"].append((e["created_at"], amount))
    return seq


def _milestones(events: list[dict]) -> dict:
    seq = _progress(events)
    items = []
    for m in RULES["milestones"]:
        steps = seq[m["kind"]]
        value = steps[-1][1] if steps else 0
        reached = next((at for at, v in steps if v >= m["target"]), None)
        items.append({
            "id": m["id"], "title": m["title"], "description": m["description"],
            "kind": m["kind"], "value": value, "target": m["target"],
            "unlocked": reached is not None, "unlocked_at": reached,
        })
    return {"unlocked": sum(1 for i in items if i["unlocked"]), "total": len(items), "items": items}


def _footprint(events: list[dict], now: datetime.datetime) -> dict:
    today = now.astimezone(garden.CST).date()
    span = int(RULES["recent_days"])
    days = {today - datetime.timedelta(days=i): {"planted": 0, "harvested": 0, "harvested_amount": 0}
            for i in range(span)}
    for e in events:
        d = days.get(e["day"])
        if not d:
            continue
        if e["kind"] == "plant":
            d["planted"] += 1
        else:
            d["harvested"] += 1
            d["harvested_amount"] += e["amount"]
    rows = [{"date": k.isoformat(), **v} for k, v in sorted(days.items())]
    return {
        "timezone": "UTC+8",
        "days": rows,
        "totals": {k: sum(r[k] for r in rows) for k in ("planted", "harvested", "harvested_amount")},
    }


def _guardian(c, user_id: int, now: datetime.datetime) -> tuple[dict, bool]:
    g = c.execute("SELECT id FROM gardens WHERE owner_id=?", (user_id,)).fetchone()
    pref = c.execute(
        "SELECT guardian_id FROM garden_companion_preferences WHERE owner_id=?", (user_id,)
    ).fetchone()
    by_id = {x["id"]: x for x in RULES["guardians"]}
    selected = pref["guardian_id"] if pref and pref["guardian_id"] in by_id else None
    watch = None
    if selected:
        plots = c.execute(
            "SELECT crop_id,ripe_at FROM garden_plots WHERE garden_id=?", (g["id"],)
        ).fetchall() if g else []
        ripe = growing = 0
        next_ripe = None
        for p in plots:
            if not p["crop_id"]:
                continue
            if garden._parse(p["ripe_at"]) <= now:
                ripe += 1
            else:
                growing += 1
                next_ripe = min(next_ripe or p["ripe_at"], p["ripe_at"],
                                key=garden._parse)
        empty = len(plots) - ripe - growing
        kind = ("no_garden" if not g else "ripe" if ripe else "empty" if empty else "waiting")
        message = by_id[selected]["tips"][kind].format(ripe=ripe, empty=empty, growing=growing)
        watch = {
            "guardian_id": selected, "kind": kind, "message": message,
            "situation": {"plot_count": len(plots), "ripe": ripe, "growing": growing,
                          "empty": empty, "next_ripe_at": next_ripe},
        }
    guardian = {
        "note": RULES["guardian_note"],
        "options": [{k: x[k] for k in ("id", "name", "species", "tagline", "sprite")}
                    for x in RULES["guardians"]],
        "selected_id": selected,
        "watch": watch,
    }
    return guardian, g is not None


def _view(c, user_id: int) -> dict:
    now = _now()
    guardian, garden_open = _guardian(c, user_id, now)
    events = _events(c, user_id)
    return {
        "server_now": now.isoformat(),
        "garden_open": garden_open,
        "guardian": guardian,
        "protection": {
            "steal_fraction": garden.RULES["steal_fraction"],
            "steal_amount": garden.RULES["steal_amount"],
        },
        "codex": _codex(events),
        "milestones": _milestones(events),
        "footprint": _footprint(events, now),
    }


class CompanionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    guardian_id: str | None


@router.get("/api/garden/companion")
def get_companion(request: Request):
    user = garden._member(request)
    c = _db()
    try:
        return _view(c, user["id"])
    finally:
        c.close()


@router.patch("/api/garden/companion")
def patch_companion(req: CompanionPatch, request: Request):
    user = garden._member(request)
    if req.guardian_id is not None and req.guardian_id not in {g["id"] for g in RULES["guardians"]}:
        raise HTTPException(422, "没有这位护法")
    c = _db()
    try:
        try:
            c.execute(
                "INSERT INTO garden_companion_preferences(owner_id,guardian_id,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(owner_id) DO UPDATE SET guardian_id=excluded.guardian_id,"
                "updated_at=excluded.updated_at",
                (user["id"], req.guardian_id, _now().isoformat()),
            )
            c.commit()
        except sqlite3.Error:
            c.rollback()
            raise
        return _view(c, user["id"])
    finally:
        c.close()
