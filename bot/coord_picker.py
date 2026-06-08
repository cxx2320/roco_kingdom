"""
坐标采集器 - 透明遮罩覆盖游戏窗口，手动采集坐标点
用于获取地图中魔力之源的坐标，数据可直接对接到代码中使用

快捷键：
    鼠标左键    - 记录当前坐标
    鼠标右键    - 删除上一个记录点
    Esc         - 退出并复制结果到剪贴板
    Ctrl+C      - 复制当前结果
    Space       - 切换坐标显示格式（窗口相对 / 屏幕绝对）
"""

import json
import time
from dataclasses import dataclass, field

from PyQt5.QtWidgets import (
    QWidget, QApplication, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QCheckBox
)
from PyQt5.QtCore import (
    Qt, QTimer, QPoint, pyqtSignal, QObject
)
from PyQt5.QtGui import (
    QPainter, QPen, QColor, QFont, QFontMetrics, QMouseEvent,
    QKeyEvent
)


# ============================================================
# 配置
# ============================================================

@dataclass
class PickerConfig:
    """采集器配置"""
    crosshair_size: int = 20          # 十字线半径
    crosshair_color: str = "#00FF00"  # 十字线颜色
    crosshair_width: int = 2          # 十字线宽度
    text_color: str = "#00FF00"       # 文字颜色
    point_color: str = "#FF4444"      # 已记录点颜色
    bg_alpha: int = 30                # 背景透明度 0-255
    font_size: int = 11               # 字体大小


# ============================================================
# 信号
# ============================================================

class PickerSignals(QObject):
    """线程间通信信号"""
    finished = pyqtSignal(list)       # 采集完成，携带坐标列表
    point_added = pyqtSignal(tuple)   # 新增坐标点
    point_removed = pyqtSignal()      # 移除坐标点


# ============================================================
# 遮罩窗口
# ============================================================

class CoordOverlay(QWidget):
    """透明遮罩窗口，覆盖在游戏窗口客户区上方"""

    def __init__(
        self,
        hwnd: int,
        client_region: tuple,  # (left, top, width, height)
        config: PickerConfig | None = None,
    ):
        super().__init__()
        self.hwnd = hwnd
        self.client_region = client_region
        self.cfg = config or PickerConfig()
        self.signals = PickerSignals()

        # 坐标记录
        self.points: list[tuple[int, int]] = []
        self._mouse_pos = QPoint(0, 0)
        self._show_screen_coords = False  # False=窗口相对坐标, True=屏幕绝对坐标

        self._setup_window()
        self._start_tracking()

    # ---- 窗口设置 ----

    def _setup_window(self):
        """初始化窗口属性"""
        left, top, w, h = self.client_region

        self.setWindowTitle("坐标采集器")
        self.setGeometry(left, top, w, h)

        # 无边框 + 置顶 + 透明背景
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput  # 点击穿透
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # 允许接收鼠标事件（用于采集坐标）
        # 注意：WindowTransparentForInput 会屏蔽鼠标事件
        # 这里先设为穿透，Acquire 时才启用交互
        self._interactive = False
        self.setMouseTracking(True)

    def enable_interaction(self):
        """启用鼠标交互（变为可点击）"""
        self._interactive = True
        # 去掉点击穿透，允许接收鼠标事件
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.show()  # 重新 show 使 windowFlags 生效

    def disable_interaction(self):
        """禁用鼠标交互（点击穿透）"""
        self._interactive = False
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
        )
        self.show()

    # ---- 位置跟踪 ----

    def _start_tracking(self):
        """启动定时器跟踪鼠标位置和窗口位置"""
        self._tracker = QTimer(self)
        self._tracker.timeout.connect(self._sync_position)
        self._tracker.start(50)  # 20 FPS

    def _sync_position(self):
        """同步遮罩窗口与游戏窗口位置，并跟踪鼠标"""
        try:
            import win32gui
            # 更新游戏窗口位置
            rect = win32gui.GetWindowRect(self.hwnd)
            if rect:
                win_left, win_top, win_right, win_bottom = rect
                # 获取客户区屏幕坐标
                cl, ct, cr, cb = win32gui.GetClientRect(self.hwnd)
                cw, ch = cr - cl, cb - ct
                pt = win32gui.ClientToScreen(self.hwnd, (cl, ct))
                new_region = (pt[0], pt[1], cw, ch)

                if new_region != self.client_region:
                    self.client_region = new_region
                    left, top, w, h = new_region
                    self.setGeometry(left, top, w, h)

            # 获取全局鼠标位置
            import ctypes
            from ctypes import wintypes
            pt = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            self._mouse_pos = QPoint(pt.x, pt.y)
            self.update()  # 触发重绘
        except Exception:
            pass

    # ---- 绘制 ----

    def paintEvent(self, event):
        """绘制十字线、坐标文字和已记录点"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 半透明暗色背景
        bg = QColor(0, 0, 0, self.cfg.bg_alpha)
        painter.fillRect(self.rect(), bg)

        # 鼠标相对于本窗口的位置
        local_x = self._mouse_pos.x() - self.client_region[0]
        local_y = self._mouse_pos.y() - self.client_region[1]
        w, h = self.width(), self.height()

        # 只在鼠标在遮罩区域内时绘制
        if 0 <= local_x <= w and 0 <= local_y <= h:
            self._draw_crosshair(painter, local_x, local_y)
            self._draw_coord_text(painter, local_x, local_y, w, h)

        # 绘制已记录的点
        self._draw_points(painter)

        # 绘制顶部提示栏
        self._draw_toolbar(painter, w)

    def _draw_crosshair(self, painter: QPainter, x: int, y: int):
        """绘制十字准线"""
        pen = QPen(QColor(self.cfg.crosshair_color), self.cfg.crosshair_width)
        painter.setPen(pen)
        cs = self.cfg.crosshair_size

        # 十字线（带缺口风格更直观）
        painter.drawLine(x - cs, y, x - cs // 3, y)
        painter.drawLine(x + cs // 3, y, x + cs, y)
        painter.drawLine(x, y - cs, x, y - cs // 3)
        painter.drawLine(x, y + cs // 3, x, y + cs)

        # 中心点
        painter.setPen(QPen(QColor("#FF0000"), 3))
        painter.drawPoint(x, y)

    def _draw_coord_text(self, painter: QPainter, x: int, y: int, w: int, h: int):
        """绘制坐标文字"""
        font = QFont("Consolas", self.cfg.font_size, QFont.Bold)
        painter.setFont(font)

        if self._show_screen_coords:
            coord_text_parts = [
                f"屏幕: ({self._mouse_pos.x()}, {self._mouse_pos.y()})",
            ]
        else:
            coord_text_parts = [
                f"窗口: ({x}, {y})",
            ]
        coord_text_parts.append(f"({w}x{h})")
        coord_text = "  ".join(coord_text_parts)

        # 文字背景
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(coord_text) + 8
        text_h = fm.height() + 4
        tx = x + 25
        ty = y + 20

        # 边界检查
        if tx + text_w > w:
            tx = x - text_w - 25
        if ty + text_h > h:
            ty = y - text_h - 25

        painter.fillRect(tx - 2, ty - 2, text_w, text_h, QColor(0, 0, 0, 180))
        painter.setPen(QColor(self.cfg.text_color))
        painter.drawText(tx + 2, ty + fm.ascent(), coord_text)

    def _draw_points(self, painter: QPainter):
        """绘制已记录的点"""
        if not self.points:
            return

        pen = QPen(QColor(self.cfg.point_color), 2)
        painter.setPen(pen)

        for i, (px, py) in enumerate(self.points):
            # 小十字
            s = 6
            painter.drawLine(px - s, py, px + s, py)
            painter.drawLine(px, py - s, px, py + s)

            # 序号
            font = QFont("Consolas", 8, QFont.Bold)
            painter.setFont(font)
            painter.setPen(QColor(self.cfg.point_color))
            painter.drawText(px + 8, py + 4, str(i + 1))

            # 恢复画笔
            painter.setPen(pen)

    def _draw_toolbar(self, painter: QPainter, w: int):
        """绘制顶部提示信息栏"""
        font = QFont("Consolas", 9)
        painter.setFont(font)

        hints = [
            "左键=记录 | 右键=撤销 | Esc=退出复制 | Space=切换坐标",
            f"已记录: {len(self.points)} 点 | {'窗口相对' if not self._show_screen_coords else '屏幕绝对'}",
        ]

        line_h = 18
        for i, hint in enumerate(hints):
            y = 6 + i * line_h
            fm = QFontMetrics(font)
            text_w = fm.horizontalAdvance(hint) + 12

            painter.fillRect(w // 2 - text_w // 2, y - 2, text_w, line_h, QColor(0, 0, 0, 160))
            painter.setPen(QColor("#AAAAAA"))
            painter.drawText(w // 2 - text_w // 2 + 6, y + fm.ascent() - 2, hint)

    # ---- 鼠标事件 ----

    def mousePressEvent(self, event: QMouseEvent):
        """点击采集坐标"""
        if not self._interactive:
            return

        if event.button() == Qt.LeftButton:
            # 记录窗口相对坐标
            self.points.append((event.x(), event.y()))
            self.signals.point_added.emit((event.x(), event.y()))
            self.update()

        elif event.button() == Qt.RightButton:
            if self.points:
                self.points.pop()
                self.signals.point_removed.emit()
                self.update()

    # ---- 键盘事件 ----

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self._finish()
        elif event.key() == Qt.Key_Space:
            self._show_screen_coords = not self._show_screen_coords
            self.update()
        elif event.key() == Qt.Key_C and event.modifiers() == Qt.ControlModifier:
            self._copy_to_clipboard()
        else:
            super().keyPressEvent(event)

    def _finish(self):
        """退出并复制结果"""
        self._copy_to_clipboard()
        self._tracker.stop()
        self.signals.finished.emit(list(self.points))
        self.close()

    def _copy_to_clipboard(self):
        """将坐标复制到剪贴板（Python 代码格式）"""
        if not self.points:
            return

        # 生成可直接粘贴到代码中的坐标列表
        lines = ["# 魔力之源坐标 (窗口客户区相对坐标)", "MAGIC_FOUNTAIN_COORDS = ["]
        for i, (x, y) in enumerate(self.points):
            comment = f"  # 魔力之源 {i+1}"
            lines.append(f"    ({x}, {y}),{comment}")
        lines.append("]")

        code = "\n".join(lines)
        clipboard = QApplication.clipboard()
        clipboard.setText(code)


# ============================================================
# 采集器控制器
# ============================================================

class CoordPicker(QObject):
    """
    坐标采集器控制器
    负责查找游戏窗口 → 创建遮罩 → 管理采集流程
    """

    finished = pyqtSignal(list)  # 采集完成信号

    def __init__(self, game_title: str = "洛克王国：世界"):
        super().__init__()
        self.game_title = game_title
        self.overlay: CoordOverlay | None = None

    def start(self) -> bool:
        """启动采集器，返回是否成功"""
        import win32gui

        # 查找游戏窗口
        hwnd = self._find_window(self.game_title)
        if not hwnd:
            return False

        # 获取客户区
        cl, ct, cr, cb = win32gui.GetClientRect(hwnd)
        cw, ch = cr - cl, cb - ct
        pt = win32gui.ClientToScreen(hwnd, (cl, ct))
        client_region = (pt[0], pt[1], cw, ch)

        # 创建遮罩窗口
        self.overlay = CoordOverlay(hwnd, client_region)
        self.overlay.signals.finished.connect(self._on_finished)

        # 延迟启用交互（先让用户看到遮罩，2秒后变为可交互）
        self.overlay.show()

        def _enable():
            if self.overlay:
                self.overlay.enable_interaction()

        from PyQt5.QtCore import QTimer
        QTimer.singleShot(800, _enable)

        return True

    @staticmethod
    def _find_window(title_substring: str) -> int | None:
        """查找窗口句柄"""
        import win32gui

        result: list[int] = []

        def callback(hwnd, _windows):
            if win32gui.IsWindowVisible(hwnd):
                text = win32gui.GetWindowText(hwnd)
                if text and title_substring in text:
                    _windows.append(hwnd)

        win32gui.EnumWindows(callback, result)
        return result[0] if result else None

    def _on_finished(self, points: list):
        """采集完成"""
        self.finished.emit(points)
        self.overlay = None

    def stop(self):
        """强制停止采集"""
        if self.overlay:
            self.overlay._finish()
