"""
屏幕截图与图像识别模块
负责截取游戏画面、模板匹配、OCR 文字识别
"""

import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pyautogui
from PIL import Image
from loguru import logger


def _get_root_dir() -> Path:
    """获取项目根目录，兼容开发环境和 PyInstaller 打包后的 exe"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后：优先用 _MEIPASS（--add-data 的资源目录）
        # 如果没有 _MEIPASS，则回退到 exe 所在目录
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    else:
        # 开发环境：screen.py → bot/ → 项目根
        return Path(__file__).resolve().parent.parent


ROOT_DIR = _get_root_dir()
TEMPLATES_DIR = ROOT_DIR / "assets" / "templates"

# 尝试导入 OCR（可选依赖）
try:
    import pytesseract
    HAS_OCR = True
except ImportError:
    HAS_OCR = False
    logger.warning("pytesseract 未安装，OCR 功能不可用")


class ScreenCapture:
    """屏幕截图工具"""

    def __init__(self, region: tuple | None = None):
        """
        Args:
            region: 截图区域 (left, top, width, height)，None 表示全屏
        """
        self.region = region

    def capture(self) -> np.ndarray:
        """截取屏幕区域，返回 BGR 格式的 numpy 数组"""
        img = pyautogui.screenshot(region=self.region)
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    def capture_gray(self) -> np.ndarray:
        """截取屏幕并转为灰度图"""
        return cv2.cvtColor(self.capture(), cv2.COLOR_BGR2GRAY)


class ImageMatcher:
    """图像模板匹配器"""

    def __init__(self, threshold: float = 0.8):
        """
        Args:
            threshold: 匹配置信度阈值 (0~1)，越高越严格
        """
        self.threshold = threshold

    @staticmethod
    def load_template(name: str) -> np.ndarray | None:
        """从 assets/templates 目录加载模板图片"""
        path = TEMPLATES_DIR / name
        if not path.exists():
            logger.error(f"模板文件不存在: {path}")
            return None
        return cv2.imread(str(path))

    def match(self, screenshot: np.ndarray, template: np.ndarray) -> list[tuple[int, int, float]]:
        """
        在截图中匹配模板，返回匹配到的中心坐标列表
        Returns:
            [(x, y, confidence), ...]
        """
        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= self.threshold)
        h, w = template.shape[:2]

        # 去重：使用非极大值抑制
        matches = []
        for pt in zip(*locations[::-1]):
            confidence = result[pt[1], pt[0]]
            matches.append((pt[0] + w // 2, pt[1] + h // 2, confidence))

        return self._nms(matches)

    def find_one(self, template_name: str, screenshot: np.ndarray | None = None, threshold: float | None = None) -> tuple[int, int] | None:
        """
        快速查找单个模板，返回中心坐标
        如果没传截图则自动截全屏
        Args:
            threshold: 临时覆盖置信度阈值，None 则使用实例默认值
        """
        if screenshot is None:
            screenshot = ScreenCapture().capture()

        template = self.load_template(template_name)
        if template is None:
            return None

        # 临时覆盖阈值
        original = self.threshold
        if threshold is not None:
            self.threshold = threshold
        try:
            matches = self.match(screenshot, template)
        finally:
            self.threshold = original

        if matches:
            x, y, conf = matches[0]
            logger.info(f"找到 [{template_name}] 位置: ({x}, {y}) 置信度: {conf:.2f}")
            return (x, y)
        return None

    def find_all(self, template_name: str, screenshot: np.ndarray | None = None) -> list[tuple[int, int, float]]:
        """查找所有匹配的模板"""
        if screenshot is None:
            screenshot = ScreenCapture().capture()

        template = self.load_template(template_name)
        if template is None:
            return []

        return self.match(screenshot, template)

    def wait_for(self, template_name: str, timeout: float = 10.0, interval: float = 0.5) -> tuple[int, int] | None:
        """
        等待某个画面元素出现
        Args:
            template_name: 模板文件名
            timeout: 超时时间（秒）
            interval: 检测间隔（秒）
        Returns:
            中心坐标，超时返回 None
        """
        matcher = ImageMatcher(threshold=self.threshold)
        sc = ScreenCapture()
        start = time.time()

        while time.time() - start < timeout:
            result = matcher.find_one(template_name, sc.capture())
            if result:
                return result
            time.sleep(interval)

        logger.warning(f"等待 [{template_name}] 超时 ({timeout}s)")
        return None

    @staticmethod
    def _nms(matches: list[tuple[int, int, float]], min_distance: int = 10) -> list[tuple[int, int, float]]:
        """简单的非极大值抑制，去除重复匹配"""
        if not matches:
            return []
        matches = sorted(matches, key=lambda m: m[2], reverse=True)
        kept = []
        for m in matches:
            if all(abs(m[0] - k[0]) > min_distance or abs(m[1] - k[1]) > min_distance for k in kept):
                kept.append(m)
        return kept


class OCR:
    """OCR 文字识别"""

    @staticmethod
    def read_text(image: np.ndarray, lang: str = "chi_sim") -> str:
        """
        识别图片中的文字
        Args:
            image: 图片 numpy 数组
            lang: 语言，默认简体中文
        """
        if not HAS_OCR:
            logger.warning("OCR 不可用，请安装 pytesseract 和 Tesseract-OCR")
            return ""
        # 预处理：灰度 + 二值化
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
        return pytesseract.image_to_string(binary, lang=lang).strip()

    @staticmethod
    def read_region(region: tuple, lang: str = "chi_sim") -> str:
        """截取指定区域并识别文字"""
        sc = ScreenCapture(region=region)
        return OCR.read_text(sc.capture(), lang=lang)
