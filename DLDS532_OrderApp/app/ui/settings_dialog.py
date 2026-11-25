"""设置对话框：PLC 连接参数、通信参数、DB121 变量映射（偏移与类型均可修改）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, \
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, \
    QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget

from ..config import RETENTION_CLEAR, RETENTION_KEEP, RETENTION_TEXT, RETENTION_UNFINISHED, \
    AppConfig, data_dir
from ..model import DEFAULT_VARIABLES, VarDef
from . import theme

TYPES = ["BOOL", "BYTE", "INT", "WORD", "DINT", "REAL"]


class SettingsDialog(QDialog):
    def __init__(self, cfg: AppConfig, applied: AppConfig, worker=None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setModal(True)
        self.resize(680, 640)
        self.setStyleSheet(f"QDialog {{ background: {theme.BG}; }}")
        self._cfg = cfg.copy()
        self._applied = applied
        self._worker = worker
        self.result_config: AppConfig | None = None
        self._test_pending = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_conn_tab(), "连接与通信")
        self.tabs.addTab(self._build_var_tab(), "DB121 变量映射")
        root.addWidget(self.tabs, 1)

        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(f"color: {theme.RED};")
        self.error_label.hide()
        root.addWidget(self.error_label)

        buttons = QDialogButtonBox()
        save = buttons.addButton("保存并生效", QDialogButtonBox.AcceptRole)
        save.setObjectName("Primary")
        buttons.addButton("取消", QDialogButtonBox.RejectRole)
        restore = buttons.addButton("恢复默认", QDialogButtonBox.ResetRole)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        restore.clicked.connect(self._restore_defaults)
        root.addWidget(buttons)

        if self._worker is not None:
            self._worker.sig_test_result.connect(self._on_test_result)

    # -------------------------------------------------- 连接页
    def _build_conn_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 10, 4, 4)
        layout.setSpacing(10)

        conn = QGroupBox("数据管理 PLC（S7 TCP）")
        grid = QGridLayout(conn)
        grid.setContentsMargins(14, 14, 14, 12)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self.ed_ip = QLineEdit(self._cfg.ip)
        self.sp_port = QSpinBox()
        self.sp_port.setRange(1, 65535)
        self.sp_port.setValue(self._cfg.port)
        self.sp_rack = QSpinBox()
        self.sp_rack.setRange(0, 7)
        self.sp_rack.setValue(self._cfg.rack)
        self.sp_slot = QSpinBox()
        self.sp_slot.setRange(0, 31)
        self.sp_slot.setValue(self._cfg.slot)
        self.sp_db = QSpinBox()
        self.sp_db.setRange(1, 65535)
        self.sp_db.setValue(self._cfg.db_number)

        for widget, width in ((self.ed_ip, 210), (self.sp_port, 110), (self.sp_rack, 110),
                              (self.sp_slot, 110), (self.sp_db, 130)):
            widget.setMaximumWidth(width)

        grid.addWidget(QLabel("PLC IP 地址"), 0, 0)
        grid.addWidget(self.ed_ip, 0, 1)
        grid.addWidget(QLabel("端口"), 0, 2)
        grid.addWidget(self.sp_port, 0, 3)
        grid.addWidget(QLabel("机架 Rack"), 1, 0)
        grid.addWidget(self.sp_rack, 1, 1)
        grid.addWidget(QLabel("插槽 Slot"), 1, 2)
        grid.addWidget(self.sp_slot, 1, 3)
        grid.addWidget(QLabel("DB 块号"), 2, 0)
        grid.addWidget(self.sp_db, 2, 1)
        note = QLabel("DB 必须为“非优化访问”，且 CPU 允许 PUT/GET。")
        note.setObjectName("Hint")
        grid.addWidget(note, 2, 2, 1, 2)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        layout.addWidget(conn)

        comm = QGroupBox("通信与超时")
        form = QFormLayout(comm)
        form.setContentsMargins(14, 14, 14, 12)
        form.setSpacing(8)

        self.sp_poll = QSpinBox()
        self.sp_poll.setRange(50, 10000)
        self.sp_poll.setSingleStep(50)
        self.sp_poll.setSuffix(" ms")
        self.sp_poll.setValue(self._cfg.poll_ms)

        self.sp_timeout = QSpinBox()
        self.sp_timeout.setRange(200, 30000)
        self.sp_timeout.setSingleStep(100)
        self.sp_timeout.setSuffix(" ms")
        self.sp_timeout.setValue(self._cfg.timeout_ms)

        self.sp_ack = QSpinBox()
        self.sp_ack.setRange(1, 3600)
        self.sp_ack.setSuffix(" 秒")
        self.sp_ack.setValue(self._cfg.ack_timeout_s)
        self.sp_ack.setToolTip("下发 MES下单请求 后，等待 PLC订单已下发 的最长时间，超时判定为下单失败")

        self.sp_alarm = QSpinBox()
        self.sp_alarm.setRange(0, 1440)
        self.sp_alarm.setSuffix(" 分钟")
        self.sp_alarm.setValue(self._cfg.produce_alarm_min)
        self.sp_alarm.setToolTip("生产超时仅报警，不会自动修改订单状态；0 表示不报警")

        for spin in (self.sp_poll, self.sp_timeout, self.sp_ack, self.sp_alarm):
            spin.setMaximumWidth(150)

        self.cmb_bit = QComboBox()
        self.cmb_bit.setMaximumWidth(330)
        self.cmb_bit.addItem("自动（推荐：按 S7 位地址写入）", "auto")
        self.cmb_bit.addItem("兼容（读-改-写整字节）", "rmw")
        self.cmb_bit.setCurrentIndex(0 if self._cfg.bit_write_mode != "rmw" else 1)
        self.cmb_bit.setToolTip("若现场固件不支持按位写，可切换为读改写方式；读改写会有极短的字节覆盖窗口")

        form.addRow("轮询周期", self.sp_poll)
        form.addRow("通信超时", self.sp_timeout)
        form.addRow("下单确认超时", self.sp_ack)
        form.addRow("生产超时报警", self.sp_alarm)
        form.addRow("位写入方式", self.cmb_bit)
        layout.addWidget(comm)

        sim = QGroupBox("联调与测试")
        sim_layout = QVBoxLayout(sim)
        sim_layout.setContentsMargins(14, 12, 14, 12)
        self.chk_sim = QCheckBox("启用内置模拟 PLC（无硬件时验证全流程，不访问真实设备）")
        self.chk_sim.setChecked(self._cfg.simulate)
        row = QHBoxLayout()
        row.addWidget(QLabel("模拟单件生产耗时"))
        self.sp_sim = QSpinBox()
        self.sp_sim.setRange(2, 600)
        self.sp_sim.setSuffix(" 秒")
        self.sp_sim.setValue(self._cfg.sim_duration_s)
        self.sp_sim.setMaximumWidth(130)
        row.addWidget(self.sp_sim)
        row.addStretch(1)
        sim_layout.addWidget(self.chk_sim)
        sim_layout.addLayout(row)
        layout.addWidget(sim)

        close_group = QGroupBox("关闭软件时的订单处理")
        close_layout = QVBoxLayout(close_group)
        close_layout.setContentsMargins(14, 12, 14, 12)
        close_layout.setSpacing(6)
        self.cmb_retention = QComboBox()
        self.cmb_retention.setMaximumWidth(420)
        for key in (RETENTION_KEEP, RETENTION_UNFINISHED, RETENTION_CLEAR):
            self.cmb_retention.addItem(RETENTION_TEXT[key], key)
        index = self.cmb_retention.findData(self._cfg.retention)
        self.cmb_retention.setCurrentIndex(max(0, index))
        close_layout.addWidget(self.cmb_retention)
        self.lbl_retention_hint = QLabel()
        self.lbl_retention_hint.setObjectName("Hint")
        self.lbl_retention_hint.setWordWrap(True)
        close_layout.addWidget(self.lbl_retention_hint)
        self.cmb_retention.currentIndexChanged.connect(self._update_retention_hint)
        self._update_retention_hint()
        layout.addWidget(close_group)

        test_row = QHBoxLayout()
        self.btn_test = QPushButton("读取测试（按当前已生效配置读一次 DB121）")
        self.btn_test.setMaximumWidth(320)
        self.btn_test.clicked.connect(self._on_test)
        test_row.addWidget(self.btn_test)
        test_row.addStretch(1)
        layout.addLayout(test_row)
        layout.addStretch(1)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setWidget(page)
        area.setStyleSheet("QScrollArea { background: transparent; }")
        return area

    # -------------------------------------------------- 变量页
    def _build_var_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 10, 4, 4)
        layout.setSpacing(8)

        tip = QLabel("所有变量的偏移地址与数据类型均可修改。BOOL 用“字节.位”格式（如 12.0），"
                     "整型用字节偏移（如 14）。修改后将实时生效。")
        tip.setObjectName("Hint")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        self.table = QTableWidget(len(self._cfg.variables), 4)
        self.table.setHorizontalHeaderLabels(["变量", "数据类型", "偏移地址", "S7 地址"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setColumnWidth(0, 190)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 130)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setStyleSheet(
            "QComboBox { border: 1px solid #e2e8f0; border-radius: 4px; padding: 3px 6px; }"
            "QLineEdit { border: 1px solid #e2e8f0; border-radius: 4px; padding: 3px 6px; }")
        for row, var in enumerate(self._cfg.variables):
            name_item = QTableWidgetItem(var.name)
            name_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 0, name_item)

            combo = QComboBox()
            combo.addItems(TYPES)
            combo.setCurrentText(var.dtype if var.dtype in TYPES else "INT")
            combo.currentTextChanged.connect(self._refresh_address_column)
            self.table.setCellWidget(row, 1, combo)

            edit = QLineEdit(str(var.offset))
            edit.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            edit.textChanged.connect(self._refresh_address_column)
            self.table.setCellWidget(row, 2, edit)

            addr = QTableWidgetItem("")
            addr.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 3, addr)
        layout.addWidget(self.table, 1)
        self._refresh_address_column()

        row = QHBoxLayout()
        btn_default = QPushButton("恢复默认偏移")
        btn_default.setObjectName("Link")
        btn_default.clicked.connect(self._restore_offsets)
        row.addWidget(btn_default)
        row.addStretch(1)
        path = QLabel(f"数据目录：{data_dir()}")
        path.setObjectName("Hint")
        row.addWidget(path)
        layout.addLayout(row)
        return page

    def _refresh_address_column(self) -> None:
        try:
            variables = self._collect_variables()
        except ValueError:
            return
        for row, var in enumerate(variables):
            item = self.table.item(row, 3)
            if item is None:
                continue
            try:
                item.setText(var.address_text())
            except (ValueError, TypeError):
                item.setText("地址无效")

    # -------------------------------------------------- 收集
    def _collect_variables(self) -> list[VarDef]:
        variables = []
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            combo = self.table.cellWidget(row, 1)
            edit = self.table.cellWidget(row, 2)
            if name_item is None or combo is None or edit is None:
                continue
            variables.append(VarDef(name_item.text(), combo.currentText(), edit.text().strip()))
        return variables

    def _collect(self) -> AppConfig:
        return AppConfig(
            ip=self.ed_ip.text().strip(),
            port=self.sp_port.value(),
            rack=self.sp_rack.value(),
            slot=self.sp_slot.value(),
            db_number=self.sp_db.value(),
            poll_ms=self.sp_poll.value(),
            timeout_ms=self.sp_timeout.value(),
            ack_timeout_s=self.sp_ack.value(),
            produce_alarm_min=self.sp_alarm.value(),
            simulate=self.chk_sim.isChecked(),
            sim_duration_s=self.sp_sim.value(),
            bit_write_mode=self.cmb_bit.currentData(),
            retention=self.cmb_retention.currentData(),
            variables=self._collect_variables(),
        )

    # -------------------------------------------------- 动作
    def _restore_offsets(self) -> None:
        defaults = {n: (t, o) for n, t, o in DEFAULT_VARIABLES}
        for row in range(self.table.rowCount()):
            name = self.table.item(row, 0).text()
            if name in defaults:
                dtype, offset = defaults[name]
                self.table.cellWidget(row, 1).setCurrentText(dtype)
                self.table.cellWidget(row, 2).setText(offset)
        self._refresh_address_column()

    def _restore_defaults(self) -> None:
        cfg = AppConfig()
        answer = QMessageBox.question(self, "恢复默认", "将全部连接参数与变量映射恢复为 DB121 默认值，是否继续？")
        if answer != QMessageBox.Yes:
            return
        self.ed_ip.setText(cfg.ip)
        self.sp_port.setValue(cfg.port)
        self.sp_rack.setValue(cfg.rack)
        self.sp_slot.setValue(cfg.slot)
        self.sp_db.setValue(cfg.db_number)
        self.sp_poll.setValue(cfg.poll_ms)
        self.sp_timeout.setValue(cfg.timeout_ms)
        self.sp_ack.setValue(cfg.ack_timeout_s)
        self.sp_alarm.setValue(cfg.produce_alarm_min)
        self.sp_sim.setValue(cfg.sim_duration_s)
        self.chk_sim.setChecked(False)
        self.cmb_bit.setCurrentIndex(0)
        self.cmb_retention.setCurrentIndex(0)
        self._restore_offsets()

    def _update_retention_hint(self) -> None:
        mode = self.cmb_retention.currentData()
        hints = {
            RETENTION_KEEP:
                "关闭软件不删除任何记录。下次启动会恢复未完成的订单并与 PLC 核对："
                "若产线已空闲却收不到完成信号，该订单会被判定为“中断”并允许删除，不会卡住新订单。",
            RETENTION_UNFINISHED:
                "关闭时把仍在流程中的订单标记为“下单失败（中断）”，已完成的历史保留。"
                "适合每班交接、不希望旧订单影响下次开机的情况。",
            RETENTION_CLEAR:
                "关闭时清空全部订单记录（运行日志保留），下次打开是空列表。"
                "若 PLC 里还有未处理完的订单，启动后会作为“遗留完成信号”记录并自动清除。",
        }
        self.lbl_retention_hint.setText(hints.get(mode, ""))

    def _on_save(self) -> None:
        cfg = self._collect()
        errors = cfg.validate()
        if errors:
            self.error_label.setText("配置有误：\n- " + "\n- ".join(errors[:6]))
            self.error_label.show()
            return
        self.error_label.hide()
        self.result_config = cfg
        self.accept()

    def _on_test(self) -> None:
        if self._worker is None:
            return
        if self._collect().to_dict() != self._applied.to_dict():
            QMessageBox.information(self, "读取测试",
                                    "配置已修改但尚未生效。请先点击“保存并生效”，再执行读取测试。")
            return
        self.btn_test.setEnabled(False)
        self.btn_test.setText("正在读取…")
        self._test_pending = True
        self._worker.test_read()

    def _on_test_result(self, ok: bool, msg: str, values: dict) -> None:
        if not self._test_pending:
            return
        self._test_pending = False
        self.btn_test.setEnabled(True)
        self.btn_test.setText("读取测试（按当前已生效配置读一次 DB121）")
        if not ok:
            QMessageBox.warning(self, "读取测试", msg)
            return
        lines = []
        for var in self._applied.variables:
            value = values.get(var.name, "-")
            if isinstance(value, bool):
                value = "TRUE" if value else "FALSE"
            lines.append(f"{var.name:<12}{str(value):>12}    ({var.address_text()})")
        box = QMessageBox(self)
        box.setWindowTitle("读取测试")
        box.setText("读取成功，当前 DB121 数值：")
        box.setDetailedText("\n".join(lines))
        box.exec()
