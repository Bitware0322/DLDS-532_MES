"""数据模型：变量定义、PLC 快照、订单。

这里只放与 UI / 通信实现无关的纯数据定义，便于单测复用。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------- 订单状态
ST_PENDING = "PENDING"
ST_PRODUCING = "PRODUCING"
ST_DONE = "DONE"
ST_FAILED = "FAILED"

STATUS_TEXT = {
    ST_PENDING: "待下单",
    ST_PRODUCING: "正在生产",
    ST_DONE: "已完成",
    ST_FAILED: "下单失败",
}

# 状态对应的文字颜色（浅色主题）
STATUS_COLOR = {
    ST_PENDING: "#2563eb",
    ST_PRODUCING: "#d97706",
    ST_DONE: "#15803d",
    ST_FAILED: "#dc2626",
}

# ---------------------------------------------------------------- 变量类型
# BOOL 走位地址，size 记 0 表示不占整字节
TYPE_SIZES: dict[str, int] = {
    "BOOL": 0,
    "BYTE": 1,
    "INT": 2,
    "WORD": 2,
    "DINT": 4,
    "REAL": 4,
}

# DB121 默认变量映射（与现场 TIA 非优化 DB121 一致）
DEFAULT_VARIABLES: list[tuple[str, str, str]] = [
    ("订单ID", "INT", "0"),
    ("AB物料", "INT", "2"),
    ("8mm钢珠数量", "INT", "4"),
    ("10mm钢珠数量", "INT", "6"),
    ("存储仓位", "INT", "8"),
    ("PLC通讯心跳", "INT", "10"),
    ("MES下单请求", "BOOL", "12.0"),
    ("PLC订单已下发", "BOOL", "12.1"),
    ("产线可接单", "BOOL", "12.2"),
    ("订单已完成", "BOOL", "12.3"),
    ("完成订单ID", "INT", "14"),
]

# 变量名常量，避免代码里裸写中文
V_ORDER_ID = "订单ID"
V_AB = "AB物料"
V_QTY8 = "8mm钢珠数量"
V_QTY10 = "10mm钢珠数量"
V_SLOT = "存储仓位"
V_HEARTBEAT = "PLC通讯心跳"
V_REQ = "MES下单请求"
V_ACKED = "PLC订单已下发"
V_READY = "产线可接单"
V_DONE = "订单已完成"
V_DONE_ID = "完成订单ID"


@dataclass(frozen=True)
class VarDef:
    """单个 PLC 变量的映射定义。offset 保存原始文本，例如 '12.0' / '0'。"""

    name: str
    dtype: str
    offset: str

    # -------------------------------------------------- 地址解析
    @property
    def byte(self) -> int:
        text = str(self.offset).strip()
        if not text:
            raise ValueError(f"变量“{self.name}”未填写偏移地址")
        if "." in text:
            head, _, tail = text.partition(".")
            return int(head)
        return int(text)

    @property
    def bit(self) -> int:
        text = str(self.offset).strip()
        if "." in text:
            _, _, tail = text.partition(".")
            return int(tail)
        return 0

    @property
    def size(self) -> int:
        return TYPE_SIZES.get(self.dtype, 2)

    @property
    def bit_count(self) -> int:
        return 8 if self.dtype == "BOOL" else 0

    def address_text(self) -> str:
        return f"DBX{self.byte}.{self.bit}" if self.dtype == "BOOL" else f"DBB{self.byte}"

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "dtype": self.dtype, "offset": str(self.offset)}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "VarDef":
        return VarDef(str(data.get("name", "")), str(data.get("dtype", "INT")),
                      str(data.get("offset", "0")))


@dataclass
class PlcSnapshot:
    """一次轮询读回的完整状态。"""

    connected: bool
    ts: float = field(default_factory=time.time)
    values: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    heartbeat_age: float = 0.0        # 心跳值多久没变化（秒）
    used_bit_write: str = ""

    # 便捷读取：通信中断时返回安全默认值
    def i(self, name: str) -> int:
        v = self.values.get(name, 0)
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    def b(self, name: str) -> bool:
        return bool(self.values.get(name, False))

    @property
    def ok(self) -> bool:
        return self.connected and not self.error
