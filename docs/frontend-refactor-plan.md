# nas-md 前端重构计划

> 基于 Notion 设计系统（DESIGN.md）的前端 UI 重构方案

## 目录

1. [设计令牌映射](#1-设计令牌映射)
2. [页面结构重设计](#2-页面结构重设计)
3. [组件逐项重构](#3-组件逐项重构)
4. [交互改进](#4-交互改进)
5. [暗色模式](#5-暗色模式)
6. [响应式](#6-响应式)
7. [实施阶段](#7-实施阶段)

---

## 1. 设计令牌映射

### 1.1 色彩体系

#### 主色

| Token | 当前值 | Notion 值 | 用途 |
|---|---|---|---|
| `--c-primary` | `#4f46e5` | `#5645d4` | 主 CTA、按钮、链接激活态 |
| `--c-primary-hover` | `#4338ca` | `#4534b3` | 按钮按下态 |
| `--c-primary-deep` | — | `#3a2a99` | 深色强调 |
| `--c-on-primary` | `#ffffff` | `#ffffff` | 主色上的文字 |

#### 中性色

| Token | 当前值 | Notion 值 | 用途 |
|---|---|---|---|
| `--c-bg` | `#ffffff` | `#ffffff` | 画布背景 |
| `--c-bg-sidebar` | `#f7f7f8` | `#f6f5f4` | 侧边栏背景（surface） |
| `--c-bg-hover` | `#ececef` | `#f0eeec` | 悬停背景 |
| `--c-bg-active` | `#e3e3e8` | `#e5e3df` | 激活/选中背景 |
| `--c-border` | `#e4e4ea` | `#e5e3df` | 边框（hairline） |
| `--c-border-strong` | — | `#c8c4be` | 强调边框 |

#### 文字色

| Token | 当前值 | Notion 值 | 用途 |
|---|---|---|---|
| `--c-text` | `#1a1a2e` | `#1a1a1a` | 主文字（ink） |
| `--c-text-secondary` | `#6b6b80` | `#787671` | 次要文字（steel） |
| `--c-text-muted` | `#9999ad` | `#bbb8b1` | 弱化文字（muted） |

#### 语义色

| Token | 当前值 | Notion 值 | 用途 |
|---|---|---|---|
| `--c-link` | — | `#0075de` | 链接蓝 |
| `--c-link-hover` | — | `#005bab` | 链接悬停 |
| `--c-success` | `#22c55e` | `#1aae39` | 成功 |
| `--c-warning` | `#f59e0b` | `#dd5b00` | 警告 |
| `--c-danger` | `#ef4444` | `#e03131` | 危险 |

#### Pastel Tint（欢迎页卡片）

| Token | Notion 值 | 用途 |
|---|---|---|
| `--c-tint-lavender` | `#e6e0f5` | 淡紫 |
| `--c-tint-sky` | `#dcecfa` | 淡蓝 |
| `--c-tint-mint` | `#d9f3e1` | 淡绿 |
| `--c-tint-peach` | `#ffe8d4` | 淡橙 |
| `--c-tint-rose` | `#fde0ec` | 淡粉 |
| `--c-tint-yellow` | `#fef7d6` | 淡黄 |

### 1.2 字体体系

#### 字体栈

```
当前：-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif
目标："Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif
```

Inter 字体引入方式：本地托管（`web/lib/fonts/inter-*.woff2`），避免 CDN 依赖。

#### 字号层级

| Token | 当前 | Notion | 用途 |
|---|---|---|---|
| `--f-hero` | — | 48px / 600 | 欢迎页大标题 |
| `--f-h1` | 24px | 28px / 600 | 页面标题 |
| `--f-h2` | 18px | 22px / 600 | 区块标题 |
| `--f-h3` | 15px | 18px / 600 | 子标题 |
| `--f-body` | 14px | 16px / 400 | 正文 |
| `--f-body-sm` | 13px | 14px / 400 | 次要文本 |
| `--f-caption` | 12px | 13px / 400 | 注释 |
| `--f-micro` | — | 12px / 500 | 微小标签 |

#### 行高

- 标题：1.25-1.30
- 正文：1.65（编辑器区域）、1.50（UI 文本）
- 注释：1.40

#### 字重

- Regular：400
- Medium：500（按钮、标签）
- Semibold：600（标题）
- Bold：700（强调）

### 1.3 圆角

| Token | 当前 | Notion | 用途 |
|---|---|---|---|
| `--r-sm` | 4px | 6px | 小元素（标签、徽章内部） |
| `--r-md` | 8px | 8px | 按钮、输入框 |
| `--r-lg` | 16px | 12px | 卡片 |
| `--r-xl` | — | 16px | 模态框 |
| `--r-full` | 100px | 9999px | 徽章、pill 标签 |

### 1.4 间距

基于 4px 基线：

| Token | 值 | 用途 |
|---|---|---|
| `--s-xs` | 4px | 图标与文字间距 |
| `--s-sm` | 8px | 紧凑间距 |
| `--s-md` | 12px | 组件内间距 |
| `--s-lg` | 16px | 标准间距 |
| `--s-xl` | 24px | section 内间距 |
| `--s-xxl` | 32px | section 间间距 |
| `--s-section` | 48px | 欢迎页 section 间距 |

### 1.5 阴影

| Token | 当前 | Notion | 用途 |
|---|---|---|---|
| `--shadow-sm` | `0 1px 3px rgba(0,0,0,0.08)` | `0 1px 2px rgba(0,0,0,0.06)` | 卡片、按钮 |
| `--shadow-md` | `0 10px 40px rgba(0,0,0,0.12)` | `0 4px 12px rgba(0,0,0,0.08)` | 模态框、弹出层 |
| `--shadow-lg` | — | `0 8px 24px rgba(0,0,0,0.12)` | 侧边栏浮层 |

---

## 2. 页面结构重设计

### 2.1 当前结构

```
layout (flex row, 100vh)
├── sidebar (280px fixed)
│   ├── sidebar-header (48px, logo + name)
│   ├── search-box (input)
│   ├── file-tree (flex 1, scroll)
│   └── sidebar-footer (buttons: 首页/设置/登录)
└── main (flex 1)
    ├── topbar (48px)
    │   ├── breadcrumb
    │   └── topbar-actions (mode switch + save)
    └── editor-area (flex 1)
        ├── welcome-page
        ├── editor-container
        └── settings-page
```

### 2.2 目标结构

```
layout (flex row, 100vh)
├── sidebar (240px)
│   ├── sidebar-header (workspace name + avatar)
│   ├── search-pill (rounded, with icon)
│   ├── page-tree (indented tree)
│   │   ├── favorites section
│   │   └── all pages section
│   └── sidebar-footer (挂载按钮，图谱/看板入口已隐藏)
├── main (flex 1)
│   ├── page-header (52px)
│   │   ├── breadcrumb (lighter color)
│   │   └── actions (mode switch + save, right-aligned)
│   └── content-area (flex 1)
│       ├── welcome-page (redesigned)
│       └── editor-container
```

### 2.3 关键变化

| 维度 | 当前 | 目标 |
|---|---|---|
| 侧边栏宽度 | 280px | 240px |
| 侧边栏背景 | `#f7f7f8` | `#f6f5f4` |
| 顶部栏高度 | 48px | 52px |
| 面包屑位置 | topbar 左侧 | page-header 左侧 |
| 模式切换 | 按钮组 | segmented tab（下划线式） |
| 保存按钮 | primary 色实心 | ghost 样式，dirty 时高亮 |
| 文件树图标 | emoji (📁📝📄) | 内联 SVG，16x16 |
| 文件树缩进 | 12-28px 混合 | 统一 16px/级 |
| 底部操作 | emoji 按钮 | 文字链接 + 小图标 |

---

## 3. 组件逐项重构

### 3.1 侧边栏

#### 当前实现

- `sidebar-header`：h2 logo，无 workspace 概念
- `search-box`：矩形输入框，无搜索图标
- `file-tree`：递归渲染，emoji 图标，▶/▼ 展开/折叠
- `sidebar-footer`：4 个 emoji 按钮（🏠⚙️登录/退出）

#### 目标样式

**Sidebar Header：**
- 高度 48px，左右 padding 12px
- 左侧：workspace 图标（24x24 圆角方形，紫色渐变）
- 右侧：workspace 名（14px semibold）
- 整体无边框，与背景融为一体

**Search Pill：**
- 高度 36px（非 44px），圆角 8px
- 背景 `#ffffff`，边框 `1px solid #e5e3df`
- 左侧搜索图标（16x16，steel 色）
- 聚焦时边框变为 `2px solid #5645d4`
- placeholder 文字颜色 `#bbb8b1`

**File Tree：**
- 每级缩进 16px
- 文件夹图标：16x16 SVG，chevron 右箭头（折叠）/ 下箭头（展开）
- 文件图标：16x16 SVG，文档图标
- 节点高度 28px，圆角 6px
- hover 背景 `#f0eeec`
- 激活态：背景 `#e5e3df`，文字颜色 `#1a1a1a`，左侧 3px 紫色竖线
- 展开/折叠动画：150ms ease（max-height transition）

**Sidebar Footer：**
- 2 个文字链接：「New page」+「Settings」
- 12px medium，颜色 `#787671`
- hover 时颜色 `#1a1a1a`
- 底部留白 16px

### 3.2 顶部栏（Page Header）

#### 当前实现

- 48px 高度，单行 flex
- 面包屑 + 模式切换 + 保存按钮全部在一行
- 模式切换：3 个按钮组，2px padding

#### 目标样式

**布局：**
- 高度 52px
- 左侧：面包屑（14px，`#787671`），当前文件名（14px semibold，`#1a1a1a`）
- 右侧：操作区（flex row，gap 8px）

**模式切换（Segmented Tab）：**
- 容器：无背景，无边框
- 每个 tab：14px medium，`#787671`，padding 6px 12px，圆角 6px
- 激活态：`#1a1a1a`，底部 2px 下划线（`#1a1a1a`）
- hover：`#1a1a1a`
- 切换动画：下划线滑动 150ms

**保存按钮：**
- 默认：ghost 样式，透明背景，`#787671` 文字，`1px solid #c8c4be` 边框
- dirty 时：`#5645d4` 文字，`1px solid #5645d4` 边框（无填充）
- 按下：`#4534b3`
- 禁用：`#bbb8b1` 文字，`#e5e3df` 边框

### 3.3 欢迎页

#### 当前实现

- 挂载目录输入框（路径输入 + 浏览按钮 + "挂载"按钮，无显示名称输入框）
- 已挂载目录列表
- 最近访问文件列表（按访问时间排序）

> 注：标题、简介、"打开目录"/"新建笔记"/"导入文件"快捷卡片已移除。

#### 目标样式

**挂载目录输入区：**
- 路径输入框 + 浏览按钮（inline）+ "挂载"按钮
- 输入框：高度 44px，背景 `#ffffff`，边框 `1px solid #e5e3df`，圆角 8px
- 浏览按钮：`button-secondary` 样式（transparent 背景，`1px solid #c8c4be` 边框），padding 10px 18px
- 挂载按钮：`button-primary` 样式（`#5645d4` 背景），padding 10px 18px

**最近访问：**
- 标题：13px semibold uppercase，`#bbb8b1`，letter-spacing: 0.5px
- 每个文件：高度 36px，hover 背景 `#f6f5f4`，圆角 6px
- 文件名：14px medium
- 路径 + 时间：13px，`#bbb8b1`
- 卸载挂载点时自动清理对应条目

### 3.4 编辑器区域（Vditor CSS 变量方案）

Vditor 的样式系统完全建立在 CSS 变量上。**不需要逐一覆盖内部选择器**，只需在 `.vditor` 选择器中重新定义变量，所有组件（工具栏、内容区、代码块、引用块、大纲栏、弹出面板）自动更新。

#### 亮色模式变量

```css
.vditor {
  /* 边框与分割线 */
  --border-color: #e5e3df;

  /* 工具栏 */
  --toolbar-background-color: #f6f5f4;
  --toolbar-icon-color: #787671;
  --toolbar-icon-hover-color: #5645d4;
  --toolbar-height: 35px;

  /* 编辑区 / 文本区域 */
  --textarea-background-color: #ffffff;
  --textarea-text-color: #1a1a1a;

  /* 弹出面板（菜单、emoji 选择器） */
  --panel-background-color: #ffffff;
  --panel-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);

  /* 次要图标、禁用状态、placeholder */
  --second-color: rgba(120, 118, 113, 0.36);

  /* 引用块文字颜色 */
  --blockquote-color: #787671;

  /* 标题底边框（IR 模式） */
  --heading-border-color: #e5e3df;

  /* IR 模式语法标记颜色 */
  --ir-heading-color: #5645d4;
  --ir-title-color: #bbb8b1;
  --ir-bi-color: #5645d4;
  --ir-link-color: #0075de;
  --ir-bracket-color: #0075de;
  --ir-paren-color: #2a9d99;

  /* 字数统计背景 */
  --count-background-color: rgba(86, 69, 212, 0.08);

  /* 列表标记颜色 */
  --list-mark-color: #5645d4;
}
```

#### 变量 → 组件映射表

| 变量 | 影响的组件 |
|---|---|
| `--border-color` | 工具栏底边框、分割线、输入框边框 |
| `--toolbar-background-color` | 工具栏背景 |
| `--toolbar-icon-color` | 工具栏按钮（加粗、斜体等图标） |
| `--toolbar-icon-hover-color` | 工具栏按钮 hover 时的颜色 |
| `--toolbar-height` | 工具栏高度 |
| `--textarea-background-color` | 编辑区域背景 |
| `--textarea-text-color` | 编辑区域文字颜色 |
| `--panel-background-color` | 下拉菜单、emoji 面板、链接编辑面板 |
| `--panel-shadow` | 弹出面板的阴影 |
| `--second-color` | 禁用按钮、placeholder、折叠图标 |
| `--blockquote-color` | 引用块文字颜色 |
| `--heading-border-color` | IR 模式下 h1/h2 的底边框 |
| `--ir-heading-color` | IR 模式下 `#` 标记的颜色 |
| `--ir-bi-color` | IR 模式下 `**粗体**` 标记的颜色 |
| `--ir-link-color` | IR 模式下 `[链接](url)` 标记颜色 |
| `--ir-bracket-color` | IR 模式下 `[` `]` 括号颜色 |
| `--count-background-color` | 底部字数统计栏背景 |
| `--list-mark-color` | 有序列表序号、无序列表圆点颜色 |

#### 需要额外覆盖的硬编码样式

以下属性在 Vditor 中是硬编码值（不使用 CSS 变量），需要直接覆盖：

```css
/* 代码块背景和边框（硬编码 #f6f8fa） */
.vditor-ir pre.vditor-reset,
.vditor-wysiwyg pre.vditor-reset,
.vditor-sv pre.vditor-reset,
.vditor-preview pre {
  background-color: #f6f5f4 !important;
  border: 1px solid #e5e3df !important;
  border-radius: 8px !important;
}

/* 引用块左侧竖线（硬编码 border-left） */
.vditor-ir blockquote,
.vditor-wysiwyg blockquote,
.vditor-preview blockquote {
  border-left: 3px solid #c8c4be !important;
  background-color: #f6f5f4 !important;
  color: #787671 !important;
}

/* 表格表头背景 */
.vditor-ir table thead,
.vditor-wysiwyg table thead,
.vditor-preview table thead {
  background-color: #f6f5f4 !important;
}

/* 表格边框 */
.vditor-ir table td,
.vditor-ir table th,
.vditor-wysiwyg table td,
.vditor-wysiwyg table th,
.vditor-preview table td,
.vditor-preview table th {
  border-color: #e5e3df !important;
}

/* IR 模式标题前缀标记 "H1" "H2" 的颜色 */
.vditor-ir .vditor-reset > h1:before,
.vditor-ir .vditor-reset > h2:before,
.vditor-ir .vditor-reset > h3:before,
.vditor-ir .vditor-reset > h4:before,
.vditor-ir .vditor-reset > h5:before,
.vditor-ir .vditor-reset > h6:before {
  color: #bbb8b1 !important;
}

/* WYSIWYG 模式标题前缀标记 */
.vditor-wysiwyg > .vditor-reset > h1:before,
.vditor-wysiwyg > .vditor-reset > h2:before,
.vditor-wysiwyg > .vditor-reset > h3:before,
.vditor-wysiwyg > .vditor-reset > h4:before,
.vditor-wysiwyg > .vditor-reset > h5:before,
.vditor-wysiwyg > .vditor-reset > h6:before {
  color: #bbb8b1 !important;
}

/* 大纲栏激活项 */
.vditor-outline li > span.outline-active {
  color: #5645d4;
  font-weight: 700;
}

/* 大纲栏非激活项 */
.vditor-outline li > span {
  font-size: 13px;
}

/* tooltip 背景（硬编码 #3b3e43） */
.vditor-tooltipped::after {
  background: #37352f !important;
}
.vditor-tooltipped--hover::before,
.vditor-tooltipped:hover::before {
  border-bottom-color: #37352f !important;
}

/* 分割线颜色 */
.vditor-ir hr,
.vditor-wysiwyg hr {
  background-color: #e5e3df !important;
}

/* 脚注区域顶部边框 */
.vditor-ir div[data-type="footnotes-block"],
.vditor-wysiwyg div[data-type="footnotes-block"] {
  border-top-color: #e5e3df !important;
}

/* 链接颜色 */
.vditor-ir a,
.vditor-wysiwyg a,
.vditor-preview a {
  color: #0075de !important;
}

/* 行内代码背景 */
.vditor-ir code,
.vditor-wysiwyg code,
.vditor-preview code {
  background-color: #f6f5f4 !important;
  color: #5645d4 !important;
}
```

#### 内容区排版

通过 Vditor 配置 API 调整字号和行高：

```javascript
// editor.js initEditor 中
_vditor = new Vditor('vditor', {
  // ... 其他配置
  preview: {
    mode: 'both',
    markdown: {
      toc: true,
      autoSpace: true,
      fixTermTypo: true,
    },
    hljs: { enable: true, style: 'github', lineNumber: false },
    theme: { current: 'light', path: '/lib/vditor-cdn/dist/css/content-theme' },
  },
});
```

行高和字号通过 CSS 变量无法控制，需要覆盖：

```css
/* 编辑区正文字号 */
.vditor-ir .vditor-reset {
  font-size: 16px;
  line-height: 1.7;
}

/* IR 模式标题字号 */
.vditor-ir .vditor-reset > h1 { font-size: 28px; font-weight: 600; line-height: 1.25; }
.vditor-ir .vditor-reset > h2 { font-size: 22px; font-weight: 600; line-height: 1.25; }
.vditor-ir .vditor-reset > h3 { font-size: 18px; font-weight: 600; line-height: 1.30; }
.vditor-ir .vditor-reset > h4 { font-size: 16px; font-weight: 600; line-height: 1.35; }
.vditor-ir .vditor-reset > h5 { font-size: 16px; font-weight: 600; line-height: 1.35; }
.vditor-ir .vditor-reset > h6 { font-size: 16px; font-weight: 600; line-height: 1.35; }

/* SV 模式标题字号 */
.vditor-sv .h1 { font-size: 1.75em; font-weight: 600; }
.vditor-sv .h2 { font-size: 1.55em; font-weight: 600; }
.vditor-sv .h3 { font-size: 1.38em; font-weight: 600; }
.vditor-sv .h4 { font-size: 1.25em; font-weight: 600; }
.vditor-sv .h5 { font-size: 1.13em; font-weight: 600; }
.vditor-sv .h6 { font-size: 1em; font-weight: 600; }

/* WYSIWYG 模式标题字号 */
.vditor-wysiwyg .vditor-reset > h1 { font-size: 28px; font-weight: 600; }
.vditor-wysiwyg .vditor-reset > h2 { font-size: 22px; font-weight: 600; }
.vditor-wysiwyg .vditor-reset > h3 { font-size: 18px; font-weight: 600; }
.vditor-wysiwyg .vditor-reset > h4 { font-size: 16px; font-weight: 600; }
.vditor-wysiwyg .vditor-reset > h5 { font-size: 16px; font-weight: 600; }
.vditor-wysiwyg .vditor-reset > h6 { font-size: 16px; font-weight: 600; }

/* 预览区排版 */
.vditor-preview .vditor-reset {
  font-size: 16px;
  line-height: 1.7;
}
```

### 3.5 模态框

**遮罩：**
- 背景：`rgba(0, 0, 0, 0.3)`，backdrop-filter: blur(4px)
- 进入动画：opacity 0→1，150ms ease

**弹窗体：**
- 背景：`#ffffff`
- 圆角 16px
- 内边距 28px 32px
- 最大宽度 480px
- 阴影：`0 8px 24px rgba(0, 0, 0, 0.12)`
- 进入动画：opacity 0→1 + translateY(8px→0)，200ms ease
- 退出动画：opacity 1→0 + translateY(0→4px)，150ms ease

**输入框：**
- 高度 40px
- 背景：`#ffffff`
- 边框：`1px solid #c8c4be`
- 圆角 8px
- 聚焦：`2px solid #5645d4`

**按钮：**
- Primary：`#5645d4` 背景，白色文字，圆角 8px，padding 8px 18px
- Secondary：透明背景，`#1a1a1a` 文字，`1px solid #c8c4be` 边框
- Ghost：透明背景，`#787671` 文字，无边框

### 3.6 Toast

- 背景：`#37352f`（charcoal）
- 文字：`#ffffff`，13px
- 圆角 8px
- 内边距 10px 18px
- 阴影：`0 4px 12px rgba(0, 0, 0, 0.15)`
- 位置：底部 24px，右侧 24px
- 进入：opacity 0→1 + translateY(8px→0)，200ms ease
- 退出：opacity 1→0，150ms ease（在自动消失前）

### 3.7 大纲栏

- 所有标题：13px，`#787671`，常规字重
- 定位到的标题：13px，`#5645d4`，字重 700
- 缩进：每级 12px
- 行高 28px
- hover 背景：`#f6f5f4`

---

## 4. 交互改进

### 4.1 过渡与动画

| 交互 | 属性 | 时长 | 缓动 |
|---|---|---|---|
| 按钮 hover | background, border-color, color | 150ms | ease |
| 文件树节点展开 | max-height, opacity | 200ms | ease |
| 侧边栏 collapse | width | 200ms | ease |
| 页面切换 | opacity | 150ms | ease |
| 模态框 enter/exit | opacity, translateY | 200ms / 150ms | ease |
| Toast enter/exit | opacity, translateY | 200ms / 150ms | ease |
| Tab 切换 | border-color, color | 150ms | ease |
| 卡片 hover | border-color, box-shadow, transform | 150ms | ease |

### 4.2 键盘快捷键

| 快捷键 | 操作 |
|---|---|
| `Ctrl+K` / `Cmd+K` | 聚焦搜索框 |
| `Ctrl+N` / `Cmd+N` | 新建笔记 |
| `Ctrl+S` / `Cmd+S` | 保存（已有） |
| `Ctrl+/` | 切换编辑模式 |
| `Escape` | 关闭模态框 / 清除搜索 |

### 4.3 文件树交互

- 点击目录名：展开/折叠（当前行为，保留）
- 右键目录：重命名 / 新建子文件 / 删除
- 拖拽文件：移动到另一目录
- 文件树节点 hover 时显示操作图标（⋯），替代当前始终显示的 emoji

---

## 5. 暗色模式

### 5.1 实现方式

暗色模式通过 `document.documentElement.classList.toggle('dark')` 切换，偏好保存到 `localStorage`。

两套变量分别在 `:root`（亮色）和 `.dark`（暗色）中定义。Vditor 的暗色变量也在 `.dark .vditor` 中覆盖。

### 5.2 页面级暗色变量

```css
:root {
  --c-bg: #ffffff;
  --c-bg-sidebar: #f6f5f4;
  --c-bg-hover: #f0eeec;
  --c-bg-active: #e5e3df;
  --c-border: #e5e3df;
  --c-border-strong: #c8c4be;
  --c-text: #1a1a1a;
  --c-text-secondary: #787671;
  --c-text-muted: #bbb8b1;
  --c-primary: #5645d4;
  --c-primary-hover: #4534b3;
  --c-link: #0075de;
  --c-code-bg: #f6f5f4;
}

.dark {
  --c-bg: #191919;
  --c-bg-sidebar: #202020;
  --c-bg-hover: #2a2a2a;
  --c-bg-active: #333333;
  --c-border: #333333;
  --c-border-strong: #444444;
  --c-text: #e0e0e0;
  --c-text-secondary: #a0a0a0;
  --c-text-muted: #666666;
  --c-primary: #818cf8;
  --c-primary-hover: #a5b4fc;
  --c-link: #60a5fa;
  --c-code-bg: #2a2a2a;
}
```

### 5.3 Vditor 暗色变量

Vditor 内置了 `.vditor--dark` 类，但我们使用自定义的 `.dark .vditor` 选择器，确保与页面级暗色模式同步。

```css
.dark .vditor {
  /* 边框与分割线 */
  --border-color: #333333;

  /* 工具栏 */
  --toolbar-background-color: #202020;
  --toolbar-icon-color: #a0a0a0;
  --toolbar-icon-hover-color: #818cf8;

  /* 编辑区 / 文本区域 */
  --textarea-background-color: #191919;
  --textarea-text-color: #e0e0e0;

  /* 弹出面板 */
  --panel-background-color: #2a2a2a;
  --panel-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);

  /* 次要图标、禁用状态 */
  --second-color: rgba(160, 160, 160, 0.36);

  /* 引用块 */
  --blockquote-color: #a0a0a0;

  /* 标题底边框 */
  --heading-border-color: #333333;

  /* IR 模式语法标记 */
  --ir-heading-color: #818cf8;
  --ir-title-color: #666666;
  --ir-bi-color: #818cf8;
  --ir-link-color: #60a5fa;
  --ir-bracket-color: #60a5fa;
  --ir-paren-color: #2a9d99;

  /* 字数统计 */
  --count-background-color: rgba(129, 140, 248, 0.12);

  /* 列表标记 */
  --list-mark-color: #818cf8;
}
```

### 5.4 Vditor 暗色模式硬编码覆盖

以下亮色硬编码值需要在暗色模式下覆盖：

```css
.dark .vditor-ir pre.vditor-reset,
.dark .vditor-wysiwyg pre.vditor-reset,
.dark .vditor-sv pre.vditor-reset,
.dark .vditor-preview pre {
  background-color: #2a2a2a !important;
  border-color: #333333 !important;
}

.dark .vditor-ir blockquote,
.dark .vditor-wysiwyg blockquote,
.dark .vditor-preview blockquote {
  background-color: #2a2a2a !important;
  border-left-color: #444444 !important;
  color: #a0a0a0 !important;
}

.dark .vditor-ir table thead,
.dark .vditor-wysiwyg table thead,
.dark .vditor-preview table thead {
  background-color: #2a2a2a !important;
}

.dark .vditor-ir table td,
.dark .vditor-ir table th,
.dark .vditor-wysiwyg table td,
.dark .vditor-wysiwyg table th,
.dark .vditor-preview table td,
.dark .vditor-preview table th {
  border-color: #333333 !important;
}

.dark .vditor-ir code,
.dark .vditor-wysiwyg code,
.dark .vditor-preview code {
  background-color: #2a2a2a !important;
  color: #818cf8 !important;
}

.dark .vditor-ir a,
.dark .vditor-wysiwyg a,
.dark .vditor-preview a {
  color: #60a5fa !important;
}

.dark .vditor-ir hr,
.dark .vditor-wysiwyg hr {
  background-color: #333333 !important;
}

.dark .vditor-tooltipped::after {
  background: #e0e0e0 !important;
  color: #191919 !important;
}

.dark .vditor-tooltipped--hover::before,
.dark .vditor-tooltipped:hover::before {
  border-bottom-color: #e0e0e0 !important;
}

/* 大纲栏 */
.dark .vditor-outline li > span {
  color: #a0a0a0;
}

.dark .vditor-outline li > span.outline-active {
  color: #818cf8;
}
```

### 5.5 暗色模式切换按钮

在设置页或顶部栏添加切换按钮：

```javascript
// app.js
function toggleDarkMode() {
  const isDark = document.documentElement.classList.toggle('dark');
  localStorage.setItem('nasmd_dark', isDark ? '1' : '0');
}

// DOMContentLoaded 中恢复偏好
if (localStorage.getItem('nasmd_dark') === '1') {
  document.documentElement.classList.add('dark');
}
```

---

## 6. 响应式

### 6.1 断点

| 断点 | 宽度 | 变化 |
|---|---|---|
| 桌面 | ≥ 1024px | 完整布局 |
| 平板 | 768-1023px | 侧边栏收窄到 200px，欢迎页卡片 2 列 |
| 手机 | < 768px | 侧边栏变为 overlay（可收起），编辑器全宽 |

### 6.2 触摸目标

- 所有可点击元素最小 40px
- 文件树节点高度 36px → 40px（移动端）
- 按钮高度 ≥ 40px

### 6.3 侧边栏折叠

- 桌面：始终可见
- 平板：可见，但宽度收窄
- 手机：默认隐藏，点击菜单按钮展开（overlay 模式，带遮罩）

---

## 7. 实施阶段

### Phase 1：设计令牌 + 全局样式

**范围：** `app.css` 全文重写

**任务：**
1. 重写 `:root` 变量，替换为 Notion 色彩体系
2. 引入 Inter 字体（本地托管）
3. 更新基础排版（body, heading, code, blockquote, table）
4. 更新滚动条、选择高亮等全局样式
5. 添加暗色模式变量

**验证：** 刷新页面，确认颜色、字体、圆角、间距全部更新

**预计工作量：** 1-2 天

---

### Phase 2：侧边栏重构

**范围：** `app.css`（侧边栏部分）+ `app.js`（`renderSidebar` / `renderEntries`）+ `index.html`（侧边栏 HTML）

**任务：**
1. 收窄侧边栏到 240px
2. 重写 sidebar header（workspace icon + name）
3. 重写搜索框（pill 风格，带搜索图标）
4. 文件树改为 SVG 图标，统一 16px 缩进
5. 添加展开/折叠动画
6. 重写底部操作区（文字链接）

**验证：** 侧边栏视觉与 Notion 一致，文件树操作流畅

**预计工作量：** 1 天

---

### Phase 3：顶部栏 + 编辑器区域

**范围：** `app.css`（topbar 部分）+ `app.js`（`setEditorMode` / `saveFile`）+ `index.html`（topbar HTML）

**任务：**
1. 重写 topbar 布局（面包屑左，操作右）
2. 模式切换改为 segmented tab（下划线式）
3. 保存按钮改为 ghost 样式 + dirty 高亮
4. Vditor 样式覆盖（工具栏、内容区、代码块、引用块、表格）
5. 大纲栏样式更新

**验证：** 编辑器视觉与 Notion 一致，模式切换/保存功能正常

**预计工作量：** 1 天

---

### Phase 4：欢迎页 + 模态框 + Toast

**范围：** `app.css`（welcome / modal / toast 部分）+ `app.js`（相关函数）+ `index.html`（欢迎页 HTML）

**任务：**
1. 重新设计欢迎页 Hero 区域
2. 快速操作区改为 3 列卡片网格（pastel tint）
3. 最近文件列表样式更新
4. 模态框添加进入/退出动画
5. Toast 样式更新（charcoal 背景 + 动画）

**验证：** 欢迎页视觉与 Notion 一致，模态框/Toast 动画流畅

**预计工作量：** 1 天

---

### Phase 5：交互优化 + 暗色模式

**范围：** `app.js`（快捷键、动画）+ `app.css`（暗色模式）

**任务：**
1. 添加键盘快捷键（Ctrl+K/N/S/）
2. 文件树 hover 操作图标（⋯）
3. 卡片 hover 动画
4. 暗色模式完整实现 + 手动切换按钮
5. 响应式优化（侧边栏折叠、触摸目标）

**验证：** 快捷键可用，暗色模式切换正常，移动端布局合理

**预计工作量：** 1 天

---

### Phase 6：测试 + 修复

**任务：**
1. 跨浏览器测试（Chrome / Edge / Firefox）
2. 暗色模式各组件检查
3. 移动端响应式测试
4. 动画性能检查（无卡顿）
5. 功能回归测试（打开/保存/搜索/模式切换）

**预计工作量：** 1 天

---

## 附录 A：文件变更清单

| 文件 | Phase | 变更类型 |
|---|---|---|
| `web/app.css` | 1, 2, 3, 4, 5 | 全文重写 |
| `web/index.html` | 2, 3, 4 | 结构微调 |
| `web/app.js` | 2, 3, 4, 5 | 交互逻辑 + 渲染函数 |
| `web/editor.js` | 3 | Vditor 样式覆盖 |
| `web/lib/fonts/` | 1 | 新增 Inter 字体文件 |

## 附录 B：风险与注意事项

1. **Vditor CSS 变量覆盖**：Vditor 的样式系统基于 CSS 变量，大部分视觉属性（工具栏、边框、背景、文字颜色、引用块、大纲栏等）可通过 `.vditor` 选择器直接覆盖变量，无需修改 Vditor 源码。少数硬编码值（代码块背景、引用块竖线、表格边框、tooltip 背景、标题前缀标记颜色）需要 `!important` 覆盖，已在 3.4 节中列出。暗色模式同理，在 `.dark .vditor` 中重新定义变量即可。

2. **字体加载性能**：Inter 字体文件约 150KB（woff2），首次加载可能有 FOUT（无样式字体闪烁）。使用 `font-display: swap` 缓解。

3. **暗色模式的图片**：欢迎页如有插图，暗色模式下可能需要调整亮度或替换为暗色版本。当前版本无图片，低优先级。

4. **向后兼容**：重构不涉及后端 API 变更，所有功能保持不变。纯前端视觉层改造。

5. **动画性能**：侧边栏展开/折叠使用 `max-height` 过渡在节点过多时可能有性能问题。如遇到，改为 `transform: scaleY` 或简单地使用 `display` 切换。
