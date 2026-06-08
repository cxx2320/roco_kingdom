# Changelog

<!-- SCHEMA: {"ts":"ISO-8601","action":"add|promote|extract|resolve","type":"learning|error|feature","id":"entry ID","summary":"≤100字","target":"晋升目标(可选)"} -->

```jsonl
{"ts":"2026-06-07T17:30:00+08:00","action":"add","type":"learning","id":"LRN-20260607-001","summary":"PyInstaller --windowed 导致 sys.stdout=None 引发 loguru TypeError"}
{"ts":"2026-06-07T17:30:00+08:00","action":"add","type":"learning","id":"LRN-20260607-002","summary":"PyInstaller --onefile 下 __file__ 指向临时目录，需用 sys._MEIPASS"}
{"ts":"2026-06-07T17:30:00+08:00","action":"add","type":"learning","id":"LRN-20260607-003","summary":"PostMessage 被 UIPI 拦截（ERROR 5），需用 SendInput 或 interception 替代"}
{"ts":"2026-06-07T17:30:00+08:00","action":"add","type":"learning","id":"LRN-20260607-004","summary":"GitHub Release 下载可用 ghproxy.com 镜像加速"}
{"ts":"2026-06-07T17:30:00+08:00","action":"add","type":"learning","id":"LRN-20260607-005","summary":"interception-python 直接通过设备路径(\\\\.\\interceptionXX)通信，不加载 DLL"}
{"ts":"2026-06-07T17:30:00+08:00","action":"add","type":"learning","id":"LRN-20260607-006","summary":"loguru 和 PyQt5 GUI 日志系统需通过自定义 sink 桥接"}
{"ts":"2026-06-07T17:30:00+08:00","action":"add","type":"error","id":"ERR-20260607-001","summary":"PostMessage 点击游戏窗口返回拒绝访问(ERROR 5)"}
{"ts":"2026-06-07T17:30:00+08:00","action":"add","type":"error","id":"ERR-20260607-002","summary":"Interception 内核驱动未安装，需管理员手动安装"}
{"ts":"2026-06-08T16:00:00+08:00","action":"add","type":"learning","id":"LRN-20260608-001","summary":"interception click()不支持state参数，拖拽必须用mouse_down/mouse_up+move_to"}
{"ts":"2026-06-08T16:00:00+08:00","action":"add","type":"learning","id":"LRN-20260608-002","summary":"检测动态画面用正向匹配(等标志出现)比反向(等loading消失)更可靠"}
{"ts":"2026-06-08T16:00:00+08:00","action":"add","type":"learning","id":"LRN-20260608-003","summary":"大距离拖拽分段+段间复位中心，避免鼠标移出窗口"}
```
