"""DLDS-532 下单软件入口。"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def resource_path(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*parts)


def main() -> int:
    # 高 DPI 缩放由 Qt6 自动处理；固定任务栏图标分组
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DLDS532.OrderApp")
        except Exception:  # noqa: BLE001
            pass

    from PySide6.QtGui import QFont, QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox

    from app.config import APP_TITLE, APP_VERSION, data_dir
    from app.ui import theme
    from app.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setApplicationDisplayName(APP_TITLE)
    app.setStyleSheet(theme.QSS)
    font = QFont("Microsoft YaHei UI", 9)
    app.setFont(font)
    icon_file = resource_path("assets", "app.ico")
    if icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))

    def excepthook(exc_type, exc_value, exc_tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            (data_dir() / "error.log").open("a", encoding="utf-8").write(text + "\n")
        except OSError:
            pass
        QMessageBox.critical(None, "程序异常", f"{exc_value}\n\n详细信息已写入 {data_dir() / 'error.log'}")

    sys.excepthook = excepthook

    window = MainWindow()
    window.show()

    if "--selftest" in sys.argv:
        # 打包验证用：启动界面、跑几秒事件循环、写标记文件后自动退出
        from PySide6.QtCore import QTimer

        def finish() -> None:
            import snap7
            from PySide6 import QtCore
            lines = [
                "selftest ok",
                f"version={APP_VERSION}",
                f"pyside={QtCore.__version__}",
                f"snap7={getattr(snap7, '__version__', '?')}",
                f"data_dir={data_dir()}",
                f"db={window.storage.path}",
                f"cwd={os.getcwd()}",
            ]
            # 数据库写探测：打包后最容易出问题的是文件权限 / 只读
            try:
                probe = window.storage.create_order(1, 1, 1, 1)
                window.storage.delete_order(probe.rec_id)
                lines.append(f"db_write=ok id={probe.order_id}")
            except Exception as exc:  # noqa: BLE001
                lines.append(f"db_write=FAIL {type(exc).__name__}: {exc}")
            try:
                mode = window.storage._query("PRAGMA journal_mode")[0][0]
                lines.append(f"journal_mode={mode}")
            except Exception as exc:  # noqa: BLE001
                lines.append(f"journal_mode=FAIL {exc}")
            try:
                probe_file = data_dir() / "probe.tmp"
                probe_file.write_text("x", encoding="utf-8")
                probe_file.unlink()
                lines.append("file_write=ok")
            except Exception as exc:  # noqa: BLE001
                lines.append(f"file_write=FAIL {type(exc).__name__}: {exc}")
            try:
                (data_dir() / "selftest_ok.txt").write_text("\n".join(lines), encoding="utf-8")
            except OSError as exc:
                (data_dir() / "selftest_ok.txt").write_text(f"write failed {exc}", encoding="utf-8")
            window.close()
            app.quit()

        QTimer.singleShot(2500, finish)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
