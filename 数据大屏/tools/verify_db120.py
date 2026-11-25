# -*- coding: utf-8 -*-
"""按 config/db120.mapping.json 解码 DB120 实时数据（只读）。

用法：
  python tools/verify_db120.py [IP]

用途：阶段一地址映射表验证 / 阶段三通信联调。全程只执行 db_read，不写 PLC。
"""
from __future__ import annotations

import json
import struct
import sys
import time
from pathlib import Path

import snap7

ROOT = Path(__file__).resolve().parent.parent
MAPPING = ROOT / "config" / "db120.mapping.json"


def load_fields():
    doc = json.loads(MAPPING.read_text(encoding="utf-8"))
    return doc, doc["fields"], doc["totalBytes"]


def decode(raw: bytes, f: dict):
    off, typ = f["offset"], f["type"]
    if typ == "Int":
        return int.from_bytes(raw[off:off + 2], "big", signed=True)
    if typ == "Real":
        return round(struct.unpack(">f", raw[off:off + 4])[0], 4)
    if typ == "Bool":
        return bool((raw[off] >> f["bit"]) & 1)
    if typ.startswith("Bool["):
        return [bool((raw[e["byte"]] >> e["bit"]) & 1) for e in f["elements"]]
    if typ.startswith("Int["):
        return [int.from_bytes(raw[e["byte"]:e["byte"] + 2], "big", signed=True) for e in f["elements"]]
    return None


def fmt(v):
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, list):
        return "[" + ", ".join(("1" if x is True else "0" if x is False else str(x)) for x in v) + "]"
    return str(v)


RUNMODE = {0: "手动", 1: "自动待机", 2: "自动运行"}
AB = {1: "A 料", 2: "B 料", 3: "不需要"}
SLOT_NAME = "ABCDEFGHI"


def main():
    ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.40.115"
    doc, fields, total = load_fields()

    cli = snap7.client.Client()
    cli.connect(ip, 0, 1, 102)
    print(f"连接 {ip}  CPU={cli.get_cpu_state()}  读取 DB{doc['dbNumber']} 0..{total - 1}\n")

    def snapshot():
        return cli.db_read(doc["dbNumber"], 0, total)

    raw = snapshot()
    vals = {f["id"]: decode(raw, f) for f in fields if f["id"]}

    print("── 数据管理 / 通信 ─────────────────────────────")
    print(f"  DB120 长度        : {total} B（映射表）")
    print(f"  一站 心跳         : {vals['s1.heartbeat']}")
    print(f"  二站 心跳         : {vals['s2.heartbeat']}")
    print(f"  三站 心跳         : {vals['s3.heartbeat']}")

    for st, key in (("一站 自动供料", "s1"), ("二站 智能分拣", "s2"), ("三站 智能仓储", "s3")):
        print(f"\n── {st} ─────────────────────────────")
        print(f"  在线状态={vals[key + '.online']}  运行模式={RUNMODE.get(vals[key + '.runMode'], vals[key + '.runMode'])}"
              f"  忙碌={vals[key + '.busy']}  故障码={vals[key + '.fault']}")
        print(f"  订单ID={vals[key + '.orderId']}  步骤={vals[key + '.step']:.2f}"
              f"  完成={fmt(vals[key + '.done'])}  已接收={fmt(vals[key + '.received'])}")

    print("\n── 一站工艺量 ─────────────────────────────")
    print(f"  扫码={vals['s1.scanCode']}  转盘角度={vals['s1.turntableAngle']:.2f}°"
          f"  机械手={vals['s1.robotPos']:.2f}mm  深度={vals['s1.depth']:.3f}mm")
    print(f"  料盒={vals['s1.boxUsed']}  A料={vals['s1.matA']}  B料={vals['s1.matB']}")

    print("\n── 二站工艺量 ─────────────────────────────")
    print(f"  扫码={vals['s2.scanCode']}  8mm灌注={vals['s2.inject8']}  10mm灌注={vals['s2.inject10']}")
    print(f"  8mm料仓={fmt(vals['s2.hopper8'])}  10mm料仓={fmt(vals['s2.hopper10'])}")

    print("\n── 三站工艺量 ─────────────────────────────")
    print(f"  入站扫码={vals['s3.inboundScan']}  入库扫码={vals['s3.storageScan']}  称重={vals['s3.weight']}g")
    print(f"  合格状态={vals['s3.qualityState']}  合格={vals['s3.qualifiedCount']}  不合格={vals['s3.unqualifiedCount']}")
    print(f"  X={vals['s3.axisX']:.2f}mm  Y={vals['s3.axisY']:.2f}mm")
    slots = vals["s3.slots"]
    print("  仓位: " + "  ".join(f"{SLOT_NAME[i]}={'占用' if slots[i] else '空'}" for i in range(9)))

    print("\n── 订单区 ─────────────────────────────")
    print(f"  订单ID={vals['order.id']}  物料={AB.get(vals['order.abMaterial'], vals['order.abMaterial'])}"
          f"  8mm={vals['order.ball8mmQty']}  10mm={vals['order.ball10mmQty']}"
          f"  目标仓位={vals['order.slot']}")
    print(f"  当前订单完成={fmt(vals['order.done'])}  开始信号={vals['order.startSignal']}"
          f"  复位信号={vals['order.resetSignal']}")

    time.sleep(1.5)
    raw2 = snapshot()
    v2 = {f["id"]: decode(raw2, f) for f in fields if f["id"]}
    print("\n── 心跳增量（1.5s 后） ─────────────────────────────")
    for key in ("s1", "s2", "s3"):
        a, b = vals[key + ".heartbeat"], v2[key + ".heartbeat"]
        print(f"  {key}: {a} -> {b}  ({'刷新中' if a != b else '未变化 / CPU STOP'})")

    cli.disconnect()


if __name__ == "__main__":
    main()
