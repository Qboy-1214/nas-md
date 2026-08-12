# nas-md 移动端适配方案

## 一、项目功能全景

### 1. 入口与架构
- **双入口**: Telegram Bot + PWA Web（原生 JS，零框架）
- **数据存储**: 本地 `.md` 文件，SQLite FTS5 索引
- **认证**: Cookie 会话隔离（免登录，按 session UUID 区分用户）
- **部署**: Docker 一键，自签名 HTTPS，无第三方依赖

### 2. Web 前端功能（web/ 目录）

| 功能模块 | 文件 | 说明 |
|---------|------|------|
| 主布局 | index.html | 侧边栏 + 顶部栏 + 编辑区三栏布局 |
| 主逻辑 | app.js (~1500 行) | 状态管理、文件系统操作、API 调用、搜索、版本历史 |
| 编辑器 | editor.js (~15KB) | Vditor 三种模式切换（即时/分屏/所见即所得） |
| 文件管理 | files.js (~10KB) | 树形展示、文件夹 CRUD、拖拽 |
| 知识图谱 | graph-viewer.html | D3.js 力导向图（独立页面） |
| 样式 | app.css (2300 行) | 完整样式，含暗色模式、基本响应式 |
| 强化 | mermaid_enhancer.js | Mermaid 图表渲染 |
| 身份 | identity.js | 用户身份识别 |

### 3. 核心功能列表

#### 文件操作
- [x] 多目录挂载（不限数量）
- [x] 文件树浏览（展开/折叠）
- [x] 新建/重命名/删除文件
- [x] 新建/重命名/删除文件夹
- [x] 下载文件
- [x] 从磁盘刷新
- [x] 文件夹级批量操作

#### 编辑器
- [x] Vditor 三种模式：即时渲染 / 分屏预览 / 所见即所得
- [x] Markdown 语法高亮（highlight.js）
- [x] 自动保存（默认开启）
- [x] 手动保存（Ctrl+S）
- [x] 相对路径图片自动解析
- [x] 导出 PDF
- [x] 协同编辑（SSE 实时推送，段落级合并）
- [x] 远程文件代理（深链打开局域网其他服务的 MD 文件）

#### 搜索与知识图谱
- [x] 实时全文搜索（FTS5，毫秒级）
- [x] 反向链接查询
- [x] 结构化查询（query API）
- [x] 标签云
- [x] 孤立文件检测
- [x] 知识图谱可视化（D3.js，独立页面）
- [x] 路径查找（两个节点间的路径）

#### 版本与同步
- [x] 段落级版本历史（diff + 恢复）
- [x] 增量同步（LCS 文件合并）
- [x] 同步状态指示器
- [x] 冲突检测与解决

#### 用户与权限
- [x] 免登录 Cookie 会话
- [x] 多用户隔离（挂载点按用户隔离）
- [x] Admin 模式（宿主机目录可读写）
- [x] 公开挂载点（游客可访问）
- [x] 最近访问记录

#### 数据看板
- [x] 笔记数量统计
- [x] 任务完成率报告
- [x] 标签统计
- [x] 年度 Emoji 热力图（habits 模块）

#### Telegram Bot
- [x] 笔记管理（notes, file, newDir, renameDir, delDir, touchFile）
- [x] 任务管理（add, done, del, rename, today）
- [x] 搜索与反向链接
- [x] 习惯追踪（habits）
- [x] 今日报告（stats）

### 4. 现有移动端基础

| 项目 | 状态 |
|------|------|
| viewport meta | ✅ 已有 |
| 侧边栏固定 overlay | ✅ < 768px 已实现 |
| hamburger 菜单按钮 | ✅ 已有 |
| 部分 touch target 放大 | ✅ (44px min-height) |
| dashboard 网格 2 列 | ✅ |
| 暗色模式 | ✅ |
| print 样式 | ✅ |

---

## 二、移动端适配方案

### Phase 1: 基础修复（✅ 已完成）

- [x] 480px 断点：sidebar 宽度 240px、关闭按钮、more 菜单
- [x] 767px 断点：sidebar fixed overlay、hamburger 按钮
- [x] 编辑器 toolbar 横向滚动 + 滚动指示器
- [x] 编辑器全高适配 (`calc(100vh - 48px - 44px)`)
- [x] 搜索框 sticky 定位
- [x] 文件树 touch target 优化（44px min-height）
- [x] Modal 全屏适配
- [x] JS：overlay 点击关闭、移动端检测、toolbar 滚动处理
- [x] E2E 测试：13 个 Playwright 测试全部通过
- [x] Python 单元测试：8 个全部通过

### Phase 2: 交互优化（中优先级）

#### 2.1 文件树触控优化
- **问题**: 文件夹展开用点击，小屏上难以精确操作
- **方案**:
  - 添加 touch 手势支持（滑动手势展开/折叠）
  - 文件夹 chevron 区域扩大为 44px touch target
  - 长按文件弹出操作菜单（移动、删除、分享）

#### 2.2 搜索体验
- **问题**: 搜索结果在手机上展示不完整
- **方案**:
  - 搜索结果改为卡片式布局
  - 路径用省略号截断，点击展开
  - 搜索框固定在顶部（滚动时 sticky）

#### 2.3 版本历史
- **问题**: 版本列表在手机上难以浏览
- **方案**:
  - 版本历史改为全页面板
  - diff 视图在手机上改为单列滚动

### Phase 3: PWA 增强（长期）

#### 3.1 离线支持
- 当前已是 PWA，但需要增强：
  - Service Worker 缓存策略优化
  - 离线编辑队列（编辑后网络恢复时同步）
  - IndexedDB 作为离线存储备选

#### 3.2 移动推送
- 考虑接入 Telegram Bot 推送通知
- 协同编辑时的实时通知（已有 SSE，需要移动端 toast）

#### 3.3 手势导航
- 底部 Tab Bar 替代侧边栏（参考 Notion Mobile）
- 左右滑动手势切换文件
- 双击返回上一级

---

## 三、技术约束

1. **零依赖**: 保持原生 JS，不能用 React/Vue/Svelte
2. **无构建**: 不能用 TypeScript 编译步骤
3. **PWA 兼容**: 需要 work with current manifest (if any)
4. **Vditor 限制**: Vditor 的移动端支持有限，需要 workaround
5. **SSE 稳定性**: 移动网络下 SSE 连接需要 reconnection 逻辑

---

## 四、实施计划

### 步骤 1: 响应式 CSS 增强
- 新增 `@media (max-width: 480px)` 断点
- sidebar 关闭按钮
- topbar 按钮分组（主要/次要）
- 编辑器 toolbar 横向滚动
- 文件树 touch target 优化

### 步骤 2: JavaScript 交互增强
- sidebar overlay 点击关闭
- 文件树长按菜单
- 搜索框 sticky 定位
- 编辑器移动端键盘处理

### 步骤 3: PWA 离线优化
- Service Worker 缓存策略
- 离线编辑队列
- 网络状态检测与提示

### 步骤 4: 测试
- Chrome DevTools Device Mode 测试
- 真实手机测试
- Playwright 移动端 E2E 测试
