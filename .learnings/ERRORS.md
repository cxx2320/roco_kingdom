# Errors

## [ERR-20260607-001] PostMessage 拒绝访问

**Priority**: high
**Status**: resolved
**Area**: infra

### 摘要
`win32gui.PostMessage(hwnd, WM_LBUTTONDOWN, ...)` 向游戏窗口发送点击消息时返回 `ERROR_ACCESS_DENIED (5)`。

### 错误信息
```
PostMessage 点击失败: (5, 'PostMessage', '拒绝访问。')
```

### 上下文
- 游戏客户端以管理员或更高完整性级别运行
- 辅助工具以普通用户权限运行
- Windows UIPI 阻止跨权限窗口消息

### 建议修复
改用 `SendInput` API（硬件级）或 `interception` 内核驱动。详见 LRN-20260607-003。

### 元数据
- Reproducible: yes
- See Also: LRN-20260607-003

---

## [ERR-20260607-002] Interception 驱动未安装

**Priority**: medium
**Status**: pending
**Area**: infra

### 摘要
`interception.auto_capture_devices()` 报 "Interception driver was not found or is not installed"。

### 错误信息
```
Interception driver was not found or is not installed.
Please confirm that it has been installed properly and is added to PATH.
```

### 上下文
- GitHub 直连失败，通过 ghproxy 下载了驱动包
- `install-interception.exe /install` 需要管理员权限手动确认
- 安装后需重启

### 建议修复
右键以管理员身份运行 `install-interception.exe`，重启系统。

### 元数据
- Reproducible: yes
- See Also: LRN-20260607-004, LRN-20260607-005
