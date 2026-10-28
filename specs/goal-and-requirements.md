---
id: nas-md-goal
type: goal-and-requirements
status: draft
title: nas-md · 目标与需求
---

## Goal

轻量级自托管 Markdown 笔记与知识服务，面向 NAS 场景：Docker 一键部署、数据全部是用户自己设备上的 `.md` 文件，不出内网。

## 问题与用户

- 家庭/局域网自托管用户：要一个零运维（Docker 一键起、HTTPS 开箱即用）的 Markdown 编辑器，多设备、多人共用同一服务。
- 有独立文件服务（含版本管理）的用户：想借用 nas-md 的编辑器而不重复造轮子（远程深链代理模式）。

## 入口定位（2026-10-28 确认）

- **Web 前端（Vditor SPA）是一级入口**，全部特性围绕它演进。
- **Telegram Bot（`nas_md/server/`）是遗留入口**：维护模式，不加新特性，不是演进方向。

## 身份与隔离（2026-10-28 确认）

- 免登录 + Cookie 自动会话（`nasmd_sid`，1 年）：自托管局域网场景，零摩擦优先于账号管理，**刻意不建登录/账号体系**。
- 普通用户只见自己的挂载点与公开挂载点；Admin 额外可见宿主机挂载点（`MOUNT_DIRS` / Docker `/mnt` 自动扫描）。

## 能力（代码已实现）

- Vditor 三模式（即时渲染/分屏/所见即所得）、自动保存、离线草稿
- 多挂载：宿主机挂载（Docker `/mnt` 自动扫描 + `PUBLIC_MOUNTS` 公开白名单）、浏览器本地挂载（File System Access API，HTTP 降级只读）、手动路径挂载、内置存储（全员只读）
- 全文搜索（SQLite FTS5 + trigram 分词器，CJK 免空格检索）、知识图谱（D3）、数据看板、反向链接，标签/任务/标题结构化查询
- 段落级版本历史（预览/恢复）+ 版本驱动协同编辑（SSE 推送、段落合并、后写覆盖）
- 远程文件代理：`#remote=<base64url JSON>` 深链打开局域网其他服务的 MD，编辑后回写原服务（Key 经 header 转发，nas-md 不落盘不记录）
- HTML 页面预览（隔离 iframe、同挂载点相对资源重写、opaque origin + data-URL 内联）
- Mermaid 图表全屏增强；暗色模式；文件夹管理；键盘快捷键
- Telegram 遗留入口：命令体系（task/search/habit/settings/note）、日记、习惯热力图、定时任务、插件（WorldClock）

## 非目标（由决策排除）

- 不做账号/登录体系，不做公网多租户部署
- 远程代理模式不做协同编辑与版本历史——版本管理由远程服务负责
- 不做前端框架/构建步骤（原生 JS + vendored 库是持久原则）
- 不做 ORM/数据库迁移脚本（文件即数据库）

## 持久原则

- 文件即数据库；可移植（跨平台文件名/路径处理）；LLM 友好（整个项目一个上下文窗口装得下）
- 标准库优先：运行时仅 2 个依赖（pyyaml=frontmatter 解析、watchdog=外部文件监视），各自承担单一明确职责

## 已知局限（2026-10-28 确认）

- CI pytest 挂起正在诊断中（近 5 个 commit 均为诊断性改动）
- 协同编辑段落冲突为后写覆盖（last-write-wins），无 OT/CRDT 级合并
- 远程代理模式无协同/无版本历史
- 旧文档「纯标准库零第三方依赖」说法过时（本轮回 import 时已顺手修正）
