"""PLC 通信层。

两种实现，接口完全一致：
  * Snap7Transport  —— 真实的 S7 TCP 通信（python-snap7）
  * SimulatedPlc    —— 内置 PLC 行为模拟，用于无硬件时验证下单流程

上层（PlcWorker / OrderService）只依赖 Transport 接口，因此模拟模式跑通的流程
与现场接 PLC 的流程是同一条代码路径。
"""
from __future__ import annotations

import struct
import threading
import time
from typing import Any

from .config import AppConfig
from .model import V_ACKED, V_DONE, V_DONE_ID, V_HEARTBEAT, V_ORDER_ID, V_READY, V_REQ


class TransportError(RuntimeError):
    """通信异常（连接失败、读写失败、超时）。"""


# ---------------------------------------------------------------- 编解码
def decode_block(data: bytes, base: int, cfg: AppConfig) -> dict[str, Any]:
    """把读回的连续字节块按变量表解析成字典。"""
    values: dict[str, Any] = {}
    for item in cfg.variables:
        off = item.byte - base
        try:
            if item.dtype == "BOOL":
                byte_val = data[off]
                values[item.name] = bool(byte_val & (1 << item.bit))
            elif item.dtype == "INT":
                values[item.name] = struct.unpack_from(">h", data, off)[0]
            elif item.dtype == "WORD":
                values[item.name] = struct.unpack_from(">H", data, off)[0]
            elif item.dtype == "DINT":
                values[item.name] = struct.unpack_from(">i", data, off)[0]
            elif item.dtype == "REAL":
                values[item.name] = round(struct.unpack_from(">f", data, off)[0], 4)
            elif item.dtype == "BYTE":
                values[item.name] = data[off]
        except (IndexError, struct.error):
            values[item.name] = False if item.dtype == "BOOL" else 0
    return values


def encode_value(dtype: str, value: Any) -> bytes:
    if dtype == "INT":
        return struct.pack(">h", int(value))
    if dtype == "WORD":
        return struct.pack(">H", int(value) & 0xFFFF)
    if dtype == "DINT":
        return struct.pack(">i", int(value))
    if dtype == "REAL":
        return struct.pack(">f", float(value))
    if dtype == "BYTE":
        return bytes([int(value) & 0xFF])
    raise ValueError(f"不支持的类型：{dtype}")


def clamp_int16(value: int) -> int:
    return max(-32768, min(32767, int(value)))


# ---------------------------------------------------------------- 真实 PLC
class Snap7Transport:
    kind = "snap7"

    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self._client = None
        self._bit_mode = "auto" if cfg.bit_write_mode != "rmw" else "rmw"
        self.last_write_mode = ""

    # -------------------------------------------------- 连接
    def connect(self) -> None:
        try:
            import snap7
        except ImportError as exc:  # pragma: no cover - 环境缺失时的明确提示
            raise TransportError("缺少 python-snap7 库，请先执行 pip install python-snap7") from exc

        if self._client is not None:
            self.disconnect()

        client = snap7.client.Client()
        cfg = self.cfg
        # 通信超时（不同版本参数不同，失败不影响连接）
        for setter in (
            lambda: client.set_param(snap7.type.Parameter.SendTimeout, cfg.timeout_ms),
            lambda: client.set_param(snap7.type.Parameter.RecvTimeout, cfg.timeout_ms),
            lambda: client.set_param(snap7.type.Parameter.PingTimeout, 500),
        ):
            try:
                setter()
            except Exception:  # noqa: BLE001 - 兼容不同 python-snap7 版本
                pass

        try:
            try:
                client.connect(cfg.ip, cfg.rack, cfg.slot, cfg.port)
            except TypeError:
                # python-snap7 1.x 需要先设置连接参数
                client.set_connection_params(cfg.ip, cfg.rack, cfg.slot, cfg.port)
                client.connect()
        except Exception as exc:  # noqa: BLE001 - snap7 抛出的是通用异常
            try:
                client.destroy()
            except Exception:  # noqa: BLE001
                pass
            raise TransportError(f"连接 {cfg.ip}:{cfg.port} 失败：{exc}") from exc

        self._client = client
        if not self._ping():
            self.disconnect()
            raise TransportError(f"连接 {cfg.ip}:{cfg.port} 失败：握手未通过")

    def _ping(self) -> bool:
        try:
            return bool(self._client.get_connected())
        except Exception:  # noqa: BLE001
            return False

    def disconnect(self) -> None:
        client, self._client = self._client, None
        if client is None:
            return
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        try:
            client.destroy()
        except Exception:  # noqa: BLE001
            pass

    def connected(self) -> bool:
        return self._client is not None and self._ping()

    # -------------------------------------------------- 读
    def read(self, start: int, size: int) -> bytes:
        if self._client is None:
            raise TransportError("尚未连接 PLC")
        try:
            data = self._client.db_read(self.cfg.db_number, start, size)
        except Exception as exc:  # noqa: BLE001
            raise TransportError(f"读取 DB{self.cfg.db_number} 偏移 {start} 长度 {size} 失败：{exc}") from exc
        return bytes(data)

    # -------------------------------------------------- 写
    def write_int(self, byte_off: int, dtype: str, value: Any) -> None:
        if self._client is None:
            raise TransportError("尚未连接 PLC")
        payload = encode_value(dtype, value)
        try:
            self._client.db_write(self.cfg.db_number, byte_off, bytearray(payload))
        except Exception as exc:  # noqa: BLE001
            raise TransportError(f"写入 DB{self.cfg.db_number}.DBB{byte_off} 失败：{exc}") from exc

    def write_bits(self, items: list[tuple[int, int, bool]]) -> str:
        """按位写入，不影响同一字节内由 PLC 维护的其他位。

        优先使用 S7 多变量写入的 BIT 类型（真正的单 bit 写）；
        若固件/库不支持，退回“读字节-改位-写字节”，并记录使用方式。
        """
        if self._client is None:
            raise TransportError("尚未连接 PLC")
        if self._bit_mode == "auto":
            try:
                self._write_bits_multi(items)
                self.last_write_mode = "bit"
                return "bit"
            except Exception as exc:  # noqa: BLE001
                self._bit_mode = "rmw"
                self.last_write_mode = f"rmw（按位写不可用：{exc}）"
        self._write_bits_rmw(items)
        return self.last_write_mode or "rmw"

    def _write_bits_multi(self, items: list[tuple[int, int, bool]]) -> None:
        """真正的单 bit 写入：S7 位地址 = 字节*8 + 位号，不会影响同字节内 PLC 维护的其他位。"""
        from snap7.type import Areas, WordLen
        for byte, bit, value in items:
            self._client.write_area(Areas.DB, self.cfg.db_number, byte * 8 + bit,
                                    bytearray([1 if value else 0]), WordLen.Bit)

    def _write_bits_rmw(self, items: list[tuple[int, int, bool]]) -> None:
        """按字节分组，逐个字节读-改-写（存在极小的覆盖窗口，仅作兼容后备）。"""
        groups: dict[int, list[tuple[int, bool]]] = {}
        for byte, bit, value in items:
            groups.setdefault(byte, []).append((bit, value))
        for byte, bits in groups.items():
            current = bytearray(self.read(byte, 1))
            for bit, value in bits:
                if value:
                    current[0] |= (1 << bit)
                else:
                    current[0] &= ~(1 << bit) & 0xFF
            self._client.db_write(self.cfg.db_number, byte, current)


# ---------------------------------------------------------------- 模拟 PLC
class SimulatedPlc:
    """内置模拟 PLC：完整复现 DB121 的握手时序。

    idle → (MES下单请求=1 且 产线可接单=1) 锁存参数、产线可接单=0
         → 0.5s 后 PLC订单已下发=1
         → 生产 sim_duration_s 秒 → 订单已完成=1、完成订单ID=订单ID
         → MES 清除 订单已完成/PLC订单已下发 后 产线可接单=1，回到 idle
    """

    kind = "simulated"

    def __init__(self, cfg: AppConfig, log_cb=None) -> None:
        self.cfg = cfg
        self._log = log_cb or (lambda msg, level="info": None)
        self._mem = bytearray(128)
        self._lock = threading.RLock()
        self._state = "idle"
        self._t_mark = 0.0
        self._latched_id = 0
        self._ack_delay = 0.5
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._hb = 0
        self._t_hb = time.time()
        self._inited = False
        self.block_ack = False          # 置 True 可验证“下单确认超时”分支
        self.last_write_mode = "sim"

    # -------------------------------------------------- 接口
    def connect(self) -> None:
        with self._lock:
            if not self._inited:
                self._reset_memory()
                self._inited = True
                self._hb = 0
                self._state = "idle"
                self._t_mark = time.time()
                self._set_bit(V_READY, True)
            self._t_hb = time.time()
        self._stop.clear()
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, name="SimPlc", daemon=True)
            self._thread.start()
        self._log("模拟 PLC 已启动（该模式下不访问真实设备）", "warn")

    def disconnect(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=1.5)

    def connected(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def read(self, start: int, size: int) -> bytes:
        if not self.connected():
            raise TransportError("模拟 PLC 未启动")
        with self._lock:
            return bytes(self._mem[start:start + size])

    def write_int(self, byte_off: int, dtype: str, value: Any) -> None:
        payload = encode_value(dtype, value)
        with self._lock:
            self._mem[byte_off:byte_off + len(payload)] = payload
        self.last_write_mode = "sim"

    def write_bits(self, items: list[tuple[int, int, bool]]) -> str:
        with self._lock:
            for byte, bit, value in items:
                mask = 1 << bit
                if value:
                    self._mem[byte] |= mask
                else:
                    self._mem[byte] &= ~mask & 0xFF
        self.last_write_mode = "sim"
        return "sim"

    # -------------------------------------------------- 内部控制
    def _reset_memory(self) -> None:
        for item in self.cfg.variables:
            try:
                size = 1 if item.dtype == "BOOL" else item.size
                self._mem[item.byte:item.byte + size] = b"\x00" * size
            except (ValueError, IndexError):
                continue

    def _get_int(self, name: str) -> int:
        item = self.cfg.var(name)
        try:
            return struct.unpack_from(">h", self._mem, item.byte)[0]
        except (struct.error, ValueError):
            return 0

    def _get_bit(self, name: str) -> bool:
        item = self.cfg.var(name)
        try:
            return bool(self._mem[item.byte] & (1 << item.bit))
        except (IndexError, ValueError):
            return False

    def _set_bit(self, name: str, value: bool) -> None:
        item = self.cfg.var(name)
        try:
            mask = 1 << item.bit
            if value:
                self._mem[item.byte] |= mask
            else:
                self._mem[item.byte] &= ~mask & 0xFF
        except (IndexError, ValueError):
            pass

    def _set_int(self, name: str, value: int) -> None:
        item = self.cfg.var(name)
        try:
            struct.pack_into(">h", self._mem, item.byte, clamp_int16(value))
        except (struct.error, ValueError):
            pass

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as exc:  # noqa: BLE001 - 模拟线程不允许中断
                self._log(f"模拟 PLC 内部异常：{exc}", "error")
            self._stop.wait(0.1)

    def _tick(self) -> None:
        now = time.time()
        with self._lock:
            # 心跳：PLC 自己维护，每秒 +1
            if now - self._t_hb >= 1.0:
                self._t_hb = now
                self._hb = (self._hb + 1) % 32000
                self._set_int(V_HEARTBEAT, self._hb)

            req = self._get_bit(V_REQ)
            ready = self._get_bit(V_READY)
            acked = self._get_bit(V_ACKED)
            done = self._get_bit(V_DONE)

            if self._state == "idle":
                if req and ready and not done:
                    self._latched_id = self._get_int(V_ORDER_ID)
                    self._state = "accepted"
                    self._t_mark = now
                    self._set_bit(V_READY, False)
                    self._set_bit(V_ACKED, False)
                    self._log(f"模拟 PLC：收到订单 {self._latched_id}，开始校验", "info")

            elif self._state == "accepted":
                if self.block_ack:
                    return
                if not req:
                    # MES 在确认前撤销了请求：PLC 放弃接单，回到空闲
                    self._state = "idle"
                    self._set_bit(V_READY, True)
                    self._log(f"模拟 PLC：订单 {self._latched_id} 的下单请求被撤销，未接单", "warn")
                    return
                if now - self._t_mark >= self._ack_delay:
                    self._set_bit(V_ACKED, True)
                    self._state = "producing"
                    self._t_mark = now
                    self._log(f"模拟 PLC：订单 {self._latched_id} 已下发，开始生产", "info")

            elif self._state == "producing":
                if now - self._t_mark >= max(2, self.cfg.sim_duration_s):
                    self._set_int(V_DONE_ID, self._latched_id)
                    self._set_bit(V_DONE, True)
                    self._state = "done"
                    self._log(f"模拟 PLC：订单 {self._latched_id} 生产完成", "info")

            elif self._state == "done":
                # MES 清除 订单已完成 + PLC订单已下发 后才恢复可接单
                if not done and not acked:
                    self._state = "idle"
                    self._set_bit(V_READY, True)
                    self._log("模拟 PLC：握手已复位，产线可接单", "info")
