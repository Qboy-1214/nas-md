---
id: nas-md-webserver
type: module-design
status: draft
title: WebServer：HTTP 服务与挂载 API
parent: nas-md-architecture
depends-on:
  - nas-md-search
  - nas-md-pim-business
---

# WebServer：HTTP 服务与挂载 API

## 职责

`nas_md/webserver/`（约 3250 行）+ 子模块 `paragraph_diff` / `file_version_store` / `file_watcher` / `sse_handler` / `version_history`。
唯一 HTTP 入口：挂载 API（CRUD、tree、file、段落 diff 提交、版本历史）、静态 SPA 服务、多用户 Cookie 会话、SSE 协同推送、远程文件代理、搜索/图谱/看板/统计端点、gzip、Docker 自签 HTTPS。

## 边界

- **路径安全**：所有挂载文件操作走 `MountManager._safe_path`（realpath + 前缀校验）；写操作必须经过挂载 API，无旁路。
- **依赖（代码实证的 import 边）**：`search`（保存/删除时增量索引）、`plugins`（PluginManager，WorldClock）、本包内 `paragraph_diff`。
- **禁止触达**：Telegram 业务模块（journal/habits/worker/userconfig）与 `fs` 用户存储树——Web 挂载路径与 TG 存储树是两套独立机制。
- 子系统设计见 [[nas-md-multi-user-isolation]]、[[nas-md-realtime-collab]]、[[nas-md-remote-proxy]]、[[nas-md-mount-api]]。

## 不变量

- 版本驱动协同：整数版本号做乐观锁（非 mtime）；同段落冲突后写覆盖（LWW，已知局限，见 goal doc）。
- 远程代理模式不经过 FileVersionStore、不记版本历史；API Key 只经 HTTP header 转发，不落盘不记录。
- 会话 Cookie（`nasmd_sid`）丢失即换新会话，旧挂载数据留在磁盘可找回（非账号体系，刻意设计）。
