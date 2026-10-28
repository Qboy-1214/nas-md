---
id: nas-md-telegram-bot
type: module-design
status: draft
title: Telegram Bot（遗留入口）
parent: nas-md-architecture
depends-on:
  - nas-md-pim-business
  - nas-md-fs
  - nas-md-sync
---

# Telegram Bot（遗留入口）

## 定位（2026-10-28 确认）

**遗留入口，维护模式**：不加新特性，不是演进方向。Web 前端是一级入口。本 SPEC 记录现状契约，便于维护时不破坏既有行为。

## 职责

`nas_md/server/`（约 1631 行）+ `server/commands/`（task/search/habit/settings/note 按功能分组）。全部 Telegram 交互：命令路由、内联键盘、输入期望状态机、插件检查。

## 机制要点

- **双层命令路由**：装饰器注册（`router.command`，`register_all_modules()` 自动注册）> 传统命令字典（50+ 命令兜底）> 默认 home。
- **状态管理**：`DB.input_expectation` 存"输入期望"（如触发搜索后下一条消息当作关键词）。
- **交互体系**：`Keyboard` + `Btn` + `Cmd`（name/params/type/data）回调，按钮携带序列化命令回传。
- **消息流**：用户消息 → handle() → 插件检查（WorldClock）→ 命令路由 → 普通消息处理 → 输入期望检查。

## 边界

- 依赖（代码实证的 import 边）：PIM 业务簇（journal/habits/stats/userconfig/plugins）、`fs`（用户存储树）、`sync`（merge）、`pkg/*`（Telegram 类型与文本工具）。
- 不触达 `webserver`；两条入口的存储与隔离机制相互独立。
