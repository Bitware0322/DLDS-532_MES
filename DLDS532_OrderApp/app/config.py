"""应用配置：PLC 连接参数 + DB121 变量映射，保存为 JSON。"""
from __future__ import annotations

import ipaddress
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .model import DEFAULT_VARIABLES, V_AB, V_ACKED, V_DONE, V_DONE_ID, V_HEARTBEAT, \
    V_ORDER_ID, V_QTY8, V_QTY10, V_READY, V_REQ, V_SLOT, VarDef

APP_NAME = "DLDS532_OrderApp"
APP_TITLE = "DLDS-532 下单终端"
APP_VERSION = "1.1.0"

# 关闭软件时的订单处理策略
RETENTION_KEEP = "keep"              # 保留全部，重启后继续跟踪在制订单
RETENTION_UNFINISHED = "unfinished"  # 关闭时把未完成订单标记为中断，保留历史
RETENTION_CLEAR = "clear"            # 关闭时清空全部订单记录
RETENTION_TEXT = {
    RETENTION_KEEP: "保留订单记录，重启后继续跟踪",
    RETENTION_UNFINISHED: "关闭时清除未完成订单（保留已完成历史）",
    RETENTION_CLEAR: "关闭时清空全部订单记录",
}


# ---------------------------------------------------------------- 目录
def _base_dir() -> Path:
    """程序所在目录（打包后为 exe 目录）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """数据目录：exe 目录存在 portable.flag 时用便携模式，否则用 LOCALAPPDATA。"""
    base = _base_dir()
    if (base / "portable.flag").exists():
        path = base / "data"
    else:
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
        path = Path(root) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


CONFIG_FILE = "config.json"
DB_FILE = "orders.db"


def config_path() -> Path:
    return data_dir() / CONFIG_FILE


def db_path() -> Path:
    return data_dir() / DB_FILE


# ---------------------------------------------------------------- 配置
@dataclass
class AppConfig:
    # 连接参数
    ip: str = "192.168.40.115"
    port: int = 102
    rack: int = 0
    slot: int = 1
    db_number: int = 121
    # 通信参数
    poll_ms: int = 300
    timeout_ms: int = 3000
    ack_timeout_s: int = 30          # MES下单请求 -> PLC订单已下发 的确认超时
    produce_alarm_min: int = 0       # 生产超时报警（分钟，0=不报警）
    simulate: bool = False           # 内置模拟 PLC（无硬件联调用）
    sim_duration_s: int = 10         # 模拟模式单件生产耗时
    bit_write_mode: str = "auto"     # auto=按位写；rmw=读改写整字节
    retention: str = RETENTION_KEEP  # 关闭软件时的订单处理策略
    variables: list[VarDef] = field(default_factory=list)

    # -------------------------------------------------- 构造
    def __post_init__(self) -> None:
        if not self.variables:
            self.variables = default_variables()

    # -------------------------------------------------- 变量访问
    def var(self, name: str) -> VarDef:
        for item in self.variables:
            if item.name == name:
                return item
        # 缺变量时返回一个不可能命中的占位，避免 None 判断散落各处
        return VarDef(name, "INT", "0")

    def has_var(self, name: str) -> bool:
        return any(item.name == name for item in self.variables)

    def names(self) -> list[str]:
        return [item.name for item in self.variables]

    # -------------------------------------------------- 读写窗口
    def read_window(self) -> tuple[int, int]:
        """把全部变量包在一个连续块里，一次读出，减少通信次数。"""
        starts, ends = [], []
        for item in self.variables:
            size = 1 if item.dtype == "BOOL" else item.size
            starts.append(item.byte)
            ends.append(item.byte + size)
        start = min(starts)
        size = max(ends) - start
        # S7 单次读取上限 2048 字节，实际远小于此；这里做一次保护
        if size > 512:
            raise ValueError(f"变量地址跨度 {size} 字节过大，请检查偏移设置")
        return start, size

    def getpoints(self) -> list[tuple[str, str, str]]:
        return [(v.name, v.dtype, str(v.offset)) for v in self.variables]

    # -------------------------------------------------- 序列化
    def to_dict(self) -> dict[str, Any]:
        return {
            "ip": self.ip, "port": self.port, "rack": self.rack, "slot": self.slot,
            "db_number": self.db_number,
            "poll_ms": self.poll_ms, "timeout_ms": self.timeout_ms,
            "ack_timeout_s": self.ack_timeout_s,
            "produce_alarm_min": self.produce_alarm_min,
            "simulate": self.simulate, "sim_duration_s": self.sim_duration_s,
            "bit_write_mode": self.bit_write_mode,
            "retention": self.retention,
            "variables": [v.to_dict() for v in self.variables],
        }

    def copy(self) -> "AppConfig":
        return AppConfig.from_dict(self.to_dict())

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "AppConfig":
        cfg = AppConfig()
        cfg.ip = str(data.get("ip", cfg.ip))
        cfg.port = int(data.get("port", cfg.port))
        cfg.rack = int(data.get("rack", cfg.rack))
        cfg.slot = int(data.get("slot", cfg.slot))
        cfg.db_number = int(data.get("db_number", cfg.db_number))
        cfg.poll_ms = int(data.get("poll_ms", cfg.poll_ms))
        cfg.timeout_ms = int(data.get("timeout_ms", cfg.timeout_ms))
        cfg.ack_timeout_s = int(data.get("ack_timeout_s", cfg.ack_timeout_s))
        cfg.produce_alarm_min = int(data.get("produce_alarm_min", cfg.produce_alarm_min))
        cfg.simulate = bool(data.get("simulate", cfg.simulate))
        cfg.sim_duration_s = int(data.get("sim_duration_s", cfg.sim_duration_s))
        cfg.bit_write_mode = str(data.get("bit_write_mode", cfg.bit_write_mode))
        cfg.retention = str(data.get("retention", cfg.retention))
        if cfg.retention not in RETENTION_TEXT:
            cfg.retention = RETENTION_KEEP

        raw_vars = data.get("variables")
        if isinstance(raw_vars, list) and raw_vars:
            merged: dict[str, VarDef] = {}
            for item in raw_vars:
                if isinstance(item, dict) and item.get("name"):
                    merged[str(item["name"])] = VarDef.from_dict(item)
            # 以默认变量顺序为准，保证设置页顺序稳定；新增变量追加在后面
            ordered = [merged.pop(name, VarDef(name, dtype, off))
                       for name, dtype, off in DEFAULT_VARIABLES]
            ordered.extend(merged.values())
            cfg.variables = ordered
        return cfg

    # -------------------------------------------------- 校验
    def validate(self) -> list[str]:
        """返回错误列表，空列表表示通过。"""
        errors: list[str] = []
        try:
            ipaddress.IPv4Address(self.ip)
        except ValueError:
            errors.append(f"IP 地址不合法：{self.ip}")
        if not 1 <= self.port <= 65535:
            errors.append("端口需在 1-65535 之间")
        if not 0 <= self.rack <= 7:
            errors.append("机架号需在 0-7 之间")
        if not 0 <= self.slot <= 31:
            errors.append("插槽号需在 0-31 之间")
        if not 1 <= self.db_number <= 65535:
            errors.append("DB 块号需在 1-65535 之间")
        if not 50 <= self.poll_ms <= 10000:
            errors.append("轮询周期需在 50-10000 毫秒之间")
        if not 200 <= self.timeout_ms <= 30000:
            errors.append("通信超时需在 200-30000 毫秒之间")
        if not 1 <= self.ack_timeout_s <= 3600:
            errors.append("下单确认超时需在 1-3600 秒之间")
        if self.produce_alarm_min < 0:
            errors.append("生产超时报警不能为负数")
        if self.retention not in RETENTION_TEXT:
            errors.append(f"退出保留策略不合法：{self.retention}")

        # 变量地址
        spans: list[tuple[int, int, str]] = []
        bit_slots: dict[tuple[int, int], str] = {}
        for item in self.variables:
            if item.dtype not in ("BOOL", "BYTE", "INT", "WORD", "DINT", "REAL"):
                errors.append(f"“{item.name}”的数据类型不支持：{item.dtype}")
                continue
            try:
                byte = item.byte
                bit = item.bit
            except ValueError:
                errors.append(f"“{item.name}”的偏移地址无法解析：{item.offset}")
                continue
            if not 0 <= byte <= 65534:
                errors.append(f"“{item.name}”偏移超出范围：{byte}")
                continue
            if item.dtype == "BOOL":
                if not 0 <= bit <= 7:
                    errors.append(f"“{item.name}”位号需在 0-7 之间：{item.offset}")
                    continue
                key = (byte, bit)
                if key in bit_slots:
                    errors.append(f"“{item.name}”与“{bit_slots[key]}”占用同一位 {byte}.{bit}")
                else:
                    bit_slots[key] = item.name
                spans.append((byte, byte + 1, item.name))
            else:
                if "." in str(item.offset):
                    errors.append(f"“{item.name}”为 {item.dtype} 类型，偏移不应带位号")
                spans.append((byte, byte + item.size, item.name))
                if item.byte + item.size > 65535:
                    errors.append(f"“{item.name}”超出 DB 末尾")

        for i, (s1, e1, n1) in enumerate(spans):
            for s2, e2, n2 in spans[i + 1:]:
                if n1 == n2:
                    continue
                if s1 < e2 and s2 < e1:
                    # 仅当两者都不是位（位共享同一字节是允许的）
                    v1 = self.var(n1)
                    v2 = self.var(n2)
                    if v1.dtype == "BOOL" and v2.dtype == "BOOL" and v1.byte == v2.byte:
                        continue
                    errors.append(f"“{n1}”与“{n2}”地址重叠（{s1}-{e1} / {s2}-{e2}）")

        # 关键变量必须存在
        for required in (V_ORDER_ID, V_REQ, V_ACKED, V_READY, V_DONE, V_DONE_ID):
            if not self.has_var(required):
                errors.append(f"缺少必需变量：{required}")
        if not self.has_var(V_HEARTBEAT):
            errors.append(f"缺少必需变量：{V_HEARTBEAT}")

        # 类型合理性：数值变量不能是 BOOL，信号位必须是 BOOL
        for name in (V_ORDER_ID, V_AB, V_QTY8, V_QTY10, V_SLOT, V_HEARTBEAT, V_DONE_ID):
            if self.has_var(name) and self.var(name).dtype == "BOOL":
                errors.append(f"“{name}”是数值变量，类型不能选 BOOL")
        for name in (V_REQ, V_ACKED, V_READY, V_DONE):
            if self.has_var(name) and self.var(name).dtype != "BOOL":
                errors.append(f"“{name}”是信号位，类型必须为 BOOL")

        # 地址跨度检查（一次读取需覆盖全部变量）
        if not errors:
            try:
                self.read_window()
            except ValueError as exc:
                errors.append(str(exc))
        return errors

    def save(self, path: Path | None = None) -> Path:
        target = path or config_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
        return target

    @staticmethod
    def load(path: Path | None = None) -> "AppConfig":
        target = path or config_path()
        if not target.exists():
            cfg = AppConfig()
            try:
                cfg.save(target)
            except OSError:
                pass
            return cfg
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("配置格式不是对象")
            return AppConfig.from_dict(data)
        except (OSError, ValueError, json.JSONDecodeError):
            # 配置损坏时回退默认值，不阻塞启动
            return AppConfig()


def default_variables() -> list[VarDef]:
    return [VarDef(n, t, o) for n, t, o in DEFAULT_VARIABLES]
