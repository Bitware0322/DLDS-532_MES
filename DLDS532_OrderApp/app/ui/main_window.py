"""主窗口：订单列表、新建/下单、PLC 状态与日志。"""
from __future__ import annotations

import html
import time
from datetime import datetime

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QCheckBox, QFrame, QHBoxLayout, QHeaderView, \
    QLabel, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QTableWidgetItem, \
    QVBoxLayout, QWidget

from ..config import APP_TITLE, APP_VERSION, RETENTION_KEEP, AppConfig, db_path, data_dir
from ..model import ST_DONE, ST_FAILED, ST_PENDING, ST_PRODUCING, STATUS_COLOR, PlcSnapshot, \
    V_ACKED, V_DONE, V_DONE_ID, V_HEARTBEAT, V_READY
from ..order_service import OrderService
from ..plc_worker import PlcWorker
from ..storage import Order, Storage
from . import theme
from .order_dialog import OrderDialog
from .settings_dialog import SettingsDialog
from .widgets import CardRow, OrderTable, StatusDot

COLUMNS = ["订单ID", "AB物料", "8mm钢珠数量", "10mm钢珠数量", "存储仓位", "订单状态", "创建时间"]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = AppConfig.load()
        self.storage = Storage(db_path())
        self.service = OrderService(self.storage, self.cfg)
        self.worker = PlcWorker(self.cfg)
        self.service.attach_worker(self.worker)
        self.service.load_active()

        self.setWindowTitle(APP_TITLE)
        self.resize(1080, 720)
        self.setMinimumSize(QSize(900, 620))
        self._last_table_refresh = 0.0
        self._table_sig: tuple = ()
        self._selected_rec = 0
        self._alerts: list[QMessageBox] = []

        self._build_ui()
        self._load_history()

        # 回调（UI 已就绪后再挂）
        self.service.on_changed = self.refresh
        self.service.on_log = self.append_log
        self.service.on_snapshot = self._on_snapshot
        self.service.on_alert = self._on_alert
        self.worker.sig_conn.connect(self._on_conn)
        self.worker.start()

        self.refresh()
        self._log_startup()

    # -------------------------------------------------- 界面
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 12, 14, 8)
        layout.setSpacing(10)

        layout.addWidget(self._build_header())

        self.cards = CardRow([
            ("ready", "产线可接单"),
            ("acked", "PLC订单已下发"),
            ("done", "订单已完成"),
            ("done_id", "完成订单ID"),
            ("active", "当前在制订单"),
            ("hb", "PLC通讯心跳"),
        ])
        layout.addWidget(self.cards)

        layout.addLayout(self._build_toolbar())
        layout.addWidget(self._build_table(), 1)
        layout.addWidget(self._build_log())

        self.statusBar().showMessage(f"数据文件：{db_path()}")
        version = QLabel(f"v{APP_VERSION}")
        version.setObjectName("Hint")
        self.statusBar().addPermanentWidget(version)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("Header")
        box = QHBoxLayout(header)
        box.setContentsMargins(16, 10, 14, 10)
        box.setSpacing(12)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel(APP_TITLE)
        title.setObjectName("AppTitle")
        sub = QLabel("数据管理站 PLC · DB121 · S7 TCP")
        sub.setObjectName("AppSub")
        titles.addWidget(title)
        titles.addWidget(sub)
        box.addLayout(titles)
        if self.cfg.simulate:
            badge = QLabel("模拟模式 · 不连真实 PLC")
            badge.setStyleSheet(
                f"background: #fff7e6; color: {theme.AMBER}; border: 1px solid #fbdba7;"
                f"border-radius: 9px; padding: 2px 10px; font-size: 12px;")
            box.addWidget(badge)
        box.addStretch(1)

        self.dot = StatusDot()
        self.lbl_conn = QLabel("未连接")
        self.lbl_conn.setObjectName("ConnText")
        box.addWidget(self.dot)
        box.addWidget(self.lbl_conn)

        self.btn_maint = QPushButton("维护")
        self.btn_maint.setMenu(self._build_maint_menu())
        box.addWidget(self.btn_maint)

        btn_settings = QPushButton("设置")
        btn_settings.clicked.connect(self._open_settings)
        box.addWidget(btn_settings)
        return header

    def _build_maint_menu(self) -> QMenu:
        menu = QMenu(self)
        act_reconnect = QAction("重新连接 PLC", self)
        act_reconnect.triggered.connect(self._reconnect)
        act_reset = QAction("PLC 状态复位（清除握手信号）", self)
        act_reset.triggered.connect(self._reset_plc)
        act_terminate = QAction("终止当前在制订单（人工）", self)
        act_terminate.triggered.connect(self._terminate_active)
        act_clear = QAction("清空所有订单记录…", self)
        act_clear.triggered.connect(self._clear_orders)
        act_dir = QAction("打开数据目录", self)
        act_dir.triggered.connect(self._open_data_dir)
        act_about = QAction("关于", self)
        act_about.triggered.connect(self._about)
        menu.addAction(act_reconnect)
        menu.addAction(act_reset)
        menu.addSeparator()
        menu.addAction(act_terminate)
        menu.addAction(act_clear)
        menu.addSeparator()
        menu.addAction(act_dir)
        menu.addAction(act_about)
        return menu

    def _build_toolbar(self) -> QHBoxLayout:
        box = QHBoxLayout()
        box.setSpacing(8)

        self.btn_new = QPushButton("新建订单")
        self.btn_new.setObjectName("Primary")
        self.btn_new.clicked.connect(self._new_order)

        self.btn_send = QPushButton("下单")
        self.btn_send.setObjectName("Success")
        self.btn_send.clicked.connect(self._send_selected)

        self.btn_delete = QPushButton("删除订单")
        self.btn_delete.setObjectName("Danger")
        self.btn_delete.clicked.connect(self._delete_selected)

        box.addWidget(self.btn_new)
        box.addWidget(self.btn_send)
        box.addWidget(self.btn_delete)
        box.addStretch(1)

        self.chk_active = QCheckBox("仅显示进行中的订单")
        self.chk_active.toggled.connect(lambda _: self.refresh(force_table=True))
        box.addWidget(self.chk_active)

        self.lbl_hint = QLabel("")
        self.lbl_hint.setObjectName("Hint")
        box.addWidget(self.lbl_hint)
        return box

    def _build_table(self) -> QWidget:
        self.table = OrderTable(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 100)
        for i in (1, 4):
            header.setSectionResizeMode(i, QHeaderView.Fixed)
            self.table.setColumnWidth(i, 100)
        for i in (2, 3):
            header.setSectionResizeMode(i, QHeaderView.Fixed)
            self.table.setColumnWidth(i, 130)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 180)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selection)
        return self.table

    def _build_log(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        box = QVBoxLayout(panel)
        box.setContentsMargins(12, 8, 12, 10)
        box.setSpacing(4)

        head = QHBoxLayout()
        title = QLabel("运行日志")
        title.setObjectName("PanelTitle")
        head.addWidget(title)
        head.addStretch(1)
        btn_clear = QPushButton("清空")
        btn_clear.setObjectName("Link")
        btn_clear.clicked.connect(lambda: self.txt_log.clear())
        head.addWidget(btn_clear)
        box.addLayout(head)

        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumBlockCount(600)
        self.txt_log.setFixedHeight(132)
        box.addWidget(self.txt_log)
        return panel

    # -------------------------------------------------- 日志
    def append_log(self, message: str, level: str = "info") -> None:
        color = {"info": "#475569", "ok": theme.GREEN, "warn": theme.AMBER,
                 "error": theme.RED}.get(level, "#475569")
        stamp = datetime.now().strftime("%H:%M:%S")
        self.txt_log.appendHtml(
            f'<span style="color:#94a3b8">[{stamp}]</span> '
            f'<span style="color:{color}">{html.escape(message)}</span>')
        bar = self.txt_log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _load_history(self) -> None:
        for ts, level, message in self.storage.recent_events(60):
            color = {"info": "#475569", "ok": theme.GREEN, "warn": theme.AMBER,
                     "error": theme.RED}.get(level, "#475569")
            self.txt_log.appendHtml(
                f'<span style="color:#94a3b8">[{ts}]</span> '
                f'<span style="color:{color}">{html.escape(message)}</span>')

    def _log_startup(self) -> None:
        mode = "（模拟 PLC 模式）" if self.cfg.simulate else ""
        self.append_log(f"软件启动{mode}，PLC {self.cfg.ip}:{self.cfg.port}，"
                        f"DB{self.cfg.db_number}，轮询 {self.cfg.poll_ms} ms", "info")
        if self.cfg.simulate:
            self.append_log("当前为模拟模式，不会与真实 PLC 通信；现场使用前请在设置中关闭", "warn")
        if not self.storage.writable:
            self.append_log(f"数据文件不可写：{self.storage.write_error}。订单无法保存，已禁止下单！",
                            "error")
            self._warn_storage_readonly()

    def _warn_storage_readonly(self) -> None:
        box = QMessageBox(QMessageBox.Critical, "订单数据库不可写",
                          f"数据文件无法写入：\n{self.storage.path}\n\n"
                          f"错误：{self.storage.write_error}\n\n"
                          f"在修复之前，软件不会发送任何订单（避免订单写不进库却已下到 PLC）。\n\n"
                          f"可尝试：\n"
                          f"1) 检查该目录权限，或右键「以管理员身份运行」；\n"
                          f"2) 关闭可能锁定文件的杀毒/同步软件；\n"
                          f"3) 在程序目录放一个空的 portable.flag，改用便携数据目录。",
                          QMessageBox.Ok, self)
        box.setWindowModality(Qt.NonModal)
        self._alerts.append(box)
        box.finished.connect(lambda _=0, b=box: self._alerts.remove(b)
                             if b in self._alerts else None)
        box.open()

    # -------------------------------------------------- 状态刷新
    def _on_snapshot(self, snap: PlcSnapshot) -> None:
        self._update_cards(snap)

    def _on_conn(self, connected: bool, message: str) -> None:
        if connected:
            self.dot.set_state("ok")
            self.lbl_conn.setText(f"已连接 {self.cfg.ip}:{self.cfg.port}")
            self.lbl_conn.setStyleSheet("color: #15803d;")
        else:
            self.dot.set_state("error")
            self.lbl_conn.setText(message or "未连接")
            self.lbl_conn.setStyleSheet("color: #dc2626;")

    def _update_cards(self, snap: PlcSnapshot) -> None:
        if not snap.connected:
            self.cards.cards["ready"].set_value("离线", theme.MUTED)
            self.cards.cards["acked"].set_value("-", theme.MUTED)
            self.cards.cards["done"].set_value("-", theme.MUTED)
            self.cards.cards["done_id"].set_value("-", theme.MUTED)
            self.cards.cards["hb"].set_value("-", theme.MUTED)
        else:
            ready = snap.b(V_READY)
            self.cards.cards["ready"].set_value("可接单" if ready else "不可接单",
                                                theme.GREEN if ready else theme.AMBER)
            acked = snap.b(V_ACKED)
            self.cards.cards["acked"].set_value("TRUE" if acked else "FALSE",
                                                theme.AMBER if acked else theme.MUTED)
            done = snap.b(V_DONE)
            self.cards.cards["done"].set_value("TRUE" if done else "FALSE",
                                               theme.GREEN if done else theme.MUTED)
            self.cards.cards["done_id"].set_value(str(snap.i(V_DONE_ID)))
            hb_text = str(snap.i(V_HEARTBEAT))
            if snap.heartbeat_age > 5:
                self.cards.cards["hb"].set_value(f"{hb_text} · {snap.heartbeat_age:.0f}s 未变",
                                                 theme.AMBER)
                self.dot.set_state("warn")
            else:
                self.cards.cards["hb"].set_value(hb_text, theme.MUTED)

        cur = self.service.current
        if cur is None:
            self.cards.cards["active"].set_value("无", theme.MUTED)
        else:
            text = f"{cur.order_id} · " + ("生产中" if cur.status == ST_PRODUCING else "待确认")
            self.cards.cards["active"].set_value(text,
                                                 "#d97706" if cur.status == ST_PRODUCING else "#2563eb")

    def refresh(self, force_table: bool = False) -> None:
        self._update_buttons()
        now = time.time()
        if force_table or now - self._last_table_refresh >= 1.0:
            self._last_table_refresh = now
            self._refresh_table()

    def _update_buttons(self) -> None:
        order = self._selected_order()
        ok, reason = self.service.can_send(order)
        self.btn_send.setEnabled(order is not None and ok)
        if order is None:
            self.btn_send.setToolTip("请先在列表中选择一笔订单")
            self.lbl_hint.setText("")
        else:
            self.btn_send.setToolTip(reason or f"向 PLC 下发订单 {order.order_id}")
            self.lbl_hint.setText("" if ok else reason)
            self.lbl_hint.setStyleSheet(f"color: {theme.AMBER};")
        self.btn_delete.setEnabled(order is not None)
        if order is not None:
            self.btn_delete.setToolTip(
                "该订单在流程中，删除会先强制终止（解除软件占位，不影响 PLC 设备动作）"
                if order.in_flow else f"删除订单 {order.order_id} 的本地记录")

    def _refresh_table(self) -> None:
        orders = self.storage.list_orders(only_in_flow=self.chk_active.isChecked())
        sig = tuple((o.rec_id, o.status, o.request_state, o.last_error, o.completed_at,
                     o.ack_at) for o in orders)
        if sig == self._table_sig:
            return
        self._table_sig = sig

        keep = self._selected_rec
        self.table.blockSignals(True)
        self.table.setRowCount(len(orders))
        for row, order in enumerate(orders):
            values = [str(order.order_id), order.material_text, str(order.qty_8mm),
                      str(order.qty_10mm), str(order.slot), order.status_text, order.created_at]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col in (0, 2, 3, 4):
                    item.setTextAlignment(Qt.AlignCenter)
                if col == 5:
                    item.setForeground(QColor(STATUS_COLOR.get(order.status, theme.TEXT)))
                    font = QFont()
                    font.setBold(order.in_flow)
                    item.setFont(font)
                    if order.last_error:
                        item.setToolTip(order.last_error)
                if order.status == ST_DONE:
                    item.setForeground(QColor(theme.MUTED) if col != 5 else
                                       QColor(STATUS_COLOR[ST_DONE]))
                self.table.setItem(row, col, item)
            id_item = self.table.item(row, 0)
            id_item.setData(Qt.UserRole, order.rec_id)
            if order.last_error:
                id_item.setToolTip(order.last_error)
        self.table.blockSignals(False)

        target = -1
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.UserRole) == keep:
                target = row
                break
        if target < 0 and self.table.rowCount() > 0:
            target = 0
        if target >= 0:
            self.table.selectRow(target)
            self._selected_rec = self.table.item(target, 0).data(Qt.UserRole)
        else:
            self._selected_rec = 0
        self._update_buttons()

    def _on_selection(self) -> None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if rows:
            item = self.table.item(rows[0].row(), 0)
            self._selected_rec = item.data(Qt.UserRole) if item else 0
        self._update_buttons()

    def _selected_order(self) -> Order | None:
        if not self._selected_rec:
            return None
        return self.storage.get(self._selected_rec)

    # -------------------------------------------------- 动作
    def _new_order(self) -> None:
        if not self.storage.writable:
            QMessageBox.warning(self, "无法新建订单",
                                f"订单数据库不可写：\n{self.storage.write_error}\n\n"
                                f"请先修复数据目录权限（或以管理员身份运行）。")
            return
        dialog = OrderDialog(self.storage.peek_next_order_id(), self)
        if dialog.exec() != OrderDialog.Accepted:
            return
        values = dialog.values()
        try:
            order = self.storage.create_order(**values)
        except Exception as exc:  # noqa: BLE001 - 写库失败必须明确告知
            QMessageBox.critical(self, "新建订单失败", f"订单保存失败：{exc}")
            return
        self.refresh(force_table=True)
        self._select(order.rec_id)
        self.append_log(f"订单 {order.order_id} 已创建，选择该行点击“下单”发送给 PLC", "info")

    def _select(self, rec_id: int) -> None:
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.UserRole) == rec_id:
                self.table.selectRow(row)
                self._selected_rec = rec_id
                break

    def _send_selected(self) -> None:
        order = self._selected_order()
        if order is None:
            self._toast("请先在列表中选择要下单的订单")
            return
        ok, reason = self.service.can_send(order)
        if not ok:
            QMessageBox.information(self, "无法下单", reason)
            return
        if order.status == ST_FAILED:
            answer = QMessageBox.question(
                self, "重新下单",
                f"订单 {order.order_id} 上次下单失败（{order.last_error or '未知原因'}），是否重新下发？")
            if answer != QMessageBox.Yes:
                return
        self.service.send_order(order)
        self._update_buttons()

    def _delete_selected(self) -> None:
        order = self._selected_order()
        if order is None:
            return
        if order.in_flow:
            # 订单卡在流程中（例如软件重启后 PLC 已结束、或产线已复位）
            answer = QMessageBox.question(
                self, "订单仍在流程中",
                f"订单 {order.order_id} 当前状态为“{order.status_text}”，正常情况不能删除。\n\n"
                f"如果 PLC 中这笔订单实际已经结束（产线已复位、或完成信号早已被清除），"
                f"可以强制把它标记为“下单失败（人工终止）”并删除本地记录。\n\n"
                f"注意：这不是取消 PLC 的生产动作，只是解除软件里的占位。是否继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
            self.service.terminate_order(order, "人工强制终止并删除")
        else:
            answer = QMessageBox.question(self, "删除订单", f"确定删除订单 {order.order_id} 的本地记录？")
            if answer != QMessageBox.Yes:
                return
        if self.storage.delete_order(order.rec_id):
            self._selected_rec = 0
            self._table_sig = ()
            self.refresh(force_table=True)

    def _terminate_active(self) -> None:
        order = self.service.current
        if order is None:
            QMessageBox.information(self, "无在制订单", "当前没有处于流程中的订单。")
            return
        answer = QMessageBox.question(
            self, "终止订单",
            f"将把订单 {order.order_id}（{order.status_text}）标记为“下单失败（人工终止）”，"
            f"并撤销 PLC 中的 MES下单请求。\n\n该操作只解除软件中的占位，不会停止 PLC 的设备动作。"
            f"\n\n仅在确认该订单实际已不存在时使用。是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        if self.service.terminate_order(order, "人工终止"):
            self._table_sig = ()
            self.refresh(force_table=True)

    def _clear_orders(self) -> None:
        total = len(self.storage.list_orders())
        if total == 0:
            QMessageBox.information(self, "清空订单", "当前没有订单记录。")
            return
        in_flow = len(self.storage.in_flow_orders())
        extra = f"\n其中 {in_flow} 笔仍在流程中，清空后将不再跟踪。" if in_flow else ""
        answer = QMessageBox.question(
            self, "清空所有订单记录",
            f"将删除全部 {total} 条订单记录（运行日志保留），操作不可撤销。{extra}\n\n是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self.storage.clear_orders()
        self.service.current = None
        self._selected_rec = 0
        self._table_sig = ()
        self.refresh(force_table=True)
        self.append_log(f"已清空 {total} 条订单记录", "warn")

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.cfg.copy(), self.cfg, self.worker, self)
        if dialog.exec() != SettingsDialog.Accepted or dialog.result_config is None:
            return
        new_cfg = dialog.result_config
        try:
            path = new_cfg.save()
        except OSError as exc:
            QMessageBox.warning(self, "保存失败", f"配置文件写入失败：{exc}")
            return
        self.cfg = new_cfg
        self.service.cfg = new_cfg
        self.worker.apply_config(new_cfg)
        self.append_log(f"配置已保存并生效（{path}），正在重新连接 PLC", "info")
        if new_cfg.simulate:
            self.append_log("已切换到模拟 PLC 模式", "warn")

    def _reconnect(self) -> None:
        self.append_log("手动重新连接 PLC", "info")
        self.worker.reconnect()

    def _reset_plc(self) -> None:
        answer = QMessageBox.question(
            self, "PLC 状态复位",
            "将清除 PLC 中的 MES下单请求 / 订单已完成 / PLC订单已下发 三个信号。\n"
            "仅在确认产线已停机、无在制订单时使用。是否继续？")
        if answer != QMessageBox.Yes:
            return
        if not self.service.reset_plc_state():
            QMessageBox.information(self, "无法复位", "存在在制订单或 PLC 未连接，不能复位。")

    def _open_data_dir(self) -> None:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir())))

    def _about(self) -> None:
        QMessageBox.about(self, "关于",
                          f"<b>{APP_TITLE}</b> v{APP_VERSION}<br><br>"
                          f"DLDS-532 实训平台 Windows 下单软件<br>"
                          f"S7 TCP 通信，写入数据管理站 PLC 的 DB{self.cfg.db_number}<br>"
                          f"数据文件：{db_path()}<br><br>"
                          f"心跳由 PLC 维护，MES 只读；MES 不控制任何设备动作。")

    def _on_alert(self, title: str, message: str) -> None:
        box = QMessageBox(QMessageBox.Warning, title, message, QMessageBox.Ok, self)
        if title == "订单已判定中断":
            # 启动对账的提示用非模态，避免无人值守启动时被弹窗卡住
            box.setWindowModality(Qt.NonModal)
            self._alerts.append(box)
            box.finished.connect(lambda _=0, b=box: self._alerts.remove(b)
                                 if b in self._alerts else None)
            box.open()
        else:
            box.exec()

    def _toast(self, message: str) -> None:
        self.statusBar().showMessage(message, 4000)

    # -------------------------------------------------- 退出
    def _confirm_close_with_active(self) -> bool:
        order = self.service.current
        if order is None or self.cfg.retention != RETENTION_KEEP:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("订单尚未完成")
        box.setIcon(QMessageBox.Question)
        box.setText(f"订单 {order.order_id} 当前为“{order.status_text}”。\n\n"
                    f"现在关闭，软件将停止跟踪这笔订单。下次启动会与 PLC 核对："
                    f"若产线已结束生产，该订单会被判定为“中断”。")
        box.setInformativeText("也可以先在列表里用“删除订单”强制终止后再关闭。确定关闭吗？")
        yes = box.addButton("关闭", QMessageBox.AcceptRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.setDefaultButton(box.buttons()[-1])
        box.exec()
        return box.clickedButton() is yes

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._confirm_close_with_active():
            event.ignore()
            return
        try:
            # 先摘掉回调并挂起状态机，避免排队中的信号访问已关闭的数据库
            self.service.suspended = True
            self.service.on_changed = None
            self.service.on_log = None
            self.service.on_snapshot = None
            self.service.on_alert = None
            self.worker.stop()
            self.worker.wait(3000)
            self.service.apply_retention_on_close()
        finally:
            self.storage.close()
        super().closeEvent(event)
