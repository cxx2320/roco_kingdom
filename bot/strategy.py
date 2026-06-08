"""
策略模块
定义自动化脚本的行为逻辑：刷图、战斗、回血等策略

所有坐标均为【窗口客户区相对坐标】，自动转换为屏幕绝对坐标
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto

from loguru import logger

from .screen import ImageMatcher, ScreenCapture
from .input import Mouse, Keyboard, GameWindow


class BotState(Enum):
    """机器人状态"""
    IDLE = auto()        # 空闲
    RUNNING = auto()     # 运行中
    PAUSED = auto()      # 暂停
    STOPPED = auto()     # 已停止
    ERROR = auto()       # 异常


@dataclass
class BotContext:
    """机器人的运行上下文，在各策略间共享"""
    state: BotState = BotState.IDLE
    window: GameWindow = field(default_factory=GameWindow)
    matcher: ImageMatcher = field(default_factory=ImageMatcher)
    capture: ScreenCapture | None = None  # 绑定了窗口区域的截图器

    # 统计
    battle_count: int = 0
    start_time: float = 0.0

    # 窗口尺寸（启动后填入）
    win_w: int = 0
    win_h: int = 0

    def click(self, x: int, y: int) -> None:
        """在窗口客户区内点击（SendInput 硬件级，不受 UIPI 限制）"""
        if self.window.hwnd:
            Mouse.click_window_relative(self.window.hwnd, x, y)
        else:
            sx, sy = self.window.client_to_screen(x, y)
            Mouse.click_screen(sx, sy)

    def take_screenshot(self):
        """截取游戏窗口画面"""
        if self.capture is None:
            return ScreenCapture().capture()
        return self.capture.capture()


class BaseStrategy(ABC):
    """策略基类"""

    def __init__(self, ctx: BotContext):
        self.ctx = ctx

    @abstractmethod
    def should_trigger(self) -> bool:
        """判断是否应该触发该策略"""
        ...

    @abstractmethod
    def execute(self) -> bool:
        """执行策略，返回 True 表示执行成功"""
        ...

    def run(self) -> bool:
        """执行策略的包装，带异常处理"""
        try:
            if self.should_trigger():
                return self.execute()
        except Exception as e:
            logger.error(f"策略 [{self.__class__.__name__}] 出错: {e}")
        return False

    def find_in_window(self, template_name: str, screenshot=None) -> tuple[int, int] | None:
        """在游戏窗口中查找模板，返回窗口相对坐标"""
        if screenshot is None:
            screenshot = self.ctx.take_screenshot()
        result = self.ctx.matcher.find_one(template_name, screenshot)
        if result:
            # find_one 返回屏幕坐标，转为窗口相对坐标
            rx, ry = self.ctx.window.screen_to_client(*result)
            return (rx, ry)
        return None


class BattleStrategy(BaseStrategy):
    """
    战斗策略
    检测战斗场景 → 自动选择技能 → 结束
    """

    BATTLE_SCENE = "battle_scene.png"   # 战斗场景特征
    SKILL_BTN = "skill_1.png"           # 技能1按钮
    VICTORY = "victory.png"             # 胜利画面

    def should_trigger(self) -> bool:
        return self.find_in_window(self.BATTLE_SCENE) is not None

    def execute(self) -> bool:
        logger.info(">>> 进入战斗策略")
        while self.ctx.state == BotState.RUNNING:
            screenshot = self.ctx.take_screenshot()

            # 检查胜利
            if self.ctx.matcher.find_one(self.VICTORY, screenshot) is not None:
                logger.info("战斗胜利！")
                self.ctx.battle_count += 1
                time.sleep(1)
                # 点击窗口中央关闭胜利画面
                self.ctx.click(self.ctx.win_w // 2, self.ctx.win_h // 2)
                return True

            # 使用技能
            skill_pos = self.find_in_window(self.SKILL_BTN, screenshot)
            if skill_pos:
                self.ctx.click(*skill_pos)
                time.sleep(0.5)

            time.sleep(1.5)

        return True


class ExploreStrategy(BaseStrategy):
    """
    探索/刷图策略
    在场景中移动并触发战斗
    坐标均为窗口客户区内的相对坐标
    """

    def should_trigger(self) -> bool:
        return (
            self.ctx.state == BotState.RUNNING
            and self.find_in_window(BattleStrategy.BATTLE_SCENE) is None
        )

    def execute(self) -> bool:
        logger.info(">>> 进入探索/刷图策略")

        w, h = self.ctx.win_w, self.ctx.win_h
        # 移动点：窗口的相对位置（基于窗口百分比）
        positions = [
            (w // 6, h // 2),        # 左
            (w * 5 // 6, h // 2),    # 右
            (w // 2, h * 3 // 4),    # 下
            (w // 2, h // 4),        # 上
        ]

        for pos in positions:
            if self.ctx.state != BotState.RUNNING:
                break
            self.ctx.click(*pos)
            time.sleep(0.2)
            # 检查是否进入战斗
            if self.find_in_window(BattleStrategy.BATTLE_SCENE):
                return True
        return True


class TeleportStrategy:
    """
    传送策略（一次性任务）
    流程：
    1. 按 M 键打开地图
    2. 拖拽地图对齐到标准位置
    3. 使用硬编码坐标逐个点击魔力之源
    4. 点击传送按钮
    5. 等待加载画面消失
    6. 全部完成后停止
    """

    from bot.shade import MAGIC_FOUNTAIN_COORDS, TELEPORT_BTN_COORD
    LOADING = "loading.png"  # loading 模板（可选，动态画面匹配差）
    LOADED_MARK = "loaded.png"  # 加载完成后出现的标志图片（更可靠）

    # 地图校准偏移 (先拖到左下死角，再拖此偏移到标准位置)
    MAP_CALIBRATE_DX = 152
    MAP_CALIBRATE_DY = 325

    # 拖拽参数
    CORNER_RIGHT = 400           # 先向右拖到右边界（不要太大，避免鼠标移出窗口）
    CORNER_UP = 550              # 再向上拖到上边界
    DRAG_STEPS = 30              # 拖拽步数
    DRAG_STEP_DELAY = 0.03      # 每步延时

    # 等待参数
    LOADING_CHECK_INTERVAL = 1.0
    LOADING_TIMEOUT = 30.0

    def __init__(self, ctx: BotContext):
        self.ctx = ctx
        self.coords = list(self.MAGIC_FOUNTAIN_COORDS)

    def _align_map(self):
        """
        拖拽地图到固定标准位置，每步拖拽分多个小段，段间复位鼠标到窗口中心，
        保证鼠标不离开窗口导致拖拽失效：
        1. 向右拖到边界
        2. 向上拖到边界 → 左下死角
        3. 校准偏移到标准位置
        """
        w, h = self.ctx.win_w, self.ctx.win_h
        cx, cy = w // 2, h // 2

        CHUNK = 150  # 每小段最大拖拽距离（保证鼠标不离开窗口）

        def _drag_chunked(dx: int, dy: int, label: str):
            """分段拖拽，段间复位到窗口中心"""
            total_dx = abs(dx)
            total_dy = abs(dy)
            need = max(total_dx, total_dy)
            if need == 0:
                return
            full_chunks = need // CHUNK
            remainder = need % CHUNK
            chunks = [CHUNK] * full_chunks + ([remainder] if remainder > 0 else [])

            sign_x = 1 if dx > 0 else (-1 if dx < 0 else 0)
            sign_y = 1 if dy > 0 else (-1 if dy < 0 else 0)

            total_done = 0
            for i, chunk in enumerate(chunks):
                chunk_dx = sign_x * (chunk if dx != 0 else 0)
                chunk_dy = sign_y * (chunk if dy != 0 else 0)

                # 复位到窗口中心（仅移动，不点击）
                screen_cx, screen_cy = self.ctx.window.client_to_screen(cx, cy)
                Mouse.move(screen_cx, screen_cy)
                time.sleep(0.05)  # 等游戏处理完上一次 mouse_up，避免误判为点击

                if i == len(chunks) - 1:
                    logger.info(f"  拖拽地图 → {label}")
                Mouse.drag_window_relative(self.ctx.window.hwnd,
                    cx, cy, cx + chunk_dx, cy + chunk_dy,
                    steps=self.DRAG_STEPS, step_delay=self.DRAG_STEP_DELAY)
                total_done += chunk
                time.sleep(0.05)

        # 第1步：向右拖
        _drag_chunked(self.CORNER_RIGHT, 0, f"右 {self.CORNER_RIGHT}px")

        # 第2步：向上拖 → 左下死角
        _drag_chunked(0, -self.CORNER_UP, f"上 {self.CORNER_UP}px")

        # 第3步：向下拖校准
        _drag_chunked(0, self.MAP_CALIBRATE_DY, f"下 {self.MAP_CALIBRATE_DY}px")

        # 第4步：向左拖校准
        _drag_chunked(-self.MAP_CALIBRATE_DX, 0, f"左 {self.MAP_CALIBRATE_DX}px")

    def run(self) -> dict:

        total = len(self.coords)
        task_start = time.time()
        logger.info("=" * 40)
        logger.info(f"传送任务 开始 (共 {total} 个魔力之源)")
        logger.info("=" * 40)

        if total == 0:
            logger.warning("坐标列表为空，任务结束")
            elapsed = time.time() - task_start
            logger.info(f"耗时: {elapsed:.1f}s")
            return {"total": 0, "success": 0, "failed": 0}

        # Step 1: 打开地图并对齐
        logger.info("[1/3] 按 M 键打开地图...")
        self.ctx.window.focus()
        time.sleep(0.3)
        Keyboard.press('m')
        time.sleep(0.8)
        self._align_map()

        # Step 2: 逐个点击魔力之源 → 传送
        logger.info(f"[2/3] 开始逐个传送...")
        success = 0
        failed = 0

        for i, (x, y) in enumerate(self.coords, 1):
            # 检查状态：暂停则等待，停止则退出
            while self.ctx.state == BotState.PAUSED:
                time.sleep(0.3)
            if self.ctx.state == BotState.STOPPED:
                elapsed = time.time() - task_start
                logger.info(f"传送任务被中断 (已完成 {success} 个, 耗时 {elapsed:.1f}s)")
                break

            logger.info(f"--- [{i}/{total}] 魔力之源 ({x}, {y}) ---")

            # 点击魔力之源
            self.ctx.click(x, y)
            time.sleep(0.5)

            # 点击传送按钮（硬编码坐标，无需模板匹配）
            self.ctx.click(*self.TELEPORT_BTN_COORD)
            logger.info(f"  [{i}/{total}] 已点击传送")

            # Step 3: 等待加载完成
            logger.info(f"  [{i}/{total}] 等待传送完成...")
            if self._wait_loaded():
                success += 1
                logger.info(f"  [{i}/{total}] 传送完成 ✓")
            else:
                failed += 1
                logger.warning(f"  [{i}/{total}] 加载超时，继续下一个")

            # 下一个：重新打开地图并对齐
            if i < total:
                time.sleep(0.5)
                self.ctx.window.focus()
                time.sleep(0.3)
                Keyboard.press('m')
                time.sleep(0.8)
                self._align_map()

        elapsed = time.time() - task_start
        mins, secs = divmod(int(elapsed), 60)
        logger.info("[3/3] 传送任务 结束")
        logger.info(f"结果: 共 {total} 个, 成功 {success}, 失败 {failed}")
        logger.info(f"耗时: {mins} 分 {secs} 秒 ({elapsed:.1f}s)")
        logger.info("=" * 40)

        return {"total": total, "success": success, "failed": failed}

    def _wait_loaded(self) -> bool:
        """等待加载完成后特定标志出现，比检测 loading 消失更可靠"""
        template = self.ctx.matcher.load_template(self.LOADED_MARK)
        if template is None:
            logger.warning(f"{self.LOADED_MARK} 未找到，回退固定等待 5 秒")
            time.sleep(5)
            return True

        start = time.time()
        while time.time() - start < self.LOADING_TIMEOUT:
            screenshot = self.ctx.take_screenshot()
            result = self.ctx.matcher.find_one(self.LOADED_MARK, screenshot)
            if result is not None:
                logger.info("加载完成 ✓")
                time.sleep(0.5)
                return True
            time.sleep(0.5)

        logger.warning("等待加载完成超时")
        return False

    def _wait_loading_gone(self) -> bool:
        """等待加载画面消失，返回 True 表示加载完成"""
        template = self.ctx.matcher.load_template(self.LOADING)
        if template is None:
            logger.warning("loading.png 未找到，使用固定等待 5 秒")
            time.sleep(5)
            return True

        start = time.time()
        while time.time() - start < self.LOADING_TIMEOUT:
            screenshot = self.ctx.take_screenshot()
            result = self.ctx.matcher.find_one(self.LOADING, screenshot, threshold=0.4)
            if result is None:
                time.sleep(0.5)
                return True
            time.sleep(self.LOADING_CHECK_INTERVAL)

        return False


class BotRunner:
    """
    机器人主循环
    """

    # 查找窗口超时时间（秒）
    WINDOW_FIND_TIMEOUT = 30.0
    WINDOW_FIND_INTERVAL = 2.0

    def __init__(self):
        self.ctx = BotContext()

    def _find_game_window(self) -> bool:
        """查找并激活游戏窗口，超时则失败"""
        logger.info(f"正在查找游戏窗口 [标题: {self.ctx.window.title}] ...")
        start = time.time()

        while time.time() - start < self.WINDOW_FIND_TIMEOUT:
            if self.ctx.window.find_and_focus():
                # 初始化窗口绑定的截图器
                region = self.ctx.window.get_screenshot_region()
                if region:
                    self.ctx.capture = ScreenCapture(region=region)
                    self.ctx.win_w, self.ctx.win_h = self.ctx.window.client_size
                    return True
            logger.info(f"未找到窗口，{self.WINDOW_FIND_INTERVAL}s 后重试...")
            time.sleep(self.WINDOW_FIND_INTERVAL)

        logger.error(f"查找窗口超时 ({self.WINDOW_FIND_TIMEOUT}s)，请确认游戏已启动")
        return False

    def start(self):
        """启动机器人"""
        # --- 必须先找到游戏窗口 ---
        if not self._find_game_window():
            logger.error("未找到游戏窗口，机器人终止")
            self.ctx.state = BotState.ERROR
            return

        self.ctx.state = BotState.RUNNING
        self.ctx.start_time = time.time()

        self.strategies: list[BaseStrategy] = [
            BattleStrategy(self.ctx),
            ExploreStrategy(self.ctx),
        ]

        logger.info("=" * 40)
        logger.info("洛克王国助手 启动！")
        logger.info(f"   窗口大小: {self.ctx.win_w}x{self.ctx.win_h}")
        logger.info(f"   已加载 {len(self.strategies)} 个策略")
        logger.info("   按 Ctrl+C 可紧急停止")
        logger.info("=" * 40)

        try:
            while self.ctx.state == BotState.RUNNING:
                # 定期检查窗口是否还存在
                if not self.ctx.window.is_valid():
                    logger.error("游戏窗口已关闭，机器人终止")
                    break

                for strategy in self.strategies:
                    if self.ctx.state != BotState.RUNNING:
                        break
                    strategy.run()
                    time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("收到停止信号")

        self.stop()

    def stop(self):
        """停止机器人"""
        self.ctx.state = BotState.STOPPED
        elapsed = time.time() - self.ctx.start_time if self.ctx.start_time else 0
        logger.info("=" * 40)
        logger.info(f"已停止 | 战斗次数: {self.ctx.battle_count} | 运行时间: {elapsed:.1f}s")
        logger.info("=" * 40)

    def run_teleport_once(self) -> dict:
        """
        执行一次传送任务（传送到所有魔力之源）
        这是一个独立的一次性任务，不受开始/暂停/停止按钮控制
        """
        if not self._find_game_window():
            logger.error("未找到游戏窗口，传送任务取消")
            self.ctx.state = BotState.ERROR
            return {"total": 0, "success": 0, "failed": 0}

        self.ctx.state = BotState.RUNNING
        teleporter = TeleportStrategy(self.ctx)
        result = teleporter.run()
        self.ctx.state = BotState.IDLE
        return result

    def test_click(self):
        """测试：找到窗口后，在正中央点击 3 次"""
        logger.info("=" * 40)
        logger.info("🧪 测试点击 开始")

        if not self._find_game_window():
            logger.error("未找到游戏窗口，测试取消")
            return

        cx, cy = self.ctx.win_w // 2, self.ctx.win_h // 2
        logger.info(f"窗口大小: {self.ctx.win_w}x{self.ctx.win_h}, 中心点: ({cx}, {cy})")

        for i in range(1, 4):
            # 每次点击前重新聚焦
            self.ctx.window.focus()
            time.sleep(0.3)

            screen_x, screen_y = self.ctx.window.client_to_screen(cx, cy)
            logger.info(f"  第 {i} 次点击: 窗口({cx},{cy}) → 屏幕({screen_x},{screen_y})")
            self.ctx.click(cx, cy)
            time.sleep(0.8)

        logger.info("🧪 测试点击 完成 (3次)")
        logger.info("=" * 40)

    def pause(self):
        self.ctx.state = BotState.PAUSED
        logger.info("已暂停")

    def resume(self):
        self.ctx.state = BotState.RUNNING
        logger.info("已恢复")
