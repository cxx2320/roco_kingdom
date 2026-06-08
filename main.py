"""
洛克王国助手 - 入口文件
"""

import sys
from pathlib import Path

from loguru import logger


def _get_root_dir() -> Path:
    """获取项目根目录，兼容开发环境和 PyInstaller 打包后的 exe"""
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    else:
        return Path(__file__).resolve().parent


ROOT_DIR = _get_root_dir()
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# 配置日志
logger.remove()

# 控制台日志：--windowed 模式下 sys.stdout 为 None，需要跳过
if sys.stdout is not None:
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )

# 文件日志：确保 logs 目录存在
try:
    log_dir = ROOT_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "bot_{time:YYYY-MM-DD}.log",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
        level="DEBUG",
    )
except Exception:
    pass


def run_gui():
    """启动图形界面"""
    from gui.panel import main
    main()


def run_cli():
    """纯命令行模式启动"""
    from bot.strategy import BotRunner
    bot = BotRunner()
    bot.start()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="洛克王国助手")
    parser.add_argument(
        "--mode", "-m",
        choices=["gui", "cli"],
        default="gui",
        help="运行模式: gui (图形界面) 或 cli (命令行)",
    )
    args = parser.parse_args()

    if args.mode == "cli":
        run_cli()
    else:
        run_gui()
