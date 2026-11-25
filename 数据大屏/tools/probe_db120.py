# -*- coding: utf-8 -*-
"""DB120 现场只读探测：确认可读长度、原始字节、候选布局自洽性。
只执行 db_read，不写任何数据。
"""
import struct
import sys

import snap7

IP = "192.168.40.115"
RACK, SLOT = 0, 1

c = snap7.client.Client()
c.connect(IP, RACK, SLOT, 102)
print("connected:", c.get_connected(), "cpu:", c.get_cpu_state())


def try_read(db, start, size):
    try:
        return c.db_read(db, start, size), None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


print("\n=== DB120 最大可读长度探测 ===")
for n in (188, 190, 191, 192, 194, 198, 200, 206):
    data, err = try_read(120, 0, n)
    print(f"  len={n:<4} {'OK' if data else 'FAIL ' + err}")

raw, err = try_read(120, 0, 190)
if raw is None:
    print("DB120 read failed:", err)
    sys.exit(1)

print("\n=== DB120 raw (0..189) ===")
for i in range(0, 190, 16):
    chunk = raw[i:i + 16]
    hexs = " ".join(f"{b:02X}" for b in chunk)
    print(f"  {i:>3}: {hexs}")

print("\n=== 按 Int(2B,大端有符号) 扫描 ===")
for off in range(0, 190, 2):
    v = int.from_bytes(raw[off:off + 2], "big", signed=True)
    print(f"  [{off:>3}] Int = {v}")

print("\n=== 按 Real(4B,大端 IEEE754, 4字节对齐) 扫描 ===")
for off in range(0, 188, 4):
    f = struct.unpack(">f", raw[off:off + 4])[0]
    print(f"  [{off:>3}] Real = {f!r}")

print("\n=== 候选布局对照 ===")


def i16(o):
    return int.from_bytes(raw[o:o + 2], "big", signed=True)


def f32(o):
    return struct.unpack(">f", raw[o:o + 4])[0]


for st, base in (("一站", 0), ("二站", 56), ("三站", 102)):
    print(f"{st} base={base}: online={i16(base)} mode={i16(base+2)} "
          f"busy={i16(base+4)} fault={i16(base+6)} order={i16(base+8)}")
    # 当前步骤：Int vs Real
    print(f"      步骤@+10/12 -> Int={i16(base+10)}  Real={f32(base+10)!r}")

hb = {"一站": (14, 16), "二站": (72, 74), "三站": (118, 120)}
for st, (o, o2) in hb.items():
    print(f"{st} heartbeat Int@{o}={i16(o)}  done/recv byte@{o2}=0x{raw[o2]:02X} "
          f"done={bool(raw[o2] & 1)} recv={bool((raw[o2] >> 1) & 1)}")

print("三站 仓位@122 bits:", [bool((raw[122 + i // 8] >> (i % 8)) & 1) for i in range(9)])
print("三站 入站/@124:", i16(124), " 入库/@126:", i16(126), " 称重/@128:", i16(128))
print("三站 合格态/@130:", i16(130), " 合格数/@132:", i16(132), " 不合格/@134:", i16(134))
print("三站 X/@136:", f32(136), " Y/@140:", f32(140))
print("订单区 @164..180:", [i16(o) for o in (164, 166, 168, 170, 172)],
      " done byte@174:", f"0x{raw[174]:02X}", " start@176:", i16(176), " reset@178:", i16(178))

raw_op, err_op = try_read(120, 180, 10)
if raw_op:
    print("订单区尾部 180..189:", " ".join(f"{b:02X}" for b in raw_op))

b, errb = try_read(121, 0, 16)
if b:
    print("\nDB121:", " ".join(f"{b_[0]:02X}" for b_ in [(x,) for x in b]))
    print("  参数@0,2,4,6,8:", [int.from_bytes(b[o:o + 2], "big", signed=True) for o in (0, 2, 4, 6, 8)])
    print("  心跳@10:", int.from_bytes(b[10:12], "big", signed=True),
          " bits@12:", bin(b[12]), " 完成ID@14:", int.from_bytes(b[14:16], "big", signed=True))
else:
    print("DB121 read failed:", errb)

c.disconnect()
