# Learnings

## [LRN-20260607-001] best_practice

**Priority**: high
**Status**: resolved
**Area**: infra

### 内容
PyInstaller `--windowed` 模式下 `sys.stdout` 为 `None`，loguru 的 `logger.add(sys.stdout, ...)` 会抛出 `TypeError: Cannot log to objects of type 'NoneType'`。

### 建议修复
在任何 `logger.add(sys.stdout, ...)` 前加 `if sys.stdout is not None:` 判断。GUI 模式下日志应通过自定义 sink 转发到 UI 组件。

### 元数据
- Source: error
- Pattern-Key: pyinstaller-windowed-stdout

---

## [LRN-20260607-002] best_practice

**Priority**: high
**Status**: resolved
**Area**: infra

### 内容
PyInstaller `--onefile` 打包后，`__file__` 指向临时解压目录而非 exe 所在目录。应使用 `sys._MEIPASS`（`--add-data` 资源存放处）或 `sys.executable`（exe 所在目录）来定位资源文件。

### 建议修复
```python
def _get_root_dir():
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', None)
        return Path(meipass) if meipass else Path(sys.executable).parent
    return Path(__file__).resolve().parent
```

### 元数据
- Source: error
- Pattern-Key: pyinstaller-frozen-path
- See Also: LRN-20260607-001

---

## [LRN-20260607-003] best_practice

**Priority**: high
**Status**: resolved
**Area**: infra

### 内容
Windows UIPI (User Interface Privilege Isolation) 会阻止低权限进程通过 `PostMessage` 向高权限窗口发送消息，报 `ERROR_ACCESS_DENIED (5)`。对于游戏辅助工具，`PostMessage`/`SendMessage` 不可靠。

### 建议修复
按可靠性排序：`interception 内核驱动` > `SendInput` > `SetCursorPos + mouse_event` > `PostMessage`。interception 是终极方案，在驱动层注入输入，游戏无法区分。

### 元数据
- Source: error
- Pattern-Key: uipi-postmessage-denied

---

## [LRN-20260607-004] best_practice

**Priority**: medium
**Status**: resolved
**Area**: infra

### 内容
GitHub 在中国大陆可能无法直连。下载 GitHub Release 文件时可使用 `ghproxy.com` 或 `ghfast.top` 等镜像加速。

### 建议修复
```
https://ghproxy.com/https://github.com/OWNER/REPO/releases/download/...
```

### 元数据
- Source: task_review
- Pattern-Key: github-china-mirror

---

## [LRN-20260607-005] best_practice

**Priority**: medium
**Status**: resolved
**Area**: infra

### 内容
`interception-python` 不通过加载 `interception.dll` 来工作。它直接通过 `CreateFileA("\\\\.\\interception00", ...)` 打开内核驱动设备句柄，然后使用 `DeviceIoControl` 通信。因此驱动必须通过 `install-interception.exe /install`（管理员权限）安装为内核服务后才能使用。

### 元数据
- Source: knowledge_gap
- Pattern-Key: interception-device-path

---

## [LRN-20260607-006] best_practice

**Priority**: high
**Status**: resolved
**Area**: tools

### 内容
loguru 日志和 PyQt5 GUI 日志是两个独立系统。bot 模块用 `logger.info()`，GUI 用 `signals.log.emit()`，互不相通。需要在 GUI 初始化时给 loguru 添加一个自定义 sink，将日志转发到 GUI 信号。

### 建议修复
```python
def _setup_log_bridge(self):
    from loguru import logger
    def gui_sink(message):
        text = message.record["message"].strip()
        if text:
            self.signals.log.emit(text)
    logger.add(gui_sink, format="{message}", level="INFO")
```

### 元数据
- Source: error
- Pattern-Key: loguru-pyqt-bridge

---

## [LRN-20260608-001] best_practice

**Priority**: high
**Status**: resolved
**Area**: tools

### 内容
`interception-python` 的 `click()` 不支持 `state='down'/'up'` 参数，拖拽必须分别调用 `mouse_down('left')` → 移动 → `mouse_up('left')`。另外 `move_relative()` 文档明确警告可能偏移 1px，拖拽应使用逐步 `move_to()` 绝对坐标替代。

### 建议修复
```python
# ❌ 错误：click 不支持 state 参数
interception.click(x, y, state='down')

# ✅ 正确：分别用 mouse_down / mouse_up
interception.move_to(sx, sy)
interception.mouse_down('left')
for i in range(1, steps+1):
    interception.move_to(sx+(ex-sx)*i/steps, sy+(ey-sy)*i/steps)
    time.sleep(delay)
interception.mouse_up('left')
```

### 元数据
- Source: error
- Pattern-Key: interception-drag-api
- See Also: LRN-20260607-005

---

## [LRN-20260608-002] best_practice

**Priority**: medium
**Status**: resolved
**Area**: tools

### 内容
检测动态画面（如游戏 loading 动画）时，用"等待目标元素**出现**"比"等待加载画面**消失**"更可靠。动态画面变化大，模板匹配置信度不稳定；而加载完成后出现的 UI 元素通常是静态的、易匹配的。

### 建议修复
```python
# ❌ 等 loading 消失（不可靠）
while loading_template_found():
    time.sleep(0.5)

# ✅ 等 loaded 标志出现（可靠）
while loaded_mark_not_found():
    time.sleep(0.5)
```

### 元数据
- Source: task_review
- Pattern-Key: positive-detection-over-negative

---

## [LRN-20260608-003] best_practice

**Priority**: medium
**Status**: resolved
**Area**: tools

### 内容
大距离鼠标拖拽（> 窗口尺寸）会导致鼠标移出窗口，后续操作失效。应拆分为 ≤200px 的小段，段间 `Mouse.move()` 复位到窗口中心，保证每次拖拽都在窗口范围内。

### 建议修复
```python
CHUNK = 200
for each chunk in split(total_px, CHUNK):
    Mouse.move(center_screen_x, center_screen_y)  # 先复位
    Mouse.drag_window_relative(hwnd, cx, cy, cx+chunk_dx, cy+chunk_dy)
```

### 元数据
- Source: error
- Pattern-Key: chunked-drag-recenter
