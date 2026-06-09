"""
控制面板 GUI
提供一个简单的 PyQt5 界面来控制机器人
"""

import sys
import threading

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QGroupBox,
    QShortcut
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QKeySequence, QPainter, QColor, QPen, QPixmap, QPainterPath

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


class MiniMap(QWidget):
    """小地图组件，显示游戏窗口小地图实时截图"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self._pixmap: QPixmap | None = None
        self._player_pos = None  # (x, y) 相对百分比坐标

    def set_image(self, pixmap: QPixmap):
        """更新小地图截图"""
        self._pixmap = pixmap
        self.update()

    def set_player_pos(self, x_pct: float, y_pct: float):
        """设置玩家位置（百分比坐标，0.0~1.0）"""
        self._player_pos = (x_pct, y_pct)
        self.update()

    def clear_position(self):
        """清除玩家位置"""
        self._player_pos = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()

        # 背景
        painter.fillRect(0, 0, w, h, QColor(26, 26, 46))

        # 圆形区域（取正方形内切圆，留 4px 边距给边框）
        diameter = min(w, h) - 4
        cx = (w - diameter) // 2
        cy = (h - diameter) // 2

        if self._pixmap and not self._pixmap.isNull():
            # 拉伸填充正方形（截取区域已是正方形，无变形）
            scaled = self._pixmap.scaled(
                diameter, diameter, Qt.IgnoreAspectRatio, Qt.SmoothTransformation
            )

            # 圆形裁剪绘制
            painter.save()
            clip_path = QPainterPath()
            clip_path.addEllipse(cx, cy, diameter, diameter)
            painter.setClipPath(clip_path)
            painter.drawPixmap(cx, cy, scaled)
            painter.restore()

            # 辅助线（在截图之上叠加）
            painter.save()
            painter.setClipPath(clip_path)
            self._draw_guide_lines(painter, cx, cy, diameter)
            painter.restore()
        else:
            painter.setPen(QColor(100, 100, 120))
            font = painter.font()
            font.setPointSize(10)
            painter.setFont(font)
            painter.drawText(0, 0, w, h, Qt.AlignCenter, "等待游戏窗口…")

        # 圆形边框
        painter.setPen(QPen(QColor(80, 80, 100), 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(cx, cy, diameter, diameter)

        # 玩家位置（红点叠加）
        if self._player_pos is not None:
            px = int(self._player_pos[0] * w)
            py = int(self._player_pos[1] * h)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 50, 50, 80))
            painter.drawEllipse(px - 8, py - 8, 16, 16)
            painter.setBrush(QColor(255, 60, 60))
            painter.drawEllipse(px - 4, py - 4, 8, 8)
            painter.setBrush(QColor(255, 180, 180))
            painter.drawEllipse(px - 1, py - 1, 2, 2)

        painter.end()

    def _draw_guide_lines(self, painter: QPainter, cx: int, cy: int, diameter: int):
        """绘制圆形小地图上的方向辅助线（十字线 + 对角线 + 方位标注）"""
        r = diameter / 2
        center_x = cx + r
        center_y = cy + r
        margin = r * 0.08  # 标注距边缘的距离

        # 十字线（半透明白）
        pen = QPen(QColor(255, 255, 255, 35), 0.8)
        painter.setPen(pen)
        painter.drawLine(int(center_x), cy, int(center_x), cy + diameter)
        painter.drawLine(cx, int(center_y), cx + diameter, int(center_y))

        # 对角线（更淡）
        pen = QPen(QColor(255, 255, 255, 20), 0.6)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        d45 = r * 0.707  # sin(45°) * r
        painter.drawLine(int(center_x - d45), int(center_y - d45),
                         int(center_x + d45), int(center_y + d45))
        painter.drawLine(int(center_x - d45), int(center_y + d45),
                         int(center_x + d45), int(center_y - d45))

        # 方位标注
        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, 100))

        # N S W E
        painter.drawText(int(center_x - 6), cy + int(margin), "N")
        painter.drawText(int(center_x - 6), cy + diameter - int(margin) + 8, "S")
        painter.drawText(cx + int(margin) - 4, int(center_y) + 4, "W")
        painter.drawText(cx + diameter - int(margin) - 6, int(center_y) + 4, "E")


class ControlPanel(QMainWindow):
    """洛克王国助手 - 控制面板"""

    WINDOW_TITLE = "洛克王国助手"
    WINDOW_SIZE = (420, 700)

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

        # === 小地图 ===
        minimap_group = QGroupBox("🗺️ 小地图")
        minimap_layout = QVBoxLayout(minimap_group)
        self.minimap = MiniMap()
        minimap_layout.addWidget(self.minimap)
        layout.addWidget(minimap_group)

        # 启动小地图实时截图
        self._start_minimap_capture()

        # === 日志输出 ===
        log_group = QGroupBox("📋 运行日志")
        log_layout = QVBoxLayout(log_group)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(220)
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

        # 全局快捷键
        QShortcut(QKeySequence("F6"), self).activated.connect(self._on_pause)
        QShortcut(QKeySequence("F7"), self).activated.connect(self._on_stop)
        QShortcut(QKeySequence("F8"), self).activated.connect(self._on_teleport)
        QShortcut(QKeySequence("F9"), self).activated.connect(self._on_test)
        QShortcut(QKeySequence("F10"), self).activated.connect(self._on_picker)

    # === 小地图实时截图 ===

    def _start_minimap_capture(self):
        """启动小地图定时截图"""
        from bot.shade import MINI_MAP_COORDS
        from bot.input import GameWindow

        # 计算小地图圆心和直径，截取正方形区域（确保与圆形裁剪完美对齐）
        xs = [p[0] for p in MINI_MAP_COORDS]
        ys = [p[1] for p in MINI_MAP_COORDS]
        center_x = (min(xs) + max(xs)) // 2
        center_y = (min(ys) + max(ys)) // 2
        size = max(max(xs) - min(xs), max(ys) - min(ys)) - 5  # 游戏地图外扩 5px
        # 正方形截取区域 (left, top, width, height)
        self._minimap_rect = (
            center_x - size // 2,
            center_y - size // 2,
            size,
            size,
        )

        self._minimap_window = GameWindow()
        self._minimap_frame = 0  # 帧计数，用于降频更新客户区
        self._minimap_timer = QTimer()
        self._minimap_timer.timeout.connect(self._capture_minimap)
        self._minimap_timer.start(25)  # 每 25ms 刷新 (~40 FPS)

    def _capture_minimap(self):
        """截取游戏窗口小地图区域（Qt 原生截屏，零拷贝）"""
        try:
            # 找窗口（缓存：只有 hwnd 失效才重新查找）
            if not self._minimap_window.is_valid():
                if not self._minimap_window.find():
                    return

            # 每 30 帧更新一次客户区坐标（降低 Win32 API 开销）
            self._minimap_frame += 1
            if self._minimap_frame % 30 == 0:
                self._minimap_window._update_client_region()

            rx, ry, rw, rh = self._minimap_rect
            sx, sy = self._minimap_window.client_to_screen(rx, ry)

            # Qt 原生屏幕抓取 → 直接得到 QPixmap（无 PIL/numpy 中间层）
            screen = QApplication.primaryScreen()
            if screen:
                pixmap = screen.grabWindow(0, sx, sy, rw, rh)
                self.minimap.set_image(pixmap)

        except Exception:
            pass

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

def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 9))
    window = ControlPanel()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
