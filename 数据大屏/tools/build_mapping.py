# -*- coding: utf-8 -*-
"""从 TIA 导出的 DB120 SCL 源文件生成地址映射表（JSON / CSV / Markdown）。

布局规则（经现场 db_read 实测验证，S7-1200 非优化块）：
  Bool            : 1 位，按位紧凑排列
  Byte/SInt/USInt : 1 字节，1 字节对齐
  Int/Word/UInt   : 2 字节，2 字节对齐
  Real/DInt/DWord : 2 字节对齐（! 不是 4 字节，这是实测结论）
  Array of Bool   : 从 2 字节边界开始（字对齐，不是字节对齐），按位排列
  Array of 其他   : 元素对齐，长度 = 个数 × 元素长度
  Struct          : 起点 2 字节对齐，长度向上取偶
  字节序          : 大端；Real = IEEE-754 单精度

用法：
  python build_mapping.py [scl路径] [输出目录]
"""
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_SCL = Path(r"D:/GthubPushRes/MES_Demo/各单元数据/通讯数据块/0.MES通讯数据.db")
OUT_DIR = Path(__file__).resolve().parent.parent

SIZES = {"Bool": (0, 0), "Byte": (1, 1), "SInt": (1, 1), "USInt": (1, 1),
         "Int": (2, 2), "Word": (2, 2), "UInt": (2, 2),
         "Real": (4, 2), "DInt": (4, 2), "DWord": (4, 2)}
TZ = timezone(timedelta(hours=8))

# 语义 ID / 中文标签 / 单位 / 小数位 / 是否上屏
SEMANTIC = {
    "一站数据.在线状态": ("s1.online", "PLC 在线状态", "", 0, True),
    "一站数据.运行模式": ("s1.runMode", "运行模式", "", 0, True),
    "一站数据.忙碌状态": ("s1.busy", "忙碌状态", "", 0, True),
    "一站数据.故障状态": ("s1.fault", "故障状态", "", 0, True),
    "一站数据.当前订单ID": ("s1.orderId", "当前订单 ID", "", 0, True),
    "一站数据.当前步骤": ("s1.step", "当前工艺步骤", "", 1, True),
    "一站数据.心跳值": ("s1.heartbeat", "心跳值", "", 0, True),
    "一站数据.一站完成": ("s1.done", "一站完成", "", 0, True),
    "一站数据.一站已接收": ("s1.received", "一站已接收", "", 0, True),
    "一站数据.扫码条码数据": ("s1.scanCode", "扫码条码数据", "", 0, True),
    "一站数据.转盘当前角度": ("s1.turntableAngle", "转盘当前角度", "°", 2, True),
    "一站数据.机械手当前位置": ("s1.robotPos", "机械手当前位置", "mm", 2, True),
    "一站数据.深度检测值": ("s1.depth", "深度检测值", "mm", 3, True),
    "一站数据.料盒使用数": ("s1.boxUsed", "料盒使用数", "", 0, True),
    "一站数据.A料使用数": ("s1.matA", "A 料使用数", "", 0, True),
    "一站数据.B料使用数": ("s1.matB", "B 料使用数", "", 0, True),
    "一站数据.一站保留数据": ("s1.reserved", "一站保留数据", "", 0, False),
    "二站数据.在线状态": ("s2.online", "PLC 在线状态", "", 0, True),
    "二站数据.运行模式": ("s2.runMode", "运行模式", "", 0, True),
    "二站数据.忙碌状态": ("s2.busy", "忙碌状态", "", 0, True),
    "二站数据.故障状态": ("s2.fault", "故障状态", "", 0, True),
    "二站数据.当前订单ID": ("s2.orderId", "当前订单 ID", "", 0, True),
    "二站数据.当前步骤": ("s2.step", "当前工艺步骤", "", 1, True),
    "二站数据.心跳值": ("s2.heartbeat", "心跳值", "", 0, True),
    "二站数据.二站完成": ("s2.done", "二站完成", "", 0, True),
    "二站数据.二站已接收": ("s2.received", "二站已接收", "", 0, True),
    "二站数据.二站扫码数据": ("s2.scanCode", "二站扫码数据", "", 0, True),
    "二站数据.8mm已灌注数量": ("s2.inject8", "8mm 已灌注数量", "颗", 0, True),
    "二站数据.10mm已灌注数量": ("s2.inject10", "10mm 已灌注数量", "颗", 0, True),
    "二站数据.8mml料仓钢珠有无": ("s2.hopper8", "8mm 料仓钢珠有无", "", 0, True),
    "二站数据.10mm料仓钢珠有无": ("s2.hopper10", "10mm 料仓钢珠有无", "", 0, True),
    "二站数据.二站保留数据": ("s2.reserved", "二站保留数据", "", 0, False),
    "三站数据.在线状态": ("s3.online", "PLC 在线状态", "", 0, True),
    "三站数据.运行模式": ("s3.runMode", "运行模式", "", 0, True),
    "三站数据.忙碌状态": ("s3.busy", "忙碌状态", "", 0, True),
    "三站数据.故障状态": ("s3.fault", "故障状态", "", 0, True),
    "三站数据.当前订单ID": ("s3.orderId", "当前订单 ID", "", 0, True),
    "三站数据.当前步骤": ("s3.step", "当前工艺步骤", "", 1, True),
    "三站数据.心跳值": ("s3.heartbeat", "心跳值", "", 0, True),
    "三站数据.三站完成": ("s3.done", "三站完成", "", 0, True),
    "三站数据.三站已接收": ("s3.received", "三站已接收", "", 0, True),
    "三站数据.仓位状态": ("s3.slots", "仓位状态 A~I", "", 0, True),
    "三站数据.入站扫码数据": ("s3.inboundScan", "入站扫码数据", "", 0, True),
    "三站数据.入库扫码数据": ("s3.storageScan", "入库扫码数据", "", 0, True),
    "三站数据.称重数据": ("s3.weight", "称重数据", "g", 0, True),
    "三站数据.产品合格状态": ("s3.qualityState", "产品合格状态", "", 0, True),
    "三站数据.合格产品计数": ("s3.qualifiedCount", "合格产品计数", "", 0, True),
    "三站数据.不合格产品计数": ("s3.unqualifiedCount", "不合格产品计数", "", 0, True),
    "三站数据.X轴当前位置": ("s3.axisX", "X 轴当前位置", "mm", 2, True),
    "三站数据.Y轴当前位置": ("s3.axisY", "Y 轴当前位置", "mm", 2, True),
    "三站数据.完成订单ID": ("s3.completedOrderId", "完成订单ID", "", 0, True),
    "三站数据.三站保留数据": ("s3.reserved", "三站保留数据", "", 0, False),
    "订单数据.订单id": ("order.id", "当前订单 ID", "", 0, True),
    "订单数据.ab物料": ("order.abMaterial", "AB 物料", "", 0, True),
    "订单数据.小钢珠数量": ("order.ball8mmQty", "8mm 钢珠订单数量", "颗", 0, True),
    "订单数据.大钢珠数量": ("order.ball10mmQty", "10mm 钢珠订单数量", "颗", 0, True),
    "订单数据.存储仓位": ("order.slot", "目标存储仓位", "", 0, True),
    "订单数据.当前订单完成": ("order.done", "当前订单完成", "", 0, True),
    "订单数据.开始信号": ("order.startSignal", "订单开始信号", "", 0, True),
    "订单数据.复位信号": ("order.resetSignal", "订单复位信号", "", 0, True),
    "订单数据.订单保留数据": ("order.reserved", "订单保留数据", "", 0, False),
}

GROUP_OF = {"一站数据": "station1", "二站数据": "station2", "三站数据": "station3", "订单数据": "order"}
FIELD_RE = re.compile(r'^\s*("?[^":;]+"?)\s*:\s*(.+?)\s*;?\s*$')
ARRAY_RE = re.compile(r"^Array\s*\[\s*(-?\d+)\s*\.\.\s*(-?\d+)\s*\]\s*of\s+(\w+)$", re.I)


# ------------------------------------------------------------------ 解析
def rebuild(body):
    """按缩进重建 Struct 层级。"""
    root = []
    stack = [(-1, root)]
    for raw in body:
        if not raw.strip():
            continue
        s = raw.strip()
        if re.fullmatch(r"(END_STRUCT;?|STRUCT)", s, re.I):
            continue
        indent = len(raw) - len(raw.lstrip())
        m = FIELD_RE.match(s)
        if not m:
            continue
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        name = m.group(1).strip().strip('"')
        typ = m.group(2).strip().rstrip(";").strip()
        node = {"name": name, "type": typ}
        if re.fullmatch(r"Struct", typ, re.I):
            node["children"] = []
            parent.append(node)
            stack.append((indent, node["children"]))
        else:
            parent.append(node)
    return root


# ------------------------------------------------------------------ 布局
class Cursor:
    def __init__(self):
        self.byte = 0
        self.bit = None

    def flush_bits(self):
        if self.bit is not None:
            self.byte += 1
            self.bit = None

    def align(self, n):
        self.byte += (-self.byte) % n


def walk(nodes, cur: Cursor, prefix="", out=None, warnings=None):
    out = [] if out is None else out
    for n in nodes:
        path = prefix + n["name"]
        if "children" in n:
            cur.flush_bits()
            cur.align(2)
            start = cur.byte
            walk(n["children"], cur, path + ".", out, warnings)
            cur.flush_bits()
            size = cur.byte - start
            if size % 2:
                size += 1
            cur.byte = start + size
            continue
        m = ARRAY_RE.match(n["type"])
        if m:
            low, high, elem = int(m.group(1)), int(m.group(2)), m.group(3)
            cnt = high - low + 1
            if elem.lower() == "bool":
                cur.flush_bits()
                # 非优化块中 Array of Bool 起点按 2 字节（字）对齐：
                # 三站 120.0~120.7 已被 8 个 Bool 占满，字节 121 是填充，数组从 122.0 起。
                # 若按字节对齐会错算成 121.0，导致 9 个仓位灯全读错字节。
                cur.align(2)
                start, sbit = cur.byte, 0
                need = cnt
                while need > 0:
                    take = min(8 - cur.bit if cur.bit is not None else 8, need)
                    if cur.bit is None:
                        cur.bit = 0
                    cur.bit += take
                    need -= take
                    if cur.bit >= 8:
                        cur.byte += 1
                        cur.bit = 0 if need > 0 else None
                cur.flush_bits()
                out.append({"path": path, "type": f"Bool[{cnt}]", "offset": start, "bit": sbit,
                            "bytes": cur.byte - start, "elements": [
                                {"index": low + k, "byte": start + (sbit + k) // 8, "bit": (sbit + k) % 8}
                                for k in range(cnt)], "low": low, "high": high})
            else:
                size, align = SIZES[elem]
                cur.flush_bits()
                cur.align(align)
                out.append({"path": path, "type": f"{elem}[{cnt}]", "offset": cur.byte, "bit": None,
                            "bytes": size * cnt, "elements": [
                                {"index": low + k, "byte": cur.byte + k * size} for k in range(cnt)],
                            "low": low, "high": high})
                cur.byte += size * cnt
            continue
        t = n["type"]
        if t not in SIZES:
            warnings.append(f"未知类型：{path} : {t}")
            continue
        size, align = SIZES[t]
        if t == "Bool":
            if cur.bit is None:
                cur.bit = 0
            if cur.bit >= 8:
                cur.byte += 1
                cur.bit = 0
            out.append({"path": path, "type": "Bool", "offset": cur.byte, "bit": cur.bit,
                        "bytes": 1, "elements": None})
            cur.bit += 1
            if cur.bit >= 8:
                cur.bit = None
                cur.byte += 1
            continue
        cur.flush_bits()
        cur.align(align)
        out.append({"path": path, "type": t, "offset": cur.byte, "bit": None,
                    "bytes": size, "elements": None})
        cur.byte += size
    return out


def main():
    scl = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SCL
    lines = [l.split("//")[0] for l in scl.read_text(encoding="utf-8-sig").splitlines()]
    # 只取第一个顶层 STRUCT 之后、BEGIN 之前的主体
    try:
        start = next(i for i, l in enumerate(lines) if re.fullmatch(r"\s*STRUCT\s*", l, re.I)) + 1
    except StopIteration:
        start = 0
    end = next((i for i, l in enumerate(lines) if l.strip().upper().startswith("BEGIN")), len(lines))
    nodes = rebuild(lines[start:end])
    cur, warns = Cursor(), []
    fields = walk(nodes, cur, "", None, warns)
    cur.flush_bits()
    total = cur.byte + (cur.byte % 2)

    assert not warns, warns
    assert total == 190, f"总长度 {total} 与实测 190 不一致"

    # 交叉校验：用实测值验证关键锚点
    anchors = {"一站数据.当前订单ID": 8, "一站数据.心跳值": 14, "一站数据.扫码条码数据": 18,
               "二站数据.在线状态": 58, "二站数据.当前订单ID": 66, "二站数据.心跳值": 72,
               "三站数据.在线状态": 104, "三站数据.心跳值": 118, "三站数据.仓位状态": 122,
               "三站数据.入站扫码数据": 124, "三站数据.X轴当前位置": 136,
               "订单数据.订单id": 164, "订单数据.当前订单完成": 174, "订单数据.开始信号": 176}
    by_path = {f["path"]: f for f in fields}
    for p, off in anchors.items():
        assert by_path[p]["offset"] == off, f"{p} 偏移 {by_path[p]['offset']} != 实测 {off}"

    out = []
    for f in fields:
        sid, label, unit, dec, show = SEMANTIC.get(f["path"], ("", f["path"].split(".")[-1], "", 0, False))
        grp = GROUP_OF.get(f["path"].split(".")[0], "other")
        out.append({**f, "id": sid, "label": label, "unit": unit, "decimals": dec,
                    "show": show, "group": grp, "rw": "R", "note": ""})

    doc = {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(TZ).isoformat(timespec="seconds"),
        "dbNumber": 120,
        "blockName": "0.MES通讯数据",
        "sourceExport": scl.name,
        "totalBytes": total,
        "byteOrder": "BigEndian",
        "layout": {"bool": "bit", "int": 2, "dint": 2, "real": 2, "struct": 2,
                   "arrayOfBool": "2-byte aligned start (word aligned, not byte aligned)"},
        "verification": {
            "plc": "192.168.40.115", "rack": 0, "slot": 1,
            "method": "snap7 db_read(120,0,190) 现场实测",
            "maxReadableBytes": 190,
            "probeResult": "190 OK / 191 FAIL(0x05 Address out of range)",
            "cpuStateAtProbe": "STOP",
            "anchors": anchors,
        },
        "fields": out,
    }

    cfg_dir = OUT_DIR / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "db120.mapping.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    docs = OUT_DIR / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    with (docs / "DB120地址映射表.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["序号", "区域", "变量名", "类型", "偏移", "位", "字节数", "语义ID", "界面用途", "读写", "备注"])
        for i, f in enumerate(out, 1):
            addr = f"{f['offset']}.{f['bit']}" if f["bit"] is not None else f"{f['offset']}.0"
            w.writerow([i, f["path"].split(".")[0], f["path"], f["type"], addr,
                        "" if f["bit"] is None else f["bit"], f["bytes"], f["id"],
                        "上屏" if f["show"] else "仅存档", f["rw"],
                        "数组起始" if f["elements"] else ""])

    print(f"总长度 {total} 字节，字段 {len(out)} 个，锚点校验全部通过")
    for f in out:
        addr = f"{f['offset']}.{f['bit']}" if f["bit"] is not None else f"{f['offset']}.0"
        print(f"  {addr:>4}  {f['bytes']:>2}B  {f['type']:<16} {f['path']}")


if __name__ == "__main__":
    main()
