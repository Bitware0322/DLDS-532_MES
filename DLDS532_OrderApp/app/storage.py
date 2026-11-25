"""本地订单存储（SQLite）。所有读写都在主线程完成，关闭软件后数据不丢失。"""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .model import ST_DONE, ST_FAILED, ST_PENDING, ST_PRODUCING, STATUS_TEXT

MAX_ORDER_ID = 32767          # PLC 侧 订单ID 是 INT(16 位有符号)
TS_FMT = "%Y-%m-%d %H:%M:%S"


def now_text() -> str:
    return datetime.now().strftime(TS_FMT)


def _row_get(row: sqlite3.Row, key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


@dataclass
class Order:
    rec_id: int
    order_id: int
    ab_material: int
    qty_8mm: int
    qty_10mm: int
    slot: int
    status: str
    request_state: str = ""
    created_at: str = ""
    sent_at: str = ""
    ack_at: str = ""
    completed_at: str = ""
    plc_done_id: int = 0
    last_error: str = ""

    # -------------------------------------------------- 展示
    @property
    def status_text(self) -> str:
        text = STATUS_TEXT.get(self.status, self.status)
        if self.status == ST_PENDING and self.request_state == "sent":
            text = "待下单·等待PLC确认"
        elif self.status == ST_PENDING and self.request_state == "sending":
            text = "待下单·发送中"
        return text

    @property
    def material_text(self) -> str:
        return {1: "A 料", 2: "B 料"}.get(self.ab_material, f"{self.ab_material}")

    @property
    def in_flow(self) -> bool:
        return self.status == ST_PRODUCING or (
            self.status == ST_PENDING and self.request_state in ("sending", "sent"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "rec_id": self.rec_id, "order_id": self.order_id,
            "ab_material": self.ab_material, "qty_8mm": self.qty_8mm,
            "qty_10mm": self.qty_10mm, "slot": self.slot, "status": self.status,
            "request_state": self.request_state, "created_at": self.created_at,
            "sent_at": self.sent_at, "ack_at": self.ack_at,
            "completed_at": self.completed_at, "plc_done_id": self.plc_done_id,
            "last_error": self.last_error,
        }

    @staticmethod
    def from_row(row: sqlite3.Row) -> "Order":
        return Order(
            rec_id=int(row["id"]), order_id=int(row["order_id"]),
            ab_material=int(row["ab_material"]), qty_8mm=int(row["qty_8mm"]),
            qty_10mm=int(row["qty_10mm"]), slot=int(row["slot"]),
            status=str(row["status"]), request_state=str(_row_get(row, "request_state", "") or ""),
            created_at=str(_row_get(row, "created_at", "") or ""),
            sent_at=str(_row_get(row, "sent_at", "") or ""),
            ack_at=str(_row_get(row, "ack_at", "") or ""),
            completed_at=str(_row_get(row, "completed_at", "") or ""),
            plc_done_id=int(_row_get(row, "plc_done_id", 0) or 0),
            last_error=str(_row_get(row, "last_error", "") or ""),
        )


SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id      INTEGER NOT NULL,
    ab_material   INTEGER NOT NULL,
    qty_8mm       INTEGER NOT NULL,
    qty_10mm      INTEGER NOT NULL,
    slot          INTEGER NOT NULL,
    status        TEXT    NOT NULL,
    request_state TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL,
    sent_at       TEXT,
    ack_at        TEXT,
    completed_at  TEXT,
    plc_done_id   INTEGER NOT NULL DEFAULT 0,
    last_error    TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE TABLE IF NOT EXISTS events (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       TEXT NOT NULL,
    level    TEXT NOT NULL,
    order_id INTEGER,
    message  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Storage:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=8000")
        self._conn.executescript(SCHEMA)
        # 只保留最近 5000 条事件，避免文件无限增长
        try:
            self._conn.execute(
                "DELETE FROM events WHERE id NOT IN "
                "(SELECT id FROM events ORDER BY id DESC LIMIT 5000)")
        except sqlite3.Error:
            pass
        # 写权限自检：数据库不可写时宁可早报警，也不能让订单写不进去还照常下单
        self.writable = True
        self.write_error = ""
        try:
            self._conn.execute("CREATE TABLE IF NOT EXISTS _write_probe (x INTEGER)")
            self._conn.execute("INSERT INTO _write_probe(x) VALUES (1)")
            self._conn.execute("DELETE FROM _write_probe")
            self._conn.commit()
        except sqlite3.Error as exc:
            self.writable = False
            self.write_error = str(exc)

        # 只保留最近 4000 条事件，避免日志表无限增长
        try:
            self._conn.execute(
                "DELETE FROM events WHERE id NOT IN "
                "(SELECT id FROM events ORDER BY id DESC LIMIT 4000)")
        except sqlite3.Error:
            pass
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass

    # -------------------------------------------------- 内部
    def _exec(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cur

    def _query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, tuple(params)).fetchall())

    # -------------------------------------------------- 订单号
    def _peek_counter(self) -> int:
        rows = self._query("SELECT value FROM app_state WHERE key='order_counter'")
        if rows:
            try:
                return int(rows[0]["value"])
            except (TypeError, ValueError):
                return 0
        rows = self._query("SELECT MAX(order_id) AS m FROM orders")
        try:
            return int(rows[0]["m"] or 0)
        except (TypeError, ValueError):
            return 0

    def peek_next_order_id(self) -> int:
        """仅预览下一次生成的订单ID，不占用（跳过仍在流程中的ID）。"""
        used = {int(r["order_id"]) for r in self._query(
            "SELECT order_id FROM orders WHERE status IN (?,?)", (ST_PENDING, ST_PRODUCING))}
        candidate = self._peek_counter() % MAX_ORDER_ID + 1
        for _ in range(MAX_ORDER_ID):
            if candidate not in used:
                return candidate
            candidate = candidate % MAX_ORDER_ID + 1
        return candidate

    def _next_order_id(self) -> int:
        used = {int(r["order_id"]) for r in self._query(
            "SELECT order_id FROM orders WHERE status IN (?,?)", (ST_PENDING, ST_PRODUCING))}
        candidate = self._peek_counter() % MAX_ORDER_ID + 1
        for _ in range(MAX_ORDER_ID):
            if candidate not in used:
                self._exec("INSERT INTO app_state(key, value) VALUES('order_counter', ?) "
                           "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                           (str(candidate),))
                return candidate
            candidate = candidate % MAX_ORDER_ID + 1
        raise RuntimeError("订单ID已耗尽（PLC 侧 INT 上限 32767），请清理历史订单")

    # -------------------------------------------------- 订单操作
    def create_order(self, ab_material: int, qty_8mm: int, qty_10mm: int, slot: int) -> Order:
        order_id = self._next_order_id()
        cur = self._exec(
            "INSERT INTO orders(order_id, ab_material, qty_8mm, qty_10mm, slot, status,"
            " request_state, created_at) VALUES (?,?,?,?,?,?,'',?)",
            (order_id, ab_material, qty_8mm, qty_10mm, slot, ST_PENDING, now_text()))
        row = self._query("SELECT * FROM orders WHERE id=?", (cur.lastrowid,))[0]
        order = Order.from_row(row)
        self.log_event("info", f"新建订单 {order.order_id}：{order.material_text}，"
                               f"8mm={order.qty_8mm}，10mm={order.qty_10mm}，"
                               f"仓位={order.slot}", order.order_id)
        return order

    def get(self, rec_id: int) -> Order | None:
        rows = self._query("SELECT * FROM orders WHERE id=?", (rec_id,))
        return Order.from_row(rows[0]) if rows else None

    def update_fields(self, rec_id: int, **fields: Any) -> Order | None:
        allowed = {"status", "request_state", "sent_at", "ack_at", "completed_at",
                   "plc_done_id", "last_error", "ab_material", "qty_8mm", "qty_10mm", "slot"}
        data = {k: v for k, v in fields.items() if k in allowed}
        if not data:
            return self.get(rec_id)
        cols = ", ".join(f"{k}=?" for k in data)
        self._exec(f"UPDATE orders SET {cols} WHERE id=?", (*data.values(), rec_id))
        return self.get(rec_id)

    def active_order(self) -> Order | None:
        """当前占用产线的订单（已发送待确认 / 正在生产）。同一时间最多一笔。"""
        rows = self._query(
            "SELECT * FROM orders WHERE status=? OR (status=? AND request_state IN ('sending','sent'))"
            " ORDER BY id LIMIT 1", (ST_PRODUCING, ST_PENDING))
        return Order.from_row(rows[0]) if rows else None

    def list_orders(self, only_in_flow: bool = False) -> list[Order]:
        if only_in_flow:
            rows = self._query(
                "SELECT * FROM orders WHERE status=? OR (status=? AND request_state IN ('sending','sent'))"
                " ORDER BY id DESC", (ST_PRODUCING, ST_PENDING))
        else:
            rows = self._query("SELECT * FROM orders ORDER BY id DESC LIMIT 500")
        return [Order.from_row(r) for r in rows]

    def delete_order(self, rec_id: int) -> bool:
        order = self.get(rec_id)
        if order is None or order.in_flow:
            return False
        self._exec("DELETE FROM orders WHERE id=?", (rec_id,))
        self.log_event("info", f"删除订单 {order.order_id}", order.order_id)
        return True

    def in_flow_orders(self) -> list[Order]:
        rows = self._query(
            "SELECT * FROM orders WHERE status=? OR (status=? AND request_state IN ('sending','sent'))"
            " ORDER BY id", (ST_PRODUCING, ST_PENDING))
        return [Order.from_row(r) for r in rows]

    def interrupt_unfinished(self, reason: str) -> list[int]:
        """把仍在流程中的订单标记为“下单失败（中断）”，返回被处理的订单ID。"""
        ids: list[int] = []
        for order in self.in_flow_orders():
            self.update_fields(order.rec_id, status=ST_FAILED, request_state="", last_error=reason)
            self.log_event("warn", f"订单 {order.order_id} 标记为中断：{reason}", order.order_id)
            ids.append(order.order_id)
        return ids

    def clear_orders(self) -> int:
        """删除全部订单记录（日志保留）。返回删除条数。"""
        total = int(self._query("SELECT COUNT(*) AS c FROM orders")[0]["c"])
        self._exec("DELETE FROM orders")
        self.log_event("warn", f"已清空全部订单记录（{total} 条），运行日志保留")
        return total

    def counts(self) -> dict[str, int]:
        data = {ST_PENDING: 0, ST_PRODUCING: 0, ST_DONE: 0, ST_FAILED: 0}
        for row in self._query("SELECT status, COUNT(*) AS c FROM orders GROUP BY status"):
            data[str(row["status"])] = int(row["c"])
        return data

    # -------------------------------------------------- 事件日志
    def log_event(self, level: str, message: str, order_id: int | None = None) -> None:
        try:
            self._exec("INSERT INTO events(ts, level, order_id, message) VALUES (?,?,?,?)",
                       (now_text(), level, order_id, message))
        except sqlite3.Error:
            pass

    def recent_events(self, limit: int = 200) -> list[tuple[str, str, str]]:
        rows = self._query("SELECT ts, level, message FROM events ORDER BY id DESC LIMIT ?", (limit,))
        return [(str(r["ts"]), str(r["level"]), str(r["message"])) for r in rows][::-1]
