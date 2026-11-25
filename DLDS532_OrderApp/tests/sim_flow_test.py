"""无硬件联调测试：使用内置模拟 PLC 验证完整下单链路。

运行：
    python tests/sim_flow_test.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication  # noqa: E402

from app.config import AppConfig  # noqa: E402
from app.model import ST_DONE, ST_FAILED, ST_PENDING, ST_PRODUCING, PlcSnapshot, V_ACKED, \
    V_DONE, V_DONE_ID, V_ORDER_ID, V_READY, V_REQ  # noqa: E402
from app.order_service import OrderService  # noqa: E402
from app.plc_worker import PlcWorker  # noqa: E402
from app.storage import Storage, now_text  # noqa: E402

APP = QCoreApplication(sys.argv)
PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASSED.append(name)
        print(f"  [OK]   {name}")
    else:
        FAILED.append(name)
        print(f"  [FAIL] {name} {detail}")


def wait_until(cond, timeout: float, label: str = "") -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        APP.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    if label:
        print(f"  [超时] {label}")
    return False


def make_cfg(**over) -> AppConfig:
    cfg = AppConfig()
    cfg.simulate = True
    cfg.poll_ms = 100
    cfg.ack_timeout_s = 5
    cfg.sim_duration_s = 2
    for key, value in over.items():
        setattr(cfg, key, value)
    errors = cfg.validate()
    assert not errors, errors
    return cfg


def open_app(cfg, storage, sim=None):
    service = OrderService(storage, cfg)
    service.alerts = []
    service.on_alert = lambda t, m: service.alerts.append((t, m))
    worker = PlcWorker(cfg, transport_factory=(lambda c: sim)) if sim is not None else PlcWorker(cfg)
    service.attach_worker(worker)
    service.load_active()
    worker.start()
    return service, worker


def settle(service, timeout: float = 20) -> bool:
    """等待回到空闲：无在制订单、产线可接单、无遗留握手信号。"""
    return wait_until(lambda: service.current is None and service.snap.connected
                      and service.snap.b(V_READY) and not service.snap.b(V_ACKED)
                      and not service.snap.b(V_DONE) and not service.snap.b(V_REQ),
                      timeout, "回到空闲")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="dlds532_test_"))
    print(f"临时目录：{tmp}")
    cfg = make_cfg()
    storage = Storage(tmp / "orders.db")
    service, worker = open_app(cfg, storage)

    print("\n[1] 连接与初始状态")
    check("PLC 连接成功", wait_until(lambda: service.snap.connected, 8, "连接"))
    check("产线可接单=TRUE", wait_until(lambda: service.snap.b(V_READY), 3, "可接单"))

    print("\n[2] 下单 -> PLC确认 -> 生产完成")
    order = storage.create_order(1, 4, 2, 3)
    ok, reason = service.send_order(order)
    check("允许下发订单", ok, reason)
    check("等待PLC确认后转为正在生产",
          wait_until(lambda: (service.current is not None
                              and service.current.status == ST_PRODUCING), 5, "确认"),
          f"状态={storage.get(order.rec_id).status}")
    snap = service.snap
    check("DB121 订单参数正确", (snap.i(V_ORDER_ID) == order.order_id
                              and snap.i("AB物料") == 1 and snap.i("8mm钢珠数量") == 4
                              and snap.i("10mm钢珠数量") == 2 and snap.i("存储仓位") == 3),
          f"{snap.i(V_ORDER_ID)}/{snap.i('8mm钢珠数量')}/{snap.i('10mm钢珠数量')}/{snap.i('存储仓位')}")
    check("MES下单请求已被 MES 清除", wait_until(lambda: not service.snap.b(V_REQ), 3, "清请求"))
    check("订单完成",
          wait_until(lambda: storage.get(order.rec_id).status == ST_DONE, 10, "完成"),
          f"状态={storage.get(order.rec_id).status}")
    done_row = storage.get(order.rec_id)
    check("完成记录包含完成订单ID", done_row.plc_done_id == order.order_id, f"{done_row.plc_done_id}")
    check("完成信号与下发信号已清除",
          wait_until(lambda: not service.snap.b(V_DONE) and not service.snap.b(V_ACKED), 5, "清信号"))
    check("产线恢复可接单", settle(service))

    print("\n[3] 第二笔订单（验证无旧信号串单）")
    order2 = storage.create_order(2, 0, 6, 7)
    ok, reason = service.send_order(order2)
    check("第二笔可下发", ok, reason)
    check("第二笔完成",
          wait_until(lambda: storage.get(order2.rec_id).status == ST_DONE, 12, "完成2"),
          f"状态={storage.get(order2.rec_id).status}")
    check("第一笔订单状态未被改动", storage.get(order.rec_id).status == ST_DONE)
    settle(service)

    print("\n[4] 同一时间只允许一笔订单在流程中")
    order3 = storage.create_order(1, 1, 1, 1)
    order4 = storage.create_order(1, 2, 2, 2)
    ok3, reason3 = service.send_order(order3)
    check("第三笔可下发", ok3, reason3)
    wait_until(lambda: service.current is not None and service.current.status == ST_PRODUCING, 5)
    allowed, reason = service.can_send(order4)
    check("生产期间禁止下发其他订单", not allowed, reason)
    check("DB121 参数未被覆盖", service.snap.i(V_ORDER_ID) == order3.order_id,
          f"DB={service.snap.i(V_ORDER_ID)} 本地={order3.order_id}")
    check("第三笔完成", wait_until(lambda: storage.get(order3.rec_id).status == ST_DONE, 12))
    check("第四笔仍为待下单", storage.get(order4.rec_id).status == ST_PENDING)
    settle(service)

    print("\n[5] 下单确认超时 -> 下单失败")
    worker._transport.block_ack = True
    order5 = storage.create_order(1, 3, 3, 4)
    ok, reason = service.send_order(order5)
    check("超时场景允许下发", ok, reason)
    check("超时后标记下单失败",
          wait_until(lambda: storage.get(order5.rec_id).status == ST_FAILED, 12, "超时失败"),
          f"状态={storage.get(order5.rec_id).status}")
    row5 = storage.get(order5.rec_id)
    check("失败原因已记录", "未确认" in (row5.last_error or ""), row5.last_error)
    check("失败后撤销 MES下单请求", wait_until(lambda: not service.snap.b(V_REQ), 5, "清请求"))
    check("失败订单不会变成已完成", storage.get(order5.rec_id).status != ST_DONE)
    check("失败有明确的界面提示", any("下单失败" in t for t, _ in service.alerts))
    worker._transport.block_ack = False
    check("超时撤销后产线可恢复接单", settle(service))

    print("\n[6] 遗留完成信号不会误判新订单")
    sim = worker._transport
    sim.write_int(cfg.var(V_DONE_ID).byte, "INT", 999)
    sim.write_bits([(cfg.var(V_DONE).byte, cfg.var(V_DONE).bit, True)])
    check("轮询读到遗留完成信号", wait_until(lambda: service.snap.b(V_DONE), 3, "读到 999"))
    check("遗留信号被自动清除",
          wait_until(lambda: not service.snap.b(V_DONE), 6, "清遗留"))
    check("遗留信号清除后仍可下单", settle(service))
    order6 = storage.create_order(1, 5, 5, 2)
    ok, reason = service.send_order(order6)
    check("遗留信号清除后可正常下单", ok, reason)
    check("新订单正常完成（未被 999 号信号误判）",
          wait_until(lambda: storage.get(order6.rec_id).status == ST_DONE, 12),
          f"状态={storage.get(order6.rec_id).status}")
    check("完成记录里的订单ID是自己的",
          storage.get(order6.rec_id).plc_done_id == order6.order_id,
          f"{storage.get(order6.rec_id).plc_done_id}")
    settle(service)

    print("\n[7] 软件重启恢复：重启时订单正在生产")
    order7 = storage.create_order(2, 7, 7, 8)
    service.send_order(order7)
    wait_until(lambda: service.current is not None and service.current.status == ST_PRODUCING, 5)
    check("重启前处于正在生产", service.current is not None
          and service.current.status == ST_PRODUCING)
    worker.stop()
    worker.wait(3000)
    storage.close()

    # 模拟软件重启：PLC 继续运行（复用同一模拟 PLC），软件重新打开同一数据库
    sim_keep = sim
    storage2 = Storage(tmp / "orders.db")
    service2, worker2 = open_app(cfg, storage2, sim=sim_keep)
    check("重启后恢复在制订单", service2.current is not None
          and service2.current.order_id == order7.order_id, f"{service2.current}")
    check("重启后不会误判为已完成",
          storage2.get(order7.rec_id).status == ST_PRODUCING,
          storage2.get(order7.rec_id).status)
    check("重启后正常收到完成",
          wait_until(lambda: storage2.get(order7.rec_id).status == ST_DONE, 15),
          f"状态={storage2.get(order7.rec_id).status}")
    check("重启后不会重复处理完成信号",
          wait_until(lambda: not service2.snap.b(V_DONE) and not service2.snap.b(V_ACKED), 6))
    worker2.stop()
    worker2.wait(3000)

    print("\n[8] 本地订单记录")
    counts = storage2.counts()
    check("已完成订单数正确", counts[ST_DONE] == 5, str(counts))
    check("失败订单数正确", counts[ST_FAILED] == 1, str(counts))
    check("待下单订单仍在本地保存", counts[ST_PENDING] == 1, str(counts))
    orders = storage2.list_orders()
    check("订单ID唯一", len({o.order_id for o in orders}) == len(orders), str(len(orders)))
    check("历史事件已记录", len(storage2.recent_events(50)) > 10)

    print("\n[9] 重启对账：PLC 已空闲时订单不再卡死")
    stuck = storage2.create_order(1, 3, 1, 6)
    storage2.update_fields(stuck.rec_id, status=ST_PRODUCING, request_state="sent",
                           ack_at=now_text())
    svc3 = OrderService(storage2, cfg)
    svc3.restore_grace_s = 0.1
    svc3.load_active()
    check("重启时恢复了在制订单", svc3.current is not None
          and svc3.current.order_id == stuck.order_id)
    idle_snap = PlcSnapshot(connected=True, values={
        V_READY: True, V_ACKED: False, V_ORDER_ID: 0, V_DONE: False, V_DONE_ID: 0})
    svc3.handle_snapshot(idle_snap)
    time.sleep(0.15)
    svc3.handle_snapshot(idle_snap)
    check("产线空闲却无完成信号 -> 判定中断",
          storage2.get(stuck.rec_id).status == ST_FAILED,
          f"状态={storage2.get(stuck.rec_id).status}")
    check("中断后不再占用流程", svc3.current is None)
    check("中断订单可以删除", storage2.delete_order(stuck.rec_id))

    print("\n[10] 人工终止卡住的订单")
    stuck2 = storage2.create_order(2, 4, 4, 9)
    storage2.update_fields(stuck2.rec_id, status=ST_PRODUCING, request_state="sent")
    svc4 = OrderService(storage2, cfg)
    svc4.load_active()
    check("人工终止成功", svc4.terminate_order(svc4.current, "测试终止")
          and storage2.get(stuck2.rec_id).status == ST_FAILED)
    check("终止后可删除", storage2.delete_order(stuck2.rec_id))

    print("\n[11] 关闭软件时的保留策略")
    keep = storage2.create_order(1, 1, 1, 1)
    storage2.update_fields(keep.rec_id, status=ST_PRODUCING, request_state="sent")
    ids = storage2.interrupt_unfinished("测试中断")
    check("未完成订单被标记为中断", ids == [keep.order_id]
          and storage2.get(keep.rec_id).status == ST_FAILED)
    total = storage2.clear_orders()
    check("清空订单记录", total >= 1 and not storage2.list_orders(), str(total))
    check("运行日志在清空后仍然保留", len(storage2.recent_events(50)) > 0)

    from app.config import RETENTION_CLEAR, RETENTION_KEEP  # noqa: E402
    cfg_r = cfg.copy()
    cfg_r.retention = RETENTION_CLEAR
    cfg_r2 = AppConfig.from_dict(cfg_r.to_dict())
    check("保留策略可保存与读取", cfg_r2.retention == RETENTION_CLEAR)
    cfg_bad = cfg.copy().to_dict()
    cfg_bad["retention"] = "乱写"
    check("非法保留策略回退为默认", AppConfig.from_dict(cfg_bad).retention == RETENTION_KEEP)

    storage2.close()
    print("\n================ 测试结果 ================")
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    if FAILED:
        for name in FAILED:
            print(f"  失败：{name}")
        print(f"临时目录保留以便排查：{tmp}")
        return 1
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
