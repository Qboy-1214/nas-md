---
id: nas-md-sync
type: module-design
status: draft
title: Sync：跨设备同步引擎
parent: nas-md-architecture
---

# Sync：跨设备同步引擎

## 职责

`nas_md/sync/`（约 344 行）。跨设备文件同步的合并与追踪能力：

- **LCS 行合并**：最长公共子序列算法合并两个版本（假设差异主要是行的增删改，对笔记场景合理）。
- **fslog**：文件系统操作日志（全局 `storage/fslog`），记录 rename/delete：`<timestamp> <op> <url_encoded_old> <url_encoded_new>`，用于跨设备追踪变更。
- **Token 认证**：一次性令牌（10 分钟过期）→ 永久令牌（SHA-256 + salt 存储于 `storage/tokens/<hash>`）；无效令牌连续提交封禁 IP 10 分钟。

## 边界

- 纯后端模块，无前端面对应；被 Telegram 入口调用（`from nas_md.sync import merge`）。
- 与 Web 侧版本驱动协同编辑（[[nas-md-realtime-collab]]）是两套机制：sync 面向跨设备离线合并，collab 面向多人在线编辑。
