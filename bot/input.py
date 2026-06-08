"""
键鼠模拟模块
使用 interception-python 内核级输入驱动（首选）
硬件层模拟，不受 UIPI 限制，不被反作弊检测
驱动不可用时自动回退 SendInput
"""

import random
import time

from loguru import logger

# === 尝试加载 Interception 驱动 ===

try:
    import interception

    interception.auto_capture_devices()
    _HAS_INTERCEPTION = True
    logger.info("Interception 驱动已就绪（内核级输入）")
except Exception as e:
    _HAS_INTERCEPTION = False
    logger.warning(f"Interception 驱动不可用: {e}")
    logger.warning("将回退到 SendInput 方案")


class Mouse:
    """鼠标操作（interception / SendInput 自动切换）"""

    @staticmethod
    def click_screen(x: int, y: int, clicks: int = 1) -> bool:
        """屏幕坐标点击"""
        logger.debug(f"点击 屏幕({x}, {y}) x{clicks}")
        if _HAS_INTERCEPTION:
            return _click_interception(x, y, clicks)
        else:
            return _click_sendinput(x, y, clicks)

    @staticmethod
    def click_window_relative(hwnd: int, x: int, y: int, clicks: int = 1) -> bool:
        """窗口客户区相对坐标点击 → 屏幕坐标"""
        try:
            import win32gui
            pt = win32gui.ClientToScreen(hwnd, (x, y))
            return Mouse.click_screen(pt[0], pt[1], clicks)
        except Exception as e:
            logger.error(f"坐标转换失败: {e}")
            return False

    @staticmethod
    def move(x: int, y: int) -> None:
        """移动光标到屏幕坐标"""
        if _HAS_INTERCEPTION:
            interception.move_to(x, y)
        else:
            import ctypes
            ctypes.windll.user32.SetCursorPos(x, y)

    @staticmethod
    def drag(screen_start_x: int, screen_start_y: int, screen_end_x: int, screen_end_y: int, steps: int = 40, step_delay: float = 0.005) -> None:
        """鼠标拖拽：从起始屏幕坐标拖到结束屏幕坐标"""
        logger.debug(f"拖拽 屏幕({screen_start_x},{screen_start_y}) → ({screen_end_x},{screen_end_y})")
        if _HAS_INTERCEPTION:
            _drag_interception(screen_start_x, screen_start_y, screen_end_x, screen_end_y, steps, step_delay)
        else:
            _drag_sendinput(screen_start_x, screen_start_y, screen_end_x, screen_end_y, steps, step_delay)

    @staticmethod
    def drag_window_relative(hwnd: int, start_x: int, start_y: int, end_x: int, end_y: int, steps: int = 30, step_delay: float = 0.005) -> None:
        """窗口客户区相对坐标拖拽"""
        try:
            import win32gui
            s = win32gui.ClientToScreen(hwnd, (start_x, start_y))
            e = win32gui.ClientToScreen(hwnd, (end_x, end_y))
            Mouse.drag(s[0], s[1], e[0], e[1], steps, step_delay)
        except Exception as e:
            logger.error(f"拖拽坐标转换失败: {e}")


class Keyboard:
    """键盘操作（interception / SendInput 自动切换）"""

    @classmethod
    def press(cls, key: str, times: int = 1, interval: float = 0.05) -> None:
        """按下一个键"""
        if _HAS_INTERCEPTION:
            for _ in range(times):
                interception.press(key)
                if times > 1:
                    time.sleep(interval)
            logger.debug(f"interception 按键 [{key}]")
        else:
            _sendinput_key_press(key, times, interval)

    @staticmethod
    def type_text(text: str, interval: float = 0.05) -> None:
        """输入文字"""
        import pyautogui
        pyautogui.typewrite(text, interval=interval)

    @staticmethod
    def hotkey(*keys: str) -> None:
        """组合键"""
        import pyautogui
        pyautogui.hotkey(*keys)


# === 回退：SendInput 实现 ===

def _click_sendinput(x: int, y: int, clicks: int) -> bool:
    try:
        import ctypes
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        ctypes.windll.user32.SetCursorPos(x, y)
        time.sleep(0.02)
        for _ in range(clicks):
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
            time.sleep(0.03)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, x, y, 0, 0)
            if clicks > 1:
                time.sleep(0.08)
        return True
    except Exception as e:
        logger.error(f"SendInput 失败: {e}")
        return False


def _click_interception(x: int, y: int, clicks: int) -> bool:
    try:
        for _ in range(clicks):
            interception.click(x, y)
            if clicks > 1:
                time.sleep(0.08)
        return True
    except Exception as e:
        logger.error(f"interception 失败，回退 SendInput: {e}")
        return _click_sendinput(x, y, clicks)


def _sendinput_key_press(key: str, times: int, interval: float) -> None:
    import ctypes
    VK = {
        'm': 0x4D, 'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45,
        'f': 0x46, 'g': 0x47, 'h': 0x48, 'i': 0x49, 'j': 0x4A,
        'k': 0x4B, 'l': 0x4C, 'n': 0x4E, 'o': 0x4F, 'p': 0x50,
        'q': 0x51, 'r': 0x52, 's': 0x53, 't': 0x54, 'u': 0x55,
        'v': 0x56, 'w': 0x57, 'x': 0x58, 'y': 0x59, 'z': 0x5A,
        '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34,
        '5': 0x35, '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,
        'enter': 0x0D, 'tab': 0x09, 'esc': 0x1B, 'space': 0x20,
        'backspace': 0x08, 'delete': 0x2E,
        'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
    }
    vk = VK.get(key.lower())
    if vk:
        for _ in range(times):
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(vk, 0, 0x0002, 0)
            if times > 1:
                time.sleep(interval)
    else:
        import pyautogui
        for _ in range(times):
            pyautogui.press(key)
            time.sleep(interval)


def _drag_sendinput(sx: int, sy: int, ex: int, ey: int, steps: int, step_delay: float) -> None:
    """SendInput 鼠标拖拽：长按左键 + 逐步移动"""
    import ctypes
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004

    # 移到起点
    ctypes.windll.user32.SetCursorPos(sx, sy)
    time.sleep(0.05)

    # 长按左键
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.03)

    # 逐步移动到终点（按住左键时 SetCursorPos 产生 WM_MOUSEMOVE，标准拖拽行为）
    for i in range(1, steps + 1):
        t = i / steps
        cx = int(sx + (ex - sx) * t)
        cy = int(sy + (ey - sy) * t)
        ctypes.windll.user32.SetCursorPos(cx, cy)
        time.sleep(step_delay)

    # 松开左键
    time.sleep(0.03)
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def _drag_interception(sx: int, sy: int, ex: int, ey: int, steps: int, step_delay: float) -> None:
    """Interception 内核级鼠标拖拽：长按左键 + 逐步移动"""
    # 移到起点
    interception.move_to(sx, sy)
    time.sleep(0.05)

    # 长按左键
    interception.mouse_down('left')
    time.sleep(0.03)

    # 逐步移动到终点（使用绝对坐标，比 move_relative 更可靠）
    for i in range(1, steps + 1):
        t = i / steps
        cx = int(sx + (ex - sx) * t)
        cy = int(sy + (ey - sy) * t)
        interception.move_to(cx, cy)
        time.sleep(step_delay)

    # 松开左键
    time.sleep(0.03)
    interception.mouse_up('left')


# === 游戏窗口管理 ===


class GameWindow:
    """游戏窗口管理"""

    def __init__(self, title: str = "洛克王国：世界"):
        self.title = title
        self.hwnd = None
        self.rect = None
        self.client_region = None
        self.client_size = (0, 0)

    def find(self) -> bool:
        try:
            import win32gui

            def callback(hwnd, windows):
                if win32gui.IsWindowVisible(hwnd):
                    text = win32gui.GetWindowText(hwnd)
                    if text and self.title in text:
                        windows.append((hwnd, text))

            windows: list = []
            win32gui.EnumWindows(callback, windows)
            if windows:
                self.hwnd = windows[0][0]
                self.rect = win32gui.GetWindowRect(self.hwnd)
                self._update_client_region()
                logger.info(f"找到窗口: [{windows[0][1]}] 窗口: {self.rect} 客户区: {self.client_size}")
                return True
            else:
                logger.warning(f"未找到标题含 [{self.title}] 的窗口")
                return False
        except ImportError:
            logger.error("pywin32 未安装")
            return False

    def find_and_focus(self) -> bool:
        if not self.find():
            return False
        return self.focus()

    def focus(self) -> bool:
        if not self.hwnd:
            return False
        try:
            import win32gui
            import win32con
            if win32gui.IsIconic(self.hwnd):
                win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
                time.sleep(0.2)
            win32gui.SetForegroundWindow(self.hwnd)
            time.sleep(0.3)
            self._update_client_region()
            return True
        except Exception as e:
            logger.error(f"激活窗口失败: {e}")
            return False

    def _update_client_region(self):
        if not self.hwnd:
            return
        try:
            import win32gui
            left, top, right, bottom = win32gui.GetClientRect(self.hwnd)
            w, h = right - left, bottom - top
            self.client_size = (w, h)
            pt = win32gui.ClientToScreen(self.hwnd, (left, top))
            self.client_region = (pt[0], pt[1], w, h)
        except Exception as e:
            logger.error(f"获取客户区失败: {e}")

    def is_valid(self) -> bool:
        if not self.hwnd:
            return False
        try:
            import win32gui
            return win32gui.IsWindow(self.hwnd)
        except Exception:
            return False

    def client_to_screen(self, x: int, y: int) -> tuple[int, int]:
        if not self.client_region:
            return (x, y)
        return (self.client_region[0] + x, self.client_region[1] + y)

    def screen_to_client(self, screen_x: int, screen_y: int) -> tuple[int, int]:
        if not self.client_region:
            return (screen_x, screen_y)
        return (screen_x - self.client_region[0], screen_y - self.client_region[1])

    def get_screenshot_region(self) -> tuple[int, int, int, int] | None:
        return self.client_region
