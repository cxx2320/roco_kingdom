# 洛克王国助手

基于 Python 的游戏辅助工具，用于自动化执行「洛克王国：世界」中的重复性任务。

## 功能

- 🗺️ **地图坐标采集** — 透明遮罩覆盖游戏窗口，手动点击采集坐标
- 🌀 **魔力之源传送** — 自动遍历地图传送点，逐个传送收集资源
- 🖱️ **内核级键鼠模拟** — 基于 interception 驱动，硬件层输入不会被反作弊检测
- 🖥️ **图形化控制面板** — PyQt5 界面，F5-F10 快捷键控制

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动 GUI
python main.py

# 命令行模式
python main.py --mode cli
```

## 项目结构

```
├── bot/
│   ├── input.py         # 键鼠模拟（interception / SendInput）
│   ├── screen.py        # 屏幕截图与图像识别
│   ├── strategy.py      # 自动化策略（传送、战斗）
│   ├── coord_picker.py  # 坐标采集器（透明遮罩）
│   └── shade.py         # 硬编码坐标数据
├── gui/
│   └── panel.py         # PyQt5 控制面板
├── assets/templates/    # 模板图片
└── main.py              # 入口
```

## 免责声明

**本项目仅用于技术学习与研究目的。**

- 本工具为个人技术实践项目，旨在学习 Python 自动化、图像识别、内核驱动通信等技术
- 请勿将本项目用于任何违反游戏服务条款的行为
- 使用者应自行承担使用本工具产生的一切后果
- 作者不对因使用本项目而导致的任何账号封禁、数据丢失或其他损失负责

## License

MIT
