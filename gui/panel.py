"""
控制面板 GUI
提供一个简单的 PyQt5 界面来控制机器人
"""

import sys
import threading

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QSpinBox, QGroupBox, QFormLayout,
    QShortcut
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QKeySequence

# 项目根路径处理
import os
import sys as _sys
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in _sys.path:
    _sys.path.insert(0, _project_root)


# 全局引用，供 loguru sink 使用
_panel_instance: "ControlPanel | None" = None


class BotSignals(QObject):
    """用于线程间安全通信的信号"""
    log = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    stats_updated = pyqtSignal(int, float)


class ControlPanel(QMainWindow):
    """洛克王国助手 - 控制面板"""

    WINDOW_TITLE = "洛克王国助手"
    WINDOW_SIZE = (420, 570)

    def __init__(self):
        super().__init__()
        global _panel_instance
        _panel_instance = self
        self.bot_runner = None
        self.signals = BotSignals()
        self._setup_ui()
        self._connect_signals()
        self._setup_log_bridge()
        self._bot_thread = None

    def _setup_ui(self):
        """构建界面"""
        self.setWindowTitle(self.WINDOW_TITLE)
        self.setFixedSize(*self.WINDOW_SIZE)

        # 整体风格
        self.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; }
            QGroupBox { 
                color: #cccccc; 
                border: 1px solid #555; 
                border-radius: 6px; 
                margin-top: 10px;
                padding-top: 14px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
            QPushButton { 
                padding: 8px 16px; 
                border-radius: 4px; 
                font-size: 13px; 
                font-weight: bold;
            }
            QPushButton#btnPause { background-color: #FF9800; color: white; }
            QPushButton#btnPause:hover { background-color: #e68900; }
            QPushButton#btnStop { background-color: #f44336; color: white; }
            QPushButton#btnStop:hover { background-color: #d32f2f; }
            QPushButton#btnTeleport { background-color: #2196F3; color: white; }
            QPushButton#btnTeleport:hover { background-color: #1976D2; }
            QPushButton#btnTeleport:disabled { background-color: #555; color: #888; }
            QPushButton#btnTest { background-color: #9C27B0; color: white; }
            QPushButton#btnTest:hover { background-color: #7B1FA2; }
            QPushButton#btnTest:disabled { background-color: #555; color: #888; }
            QLabel { color: #cccccc; }
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 4px;
                font-family: Consolas, monospace;
                font-size: 12px;
            }
            QSpinBox {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 4px;
            }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)

        # === 状态栏 ===
        self.lbl_status = QLabel("⚪ 就绪")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setFont(QFont("Microsoft YaHei", 12))
        layout.addWidget(self.lbl_status)

        # === 控制按钮 ===
        btn_layout = QHBoxLayout()
        self.btn_pause = QPushButton("⏸ 暂停 (F6)")
        self.btn_pause.setObjectName("btnPause")
        self.btn_pause.setEnabled(False)
        self.btn_stop = QPushButton("⏹ 停止 (F7)")
        self.btn_stop.setObjectName("btnStop")
        self.btn_stop.setEnabled(False)
        self.btn_teleport = QPushButton("🌀 传送 (F8)")
        self.btn_teleport.setObjectName("btnTeleport")

        btn_layout.addWidget(self.btn_pause)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addWidget(self.btn_teleport)

        # 第二行按钮
        btn_layout2 = QHBoxLayout()
        self.btn_test = QPushButton("🧪 测试点击 (F9)")
        self.btn_test.setObjectName("btnTest")
        self.btn_picker = QPushButton("📍 坐标采集 (F10)")
        self.btn_picker.setObjectName("btnPicker")
        self.btn_picker.setStyleSheet(
            "QPushButton#btnPicker { background-color: #00BCD4; color: white; }"
            "QPushButton#btnPicker:hover { background-color: #0097A7; }"
        )
        btn_layout2.addWidget(self.btn_test)
        btn_layout2.addWidget(self.btn_picker)
        layout.addLayout(btn_layout2)
        layout.addLayout(btn_layout)

        # === 统计信息 ===
        stats_group = QGroupBox("📊 运行统计")
        stats_form = QFormLayout(stats_group)
        self.lbl_battles = QLabel("0 次")
        self.lbl_runtime = QLabel("00:00")
        stats_form.addRow("战斗次数:", self.lbl_battles)
        stats_form.addRow("运行时间:", self.lbl_runtime)
        layout.addWidget(stats_group)

        # === 设置 ===
        settings_group = QGroupBox("⚙️ 设置")
        settings_form = QFormLayout(settings_group)
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(100, 5000)
        self.spin_interval.setValue(500)
        self.spin_interval.setSuffix(" ms")
        settings_form.addRow("操作间隔:", self.spin_interval)
        layout.addWidget(settings_group)

        # === 日志输出 ===
        log_group = QGroupBox("📋 运行日志")
        log_layout = QVBoxLayout(log_group)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(150)
        log_layout.addWidget(self.log_area)
        layout.addWidget(log_group)

    def _setup_log_bridge(self):
        """将 loguru 日志桥接到 GUI 的 log_area"""
        from loguru import logger

        def gui_sink(message):
            record = message.record
            text = record["message"].strip()
            if text:
                self.signals.log.emit(text)

        logger.add(
            gui_sink,
            format="{message}",
            level="INFO",
            colorize=False,
        )

    def _connect_signals(self):
        """连接信号和按钮事件"""
        self.btn_pause.clicked.connect(self._on_pause)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_teleport.clicked.connect(self._on_teleport)
        self.btn_test.clicked.connect(self._on_test)
        self.btn_picker.clicked.connect(self._on_picker)

        self.signals.log.connect(self._append_log)
        self.signals.status_changed.connect(self._update_status)
        self.signals.stats_updated.connect(self._update_stats)

        # 全局快捷键
        QShortcut(QKeySequence("F6"), self).activated.connect(self._on_pause)
        QShortcut(QKeySequence("F7"), self).activated.connect(self._on_stop)
        QShortcut(QKeySequence("F8"), self).activated.connect(self._on_teleport)
        QShortcut(QKeySequence("F9"), self).activated.connect(self._on_test)
        QShortcut(QKeySequence("F10"), self).activated.connect(self._on_picker)

        # 定时刷新统计
        self._timer = QTimer()
        self._timer.timeout.connect(self._refresh_stats)
        self._timer.start(1000)

    # === 按钮事件 ===

    def _on_pause(self):
        if self.bot_runner:
            from bot.strategy import BotState
            if self.bot_runner.ctx.state == BotState.RUNNING:
                self.bot_runner.pause()
                self.btn_pause.setText("▶ 继续 (F6)")
                self.signals.status_changed.emit("🟡 已暂停")
            elif self.bot_runner.ctx.state == BotState.PAUSED:
                self.bot_runner.resume()
                self.btn_pause.setText("⏸ 暂停 (F6)")
                self.signals.status_changed.emit("🌀 传送中...")
            else:
                self.bot_runner.resume()
                self.btn_pause.setText("⏸ 暂停 (F6)")
                self.signals.status_changed.emit("🟢 运行中")

    def _on_stop(self):
        if self.bot_runner:
            self.bot_runner.stop()
        self._cleanup_teleport()
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_teleport.setEnabled(True)
        self.btn_test.setEnabled(True)
        self.btn_picker.setEnabled(True)
        self.btn_pause.setText("⏸ 暂停 (F6)")
        self.signals.status_changed.emit("🔴 已停止")

    def _on_teleport(self):
        """执行一次性传送任务"""
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.btn_teleport.setEnabled(False)
        self.btn_test.setEnabled(False)
        self.btn_picker.setEnabled(False)
        self.btn_pause.setText("⏸ 暂停 (F6)")
        self.signals.status_changed.emit("🌀 传送中...")

        from bot.strategy import BotRunner
        self.bot_runner = BotRunner()

        def _run():
            result = self.bot_runner.run_teleport_once()
            # 通过信号通知 GUI 更新
            self.signals.log.emit(
                f"传送完成: 共 {result['total']} 个魔力之源, "
                f"成功 {result['success']}, 失败 {result['failed']}"
            )

        def _on_done():
            # 恢复按钮状态
            self.btn_teleport.setEnabled(True)
            self.btn_test.setEnabled(True)
            self.btn_picker.setEnabled(True)
            self.signals.status_changed.emit("⚪ 就绪")

        self._bot_thread = threading.Thread(target=_run, daemon=True)
        self._bot_thread.start()
        # 用定时器检查线程是否完成
        self._teleport_timer = QTimer()
        self._teleport_timer.timeout.connect(
            lambda: self._check_teleport_done(_on_done)
        )
        self._teleport_timer.start(500)

    def _check_teleport_done(self, callback):
        """检查传送任务是否完成"""
        if self._bot_thread and not self._bot_thread.is_alive():
            self._teleport_timer.stop()
            callback()

    def _on_test(self):
        """测试：找到窗口后点击 3 次"""
        self.btn_test.setEnabled(False)
        self.btn_picker.setEnabled(False)
        self.signals.status_changed.emit("🧪 测试点击中...")

        from bot.strategy import BotRunner
        self.bot_runner = BotRunner()

        def _run():
            try:
                self.bot_runner.test_click()
            except Exception as e:
                self.signals.log.emit(f"测试异常: {e}")

        def _on_done():
            self.btn_test.setEnabled(True)
            self.btn_picker.setEnabled(True)
            self.signals.status_changed.emit("⚪ 就绪")

        self._bot_thread = threading.Thread(target=_run, daemon=True)
        self._bot_thread.start()
        self._test_timer = QTimer()
        self._test_timer.timeout.connect(
            lambda: self._check_test_done(_on_done)
        )
        self._test_timer.start(500)

    def _check_test_done(self, callback):
        """检查测试任务是否完成"""
        if self._bot_thread and not self._bot_thread.is_alive():
            self._test_timer.stop()
            callback()

    def _on_picker(self):
        """启动坐标采集器"""
        self.btn_picker.setEnabled(False)
        self.signals.status_changed.emit("📍 坐标采集中...")
        self.signals.log.emit("坐标采集器已启动，左键记录坐标，右键撤销，Esc 退出")

        from bot.coord_picker import CoordPicker
        self._coord_picker = CoordPicker()
        self._coord_picker.finished.connect(self._on_picker_done)

        if not self._coord_picker.start():
            self.signals.log.emit("❌ 未找到游戏窗口，坐标采集器启动失败")
            self._on_picker_done([])

    def _on_picker_done(self, points: list):
        """坐标采集完成"""
        self.btn_picker.setEnabled(True)
        self.signals.status_changed.emit("⚪ 就绪")

        if points:
            self.signals.log.emit(f"✅ 采集完成: 共 {len(points)} 个坐标点 (已复制到剪贴板)")
            for i, (x, y) in enumerate(points, 1):
                self.signals.log.emit(f"   点{i}: ({x}, {y})")
        else:
            self.signals.log.emit("坐标采集已取消")

    def _cleanup_teleport(self):
        """清理传送任务的定时器，防止 _on_done 回调覆盖停止后的按钮状态"""
        if hasattr(self, '_teleport_timer') and self._teleport_timer is not None:
            self._teleport_timer.stop()
            self._teleport_timer = None

    # === 信号处理 ===

    def _append_log(self, msg: str):
        self.log_area.append(msg)

    def _update_status(self, status: str):
        self.lbl_status.setText(status)

    def _update_stats(self, battles: int, runtime: float):
        self.lbl_battles.setText(f"{battles} 次")
        mins, secs = divmod(int(runtime), 60)
        self.lbl_runtime.setText(f"{mins:02d}:{secs:02d}")

    def _refresh_stats(self):
        if self.bot_runner and hasattr(self.bot_runner, 'ctx'):
            import time
            elapsed = time.time() - self.bot_runner.ctx.start_time if self.bot_runner.ctx.start_time else 0
            self._update_stats(self.bot_runner.ctx.battle_count, elapsed)


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 9))
    window = ControlPanel()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
