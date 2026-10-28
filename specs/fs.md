---
id: nas-md-fs
type: module-design
status: draft
title: FS：用户隔离文件系统
parent: nas-md-architecture
---

# FS：用户隔离文件系统

## 职责

`nas_md/fs/`（约 650 行）。用户隔离的文件系统抽象，是 Telegram 入口及其 PIM 业务模块（journal/habits/worker/…）的存储底座。每个 TG 用户对应 `storage/<user_id>/` 下独立的目录树（Chat.md / Later.md / Done.md / journal/ / habits/ / media/ …）。

## 设计要点

- **双后端**：`backend="os"`（生产）/ `backend="mem"`（测试，`dict[bytes, bytes]` 模拟，全隔离）；内存后端 `_norm()` 统一路径分隔符为 `/`，保证 Windows 下行为一致。
- **路径安全**：`safe_path()` + `_is_local()` 检测 `..` 逃逸，所有文件操作先过校验。
- **文件名清洗**：`FORBIDDEN_CHARS` 把非法字符替换为全角等价字符（跨平台安全）。
- **文件名哈希**：MD5 前 11 位作为安全引用，避免在 Telegram callback data（64 字节限制）里暴露真实文件名。

## 边界

- 服务对象是 TG 存储树（`storage/<user_id>/`），**Web 挂载 API 不使用本模块**（Web 侧走 MountManager 的 realpath 前缀校验，两套机制独立）。
