"""PLC 通信线程：所有 S7 读写都在这个线程里完成，界面线程永不阻塞。

命令通过队列下发，结果通过 Qt 信号回到主线程，保证：
  * 界面按钮点击不会卡住（连接超时、写失败都在后台）
  * 同一时刻只有一个线程访问 PLC，读写不会互相打断
"""
from __future__ import annotations

import queue
import time
from typing import Any

from PySide6.QtCore import QThread, Signal

from .config import AppConfig
from .model import V_AB, V_ACKED, V_DONE, V_DONE_ID, V_HEARTBEAT, V_ORDER_ID, V_QTY8, V_QTY10, \
    V_READY, V_REQ, V_SLOT
from .plc_transport import SimulatedPlc, Snap7Transport, TransportError, decode_block


class PlcWorker(QThread):
    sig_snapshot = Signal(object)          # PlcSnapshot
    sig_conn = Signal(bool, str)           # connected, message
    sig_log = Signal(str, str)             # message, level
    sig_send_result = Signal(object, bool, str)   # order dict, ok, message
    sig_bit_result = Signal(str, bool, str)       # tag, ok, message
    sig_test_result = Signal(bool, str, object)   # ok, message, values dict

    def __init__(self, cfg: AppConfig, transport_factory=None, parent=None) -> None:
        super().__init__(parent)
        self._cfg = cfg.copy()
        self._factory = transport_factory
        self._queue: queue.Queue[tuple] = queue.Queue()
        self._stop = False
        self._want_conn = True
        self._transport: Any = None
        self._connected = False
        self._last_err = ""
        self._hb_value: Any = None
        self._hb_since = time.time()
        self._last_poll = 0.0
        self._next_retry = 0.0

    # -------------------------------------------------- 外部接口（主线程调用）
    def enqueue(self, *cmd: Any) -> None:
        self._queue.put(tuple(cmd))

    def send_order(self, order: dict[str, Any]) -> None:
        self.enqueue("send", order)

    def clear_bits(self, tag: str, names: list[str]) -> None:
        self.enqueue("bits", tag, names)

    def apply_config(self, cfg: AppConfig) -> None:
        self.enqueue("config", cfg)

    def test_read(self) -> None:
        self.enqueue("test")

    def reconnect(self) -> None:
        self.enqueue("reconnect")

    def stop(self) -> None:
        self._stop = True
        self._queue.put(("quit",))

    # -------------------------------------------------- 线程主体
    def run(self) -> None:  # noqa: D401
        while not self._stop:
            try:
                cmd = self._queue.get(timeout=0.02)
            except queue.Empty:
                cmd = None
            if cmd is not None:
                self._handle(cmd)
                if cmd[0] == "quit":
                    break
            self._maintain()
        self._teardown()

    # -------------------------------------------------- 命令分发
    def _handle(self, cmd: tuple) -> None:
        kind = cmd[0]
        try:
            if kind == "config":
                self._cfg = cmd[1]
                self._drop("配置已更新，重新连接")
            elif kind == "reconnect":
                self._drop("手动重连")
            elif kind == "connect":
                self._want_conn = True
                self._next_retry = 0.0
            elif kind == "disconnect":
                self._want_conn = False
                self._drop("已断开")
            elif kind == "send":
                self._do_send(cmd[1])
            elif kind == "bits":
                self._do_clear_bits(cmd[1], cmd[2])
            elif kind == "test":
                self._do_test()
            elif kind == "quit":
                pass
        except Exception as exc:  # noqa: BLE001 - 线程内兜底，避免线程退出
            self.sig_log.emit(f"通信线程异常：{exc}", "error")

    # -------------------------------------------------- 连接维护
    def _maintain(self) -> None:
        if not self._want_conn:
            return
        now = time.time()
        if self._transport is None or not self._connected:
            if now < self._next_retry:
                return
            self._try_connect()
            return
        if now - self._last_poll >= max(50, self._cfg.poll_ms) / 1000.0:
            self._last_poll = now
            self._poll()

    def _build_transport(self):
        if self._factory is not None:
            return self._factory(self._cfg)
        if self._cfg.simulate:
            return SimulatedPlc(self._cfg, lambda msg, level="info": self.sig_log.emit(msg, level))
        return Snap7Transport(self._cfg)

    def _try_connect(self) -> None:
        if self._transport is not None:
            try:
                self._transport.disconnect()
            except Exception:  # noqa: BLE001
                pass
        self._transport = self._build_transport()
        try:
            self._transport.connect()
        except TransportError as exc:
            self._connected = False
            self._next_retry = time.time() + 2.0
            msg = str(exc)
            if msg != self._last_err:
                self._last_err = msg
                self.sig_conn.emit(False, msg)
                self.sig_log.emit(msg, "warn")
            self.sig_snapshot.emit(self._offline_snapshot(msg))
            try:
                self._transport.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._transport = None
            return

        self._connected = True
        self._last_err = ""
        self._next_retry = 0.0
        self._last_poll = 0.0
        self._hb_value = None
        self._hb_since = time.time()
        self.sig_conn.emit(True, f"已连接 {self._cfg.ip}:{self._cfg.port} "
                                 f"(机架 {self._cfg.rack} / 插槽 {self._cfg.slot})")
        self.sig_log.emit(f"PLC 连接成功：{self._cfg.ip}:{self._cfg.port}，DB{self._cfg.db_number}",
                          "ok")
        self._poll()

    def _drop(self, reason: str) -> None:
        if self._transport is not None:
            try:
                self._transport.disconnect()
            except Exception:  # noqa: BLE001
                pass
        self._transport = None
        if self._connected:
            self.sig_conn.emit(False, reason)
            self.sig_snapshot.emit(self._offline_snapshot(reason))
        self._connected = False
        self._next_retry = time.time() + 0.5

    def _teardown(self) -> None:
        if self._transport is not None:
            try:
                self._transport.disconnect()
            except Exception:  # noqa: BLE001
                pass
        self._transport = None
        self._connected = False

    # -------------------------------------------------- 轮询
    def _offline_snapshot(self, msg: str):
        from .model import PlcSnapshot
        return PlcSnapshot(connected=False, error=msg)

    def _read_values(self) -> dict[str, Any]:
        start, size = self._cfg.read_window()
        data = self._transport.read(start, size)
        return decode_block(data, start, self._cfg)

    def _poll(self) -> None:
        from .model import PlcSnapshot
        try:
            values = self._read_values()
        except (TransportError, ValueError) as exc:
            self._drop(f"通信中断：{exc}")
            self.sig_log.emit(f"通信中断：{exc}", "error")
            return

        hb = values.get(V_HEARTBEAT)
        now = time.time()
        if hb != self._hb_value:
            self._hb_value = hb
            self._hb_since = now
        snap = PlcSnapshot(connected=True, ts=now, values=values,
                           heartbeat_age=now - self._hb_since,
                           used_bit_write=getattr(self._transport, "last_write_mode", ""))
        self.sig_snapshot.emit(snap)

    # -------------------------------------------------- 下单
    def _do_send(self, order: dict[str, Any]) -> None:
        ok, msg = self._send_order_impl(order)
        self.sig_send_result.emit(order, ok, msg)

    def _send_order_impl(self, order: dict[str, Any]) -> tuple[bool, str]:
        if self._transport is None or not self._connected:
            return False, "PLC 未连接，请检查网线、IP 与 PLC 电源"

        # 1) 发送前重新读取一次，确认产线可接单且没有遗留握手信号
        try:
            values = self._read_values()
        except (TransportError, ValueError) as exc:
            return False, f"发送前读取 PLC 失败：{exc}"

        if not bool(values.get(V_READY)):
            return False, "产线当前不可接单（产线可接单=FALSE），请等待产线空闲"
        if bool(values.get(V_REQ)):
            return False, "PLC 中 MES下单请求 仍为 TRUE，请先复位上一笔请求"
        if bool(values.get(V_ACKED)) or bool(values.get(V_DONE)):
            return False, "PLC 仍保留上一笔订单的确认/完成信号，请稍候或执行状态复位"

        # 2) 写订单参数（PLC 不写这些字段，可直接按字节写）
        params = [
            (V_ORDER_ID, int(order["order_id"])),
            (V_AB, int(order["ab_material"])),
            (V_QTY8, int(order["qty_8mm"])),
            (V_QTY10, int(order["qty_10mm"])),
            (V_SLOT, int(order["slot"])),
        ]
        try:
            for name, value in params:
                var = self._cfg.var(name)
                self._transport.write_int(var.byte, var.dtype, value)
        except (TransportError, ValueError) as exc:
            return False, f"写入订单参数失败：{exc}"

        # 3) 回读校验，参数不一致绝不能置位下单请求
        try:
            check = self._read_values()
        except (TransportError, ValueError) as exc:
            return False, f"写入后校验读取失败：{exc}"
        diff = []
        for name, value in params:
            got = check.get(name)
            if int(got if got is not None else 0) != value:
                diff.append(f"{name} 期望 {value} 实际 {got}")
        if diff:
            return False, "订单参数写入校验失败：" + "；".join(diff)

        # 4) 置 MES下单请求 = TRUE
        req = self._cfg.var(V_REQ)
        try:
            mode = self._transport.write_bits([(req.byte, req.bit, True)])
            if mode and mode != "sim":
                self.sig_log.emit(f"位写入方式：{mode}", "info")
        except TransportError as exc:
            return False, f"写入 MES下单请求 失败：{exc}"

        # 5) 确认请求位确实生效
        try:
            verify = self._read_values()
        except (TransportError, ValueError):
            verify = {}
        if verify and not bool(verify.get(V_REQ)):
            return False, "MES下单请求 置位后回读为 FALSE，写入未生效"
        return True, "订单已写入 DB121，等待 PLC 确认下发"

    # -------------------------------------------------- 清除握手位
    def _do_clear_bits(self, tag: str, names: list[str]) -> None:
        ok, msg = self._clear_bits_impl(names)
        self.sig_bit_result.emit(tag, ok, msg)

    def _clear_bits_impl(self, names: list[str]) -> tuple[bool, str]:
        if self._transport is None or not self._connected:
            return False, "PLC 未连接，无法清除信号（软件会持续重试）"
        items = []
        for name in names:
            var = self._cfg.var(name)
            if var.dtype != "BOOL":
                continue
            items.append((var.byte, var.bit, False))
        if not items:
            return True, "无需清除"
        try:
            mode = self._transport.write_bits(items)
        except TransportError as exc:
            return False, f"清除信号失败：{exc}"
        try:
            values = self._read_values()
        except (TransportError, ValueError):
            return True, "已写入清除命令（回读校验失败，稍后由轮询确认）"
        remaining = [n for n in names if bool(values.get(n))]
        if remaining:
            return False, f"信号未能清除：{'、'.join(remaining)}"
        extra = f"（位写入方式：{mode}）" if mode and mode not in ("sim", "bit") else ""
        return True, f"已清除 {'、'.join(names)}{extra}"

    # -------------------------------------------------- 地址测试
    def _do_test(self) -> None:
        if self._transport is None or not self._connected:
            self.sig_test_result.emit(False, "PLC 未连接", {})
            return
        try:
            values = self._read_values()
        except (TransportError, ValueError) as exc:
            self.sig_test_result.emit(False, f"读取失败：{exc}", {})
            return
        self.sig_test_result.emit(True, "读取成功", values)
