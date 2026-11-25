"""订单状态机（不依赖 Qt，便于独立测试）。

严格按现场握手规则实现：

  待下单 --(下单: 写参数 + MES下单请求=TRUE)--> 待下单·等待确认
  等待确认 --(PLC订单已下发=TRUE 且 订单ID一致)--> 正在生产，随后清 MES下单请求
  正在生产 --(订单已完成=TRUE 且 完成订单ID==当前订单ID)--> 已完成，随后清 订单已完成/PLC订单已下发
  等待确认 --(超过确认超时 / 写入失败)--> 下单失败

铁律：
  1. 同一时间只有一笔订单进入 PLC（本地可保存任意多笔）
  2. 完成信号必须 ID 匹配才认可，绝不用旧信号判断新订单
  3. 先落库再清 PLC 状态；清状态失败会持续重试并报警
  4. 心跳只读不写；不控制任何设备动作
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Callable

from .config import RETENTION_CLEAR, RETENTION_UNFINISHED, AppConfig
from .model import ST_DONE, ST_FAILED, ST_PENDING, ST_PRODUCING, PlcSnapshot, \
    V_ACKED, V_DONE, V_DONE_ID, V_HEARTBEAT, V_ORDER_ID, V_READY, V_REQ
from .storage import Order, Storage, TS_FMT, now_text

STALE_TAG = "stale"
CLEAR_RETRY_S = 2.0
HEARTBEAT_STALL_S = 5.0
RESTORE_GRACE_S = 5.0      # 重启后与 PLC 对账的宽限期（避免首个采样误判）
CLOSE_INTERRUPT_REASON = "软件关闭时订单未完成，已标记为中断（未收到完成信号）"
STARTUP_INTERRUPT_REASON = "上次退出时订单未完成，启动时标记为中断"


def parse_ts(text: str) -> float | None:
    try:
        return datetime.strptime(text, TS_FMT).timestamp()
    except (ValueError, TypeError):
        return None


class OrderService:
    def __init__(self, storage: Storage, cfg: AppConfig) -> None:
        self.storage = storage
        self.cfg = cfg
        self.worker = None
        self.current: Order | None = None
        self.snap = PlcSnapshot(connected=False)
        self.on_changed: Callable[[], None] | None = None
        self.on_log: Callable[[str, str], None] | None = None
        self.on_snapshot: Callable[[PlcSnapshot], None] | None = None
        self.on_alert: Callable[[str, str], None] | None = None
        self._pending_clears: dict[str, dict[str, Any]] = {}
        self._warned: set[str] = set()
        self._last_done_id = 0
        self.suspended = False          # 关闭过程中置位，忽略后续通信回调
        self._restored = False          # 当前订单是否来自“上次运行的恢复”
        self._first_conn_ts = 0.0       # 本次启动后第一次成功通信的时间
        self.restore_grace_s = RESTORE_GRACE_S

    # -------------------------------------------------- 基础设施
    def attach_worker(self, worker) -> None:
        self.worker = worker
        worker.sig_snapshot.connect(self.handle_snapshot)
        worker.sig_send_result.connect(self.on_send_result)
        worker.sig_bit_result.connect(self.on_bit_result)

    def log(self, message: str, level: str = "info", order_id: int | None = None) -> None:
        self.storage.log_event(level, message, order_id)
        if self.on_log:
            self.on_log(message, level)

    def _changed(self) -> None:
        if self.on_changed:
            self.on_changed()

    def _warn_once(self, key: str, message: str, level: str = "warn") -> None:
        if key in self._warned:
            return
        self._warned.add(key)
        self.log(message, level)

    def forget_warning(self, key: str) -> None:
        self._warned.discard(key)

    # -------------------------------------------------- 启动恢复
    def apply_retention_on_start(self) -> None:
        """按“退出保留策略”收口上次遗留数据（异常退出也在这里兜底）。"""
        mode = self.cfg.retention
        try:
            if mode == RETENTION_CLEAR:
                total = self.storage.clear_orders()
                if total:
                    self.log(f"按设置“关闭时清空”已清除上次的 {total} 条订单记录", "warn")
            elif mode == RETENTION_UNFINISHED:
                ids = self.storage.interrupt_unfinished(STARTUP_INTERRUPT_REASON)
                if ids:
                    text = "、".join(str(i) for i in ids[:5])
                    self.log(f"按设置已把上次未完成的订单标记为中断（订单ID：{text}"
                             f"{' 等' if len(ids) > 5 else ''}），不会阻塞新订单", "warn")
        except Exception as exc:  # noqa: BLE001 - 清理失败不能阻塞启动
            self.log(f"处理上次遗留订单失败：{exc}", "error")

    def load_active(self) -> None:
        """启动时从本地数据库恢复订单，并对照 PLC 状态，绝不臆测完成。"""
        self.apply_retention_on_start()
        order = self.storage.active_order()
        if order is None:
            self.current = None
            self._restored = False
            return
        if order.status == ST_PENDING and order.request_state == "sending":
            # 上次下单过程被中断：保留为“已发送”继续等待 PLC 确认，超时后自然转为失败
            order = self.storage.update_fields(order.rec_id, request_state="sent",
                                               sent_at=order.sent_at or now_text()) or order
            self.log(f"订单 {order.order_id} 上次下单被中断，继续等待 PLC 确认", "warn",
                     order.order_id)
        self.current = order
        self._restored = True
        if order.status == ST_PRODUCING:
            self.log(f"恢复在制订单 {order.order_id}，正在与 PLC 状态核对（{self.restore_grace_s:.0f} 秒内完成对账）",
                     "info", order.order_id)
        else:
            self.log(f"恢复待确认订单 {order.order_id}，正在与 PLC 状态核对", "info", order.order_id)

    # -------------------------------------------------- 轮询结果处理
    def handle_snapshot(self, snap: PlcSnapshot) -> None:
        if self.suspended:
            return
        self.snap = snap
        if self.on_snapshot:
            self.on_snapshot(snap)
        if not snap.connected:
            self._changed()
            return
        if not self.storage.writable:
            # 数据文件不可写：只做 PLC 状态显示，不再尝试改订单（否则会持续抛异常）
            self._changed()
            return
        if not self._first_conn_ts:
            self._first_conn_ts = time.time()

        self._check_heartbeat(snap)
        self._retry_pending_clears(snap)
        self._check_stale_signals(snap)

        cur = self.current
        if cur is None:
            self._changed()
            return

        if cur.status == ST_PENDING:
            self._handle_waiting_ack(cur, snap)
        elif cur.status == ST_PRODUCING:
            self._handle_producing(cur, snap)
        self._changed()

    # -------------------------------------------------- 待确认
    def _handle_waiting_ack(self, order: Order, snap: PlcSnapshot) -> None:
        plc_id = snap.i(V_ORDER_ID)
        if snap.b(V_ACKED):
            if plc_id == order.order_id:
                updated = self.storage.update_fields(
                    order.rec_id, status=ST_PRODUCING, request_state="sent",
                    ack_at=now_text(), last_error="")
                if updated:
                    self.current = updated
                self._restored = False
                self.log(f"订单 {order.order_id} 已被 PLC 确认下发，状态改为“正在生产”", "ok",
                         order.order_id)
                # 已落库，再清 MES下单请求
                self._request_clear("ack", [V_REQ])
            else:
                self._fail_order(order, f"PLC 确认的订单ID({plc_id}) 与本地订单({order.order_id}) 不一致，"
                                        f"为避免错单已中止该订单")
                self._request_clear("ack_mismatch", [V_REQ])
            return

        # 重启恢复的对账：PLC 已空闲且订单ID不是本单，说明这笔请求 PLC 从未接单
        if self._restored and self._grace_passed() and snap.b(V_READY) and plc_id != order.order_id:
            self._fail_order(order, f"软件重启后核对：产线已空闲且 PLC 订单ID={plc_id}（非 {order.order_id}），"
                                    f"PLC 未接单，已标记为中断", alert_title="订单已判定中断")
            return

        # 确认超时
        sent_ts = parse_ts(order.sent_at)
        waited = (time.time() - sent_ts) if sent_ts else 0.0
        if waited > self.cfg.ack_timeout_s:
            self._fail_order(order, f"PLC 在 {self.cfg.ack_timeout_s} 秒内未确认下单"
                                   f"（PLC订单已下发 一直为 FALSE），已撤销请求")
            self._request_clear("ack_timeout", [V_REQ])

    # -------------------------------------------------- 生产中
    def _handle_producing(self, order: Order, snap: PlcSnapshot) -> None:
        if snap.b(V_DONE):
            done_id = snap.i(V_DONE_ID)
            if done_id == order.order_id:
                self._complete_order(order, done_id)
                return
            if done_id > 0:
                if done_id != self._last_done_id:
                    self._last_done_id = done_id
                    self.log(f"收到完成信号但完成订单ID={done_id}，当前在制订单={order.order_id}，"
                             f"已忽略（不修改订单状态，等待本单完成）", "warn", order.order_id)
            else:
                self._warn_once(f"done_no_id_{order.order_id}",
                                "订单已完成=TRUE 但 完成订单ID=0，无法确认归属，已忽略", "warn")

        # 重启恢复的订单：与 PLC 对账，避免订单永久卡在“正在生产”
        self._reconcile_restored(order, snap)
        if self.current is None:
            return

        # 生产超时仅报警，不擅自修改订单状态
        if self.cfg.produce_alarm_min > 0:
            ack_ts = parse_ts(order.ack_at)
            if ack_ts and (time.time() - ack_ts) > self.cfg.produce_alarm_min * 60:
                self._warn_once(f"produce_timeout_{order.order_id}",
                                f"订单 {order.order_id} 已生产超过 {self.cfg.produce_alarm_min} 分钟，"
                                f"仍未收到完成信号，请检查产线", "error", )

    def _complete_order(self, order: Order, done_id: int) -> None:
        # 关键：先落库（含完成订单ID、完成时间），确认保存成功后再清 PLC 信号
        updated = self.storage.update_fields(
            order.rec_id, status=ST_DONE, completed_at=now_text(),
            plc_done_id=done_id, last_error="")
        if updated is None:
            self.log(f"订单 {order.order_id} 完成状态保存失败，暂不清除 PLC 信号", "error", order.order_id)
            return
        self.current = None
        self._last_done_id = 0
        self.log(f"订单 {order.order_id} 生产完成（完成订单ID={done_id}），已记录", "ok", order.order_id)
        self._request_clear("done", [V_DONE, V_ACKED])

    # -------------------------------------------------- 重启对账
    def _grace_passed(self) -> bool:
        return bool(self._first_conn_ts) and \
            (time.time() - self._first_conn_ts) >= self.restore_grace_s

    def _reconcile_restored(self, order: Order, snap: PlcSnapshot) -> None:
        """重启恢复的订单：只有确实还在 PLC 里生产才继续跟踪。

        PLC 已空闲却收不到完成信号（例如生产早已结束、PLC 已复位），说明这笔订单
        的完成记录已丢失；继续挂着只会永久占用流程且不允许删除，因此判定为中断，
        由操作员现场核实后重新下单。
        """
        if not self._restored or not self._grace_passed():
            return

        if snap.b(V_READY):
            done_id = snap.i(V_DONE_ID)
            extra = ""
            if snap.b(V_DONE):
                extra = f"；PLC 中残留的完成信号（完成订单ID={done_id}）已作为遗留信号清除"
            self._fail_order(
                order,
                f"软件重启后核对：产线已空闲（产线可接单=TRUE）却未收到本单完成信号"
                f"{'，且完成订单ID=' + str(done_id) if done_id else ''}"
                f"。该订单判定为中断或完成记录丢失，请核实产线实物后重新下单{extra}",
                alert_title="订单已判定中断")
            if snap.b(V_DONE) or snap.b(V_ACKED):
                self._request_clear("restore_stale", [V_DONE, V_ACKED])
            self._restored = False
            return

        if snap.b(V_DONE):
            return      # 生产中的完成信号交给主流程按 ID 判定

        plc_id = snap.i(V_ORDER_ID)
        if not snap.b(V_ACKED) and plc_id != order.order_id:
            self._fail_order(
                order,
                f"软件重启后核对：PLC 中已无该订单（PLC订单已下发=FALSE，PLC 订单ID={plc_id}）"
                f"，判定为生产中断，请核实产线状态后重新下单",
                alert_title="订单已判定中断")
            self._restored = False

    # -------------------------------------------------- 失败
    def _fail_order(self, order: Order, reason: str, alert_title: str = "下单失败") -> None:
        self.storage.update_fields(order.rec_id, status=ST_FAILED, request_state="",
                                   last_error=reason)
        self.current = None
        self.log(f"订单 {order.order_id} 下单失败：{reason}", "error", order.order_id)
        if self.on_alert:
            self.on_alert(alert_title, f"订单 {order.order_id}\n\n{reason}")

    # -------------------------------------------------- 人工终止
    def terminate_order(self, order: Order, reason: str = "人工终止") -> bool:
        """把卡在流程中的订单手工终止（本地改状态并撤销下单请求）。"""
        if order.status not in (ST_PENDING, ST_PRODUCING):
            return False
        self.storage.update_fields(order.rec_id, status=ST_FAILED, request_state="",
                                   last_error=reason)
        if self.current is not None and self.current.rec_id == order.rec_id:
            self.current = None
        self._restored = False
        self.log(f"订单 {order.order_id} 已人工终止：{reason}", "warn", order.order_id)
        if self.snap.connected:
            self._request_clear("terminate", [V_REQ])
        self._changed()
        return True

    # -------------------------------------------------- 关闭时的保留策略
    def apply_retention_on_close(self) -> list[int]:
        """按设置处理关闭时的订单数据，返回被标记为中断的订单ID。"""
        if self.cfg.retention == RETENTION_CLEAR:
            total = self.storage.clear_orders()
            if total:
                self.log(f"按设置“关闭时清空”已删除 {total} 条订单记录", "warn")
            return []
        if self.cfg.retention == RETENTION_UNFINISHED:
            ids = self.storage.interrupt_unfinished(CLOSE_INTERRUPT_REASON)
            if ids:
                text = "、".join(str(i) for i in ids[:5])
                self.log(f"按设置把未完成的订单标记为中断（订单ID：{text}"
                         f"{' 等' if len(ids) > 5 else ''}）", "warn")
            return ids
        return []

    # -------------------------------------------------- 空闲时的遗留信号
    def _check_stale_signals(self, snap: PlcSnapshot) -> None:
        if self.current is not None:
            return
        if snap.b(V_DONE):
            done_id = snap.i(V_DONE_ID)
            self._warn_once(f"stale_done_{done_id}",
                            f"检测到遗留完成信号（完成订单ID={done_id}），该订单不在本地在制列表中，"
                            f"正在清除信号，不影响新订单下单", "warn")
            self._request_clear(STALE_TAG, [V_DONE, V_ACKED])
        elif snap.b(V_ACKED):
            # PLC 已确认、但本地没有在制记录（例如超时被判失败后 PLC 才确认）：
            # 不能清除已下发位，否则会打断 PLC 的生产判断，只能等它自己完成
            self._warn_once("stale_acked",
                            "PLC 处于“订单已下发”状态，但本地没有对应的在制订单；"
                            "请等待该笔生产结束（完成信号会自动清除），或停机后执行状态复位", "warn")
        elif snap.b(V_REQ):
            self._warn_once("stale_req",
                            "PLC 中 MES下单请求 残留为 TRUE，新订单无法下发；"
                            "请在“维护”菜单执行 PLC 状态复位", "warn")

    # -------------------------------------------------- 心跳
    def _check_heartbeat(self, snap: PlcSnapshot) -> None:
        if snap.heartbeat_age > HEARTBEAT_STALL_S:
            self._warn_once("hb_stall",
                            f"PLC 通讯心跳 {snap.heartbeat_age:.0f} 秒无变化，"
                            f"通信链路可能异常（心跳由 PLC 维护，MES 只读）", "warn")
        else:
            self.forget_warning("hb_stall")

    # -------------------------------------------------- 清除信号（带重试）
    def _request_clear(self, tag: str, names: list[str]) -> None:
        if self.worker is None:
            return
        self._pending_clears[tag] = {"names": names, "last": 0.0, "tries": 0}
        self.worker.clear_bits(tag, names)
        self._pending_clears[tag]["last"] = time.time()
        self._changed()

    def _retry_pending_clears(self, snap: PlcSnapshot) -> None:
        if not self._pending_clears:
            return
        now = time.time()
        for tag, item in list(self._pending_clears.items()):
            if now - item["last"] < CLEAR_RETRY_S:
                continue
            # 只有当对应信号仍然存在时才重试
            if not any(snap.b(n) for n in item["names"]):
                self._pending_clears.pop(tag, None)
                continue
            if item["tries"] >= 10:
                if item["tries"] == 10:
                    self.log("清除 PLC 握手信号多次失败，请检查写入权限（DB 需允许 PUT/GET、非优化访问）",
                             "error")
                    item["tries"] += 1
                continue
            item["tries"] += 1
            item["last"] = now
            self.worker.clear_bits(tag, item["names"])

    def on_bit_result(self, tag: str, ok: bool, msg: str) -> None:
        if self.suspended:
            return
        if ok:
            self._pending_clears.pop(tag, None)
            if tag != STALE_TAG:
                self.log(msg, "info")
        else:
            self._pending_clears.setdefault(tag, {"names": [], "last": 0.0, "tries": 1})
            self._pending_clears[tag]["last"] = time.time()
            self.log(f"清除 PLC 信号失败：{msg}，将自动重试", "warn")
        self._changed()

    def has_pending_clear(self) -> bool:
        return bool(self._pending_clears)

    # -------------------------------------------------- 下单
    def can_send(self, order: Order | None = None) -> tuple[bool, str]:
        if self.worker is None:
            return False, "通信线程未启动"
        if not self.storage.writable:
            return False, f"订单数据库不可写（{self.storage.write_error}），请检查数据目录权限后再下单"
        if not self.snap.connected:
            return False, "PLC 未连接"
        cur = self.current
        if cur is not None:
            if cur.status == ST_PRODUCING:
                return False, f"订单 {cur.order_id} 正在生产，完成前不能再下发新订单"
            return False, f"订单 {cur.order_id} 已下发，正在等待 PLC 确认"
        if self._pending_clears:
            return False, "正在清除上一笔订单的 PLC 信号，请稍候"
        if not self.snap.b(V_READY):
            return False, "产线当前不可接单（产线可接单=FALSE）"
        if self.snap.b(V_REQ):
            return False, "PLC 中 MES下单请求 残留为 TRUE，请先执行状态复位"
        if self.snap.b(V_ACKED) or self.snap.b(V_DONE):
            return False, "PLC 仍有上一笔订单的确认/完成信号未清除"
        if order is not None and order.status not in (ST_PENDING, ST_FAILED):
            return False, f"订单 {order.order_id} 当前状态为“{order.status_text}”，不能下单"
        return True, ""

    def send_order(self, order: Order) -> tuple[bool, str]:
        ok, reason = self.can_send(order)
        if not ok:
            self.log(f"无法下单：{reason}", "warn", order.order_id)
            return False, reason

        self.storage.update_fields(order.rec_id, status=ST_PENDING, request_state="sending",
                                   last_error="")
        payload = {
            "rec_id": order.rec_id, "order_id": order.order_id,
            "ab_material": order.ab_material, "qty_8mm": order.qty_8mm,
            "qty_10mm": order.qty_10mm, "slot": order.slot,
        }
        self.log(f"正在向 PLC 下发订单 {order.order_id}（{order.material_text}，"
                 f"8mm={order.qty_8mm}，10mm={order.qty_10mm}，仓位={order.slot}）", "info",
                 order.order_id)
        self.worker.send_order(payload)
        self._changed()
        return True, ""

    def on_send_result(self, order: dict[str, Any], ok: bool, msg: str) -> None:
        if self.suspended:
            return
        rec = self.storage.get(int(order.get("rec_id", 0)))
        order_id = int(order.get("order_id", 0))
        if rec is None:
            self.log(f"下单结果对应的订单记录不存在（订单ID={order_id}）：{msg}", "error")
            return
        if ok:
            self.storage.update_fields(rec.rec_id, request_state="sent", sent_at=now_text())
            self.current = self.storage.get(rec.rec_id)
            self.log(f"订单 {order_id} {msg}", "ok", order_id)
        else:
            self.storage.update_fields(rec.rec_id, status=ST_FAILED, request_state="",
                                       last_error=msg)
            self.current = None
            self.log(f"订单 {order_id} 下发失败：{msg}", "error", order_id)
            # 参数可能已部分写入，撤销请求位避免 PLC 误接单
            self._request_clear("send_failed", [V_REQ])
            if self.on_alert:
                self.on_alert("下单失败", f"订单 {order_id} 未能写入 PLC：\n\n{msg}")
        self._changed()

    # -------------------------------------------------- 维护操作
    def reset_plc_state(self) -> bool:
        """强制清除 MES 侧握手信号（仅在无在制订单时可用）。"""
        if self.current is not None:
            self.log("存在在制订单，禁止执行 PLC 状态复位", "warn")
            return False
        if not self.snap.connected:
            self.log("PLC 未连接，无法复位", "warn")
            return False
        self.log("手动执行 PLC 状态复位：清除 MES下单请求 / 订单已完成 / PLC订单已下发", "warn")
        self._request_clear("manual", [V_REQ, V_DONE, V_ACKED])
        return True

    def note(self, message: str, level: str = "info") -> None:
        self.log(message, level)

    def heartbeat_text(self) -> str:
        if not self.snap.connected:
            return "-"
        hb = self.snap.i(V_HEARTBEAT)
        if self.snap.heartbeat_age > HEARTBEAT_STALL_S:
            return f"{hb}（{self.snap.heartbeat_age:.0f}s 无变化）"
        return str(hb)
