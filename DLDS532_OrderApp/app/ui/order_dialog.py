"""新建订单对话框。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, \
    QLabel, QLineEdit, QSpinBox, QVBoxLayout, QWidget

from . import theme


class OrderDialog(QDialog):
    def __init__(self, next_order_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("新建订单")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setStyleSheet(f"QDialog {{ background: {theme.BG}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(12)

        title = QLabel("新建订单")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        root.addWidget(title)

        panel = QFrame()
        panel.setObjectName("Panel")
        form = QFormLayout(panel)
        form.setContentsMargins(16, 14, 16, 14)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.edit_id = QLineEdit(str(next_order_id))
        self.edit_id.setReadOnly(True)
        self.edit_id.setToolTip("订单ID 由软件自动生成，并写入 PLC 的 INT 变量（范围 1-32767）")

        self.cmb_material = QComboBox()
        self.cmb_material.addItem("A 料", 1)
        self.cmb_material.addItem("B 料", 2)

        self.spin_8 = QSpinBox()
        self.spin_8.setRange(0, 999)
        self.spin_8.setValue(4)
        self.spin_8.setSuffix(" 颗")

        self.spin_10 = QSpinBox()
        self.spin_10.setRange(0, 999)
        self.spin_10.setValue(2)
        self.spin_10.setSuffix(" 颗")

        self.spin_slot = QSpinBox()
        self.spin_slot.setRange(1, 9)
        self.spin_slot.setValue(1)
        self.spin_slot.setSuffix(" 号仓位")
        self.spin_slot.setToolTip("对应三站仓位的 9 个格位（1-9）")

        form.addRow("订单ID", self.edit_id)
        form.addRow("AB 物料", self.cmb_material)
        form.addRow("8mm 钢珠数量", self.spin_8)
        form.addRow("10mm 钢珠数量", self.spin_10)
        form.addRow("存储仓位", self.spin_slot)
        root.addWidget(panel)

        self.hint = QLabel("提示：同一时间只允许一笔订单进入 PLC，其余订单保存在本地等待。")
        self.hint.setObjectName("Hint")
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)

        buttons = QDialogButtonBox()
        ok = buttons.addButton("创建订单", QDialogButtonBox.AcceptRole)
        ok.setObjectName("Primary")
        buttons.addButton("取消", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_accept(self) -> None:
        if self.spin_8.value() == 0 and self.spin_10.value() == 0:
            self.hint.setText("8mm 与 10mm 钢珠数量不能同时为 0。")
            self.hint.setStyleSheet(f"color: {theme.RED};")
            return
        self.accept()

    def values(self) -> dict[str, int]:
        return {
            "ab_material": int(self.cmb_material.currentData()),
            "qty_8mm": self.spin_8.value(),
            "qty_10mm": self.spin_10.value(),
            "slot": self.spin_slot.value(),
        }
