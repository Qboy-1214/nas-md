# SilverBullet 调研报告

> 调研时间：2026-06-03
> 项目地址：https://github.com/silverbulletmd/silverbullet
> 官网：https://silverbullet.md

## 一句话总结

SilverBullet 是一个**可编程的个人知识数据库**。浏览器内运行的 Markdown 编辑器 + Wiki 风格双向链接 + 内置对象索引和查询语言 + Space Lua 脚本环境，把笔记变成一个可编程系统。

## 技术栈

| 维度 | SilverBullet | nas-md |
|------|-------------|--------|
| 前端 | TypeScript + CodeMirror 6 + Preact | 纯 HTML/CSS/JS（无构建） |
| 后端 | Go | Python 3.11+（纯 stdlib） |
| 存储 | 文件系统（服务端）+ IndexedDB（客户端） | 文件系统（服务端） |
| 脚本 | Space Lua（自定义 Lua 方言） | 无 |
| 扩展 | Plug 系统（Web Worker 沙箱） | Plugin 系统（Python，仅 WorldClock） |
| 同步 | Service Worker 双向同步（20s 周期） | 手动 Sync API（LCS merge） |
| 部署 | 单二进制 / Docker | Python 脚本 / Docker Compose |

## SilverBullet 的核心能力

### 1. 对象索引与查询（Objects + LIQ）

这是 SilverBullet 最有特色的能力。它会自动索引所有内容：

- **Pages** — 页面（含 frontmatter 元数据）
- **Tasks** — 任务（`- [ ]` / `- [x]`）
- **Items** — 列表项
- **Links / Tags / Anchors** — 链接、标签、锚点
- **space-lua** — Lua 代码块

然后通过类 SQL 的查询语言（LIQ）跨页面聚合数据：

```lua
query [from t = tags.task where not t.done limit 3 select templates.taskItem(t)]
```

这相当于从整个笔记库中自动收集所有未完成的任务，渲染成一个动态列表。页面内容会随着底层数据变化自动更新。

### 2. Space Lua 脚本环境

在 Markdown 中嵌入 `space-lua` 代码块，整个 Space 共享作用域：

```lua
-- 定义一个函数，整个笔记库都能用
function featureList()
  local items = query([from f = tags.feature order by f.awesomeness desc])
  return renderList(items)
end
```

在普通 Markdown 页面中用 `${featureList()}` 调用，Live Preview 实时渲染结果。

支持：
- 自定义命令和快捷键
- 页面模板
- Widget（自定义 UI 组件）
- 事件钩子（文件保存、页面打开等）

### 3. Plug 扩展系统

每个 Plug 是一个独立的 `.plug.js` 文件，运行在 Web Worker 沙箱中，通过 syscall 与主进程通信。社区已有：

- SilverSearch（全文搜索）
- TreeView（树形目录）
- GraphView（知识图谱）
- PDF / Mermaid / PlantUML / Draw.io / Excalidraw

### 4. 双向同步引擎

- Service Worker 后台运行
- 整个 Space 约 20 秒同步一次
- 当前打开的文件 4-5 秒同步一次
- 冲突时创建副本（不自动合并）
- 支持 `.gitignore` 语法的同步过滤

### 5. 离线优先

- 浏览器端 IndexedDB 缓存所有文件
- 断网时可正常编辑，恢复连接后自动同步
- 服务端只是一个文件存储 + 认证层

## 对 nas-md 的可借鉴点

### 🔴 高优先级：立即可借鉴

#### 1. 对象索引 + 跨文件查询

**SilverBullet 的做法：** 自动索引所有 Task、Link、Tag，支持跨页面查询。

**nas-md 的现状：** 已有按文件名的搜索（`search_files_by_name`），但没有内容级别的索引。Task 散落在 Chat.md、Later.md 等文件中，无法跨文件聚合。

**可借鉴方案：** 在 FS 层或 Server 层增加一个轻量索引器，定期扫描所有 `.md` 文件，提取：
- Task 项（`- [ ]` / `- [x]`）
- 标签（`#tag`）
- 链接（`[[wiki-link]]`）
- Frontmatter 元数据

然后提供一个查询接口，比如 `GET /api/query?type=task&status=pending`，让前端和 Telegram Bot 都能获取跨文件的聚合视图。

#### 2. Frontmatter 元数据

**SilverBullet 的做法：** 页面顶部的 YAML frontmatter 作为结构化元数据，可被查询和过滤。

```yaml
---
tags: [feature, active]
awesomeness: 8
status: in-progress
---
```

**nas-md 的现状：** 文件内容完全是自由格式 Markdown，没有结构化元数据层。用户配置存在 `config.json` 中，但笔记本身没有元数据。

**可借鉴方案：** 在笔记文件头部支持可选的 frontmatter 块，用于：
- 标签分类（`tags: [project, active]`）
- 自定义属性（`status: in-progress`）
- 模板标记（`template: weekly-review`）

FS 层解析 frontmatter，索引器消费它，查询接口暴露它。对现有文件完全兼容（没有 frontmatter 的文件不受影响）。

#### 3. 双向链接

**SilverBullet 的做法：** `[[Page Name]]` 创建双向链接，自动维护 backlinks（反链）。

**nas-md 的现状：** 已有 `[[wiki-link]]` 的解析（`tgtxt.py` 中的 `wiki_link_regexp`），但只用于提取链接，没有维护反链索引。

**可借鉴方案：** 在索引器中维护一个 `{page: [backlinks]}` 的映射，提供 API 返回每个页面的反链列表。Telegram Bot 中也可以增加"查看反链"按钮。

### 🟡 中优先级：中期可考虑

#### 4. 可编程性 / 模板

**SilverBullet 的做法：** Space Lua 让用户写脚本动态生成内容。

**nas-md 的现状：** 完全没有脚本能力。所有展示逻辑硬编码在 Server 和前端中。

**可借鉴方案：** 不需要引入 Lua，但可以在 Markdown 中支持轻量的模板语法。比如：

- `{{query:tasks:pending}}` — 自动替换为当前所有未完成任务
- `{{template:daily-review}}` — 引用一个模板页面

后端渲染时解析这些占位符，替换为实际内容。这比完整的脚本语言简单得多，但能解决 80% 的动态内容需求。

#### 5. 更丰富的 Markdown 扩展

**SilverBullet 的做法：** 支持 frontmatter、`${expression}` 嵌入、wiki-link、标签语法等。

**nas-md 的现状：** 支持标准 Markdown + wiki-link 解析，但没有标签、frontmatter、嵌入表达式等。

**可借鉴方案：** 逐步扩展 Markdown 方言：
- `#tag` 语法（在文本中内联标签）
- `[[page]]` 双向链接（已有解析，缺索引）
- `{{template}}` 模板引用

#### 6. 全文搜索

**SilverBullet 的做法：** 内置全文搜索，社区还有 SilverSearch 插件。

**nas-md 的现状：** 只有按文件名的模糊搜索（基于最长公共子串的相似度匹配），没有内容搜索。

**可借鉴方案：** 在索引器中增加倒排索引，支持内容级别的全文搜索。不需要引入 Elasticsearch 等重型方案，纯 Python 的简单倒排索引就够用。

### 🟢 低优先级：长期愿景

#### 7. Plug 扩展系统

SilverBullet 的 Plug 系统非常强大，允许社区开发独立功能模块。nas-md 目前的 Plugin 系统只有一个 WorldClockPlugin，且是硬编码的。

长期来看，可以设计一个更开放的插件接口，允许用户编写 Python 插件来扩展 Telegram Bot 命令或 Web API。

#### 8. 离线优先 + 客户端缓存

SilverBullet 的 Service Worker + IndexedDB 方案实现了真正的离线优先。nas-md 的 PWA 目前只是"可安装"，没有真正的离线缓存和同步机制。

#### 9. 冲突处理

SilverBullet 检测到冲突时创建副本文件，让用户手动处理。nas-md 的 LCS merge 试图自动合并，但在多客户端场景下可能产生意外结果。可以参考 SilverBullet 的策略：冲突时保留两个版本，让用户决定。

## 不可借鉴的地方

以下 SilverBullet 的特性与 nas-md 的设计哲学冲突，不建议借鉴：

| 特性 | 原因 |
|------|------|
| TypeScript + Go 双语言 | nas-md 坚持纯 Python stdlib，引入 TS/Go 违背核心哲学 |
| 前端构建系统（ESBuild） | nas-md 明确"无构建系统"，10年后 index.html 应该直接能用 |
| CodeMirror 6 重型编辑器 | nas-md 前端追求极简，不需要这么复杂的编辑器 |
| IndexedDB 客户端存储 | nas-md 是服务端存储模型，不需要客户端数据库 |
| Space Lua 完整脚本语言 | 引入脚本语言大幅增加复杂度，与"LLM 能装下整个项目"的目标冲突 |
| Service Worker 同步 | 过于复杂，nas-md 的同步需求可以用更简单的方案满足 |

## 总结

SilverBullet 最核心的可借鉴价值是**三层能力递进**：

```
第一层：结构化元数据（Frontmatter）
    ↓
第二层：自动索引（Object Index）
    ↓
第三层：跨文件查询（LIQ）
```

这三层让笔记从"静态文档"变成"可编程数据库"。nas-md 目前只有第一层的部分能力（文件名约定），缺少索引和查询。

**建议的演进路径：**

1. **Phase 1** — 支持可选的 YAML frontmatter，FS 层解析
2. **Phase 2** — 增加轻量对象索引器（Task/Tag/Link），提供查询 API
3. **Phase 3** — 支持 `{{query}}` 模板语法，页面内动态嵌入查询结果
4. **Phase 4** — 全文搜索 + 双向链接反链

每一步都保持对现有文件的完全兼容，新功能是"增量叠加"而非"破坏性改造"。
