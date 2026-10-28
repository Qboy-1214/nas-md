---
id: nas-md-pim-business
type: module-design
status: draft
title: PIM 业务簇（日记/习惯/定时任务）
parent: nas-md-architecture
depends-on:
  - nas-md-fs
---

# PIM 业务簇（日记/习惯/定时任务）

## 定位

Telegram 时代的 PIM（个人信息管理）业务簇（2026-10-28 确认随 TG 入口处于维护模式）：`journal/` `habits/` `stats/` `worker/` `userconfig/` `plugins/`，加基础层 `db/` `config/` `pkg/` `i18n/`。服务对象是 [[nas-md-telegram-bot]]，Web 入口不使用本簇。

## 模块职责

- **journal**（~115 行）：按月日记文件（`journal/2026.06 June.md`），每天一个二级标题，时间戳记录 + Emoji 追加；用户级 `Lock` 防并发写。
- **habits**（~210 行 + render）：年度 Emoji 热力图（🟢 工作日 / 🟡 周末 / ⚪️ 跳过；Mood 用 6 级量表），数据存 `insights/2026 Habits.md`。
- **stats**：今日完成报告、归档统计。
- **worker**（~306 行）：两个定时任务——到期任务移入 `Chat.md` 收件箱；`Chat.md`/`Later.md` 已完成 checklist 归档到 `Done.md` 并写日记。
- **userconfig**（~223 行）：JSON 用户配置（显示模式/时区/快捷按钮/计划任务/番茄钟时长等），存用户根目录 `config.json`。
- **plugins**（~342 行）：插件体系，内置 WorldClock（识别消息中的日期/时间戳，多时区显示）。
- **基础层**：`db`（内存 KV + 临时文件持久化）、`config`（环境变量加载 + 单例）、`pkg`（txt 文本工具 / tg 类型定义 / slice 分片）、`i18n`（Emoji 关键词映射）。

## 边界

- 依赖（代码实证的 import 边）：`fs`（用户存储树）、`config`；`worker`/`server` 另用 `stats`/`journal`/`habits` 相互引用。
- Web 侧仅 `plugins` 被 `webserver` 反向引用（PluginManager，`from nas_md.plugins import PluginManager`）——这是本簇与 Web 入口的唯一交汇点。
