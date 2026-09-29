"""偷菜家园：成员菜园 + 串门偷菜（GARDEN-API R1）。

契约冻结（.fleet/growth-content-20260924/garden-contract.md）：
- 真人 session only：匿名被 auth 中间件 401；Agent 403；他人 private 家园 404。
- 所有响应 Cache-Control: no-store；开通默认 private，明确开放才 members/进邻居列表。
- plant/harvest/steal 按 actor+client_id 幂等：重放返回原 action 回执（id/amount 不变），
  同 client_id 换路径/换负载 409；失败请求不占 client_id。
- BEGIN IMMEDIATE 包住成熟检查、cycle_id 比对、结算、事件、幂等回执；
  每访客每茬每地块只偷一次（DB 部分唯一索引）；floor(yield*steal_fraction) 保护份额不被偷穿。
- 成熟按服务端时钟实时判定；测试经 configure(clock=...) 注入时钟，生产无提速参数。
"""

import datetime
import json
import math
import secrets
import sqlite3
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

CST = datetime.timezone(datetime.timedelta(hours=8))
RULES_PATH = Path(__file__).with_name("garden_rules.json")

_db: Callable[[], Any] | None = None
_clock: Callable[[], datetime.datetime] | None = None


def configure(*, db: Callable[[], Any], clock: Callable[[], datetime.datetime] | None = None) -> None:
    """由 main 注入现有 db()；clock 仅供单元测试注入服务端时钟。"""
    global _db, _clock
    _db = db
    if clock is not None:
        _clock = clock


def _load_rules() -> dict:
    """garden_rules.json 是唯一规则源；配置缺失/畸形直接启动失败，不落默认值。"""
    data = json.loads(RULES_PATH.read_text("utf-8"))
    crops = data.get("crops")
    if not isinstance(data.get("plot_count"), int) or data["plot_count"] < 1:
        raise ValueError("garden_rules.json: plot_count 必须是 >=1 的整数")
    if not isinstance(data.get("steal_amount"), int) or data["steal_amount"] < 1:
        raise ValueError("garden_rules.json: steal_amount 必须是 >=1 的整数")
    if not isinstance(data.get("steal_fraction"), (int, float)) or not 0 <= data["steal_fraction"] < 1:
        raise ValueError("garden_rules.json: steal_fraction 必须在 [0,1) 区间")
    if not isinstance(crops, list) or not crops:
        raise ValueError("garden_rules.json: crops 不能为空")
    for crop in crops:
        if not crop.get("id") or not crop.get("name"):
            raise ValueError("garden_rules.json: 每个作物需要 id 和 name")
        if int(crop["duration_seconds"]) <= 0 or int(crop["yield"]) <= 0:
            raise ValueError("garden_rules.json: 作物 duration_seconds/yield 必须为正整数")
    return data


RULES = _load_rules()


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["garden"], dependencies=[Depends(_no_store)])


def _member(request: Request) -> dict:
    """家园：Agent 403，匿名 401（通常已被中间件拦），成员 session 通过。"""
    kind = getattr(request.state, "auth_kind", None)
    if kind == "agent":
        raise HTTPException(403, "家园暂不开放 Agent")
    if kind != "session" or not getattr(request.state, "user", None):
        raise HTTPException(401, "请先登录")
    return request.state.user


# ── schema（幂等，只加不删）──

def ensure_schema(connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS gardens(
          id TEXT PRIMARY KEY,
          owner_id INTEGER NOT NULL UNIQUE,
          visibility TEXT NOT NULL DEFAULT 'private',
          harvest_total INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS garden_plots(
          garden_id TEXT NOT NULL,
          plot_id INTEGER NOT NULL,
          cycle_id TEXT,
          crop_id TEXT,
          planted_at TEXT,
          ripe_at TEXT,
          yield INTEGER NOT NULL DEFAULT 0,
          stolen INTEGER NOT NULL DEFAULT 0,
          protected_yield INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(garden_id, plot_id)
        );

        CREATE TABLE IF NOT EXISTS garden_events(
          id TEXT PRIMARY KEY,
          garden_id TEXT NOT NULL,
          kind TEXT NOT NULL,
          actor_id INTEGER NOT NULL,
          plot_id INTEGER,
          cycle_id TEXT,
          crop_name TEXT,
          amount INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS garden_events_garden
          ON garden_events(garden_id, created_at DESC, id DESC);
        -- 每访客每一茬每地块只偷一次的 DB 兜底（并发重复点击由它拦下）
        CREATE UNIQUE INDEX IF NOT EXISTS garden_steal_once
          ON garden_events(garden_id, plot_id, cycle_id, actor_id) WHERE kind='steal';

        -- 幂等回执：actor+client_id 唯一；同 id 换操作/换负载判 409
        CREATE TABLE IF NOT EXISTS garden_actions(
          actor_id INTEGER NOT NULL,
          client_id TEXT NOT NULL,
          op TEXT NOT NULL,
          payload TEXT NOT NULL,
          event_id TEXT,
          created_at TEXT NOT NULL,
          PRIMARY KEY(actor_id, client_id)
        );
        """
    )


# ── 时钟与序列化 ──

def _now_dt() -> datetime.datetime:
    dt = (_clock or (lambda: datetime.datetime.now(CST)))()
    return dt if dt.tzinfo else dt.replace(tzinfo=CST)


def _parse(text: str) -> datetime.datetime:
    dt = datetime.datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.replace(tzinfo=CST)


def _crop(crop_id: str) -> dict | None:
    return next((c for c in RULES["crops"] if c["id"] == crop_id), None)


def _crop_name(crop_id) -> str | None:
    if crop_id is None:
        return None
    c = _crop(crop_id)
    return c["name"] if c else str(crop_id)


def _owner(c, user_id: int) -> dict:
    """Owner 公开身份：只给展示名与 member_key，不暴露邮箱/账号对象。"""
    u = c.execute(
        "SELECT username,display_name,member_key FROM users WHERE id=?", (user_id,)
    ).fetchone()
    if not u:
        return {"name": "成员", "member_key": None}
    return {"name": u["display_name"] or u["username"], "member_key": u["member_key"]}


def _plot_state(p, now: datetime.datetime) -> str:
    if not p["crop_id"]:
        return "empty"
    return "ripe" if _parse(p["ripe_at"]) <= now else "growing"


def _garden(c, g, viewer_id: int, now: datetime.datetime) -> dict:
    is_mine = viewer_id == g["owner_id"]
    plots = c.execute(
        "SELECT * FROM garden_plots WHERE garden_id=? ORDER BY plot_id ASC", (g["id"],)
    ).fetchall()
    has_own = is_mine or c.execute(
        "SELECT 1 FROM gardens WHERE owner_id=?", (viewer_id,)
    ).fetchone() is not None
    stolen_cycles: set[tuple] = set()
    if not is_mine:
        stolen_cycles = {
            (r["plot_id"], r["cycle_id"])
            for r in c.execute(
                "SELECT plot_id,cycle_id FROM garden_events "
                "WHERE garden_id=? AND kind='steal' AND actor_id=?",
                (g["id"], viewer_id),
            )
        }
    items = []
    for p in plots:
        state = _plot_state(p, now)
        items.append({
            "id": p["plot_id"],
            "cycle_id": p["cycle_id"],
            "crop_id": p["crop_id"],
            "state": state,
            "planted_at": p["planted_at"],
            "ripe_at": p["ripe_at"],
            "yield": p["yield"],
            "stolen": p["stolen"],
            "protected_yield": p["protected_yield"],
            "can_steal": bool(
                not is_mine and has_own and state == "ripe"
                and p["stolen"] < p["yield"] - p["protected_yield"]
                and (p["plot_id"], p["cycle_id"]) not in stolen_cycles
            ),
        })
    return {
        "id": g["id"],
        "owner": _owner(c, g["owner_id"]),
        "is_mine": is_mine,
        "visibility": g["visibility"],
        "harvest_total": g["harvest_total"],
        "plots": items,
        "created_at": g["created_at"],
    }


def _garden_response(c, g, user: dict, now: datetime.datetime) -> dict:
    return {
        "garden": _garden(c, g, user["id"], now) if g else None,
        "rules": RULES,
        "server_now": now.isoformat(),
    }


def _action_response(c, g, user: dict, event_id: str, replayed: bool, now: datetime.datetime) -> dict:
    """ActionResponse：action 是原操作回执（id/amount 不变），garden 为当前状态。"""
    ev = c.execute(
        "SELECT id,kind,amount FROM garden_events WHERE id=?", (event_id,)
    ).fetchone()
    resp = _garden_response(c, g, user, now)
    resp["action"] = {"id": ev["id"], "kind": ev["kind"], "amount": ev["amount"]}
    resp["replayed"] = replayed
    return resp


# ── 幂等回执（actor+client_id 唯一，事务内判重）──

def _idem_lookup(c, actor_id: int, client_id: str, op: str, payload: str):
    """命中且负载一致 → 返回回执行（走重放）；命中但换操作/负载 → 409。"""
    r = c.execute(
        "SELECT op,payload,event_id FROM garden_actions WHERE actor_id=? AND client_id=?",
        (actor_id, client_id),
    ).fetchone()
    if r and (r["op"] != op or r["payload"] != payload):
        raise HTTPException(409, "client_id 已被其它请求占用，请换新")
    return r


def _idem_record(c, actor_id: int, client_id: str, op: str, payload: str, event_id, now) -> None:
    c.execute(
        "INSERT INTO garden_actions(actor_id,client_id,op,payload,event_id,created_at) "
        "VALUES(?,?,?,?,?,?)",
        (actor_id, client_id, op, payload, event_id, now.isoformat()),
    )


def _idem_replay(c, actor_id: int, client_id: str, op: str, payload: str):
    """并发同 client_id 撞 PK 后读赢家回执；查不到返回 None。"""
    r = c.execute(
        "SELECT event_id FROM garden_actions WHERE actor_id=? AND client_id=? AND op=? AND payload=?",
        (actor_id, client_id, op, payload),
    ).fetchone()
    return r["event_id"] if r else None


def _event(c, garden_id: str, kind: str, actor_id: int, plot_id, cycle_id, crop_name, amount: int, now) -> str:
    eid = "ev_" + secrets.token_urlsafe(9)
    c.execute(
        "INSERT INTO garden_events(id,garden_id,kind,actor_id,plot_id,cycle_id,crop_name,amount,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (eid, garden_id, kind, actor_id, plot_id, cycle_id, crop_name, amount, now.isoformat()),
    )
    return eid


def _own_garden(c, user_id: int):
    g = c.execute("SELECT * FROM gardens WHERE owner_id=?", (user_id,)).fetchone()
    if not g:
        raise HTTPException(404, "还没有家园")
    return g


def _visible_garden(c, gid: str, user_id: int):
    """本人可读自己家园；他人仅 members 可见，private/不存在统一 404。"""
    g = c.execute("SELECT * FROM gardens WHERE id=?", (gid,)).fetchone()
    if not g or (g["visibility"] != "members" and g["owner_id"] != user_id):
        raise HTTPException(404, "这个家园不存在")
    return g


# ── 输入 ──

class GardenOpenReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_id: str = Field(min_length=1, max_length=80)


class GardenPatchReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    visibility: Literal["private", "members"]
    client_id: str = Field(min_length=1, max_length=80)


class PlantReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plot_id: int = Field(ge=1)
    crop_id: str = Field(min_length=1, max_length=40)
    client_id: str = Field(min_length=1, max_length=80)


class CycleReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plot_id: int = Field(ge=1)
    cycle_id: str = Field(min_length=1, max_length=80)
    client_id: str = Field(min_length=1, max_length=80)


# ── 我的家园 ──

@router.get("/api/garden/mine")
def get_mine(request: Request):
    user = _member(request)
    c = _db()
    try:
        g = c.execute("SELECT * FROM gardens WHERE owner_id=?", (user["id"],)).fetchone()
        return _garden_response(c, g, user, _now_dt())
    finally:
        c.close()


@router.post("/api/garden/mine")
def open_mine(req: GardenOpenReq, request: Request):
    user = _member(request)
    c = _db()
    try:
        c.execute("BEGIN IMMEDIATE")
        try:
            now = _now_dt()
            if not _idem_lookup(c, user["id"], req.client_id, "open", ""):
                g = c.execute(
                    "SELECT * FROM gardens WHERE owner_id=?", (user["id"],)
                ).fetchone()
                if not g:
                    gid = "gd_" + secrets.token_urlsafe(9)
                    c.execute(
                        "INSERT INTO gardens(id,owner_id,visibility,harvest_total,created_at) "
                        "VALUES(?,?,'private',0,?)",
                        (gid, user["id"], now.isoformat()),
                    )
                    for pid in range(1, int(RULES["plot_count"]) + 1):
                        c.execute(
                            "INSERT INTO garden_plots(garden_id,plot_id) VALUES(?,?)", (gid, pid)
                        )
                _idem_record(c, user["id"], req.client_id, "open", "", None, now)
            c.commit()
        except sqlite3.IntegrityError:
            c.rollback()  # 并发开通/同 client_id 撞单：赢家已落库，直接读现状
        except Exception:
            c.rollback()
            raise
        g = c.execute("SELECT * FROM gardens WHERE owner_id=?", (user["id"],)).fetchone()
        if not g:
            raise HTTPException(500, "开通失败，请稍后再试")
        return _garden_response(c, g, user, _now_dt())
    finally:
        c.close()


@router.patch("/api/garden/mine")
def patch_mine(req: GardenPatchReq, request: Request):
    user = _member(request)
    c = _db()
    try:
        c.execute("BEGIN IMMEDIATE")
        try:
            now = _now_dt()
            if not _idem_lookup(c, user["id"], req.client_id, "visibility", req.visibility):
                g = _own_garden(c, user["id"])
                eid = None
                if g["visibility"] != req.visibility:
                    c.execute(
                        "UPDATE gardens SET visibility=? WHERE id=?", (req.visibility, g["id"])
                    )
                    # amount 记录新状态：1=开放串门，0=回到 private
                    eid = _event(c, g["id"], "visibility", user["id"], None, None, None,
                                 1 if req.visibility == "members" else 0, now)
                _idem_record(c, user["id"], req.client_id, "visibility", req.visibility, eid, now)
            c.commit()
        except sqlite3.IntegrityError:
            c.rollback()
        except Exception:
            c.rollback()
            raise
        g = c.execute("SELECT * FROM gardens WHERE owner_id=?", (user["id"],)).fetchone()
        if not g:
            raise HTTPException(404, "还没有家园")
        return _garden_response(c, g, user, _now_dt())
    finally:
        c.close()


@router.post("/api/garden/mine/plant")
def plant(req: PlantReq, request: Request):
    user = _member(request)
    crop = _crop(req.crop_id)
    if not crop:
        raise HTTPException(422, "没有这种种子")
    payload = f"{req.plot_id}:{req.crop_id}"
    c = _db()
    try:
        c.execute("BEGIN IMMEDIATE")
        event_id, replayed = None, False
        try:
            now = _now_dt()
            hit = _idem_lookup(c, user["id"], req.client_id, "plant", payload)
            if hit:
                event_id, replayed = hit["event_id"], True
            else:
                g = _own_garden(c, user["id"])
                p = c.execute(
                    "SELECT * FROM garden_plots WHERE garden_id=? AND plot_id=?",
                    (g["id"], req.plot_id),
                ).fetchone()
                if not p:
                    raise HTTPException(404, "这块地不存在")
                if p["crop_id"]:
                    raise HTTPException(409, "这块地已经种着了")
                cycle = "cy_" + secrets.token_urlsafe(9)
                amount_yield = int(crop["yield"])
                protected = amount_yield - math.floor(
                    amount_yield * float(RULES["steal_fraction"])
                )
                c.execute(
                    """UPDATE garden_plots SET cycle_id=?,crop_id=?,planted_at=?,ripe_at=?,
                       yield=?,stolen=0,protected_yield=? WHERE garden_id=? AND plot_id=?""",
                    (
                        cycle, crop["id"], now.isoformat(),
                        (now + datetime.timedelta(seconds=int(crop["duration_seconds"]))).isoformat(),
                        amount_yield, protected, g["id"], req.plot_id,
                    ),
                )
                event_id = _event(c, g["id"], "plant", user["id"], req.plot_id, cycle,
                                  crop["name"], 0, now)
                _idem_record(c, user["id"], req.client_id, "plant", payload, event_id, now)
            c.commit()
        except sqlite3.IntegrityError:
            c.rollback()
            event_id = _idem_replay(c, user["id"], req.client_id, "plant", payload)
            if not event_id:
                raise HTTPException(409, "操作冲突，请刷新后重试")
            replayed = True
        except Exception:
            c.rollback()
            raise
        g = c.execute("SELECT * FROM gardens WHERE owner_id=?", (user["id"],)).fetchone()
        return _action_response(c, g, user, event_id, replayed, _now_dt())
    finally:
        c.close()


@router.post("/api/garden/mine/harvest")
def harvest(req: CycleReq, request: Request):
    user = _member(request)
    payload = f"{req.plot_id}:{req.cycle_id}"
    c = _db()
    try:
        c.execute("BEGIN IMMEDIATE")
        event_id, replayed = None, False
        try:
            now = _now_dt()
            hit = _idem_lookup(c, user["id"], req.client_id, "harvest", payload)
            if hit:
                event_id, replayed = hit["event_id"], True
            else:
                g = _own_garden(c, user["id"])
                p = c.execute(
                    "SELECT * FROM garden_plots WHERE garden_id=? AND plot_id=?",
                    (g["id"], req.plot_id),
                ).fetchone()
                if not p:
                    raise HTTPException(404, "这块地不存在")
                if not p["crop_id"] or p["cycle_id"] != req.cycle_id:
                    raise HTTPException(409, "这块地已经换茬了，刷新再看看")
                if _parse(p["ripe_at"]) > now:
                    raise HTTPException(409, "还没成熟，再等等")
                gain = p["yield"] - p["stolen"]
                c.execute(
                    "UPDATE gardens SET harvest_total=harvest_total+? WHERE id=?",
                    (gain, g["id"]),
                )
                c.execute(
                    """UPDATE garden_plots SET cycle_id=NULL,crop_id=NULL,planted_at=NULL,
                       ripe_at=NULL,yield=0,stolen=0,protected_yield=0
                       WHERE garden_id=? AND plot_id=?""",
                    (g["id"], req.plot_id),
                )
                event_id = _event(c, g["id"], "harvest", user["id"], req.plot_id, req.cycle_id,
                                  _crop_name(p["crop_id"]), gain, now)
                _idem_record(c, user["id"], req.client_id, "harvest", payload, event_id, now)
            c.commit()
        except sqlite3.IntegrityError:
            c.rollback()
            event_id = _idem_replay(c, user["id"], req.client_id, "harvest", payload)
            if not event_id:
                raise HTTPException(409, "操作冲突，请刷新后重试")
            replayed = True
        except Exception:
            c.rollback()
            raise
        g = c.execute("SELECT * FROM gardens WHERE owner_id=?", (user["id"],)).fetchone()
        return _action_response(c, g, user, event_id, replayed, _now_dt())
    finally:
        c.close()


# ── 串门与偷菜 ──

@router.get("/api/garden/neighbors")
def neighbors(request: Request, limit: int = 12, offset: int = 0):
    user = _member(request)
    limit = min(max(1, int(limit)), 30)
    offset = max(0, int(offset))
    c = _db()
    try:
        now = _now_dt()
        total = c.execute(
            "SELECT COUNT(*) FROM gardens WHERE visibility='members' AND owner_id<>?",
            (user["id"],),
        ).fetchone()[0]
        rows = c.execute(
            """SELECT g.id,g.owner_id,g.harvest_total,
                 (SELECT COUNT(*) FROM garden_plots p WHERE p.garden_id=g.id
                    AND p.crop_id IS NOT NULL AND p.ripe_at<=?) AS ripe_count
               FROM gardens g WHERE g.visibility='members' AND g.owner_id<>?
               ORDER BY ripe_count DESC, g.created_at ASC, g.id ASC LIMIT ? OFFSET ?""",
            (now.isoformat(), user["id"], limit, offset),
        ).fetchall()
        items = [
            {
                "id": r["id"],
                "owner": _owner(c, r["owner_id"]),
                "ripe_count": r["ripe_count"],
                "harvest_total": r["harvest_total"],
            }
            for r in rows
        ]
        return {
            "items": items, "total": total, "limit": limit, "offset": offset,
            "server_now": now.isoformat(),
        }
    finally:
        c.close()


@router.get("/api/garden/visit/{gid}")
def visit(gid: str, request: Request):
    user = _member(request)
    c = _db()
    try:
        return _garden_response(c, _visible_garden(c, gid, user["id"]), user, _now_dt())
    finally:
        c.close()


@router.post("/api/garden/visit/{gid}/steal")
def steal(gid: str, req: CycleReq, request: Request):
    user = _member(request)
    payload = f"{gid}:{req.plot_id}:{req.cycle_id}"
    c = _db()
    try:
        c.execute("BEGIN IMMEDIATE")
        event_id, replayed = None, False
        try:
            now = _now_dt()
            hit = _idem_lookup(c, user["id"], req.client_id, "steal", payload)
            if hit:
                event_id, replayed = hit["event_id"], True
            else:
                mine = c.execute(
                    "SELECT * FROM gardens WHERE owner_id=?", (user["id"],)
                ).fetchone()
                if not mine:
                    raise HTTPException(409, "先开通自己的家园才能去偷菜")
                g = c.execute("SELECT * FROM gardens WHERE id=?", (gid,)).fetchone()
                if not g or g["visibility"] != "members":
                    raise HTTPException(404, "这个家园不存在")
                if g["owner_id"] == user["id"]:
                    raise HTTPException(409, "不能偷自己的菜")
                p = c.execute(
                    "SELECT * FROM garden_plots WHERE garden_id=? AND plot_id=?",
                    (gid, req.plot_id),
                ).fetchone()
                if not p:
                    raise HTTPException(404, "这块地不存在")
                if not p["crop_id"] or p["cycle_id"] != req.cycle_id:
                    raise HTTPException(409, "这块地已经换茬了，刷新再看看")
                if _parse(p["ripe_at"]) > now:
                    raise HTTPException(409, "还没成熟，偷不到")
                if c.execute(
                    "SELECT 1 FROM garden_events WHERE garden_id=? AND plot_id=? "
                    "AND cycle_id=? AND kind='steal' AND actor_id=?",
                    (gid, req.plot_id, req.cycle_id, user["id"]),
                ).fetchone():
                    raise HTTPException(409, "这一茬你已经偷过了")
                stealable = p["yield"] - p["protected_yield"] - p["stolen"]
                if stealable <= 0:
                    raise HTTPException(409, "这块地能偷的已经到上限了")
                amount = min(int(RULES["steal_amount"]), stealable)
                c.execute(
                    "UPDATE garden_plots SET stolen=stolen+? "
                    "WHERE garden_id=? AND plot_id=? AND cycle_id=?",
                    (amount, gid, req.plot_id, req.cycle_id),
                )
                # 偷到的收成只入访客自己家园的总收成
                c.execute(
                    "UPDATE gardens SET harvest_total=harvest_total+? WHERE id=?",
                    (amount, mine["id"]),
                )
                event_id = _event(c, gid, "steal", user["id"], req.plot_id, req.cycle_id,
                                  _crop_name(p["crop_id"]), amount, now)
                _idem_record(c, user["id"], req.client_id, "steal", payload, event_id, now)
            c.commit()
        except sqlite3.IntegrityError:
            c.rollback()
            event_id = _idem_replay(c, user["id"], req.client_id, "steal", payload)
            if event_id:
                replayed = True
            else:
                # 并发同访客同茬：唯一索引拦下的另一次点击
                raise HTTPException(409, "这一茬你已经偷过了")
        except Exception:
            c.rollback()
            raise
        # 回执里的 garden 是被偷家园的现状；若主人已关私，退回访客自己家园
        g = c.execute("SELECT * FROM gardens WHERE id=?", (gid,)).fetchone()
        if not g or (g["visibility"] != "members" and g["owner_id"] != user["id"]):
            g = c.execute("SELECT * FROM gardens WHERE owner_id=?", (user["id"],)).fetchone()
        return _action_response(c, g, user, event_id, replayed, _now_dt())
    finally:
        c.close()


@router.get("/api/garden/{gid}/events")
def events(gid: str, request: Request, limit: int = 12, offset: int = 0):
    user = _member(request)
    limit = min(max(1, int(limit)), 30)
    offset = max(0, int(offset))
    c = _db()
    try:
        _visible_garden(c, gid, user["id"])
        total = c.execute(
            "SELECT COUNT(*) FROM garden_events WHERE garden_id=?", (gid,)
        ).fetchone()[0]
        rows = c.execute(
            "SELECT * FROM garden_events WHERE garden_id=? "
            "ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
            (gid, limit, offset),
        ).fetchall()
        items = [
            {
                "id": r["id"],
                "kind": r["kind"],
                "actor": _owner(c, r["actor_id"]),
                "plot_id": r["plot_id"],
                "crop_name": r["crop_name"],
                "amount": r["amount"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    finally:
        c.close()
