# nas-md 前端重构计划 v2

> 基于 Notion 设计系统（DESIGN.md）的精确重构方案
> v2 在 v1 基础上做了全面的差距审计、属性级细化和可执行性强化

---

## 目录

1. [设计审计（含逐属性严重度标记）](#1-设计审计)
   - [1.1 色彩硬编码审计](#11-appcss-色彩硬编码审计)
   - [1.2 字体定义审计](#12-appcss-字体定义审计)
   - [1.3 间距硬编码审计](#13-appcss-间距硬编码审计)
   - [1.4 圆角硬编码审计](#14-appcss-圆角硬编码审计)
   - [1.5 阴影硬编码审计](#15-appcss-阴影硬编码审计)
   - [1.6 组件级审计](#16-组件级审计)
   - [1.7 app.js 硬编码审计](#17-appjs-硬编码值审计)
   - [1.8 editor.js 硬编码审计](#18-editorjs-硬编码值审计)
   - [1.9 index.html 结构审计](#19-indexhtml-结构审计)
   - [1.10 响应式审计](#110-响应式审计)
   - [1.11 审计总结](#111-审计总结)
2. [色彩系统重构](#2-色彩系统重构)
3. [排版系统重构](#3-排版系统重构)
4. [间距与布局系统](#4-间距与布局系统)
5. [圆角与阴影体系](#5-圆角与阴影体系)
6. [组件重构规格](#6-组件重构规格)
7. [暗色模式](#7-暗色模式)
8. [响应式](#8-响应式)
9. [实施阶段](#9-实施阶段)
10. [风险与注意事项](#10-风险与注意事项)

---

## 1. 设计审计

逐文件、逐属性搜索当前代码中的所有硬编码值，与 DESIGN.md 精确对比。
严重程度标记：🔴 严重偏差（视觉完全不同）｜🟡 中等偏差（可感知但不影响功能）｜🟢 基本符合（误差 < 10%）

---

### 1.1 app.css 色彩硬编码审计

搜索范围：全文所有 `#xxx` / `#xxxxxx` 颜色值（排除 CSS 变量定义行和 fallback 值）

| 行号 | 选择器 | 硬编码值 | DESIGN.md 对应值 | 严重度 | 说明 |
|---|---|---|---|---|---|
| 7 | `:root --bg` | `#ffffff` | `#ffffff` (canvas) | 🟢 | 一致 |
| 8 | `:root --bg-sidebar` | `#f7f7f8` | `#f6f5f4` (surface) | 🟡 | 偏冷灰 → 暖灰，ΔE ≈ 1.5 |
| 9 | `:root --bg-hover` | `#ececef` | `#f0eeec` (tint-gray) | 🟡 | 偏紫灰 → 暖灰，ΔE ≈ 3 |
| 10 | `:root --bg-active` | `#e3e3e8` | `#e5e3df` (hairline) | 🟡 | 偏蓝灰 → 暖灰，ΔE ≈ 2.5 |
| 11 | `:root --text` | `#1a1a2e` | `#1a1a1a` (ink) | 🟡 | 偏蓝黑 → 纯黑，ΔE ≈ 2 |
| 12 | `:root --text-secondary` | `#6b6b80` | `#787671` (steel) | 🟡 | 偏紫灰 → 暖灰，ΔE ≈ 3.5 |
| 13 | `:root --text-muted` | `#9999ad` | `#bbb8b1` (muted) | 🟡 | 偏紫灰 → 暖灰，ΔE ≈ 4 |
| 14 | `:root --border` | `#e4e4ea` | `#e5e3df` (hairline) | 🟡 | 偏冷 → 暖灰，ΔE ≈ 1.5 |
| 15 | `:root --accent` | `#4f46e5` | `#5645d4` (primary) | 🔴 | 色相偏移 +3°，饱和度略低，视觉明显不同 |
| 16 | `:root --accent-hover` | `#4338ca` | `#4534b3` (primary-pressed) | 🔴 | 色相偏移 +2° |
| 17 | `:root --accent-light` | `#eef2ff` | `#e6e0f5` (tint-lavender) | 🟡 | 仅一种 tint，DESIGN.md 有 7 种 |
| 18 | `:root --danger` | `#ef4444` | `#e03131` | 🟡 | 偏亮 → 略深，ΔE ≈ 2 |
| 19 | `:root --success` | `#22c55e` | `#1aae39` | 🟡 | 偏亮 → 略深，ΔE ≈ 3 |
| 20 | `:root --warning` | `#f59e0b` | `#dd5b00` | 🔴 | 琥珀色 → 橙红色，色相偏移 -30°，完全不同的颜色 |
| 31-43 | `@media (prefers-color-scheme: dark)` | 整套暗色变量 | DESIGN.md 要求 `.dark` 类切换 | 🔴 | 实现方式不同（系统偏好 vs 手动切换），色值也不匹配 |
| 184 | `.backlinks-panel border-top` | `#e0e0e0` (fallback) | `#e5e3df` | 🟡 | fallback 值偏冷 |
| 185 | `.backlinks-panel background` | `#f8f9fa` (fallback) | `#f6f5f4` | 🟡 | fallback 值偏冷 |
| 196 | `.backlinks-header color` | `#666` (fallback) | `#787671` | 🟡 | 可接受但偏冷 |
| 198 | `.backlinks-header:hover bg` | `#eee` (fallback) | `#f0eeec` | 🟡 | 可接受 |
| 215 | `.backlink-item color` | `#333` (fallback) | `#1a1a1a` | 🟢 | 接近 |
| 217 | `.backlink-item:hover bg` | `#eee` (fallback) | `#f0eeec` | 🟡 | 可接受 |
| 218 | `.backlink-page color` | `#4a90d9` (fallback) | `#0075de` | 🟡 | 偏亮蓝 → 标准蓝 |
| 219 | `.backlink-line color` | `#999` (fallback) | `#bbb8b1` | 🟡 | 偏冷 → 暖灰 |
| 224 | `.graph-container border` | `#e0e0e0` (fallback) | `#e5e3df` | 🟡 | 偏冷 |
| 224 | `.graph-container bg` | `#fff` | `#ffffff` | 🟢 | 一致 |
| 227 | `.graph-node circle stroke` | `#fff` | `#ffffff` | 🟢 | 一致 |
| 228 | `.graph-node text fill` | `#333` | `#1a1a1a` | 🟢 | 接近 |
| 229 | `.graph-link stroke` | `#ccc` | `#e5e3df` | 🟡 | 偏冷 |
| 234 | `.dashboard-page h2 color` | `#666` (fallback) | `#787671` | 🟡 | 可接受 |
| 237 | `.dash-card bg` | `#f8f9fa` (fallback) | `#f6f5f4` | 🟡 | 偏冷 |
| 238 | `.dash-card border` | `#e0e0e0` (fallback) | `#e5e3df` | 🟡 | 偏冷 |
| 243 | `.dash-value color` | `#4a90d9` (fallback) | `#5645d4` (primary) | 🔴 | 链接蓝 → 品牌紫，语义错误 |
| 244 | `.dash-label color` | `#666` (fallback) | `#787671` | 🟡 | 可接受 |
| 248 | `.dash-recent-item bg` | `#f8f9fa` (fallback) | `#f6f5f4` | 🟡 | 偏冷 |
| 251 | `.dash-recent-item:hover bg` | `#eee` (fallback) | `#f0eeec` | 🟡 | 可接受 |
| 252 | `.dash-recent-title color` | `#4a90d9` (fallback) | `#0075de` (link) | 🟡 | 偏亮蓝 → 标准蓝 |
| 253 | `.dash-recent-time color` | `#999` (fallback) | `#bbb8b1` | 🟡 | 偏冷 |
| 257 | `.sync-indicator.synced` | `#4caf50` | `#1aae39` | 🟡 | 偏亮 → 略深 |
| 258 | `.sync-indicator.syncing` | `#ff9800` | `#dd5b00` | 🔴 | 琥珀色 → 橙红色，与 `--warning` 同理 |
| 259 | `.sync-indicator.offline` | `#f44336` | `#e03131` | 🟡 | 偏亮 → 略深 |
| 260 | `.sync-indicator.conflict` | `#9c27b0` | `#7b3ff2` (brand-purple) | 🟡 | 偏暗 → 略亮 |
| 281 | `.welcome-logo gradient` | `#a78bfa` (渐变终点) | `#5645d4` (primary) | 🔴 | 渐变效果 → DESIGN.md 要求纯文字 |
| 503 | `.vditor-outline .outline-active` | `#1677ff` | `#5645d4` (primary) | 🔴 | 亮蓝 → 品牌紫，视觉不一致 |

**色彩审计小结：**
- 🔴 严重偏差：6 处（accent 色相偏移、warning 色相完全不同、暗色实现方式、dash-value 语义错误、welcome-logo 渐变、outline-active 颜色）
- 🟡 中等偏差：约 30 处（主要是 fallback 值偏冷灰、个别颜色偏亮）
- 🟢 基本符合：约 5 处

---

### 1.2 app.css 字体定义审计

| 行号 | 选择器 | 当前属性 | DESIGN.md 对应值 | 严重度 | 说明 |
|---|---|---|---|---|---|
| 4-5 | `html, body` | `font-family: var(--font)` → `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif` | `"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif` | 🔴 | 缺少 Inter 字体 |
| 49 | `html, body` | 未定义 font-size | `16px` (body-md) | 🔴 | 浏览器默认 16px 碰巧一致，但未显式声明 |
| 49 | `html, body` | 未定义 line-height | `1.55` (body-md) | 🟡 | 浏览器默认 1.5 接近但未对齐 |
| 66 | `.logo` | `font-size: 18px; font-weight: 700` | 14px / 600 (sidebar header) | 🔴 | 偏大 + 字重过高 |
| 72 | `.search-input` | `font-size: 13px` | 14px (body-md) | 🟡 | 偏小 1px |
| 84 | `.result-path` | `font-size: 13px; font-weight: 500` | 14px / 500 | 🟡 | 偏小 1px |
| 85 | `.result-snippet` | `font-size: 12px` | 13px (caption) | 🟡 | 偏小 1px |
| 95 | `.mount-name` | `font-size: 13px; font-weight: 600` | 14px / 600 | 🟡 | 偏小 1px |
| 101 | `.mount-remove-btn` | `font-size: 14px` | 12px (micro) | 🟡 | 偏大 |
| 108 | `.mount-builtin-badge` | `font-size: 12px` | 12px | 🟢 | 一致 |
| 111 | `.mount-icon` | `font-size: 10px` | 12px (chevron icon) | 🟡 | 偏小 |
| 112 | `.mount-badge` | `font-size: 11px` | 11px (micro-uppercase) | 🟢 | 一致 |
| 115 | `.tree-item` | `font-size: 13px` | 14px (body-sm) | 🔴 | 偏小 1px，影响可读性 |
| 120 | `.tree-item.active` | `font-weight: 500` | 500 (medium) | 🟢 | 一致 |
| 122 | `.mount-builtin-badge` | `font-size: 11px` | 11px | 🟢 | 一致 |
| 124 | `.tree-icon` | `font-size: 14px` | 16px (SVG icon) | 🟡 | emoji → SVG，尺寸需调整 |
| 125 | `.tree-folder` | `font-size: 13px` | 14px | 🟡 | 偏小 |
| 127 | `.tree-loading` | `font-size: 12px` | 12px | 🟢 | 一致 |
| 136 | `.nav-btn` | `font-size: 13px` | 14px / 500 | 🟡 | 偏小 1px |
| 150 | `.breadcrumb` | `font-size: 14px` | 14px (body-sm) | 🟢 | 一致 |
| 157 | `.editor-modes button` | `font-size: 12px` | 14px / 500 (button-md) | 🔴 | 偏小 2px |
| 165 | `.save-btn` | `font-size: 13px` | 14px / 500 | 🟡 | 偏小 1px |
| 195 | `.backlinks-panel` | `font-size: 13px` | 14px (body-sm) | 🟡 | 偏小 |
| 199 | `.backlinks-title` | `font-weight: 500` | 600 (semibold) | 🟡 | 字重偏低 |
| 200 | `.backlinks-toggle` | `font-size: 11px` | 11px | 🟢 | 一致 |
| 214 | `.backlink-item` | `font-size: 13px` | 14px | 🟡 | 偏小 |
| 218 | `.backlink-page` | `font-weight: 500` | 500 | 🟢 | 一致 |
| 219 | `.backlink-line` | `font-size: 12px` | 13px | 🟡 | 偏小 |
| 223 | `.graph-page h1` | `font-size: 20px` | 28px (heading-3) | 🔴 | 偏小 8px |
| 228 | `.graph-node text` | `font-size: 11px` | 12px (micro) | 🟡 | 偏小 |
| 233 | `.dashboard-page h1` | `font-size: 20px` | 28px (heading-3) | 🔴 | 偏小 8px |
| 234 | `.dashboard-page h2` | `font-size: 16px` | 18px (heading-5) | 🟡 | 偏小 2px |
| 243 | `.dash-value` | `font-size: 28px; font-weight: 700` | 28px / 700 | 🟢 | 一致 |
| 244 | `.dash-label` | `font-size: 13px` | 14px (body-sm) | 🟡 | 偏小 |
| 249 | `.dash-recent-item` | `font-size: 13px` | 14px | 🟡 | 偏小 |
| 253 | `.dash-recent-time` | `font-size: 12px` | 13px (caption) | 🟡 | 偏小 |
| 256 | `.sync-indicator` | `font-size: 10px` | 12px (micro) | 🟡 | 偏小 |
| 278 | `.welcome-logo` | `font-size: 40px; font-weight: 800; letter-spacing: -1px` | 48px / 600 / -0.5px | 🔴 | 偏小 + 字重过高 + 字间距过紧 |
| 279 | `.welcome-logo` | `font-weight: 800` | 600 (semibold) | 🔴 | 字重过高 |
| 280 | `.welcome-logo` | `letter-spacing: -1px` | -0.5px (heading-1) | 🟡 | 字间距过紧 |
| 288 | `.welcome-subtitle` | `font-size: 18px; font-weight: 500` | 18px / 400 (subtitle) | 🟡 | 字重偏高 |
| 291 | `.welcome-subtitle` | `font-weight: 500` | 400 (regular) | 🟡 | 字重偏高 |
| 294 | `.welcome-desc` | `font-size: 14px; line-height: 1.7` | 14px / 1.55 | 🟡 | 行高略大 |
| 304 | `.section-label` | `font-size: 13px; font-weight: 600` | 13px / 600 (uppercase) | 🟡 | 缺少 text-transform: uppercase |
| 310 | `.section-title` | `font-size: 15px; font-weight: 600` | 18px / 600 (heading-5) | 🔴 | 偏小 3px |
| 329 | `.open-dir-input` | `font-size: 14px` | 16px (body-md) | 🟡 | 偏小（但输入框 14px 可接受） |
| 337 | `.open-dir-name-input` | `font-size: 14px` | 16px | 🟡 | 同上 |
| 342 | `.open-dir-hint` | `font-size: 12px` | 13px (caption) | 🟡 | 偏小 |
| 349 | `.browse-btn` | `font-size: 14px` | 14px / 500 | 🟢 | 一致 |
| 357 | `.primary-btn` | `font-size: 14px` | 14px / 500 | 🟢 | 一致 |
| 376 | `.mount-card-icon` | `font-size: 24px` (emoji) | 不适用（→ SVG） | 🔴 | emoji → SVG 图标 |
| 379 | `.mount-card-name` | `font-size: 14px; font-weight: 600` | 14px / 600 | 🟢 | 一致 |
| 381 | `.mount-card-path` | `font-size: 12px` | 12px (micro) | 🟢 | 一致 |
| 385 | `.mount-card-toggle` | `font-size: 16px` (emoji ▶/▼) | 不适用（→ SVG chevron） | 🔴 | emoji → SVG |
| 395 | `.public-badge` | `font-size: 11px; font-weight: 500` | 13px / 600 (caption-bold) | 🟡 | 偏小 + 字重偏低 |
| 406 | `.recent-name` | `font-size: 14px` | 14px / 500 | 🟢 | 一致 |
| 407 | `.recent-time` | `font-size: 12px` | 13px (caption) | 🟡 | 偏小 |
| 424 | `.modal h3` | `font-size: 18px` | 18px (heading-5) | 🟢 | 一致 |
| 431 | `.modal-close` | `font-size: 18px` (emoji ✕) | 不适用（→ SVG ×） | 🔴 | emoji → SVG |
| 438 | `.modal-input` | `font-size: 14px` | 16px (body-md) | 🟡 | 偏小 |
| 446 | `.modal-actions button` | `font-size: 14px` | 14px / 500 | 🟢 | 一致 |
| 457 | `.toast` | `font-size: 14px` | 14px | 🟢 | 一致 |

**字体审计小结：**
- 🔴 严重偏差：7 处（缺 Inter、logo 过大、welcome-logo 渐变+字重、welcome-desc 行高、section-title 偏小、emoji 图标→SVG）
- 🟡 中等偏差：约 40 处（主要是 13px → 14px、12px → 13px、个别字重偏差）
- 🟢 基本符合：约 10 处

---

### 1.3 app.css 间距硬编码审计

搜索范围：所有 `padding` / `margin` 声明

| 行号 | 选择器 | 当前值 | DESIGN.md 对应值 | 严重度 | 说明 |
|---|---|---|---|---|---|
| 2 | `*` | `margin: 0; padding: 0` | CSS Reset | 🟢 | 一致 |
| 63 | `.sidebar-header` | `padding: 12px 16px` | 12px 16px | 🟢 | 一致 |
| 63 | `.sidebar-header` | `border-bottom: 1px solid var(--border)` | 应移除 | 🔴 | DESIGN.md 侧边栏 header 无底边框 |
| 69 | `.search-box` | `padding: 8px 12px` | 8px 12px | 🟢 | 一致 |
| 71 | `.search-input` | `padding: 8px 12px` | 12px 16px | 🟡 | 偏小 + 缺少左图标空间 |
| 78 | `.search-results` | `top: 44px` | 应基于 search-box height + gap | 🟡 | 硬编码像素值 |
| 81 | `.search-result-item` | `padding: 8px 12px` | 8px 12px | 🟢 | 一致 |
| 88 | `.file-tree` | `padding: 8px 0` | 8px 0 | 🟢 | 一致 |
| 89 | `.mount-group` | `margin-bottom: 4px` | 4px | 🟢 | 一致 |
| 92 | `.mount-name-row` | `padding: 0 8px 0 16px` | 0 8px 0 16px | 🟢 | 一致 |
| 95 | `.mount-name` | `padding: 6px 0` | 8px 0 | 🟡 | 偏小 2px |
| 102 | `.mount-remove-btn` | `padding: 4px 6px` | 4px 8px | 🟡 | 略偏小 |
| 108 | `.mount-builtin-badge` | `padding: 4px` | 2px 8px (badge-sm) | 🟡 | 不统一 |
| 113 | `.mount-tree` | `padding-left: 8px` | 应移除（缩进由 tree-sub 处理） | 🟡 | 多余缩进 |
| 115 | `.tree-item` | `padding: 4px 16px 4px 28px` | 4px 16px 4px 20px | 🔴 | 左 padding 28px 不统一，应为 20px（16px 缩进 + 4px 余量） |
| 117 | `.tree-item` | `margin: 1px 8px 1px 0` | 1px 8px 1px 0 | 🟢 | 一致 |
| 126 | `.tree-sub` | `padding-left: 12px` | 16px | 🔴 | 缩进不统一，DESIGN.md 要求 16px/级 |
| 127 | `.tree-loading` | `padding: 8px 16px` | 8px 16px | 🟢 | 一致 |
| 131 | `.sidebar-footer` | `padding: 12px` | 12px | 🟢 | 一致 |
| 135 | `.nav-btn` | `padding: 8px` | 8px 12px | 🟡 | 缺少水平 padding |
| 147 | `.topbar` | `padding: 0 16px; gap: 12px` | 0 20px; gap: 16px | 🟡 | 偏小 |
| 154 | `.editor-modes` | `gap: 2px; padding: 2px` | 应移除（改为 segmented tab） | 🔴 | 整个模式切换组件需重写 |
| 156 | `.editor-modes button` | `padding: 6px 12px; border-radius: 6px` | 12px 16px; border-radius: 0 | 🔴 | 按钮组 → segmented tab |
| 164 | `.save-btn` | `padding: 6px 16px` | 8px 16px; border-radius: 8px | 🟡 | 偏小 |
| 171 | `.user-area` | `margin-left: 4px` | 8px | 🟡 | 偏小 |
| 192 | `.backlinks-header` | `padding: 6px 12px` | 8px 16px | 🟡 | 偏小 |
| 206 | `.backlinks-content` | `padding: 4px 0` | 4px 0 | 🟢 | 一致 |
| 212 | `.backlink-item` | `padding: 4px 12px` | 4px 16px | 🟡 | 偏小 |
| 222 | `.graph-page` | `padding: 20px` | 20px | 🟢 | 一致 |
| 223 | `.graph-page h1` | `margin-bottom: 12px` | 12px | 🟢 | 一致 |
| 232 | `.dashboard-page` | `padding: 20px` | 20px | 🟢 | 一致 |
| 233 | `.dashboard-page h1` | `margin-bottom: 16px` | 16px | 🟢 | 一致 |
| 234 | `.dashboard-page h2` | `margin: 20px 0 10px` | 24px 0 12px | 🟡 | 偏小 |
| 240 | `.dash-card` | `padding: 16px` | 16px | 🟢 | 一致 |
| 244 | `.dash-label` | `margin-top: 4px` | 4px | 🟢 | 一致 |
| 248 | `.dash-recent-item` | `padding: 8px 12px` | 8px 12px | 🟢 | 一致 |
| 256 | `.sync-indicator` | `margin-left: 8px` | 8px | 🟢 | 一致 |
| 265 | `.welcome-page` | `padding: 48px 48px 64px` | 64px | 🔴 | 不一致，DESIGN.md 要求统一 64px |
| 275 | `.welcome-hero` | `padding: 40px 0 48px` | 40px 0 48px | 🟢 | 一致 |
| 285 | `.welcome-logo` | `margin-bottom: 8px` | 8px | 🟢 | 一致 |
| 290 | `.welcome-subtitle` | `margin-bottom: 16px` | 16px | 🟢 | 一致 |
| 298 | `.welcome-desc` | `margin: 0 auto` | 0 auto | 🟢 | 一致 |
| 307 | `.section-label` | `margin-bottom: 8px` | 8px | 🟢 | 一致 |
| 313 | `.section-title` | `margin-bottom: 14px` | 12px | 🟡 | 偏大 2px |
| 321 | `.open-dir-section` | `margin-bottom: 40px` | 48px (section-sm) | 🟡 | 偏小 8px |
| 328 | `.open-dir-input` | `padding: 10px 14px` | 12px 16px | 🟡 | 不统一 |
| 336 | `.open-dir-name-input` | `padding: 10px 14px` | 12px 16px | 🟡 | 同上 |
| 344 | `.open-dir-hint` | `margin-top: 8px` | 8px | 🟢 | 一致 |
| 349 | `.browse-btn` | `padding: 10px 14px` | 12px 16px | 🟡 | 不统一 |
| 357 | `.primary-btn` | `padding: 10px 20px` | 12px 20px | 🟡 | 水平 padding 偏小 |
| 364 | `.mounted-dirs` | `margin-bottom: 40px` | 48px | 🟡 | 偏小 |
| 367 | `.mount-card` | `padding: 14px 16px; gap: 12px` | 12px 16px; gap: 16px | 🟡 | 垂直 padding 偏大，gap 偏小 |
| 386 | `.mount-card-toggle` | `padding: 4px 8px` | 8px | 🟡 | 偏小 |
| 394 | `.public-badge` | `padding: 1px 8px` | 4px 10px (badge-purple) | 🟡 | 偏小 |
| 399 | `.recent-files` | `margin-bottom: 40px` | 48px | 🟡 | 偏小 |
| 402 | `.recent-item` | `padding: 10px 16px` | 8px 16px | 🟡 | 垂直 padding 偏大 |
| 421 | `.modal` | `padding: 28px 32px` | 32px 40px | 🟡 | 偏小 |
| 424 | `.modal h3` | `margin-bottom: 16px` | 16px | 🟢 | 一致 |
| 427 | `.modal-header-row` | `margin-bottom: 16px` | 16px | 🟢 | 一致 |
| 432 | `.modal-close` | `padding: 4px` | 4px | 🟢 | 一致 |
| 437 | `.modal-input` | `padding: 10px 14px; margin-bottom: 20px` | 12px 16px; margin-bottom: 20px | 🟡 | padding 不统一 |
| 445 | `.modal-actions button` | `padding: 8px 16px` | 8px 16px | 🟢 | 一致 |
| 455 | `.toast` | `padding: 12px 20px; bottom: 24px; right: 24px` | 12px 20px; 24px 24px | 🟢 | 一致 |
| 463 | `.outline-toggle-btn` | `padding: 6px` | 8px | 🟡 | 偏小 |
| 472 | `.mount-path-hint` | `padding: 2px 8px 4px` | 4px 8px 4px | 🟡 | 不统一 |
| 479 | `.vditor-content` | `padding: 0 !important` | 0 | 🟢 | 一致 |
| 489 | `@media max-768 .welcome-page` | `padding: 24px 20px` | 20px | 🟢 | 一致 |
| 494 | `@media max-768 .modal` | `padding: 24px 20px` | 20px | 🟢 | 一致 |

**间距审计小结：**
- 🔴 严重偏差：4 处（sidebar-header border-bottom、模式切换组件整体重写、tree-item 左 padding 28px、tree-sub padding-left 12px）
- 🟡 中等偏差：约 25 处（主要是 padding 10px 14px → 12px 16px、section 间距 40px → 48px）
- 🟢 基本符合：约 25 处

---

### 1.4 app.css 圆角硬编码审计

| 行号 | 选择器 | 当前值 | DESIGN.md 对应值 | 严重度 | 说明 |
|---|---|---|---|---|---|
| 72 | `.search-input` | `var(--radius)` → 8px | `--r-md` → 8px | 🟢 | 一致 |
| 78 | `.search-results` | `var(--radius)` → 8px | `--r-md` → 8px | 🟢 | 一致 |
| 97 | `.mount-name` | `var(--radius-sm)` → 4px | `--r-sm` → 6px | 🟡 | 偏小 2px |
| 102 | `.mount-remove-btn` | `var(--radius-sm)` → 4px | `--r-sm` → 6px | 🟡 | 偏小 2px |
| 116 | `.tree-item` | `var(--radius-sm)` → 4px | `--r-sm` → 6px | 🟡 | 偏小 2px |
| 136 | `.nav-btn` | `var(--radius)` → 8px | `--r-md` → 8px | 🟢 | 一致 |
| 154 | `.editor-modes` | `var(--radius)` → 8px | 应移除（segmented tab 无圆角） | 🔴 | 组件重写 |
| 156 | `.editor-modes button` | `6px` | 0（无圆角） | 🔴 | 组件重写 |
| 165 | `.save-btn` | `var(--radius)` → 8px | `--r-md` → 8px | 🟢 | 一致 |
| 224 | `.graph-container` | `8px` | `--r-md` → 8px | 🟢 | 一致 |
| 239 | `.dash-card` | `8px` | `--r-md` → 8px | 🟢 | 一致 |
| 249 | `.dash-recent-item` | `6px` | `--r-sm` → 6px | 🟢 | 一致 |
| 329 | `.open-dir-input` | `var(--radius)` → 8px | `--r-md` → 8px | 🟢 | 一致 |
| 337 | `.open-dir-name-input` | `var(--radius)` → 8px | `--r-md` → 8px | 🟢 | 一致 |
| 350 | `.browse-btn` | `var(--radius)` → 8px | `--r-md` → 8px | 🟢 | 一致 |
| 358 | `.primary-btn` | `var(--radius)` → 8px | `--r-md` → 8px | 🟢 | 一致 |
| 368 | `.mount-card` | `var(--radius)` → 8px | `--r-lg` → 12px | 🔴 | 偏小 4px |
| 386 | `.mount-card-toggle` | `var(--radius-sm)` → 4px | `--r-sm` → 6px | 🟡 | 偏小 2px |
| 395 | `.public-badge` | `100px` | `--r-full` → 9999px | 🟡 | 值不同但效果类似 |
| 402 | `.recent-item` | `var(--radius)` → 8px | `--r-sm` → 6px | 🟡 | 偏大 2px |
| 421 | `.modal` | `var(--radius-lg)` → 16px | `--r-xl` → 16px | 🟢 | 一致 |
| 432 | `.modal-close` | `var(--radius-sm)` → 4px | `--r-sm` → 6px | 🟡 | 偏小 2px |
| 438 | `.modal-input` | `var(--radius)` → 8px | `--r-md` → 8px | 🟢 | 一致 |
| 445 | `.modal-actions button` | `var(--radius)` → 8px | `--r-md` → 8px | 🟢 | 一致 |
| 456 | `.toast` | `var(--radius)` → 8px | `--r-md` → 8px | 🟢 | 一致 |
| 463 | `.outline-toggle-btn` | `var(--radius-sm)` → 4px | `--r-sm` → 6px | 🟡 | 偏小 2px |
| 484 | `.scrollbar-thumb` | `3px` | 3px | 🟢 | 一致 |

**圆角审计小结：**
- 🔴 严重偏差：2 处（editor-modes 组件重写、mount-card 8px → 12px）
- 🟡 中等偏差：9 处（主要是 `--radius-sm` 4px → 6px、public-badge 100px → 9999px）
- 🟢 基本符合：14 处

---

### 1.5 app.css 阴影硬编码审计

| 行号 | 选择器 | 当前值 | DESIGN.md 对应值 | 严重度 | 说明 |
|---|---|---|---|---|---|
| 5-6 | `:root --shadow` | `0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06)` | `rgba(15,15,15,0.06) 0 1px 2px` | 🟡 | 结构不同，当前双层阴影 |
| 5-6 | `:root --shadow-lg` | `0 10px 40px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06)` | `rgba(15,15,15,0.12) 0 8px 24px` | 🔴 | 过强（10px 40px vs 8px 24px） |
| 79 | `.search-results` | `var(--shadow)` | `--shadow-md` | 🟡 | 应使用 md 级别 |
| 159 | `.editor-modes button.active` | `0 1px 2px rgba(0,0,0,0.1)` | 应移除 | 🔴 | segmented tab 无阴影 |
| 374 | `.mount-card:hover` | `0 2px 8px rgba(79,70,229,0.08)` | `--shadow-sm` + border | 🔴 | 紫色阴影 → 中性阴影 |
| 422 | `.modal` | `var(--shadow-lg)` | `--shadow-lg` (新值) | 🟡 | 变量名相同但值不同 |
| 457 | `.toast` | `var(--shadow)` | `--shadow-md` | 🟡 | 应使用 md 级别 |

**阴影审计小结：**
- 🔴 严重偏差：3 处（--shadow-lg 过强、active mode button 有阴影、mount-card:hover 紫色阴影）
- 🟡 中等偏差：4 处（shadow 值差异、search-results/toast 应使用 md）
- 🟢 基本符合：0 处

---

### 1.6 组件级审计

| 组件 | 当前状态 | DESIGN.md 目标 | 严重度 | 主要差距 |
|---|---|---|---|---|
| **侧边栏** | 280px，emoji 图标，search 无图标，border-bottom header | 240px，SVG 图标，search 带搜索图标，无 header 分隔线 | 🔴 | 宽度 -40px、图标全量替换、搜索框重写、header border 移除 |
| **顶部栏** | 48px，按钮组模式切换（有阴影），实心保存按钮 | 52px，segmented tab 模式切换（下划线），ghost 保存按钮 + dirty 状态 | 🔴 | 高度 +4px、模式切换组件重写、保存按钮样式 + JS 逻辑 |
| **文件树** | emoji 📁📝📄▶▼，12-28px 混合缩进，无展开动画 | SVG 16x16，统一 16px/级，150ms 展开动画，hover 显示 ⋯ 操作图标 | 🔴 | emoji → SVG、缩进统一、动画新增、交互新增 |
| **欢迎页** | 渐变 logo（40px/800），独立 section 样式，无 pastel 卡片 | 纯文字 hero（48px/600），pastel tint 3 列卡片网格，section 48px 间距 | 🔴 | logo 渐变移除、字号调整、新增快速操作卡片 HTML、section 间距统一 |
| **模态框** | `rgba(0,0,0,0.4)` 遮罩，16px 圆角，无动画 | `rgba(0,0,0,0.3)` + blur，16px 圆角，200ms 进入 + 150ms 退出动画 | 🟡 | 遮罩色值 + blur、动画新增 |
| **Toast** | 反色（`var(--text)` 背景），2.5s 消失，无动画 | charcoal 背景 `#37352f`，白色文字，200ms 进入 + 200ms 退出动画 | 🔴 | 颜色完全不同（反色 vs charcoal）、动画新增 |
| **Vditor** | 无 CSS 变量覆盖，默认 Material 风格 | 完整的变量覆盖 + 硬编码覆盖（代码块/引用块/表格/tooltip/链接/行内代码） | 🔴 | 全面缺失，需要 ~50 行 CSS 变量 + ~30 行硬编码覆盖 |
| **知识图谱** | 硬编码颜色 `#4a90d9`/`#ccc`/`#333`，无暗色适配 | 使用 CSS 变量，暗色模式适配 | 🟡 | 颜色硬编码 |
| **数据看板** | 硬编码颜色 `#4a90d9`/`#666`/`#999`/`#f8f9fa`，无暗色适配 | 使用 CSS 变量，暗色模式适配 | 🟡 | 颜色硬编码 + dash-value 语义错误（用 link 色而非 primary 色） |
| **反向链接** | 硬编码颜色 `#333`/`#666`/`#999`/`#eee`，无暗色适配 | 使用 CSS 变量，暗色模式适配 | 🟡 | 颜色硬编码 |

---

### 1.7 app.js 硬编码值审计

| 行号 | 位置 | 硬编码值 | 严重度 | 说明 |
|---|---|---|---|---|
| 547 | `openFile()` 高亮 | `style.backgroundColor = '#fff3b0'` | 🟡 | 硬编码高亮色，应使用 CSS 类 |
| 680 | `showGraph()` 错误 | `color:#999` (inline style) | 🟡 | 应使用 `var(--c-muted)` |
| 688 | `showGraph()` 空态 | `color:#999` (inline style) | 🟡 | 同上 |
| 749 | `renderGraph()` 节点 | `fill: d => ... '#4a90d9' : '#ccc'` | 🟡 | 应使用 CSS 变量或 d3 比例尺 |
| 798 | `showDashboard()` 空态 | `color:#999` (inline style) | 🟡 | 同上 |
| 812 | `showDashboard()` 孤立页 | `color:#999` (inline style) | 🟡 | 同上 |
| 全文 | `style.display` / `style.visibility` | 无色彩 | 🟢 | 纯布局操作，无需 CSS 变量 |

**app.js 审计小结：**
- 🔴 严重偏差：0 处
- 🟡 中等偏差：6 处（inline style 颜色硬编码）
- 🟢 基本符合：全部布局操作

---

### 1.8 editor.js 硬编码值审计

| 行号 | 位置 | 硬编码值 | 严重度 | 说明 |
|---|---|---|---|---|
| 224 | hint 模板 | `color:var(--text-primary)`, `color:var(--text-secondary);font-size:0.85em` | 🟡 | 使用旧变量名（`--text-primary`, `--text-secondary`），应更新为 `--c-ink`, `--c-steel` |

**editor.js 审计小结：**
- 🔴 严重偏差：0 处
- 🟡 中等偏差：1 处（旧变量名引用）

---

### 1.9 index.html 结构审计

| 区域 | 当前结构 | DESIGN.md 要求 | 严重度 | 说明 |
|---|---|---|---|---|
| 侧边栏 header | `<h2 class="logo">nas-md</h2>` | 纯文字 workspace 名称 + 可选图标 | 🟡 | 移除 h2 语义 + 渐变样式 |
| 搜索框 | `<input>` 无搜索图标 | 搜索图标 + pill 样式 | 🔴 | 缺少搜索图标 SVG |
| 文件树 | emoji 📁📝📄 + ▶/▼ | SVG 16x16 图标 | 🔴 | 需要全部替换为 SVG |
| 侧边栏 footer | 3 个 emoji 按钮 🏠🔗📊 | 纯文字按钮 | 🟡 | 移除 emoji |
| 顶部栏 | `<header class="topbar">` 48px | 52px 高度 | 🟡 | 高度调整 |
| 模式切换 | `<div class="editor-modes">` 按钮组 | Segmented tab（下划线式） | 🔴 | 需要重写 HTML + CSS |
| 保存按钮 | `<button class="save-btn">` 实心 | Ghost 样式 + dirty 状态 | 🔴 | 需要重写样式 + JS 逻辑 |
| 欢迎页 hero | `<h1 class="welcome-logo">` 渐变文字 | 纯文字 48px | 🔴 | 移除渐变，调整字号 |
| 欢迎页操作 | "打开目录" + "已挂载" + "最近修改" | 新增 "快速操作" 3 列卡片网格 | 🔴 | 需要新增 HTML 结构 |
| 模态框 | 无动画 | 200ms 进入 + 150ms 退出动画 | 🟡 | 添加 CSS transition |
| Toast | 无动画 | 200ms 进入 + 200ms 退出 | 🟡 | 添加 CSS transition |
| 暗色切换 | 无按钮 | 需要暗色模式切换入口 | 🟡 | 可放在设置页或侧边栏 footer |
| 移动端菜单 | 无汉堡按钮 | 767px 以下需要菜单按钮 | 🟡 | 需新增 HTML |

---

### 1.10 响应式审计

| 行号 | @media 查询 | 当前行为 | DESIGN.md 要求 | 严重度 |
|---|---|---|---|---|
| 31 | `@media (prefers-color-scheme: dark)` | 自动暗色模式 | 手动切换 + `.dark` 类 | 🔴 | 实现方式完全不同 |
| 488 | `@media (max-width: 768px)` | 侧边栏 absolute、welcome padding 缩小、input column、modal 90vw | 767px 断点：侧边栏 overlay 模式、触摸目标 ≥ 40px | 🟡 | 断点值接近但行为不完整 |
| — | 无 1023px 断点 | — | 1023px：侧边栏收窄到 200px、卡片 2 列 | 🔴 | 缺少平板断点 |
| — | 无触摸目标规则 | — | 移动端按钮 ≥ 44px、文件树节点 ≥ 40px | 🟡 | 当前文件树节点 28px 偏小 |

---

### 1.11 审计总结

| 维度 | 🔴 严重偏差 | 🟡 中等偏差 | 🟢 基本符合 | 总计 |
|---|---|---|---|---|
| 色彩（app.css） | 6 | ~30 | ~5 | ~41 |
| 字体（app.css） | 7 | ~40 | ~10 | ~57 |
| 间距（app.css） | 4 | ~25 | ~25 | ~54 |
| 圆角（app.css） | 2 | 9 | 14 | ~25 |
| 阴影（app.css） | 3 | 4 | 0 | ~7 |
| 硬编码（app.js） | 0 | 6 | 全部布局操作 | ~6 |
| 硬编码（editor.js） | 0 | 1 | 其余 | ~1 |
| HTML 结构 | 5 | 6 | — | ~11 |
| 响应式 | 2 | 2 | — | ~4 |
| **合计** | **~29** | **~123** | **~54** | **~206** |

**关键发现：**
1. 最大的问题集中在色彩体系（accent 色相偏移、暖色/冷色差异、warning 色相完全不同）和字体体系（缺 Inter、13px 全系统一偏小 1px）
2. 间距虽然单个偏差小（2px 级别），但累计 ~25 处不统一，整体视觉不精致
3. HTML 结构需要 5 处重大调整（搜索图标 SVG、文件树 SVG 图标、segmented tab 重写、快速操作卡片新增、移动端菜单按钮）
4. app.js 中 6 处 inline style 颜色硬编码（`#999`/`#fff3b0`/`#4a90d9`/`#ccc`）需要改为 CSS 类或 CSS 变量
5. 暗色模式的实现方式需要从 `prefers-color-scheme` 改为 `.dark` 类切换
6. 总计审计 ~206 个属性点：🔴 严重偏差 ~29 处（14%）、🟡 中等偏差 ~123 处（60%）、🟢 基本符合 ~54 处（26%）

---

## 2. 色彩系统重构

### 2.1 完整 CSS 变量定义

在 `app.css` 的 `:root` 中替换全部变量：

```css
:root {
  /* === DESIGN TOKENS: Colors === */

  /* Primary */
  --c-primary: #5645d4;
  --c-primary-pressed: #4534b3;
  --c-primary-deep: #3a2a99;
  --c-on-primary: #ffffff;

  /* Brand */
  --c-brand-navy: #0a1530;
  --c-brand-navy-deep: #070f24;
  --c-brand-navy-mid: #1a2a52;
  --c-brand-orange: #dd5b00;
  --c-brand-orange-deep: #793400;
  --c-brand-pink: #ff64c8;
  --c-brand-pink-deep: #a02e6d;
  --c-brand-purple: #7b3ff2;
  --c-brand-purple-300: #d6b6f6;
  --c-brand-purple-800: #391c57;
  --c-brand-teal: #2a9d99;
  --c-brand-green: #1aae39;
  --c-brand-yellow: #f5d75e;
  --c-brand-brown: #523410;

  /* Canvas / Surface */
  --c-canvas: #ffffff;
  --c-surface: #f6f5f4;
  --c-surface-soft: #fafaf9;

  /* Hairline borders */
  --c-hairline: #e5e3df;
  --c-hairline-soft: #ede9e4;
  --c-hairline-strong: #c8c4be;

  /* Ink / Text */
  --c-ink-deep: #000000;
  --c-ink: #1a1a1a;
  --c-charcoal: #37352f;
  --c-slate: #5d5b54;
  --c-steel: #787671;
  --c-stone: #a4a097;
  --c-muted: #bbb8b1;

  /* Link */
  --c-link: #0075de;
  --c-link-pressed: #005bab;

  /* On-dark */
  --c-on-dark: #ffffff;
  --c-on-dark-muted: #a4a097;

  /* Semantic */
  --c-success: #1aae39;
  --c-warning: #dd5b00;
  --c-danger: #e03131;

  /* Pastel Tints (for welcome page feature cards) */
  --c-tint-peach: #ffe8d4;
  --c-tint-rose: #fde0ec;
  --c-tint-mint: #d9f3e1;
  --c-tint-lavender: #e6e0f5;
  --c-tint-sky: #dcecfa;
  --c-tint-yellow: #fef7d6;
  --c-tint-yellow-bold: #f9e79f;
  --c-tint-cream: #f8f5e8;
  --c-tint-gray: #f0eeec;

  /* === ALIASES (mapped to tokens above) === */
  --c-bg: var(--c-canvas);
  --c-bg-sidebar: var(--c-surface);
  --c-bg-hover: var(--c-tint-gray);
  --c-bg-active: var(--c-hairline);
  --c-border: var(--c-hairline);
  --c-border-strong: var(--c-hairline-strong);
  --c-text: var(--c-ink);
  --c-text-secondary: var(--c-steel);
  --c-text-muted: var(--c-muted);
  --c-primary-hover: var(--c-primary-pressed);
}
```

### 2.2 变量变更影响范围

| 旧变量 | 新变量 | 影响的选择器（行号） |
|---|---|---|
| `--accent` | `--c-primary` | `.save-btn`, `.primary-btn`, `.browse-btn:hover`, `.mount-card:hover`, `.public-badge`, `.welcome-logo` 渐变, `.outline-active`, `.editor-modes button.active` |
| `--accent-hover` | `--c-primary-hover` | `.save-btn:hover`, `.primary-btn:hover`, `.browse-btn:hover` |
| `--bg-sidebar` | `--c-bg-sidebar` | `.sidebar`, `.editor-modes` |
| `--bg-hover` | `--c-bg-hover` | `.tree-item:hover`, `.nav-btn:hover`, `.search-result-item:hover`, `.recent-item:hover`, `.modal-close:hover`, `.modal-actions button:hover` |
| `--bg-active` | `--c-bg-active` | `.tree-item.active`, `.mount-card-toggle:hover` |
| `--border` | `--c-border` | `.sidebar`, `.search-input`, `.nav-btn`, `.topbar`, `.sidebar-footer`, `.tree-sub`, `.modal-input`, `.open-dir-input`, `.open-dir-name-input`, `.mount-card`, `.search-results`, `.vditor-toolbar`, `.modal-actions button`, `.modal` |
| `--text` | `--c-text` | `html, body`, `.nav-btn`, `.modal-close:hover`, `.modal-actions button`, `.modal-input` |
| `--text-secondary` | `--c-text-secondary` | `.breadcrumb`, `.editor-modes button`, `.welcome-subtitle`, `.section-label`, `.mount-name` |
| `--text-muted` | `--c-text-muted` | `.welcome-desc`, `.open-dir-hint`, `.recent-time`, `.result-snippet`, `.mount-card-path`, `.mount-remove-btn`, `.modal-close`, `.tree-loading` |
| `--danger` | `--c-danger` | `.mount-remove-btn:hover` |
| `--success` | `--c-success` | `.sync-indicator.synced` |
| `--warning` | `--c-warning` | `.sync-indicator.syncing` |
| `--radius` | `--r-md` | `.search-input`, `.nav-btn`, `.tree-item`, `.save-btn`, `.primary-btn`, `.browse-btn`, `.modal-input`, `.modal-actions button`, `.mount-card`, `.recent-item`, `.search-results`, `.search-result-item` |
| `--radius-sm` | `--r-sm` | `.mount-remove-btn`, `.public-badge`, `.mount-badge`, `.outline-toggle-btn`, `.modal-close`, `.mount-card-toggle` |
| `--radius-lg` | `--r-lg` | `.modal` |
| `--shadow` | `--shadow-sm` | `.search-results`, `.toast` |
| `--shadow-lg` | `--shadow-md` | `.modal` |

---

## 3. 排版系统重构

### 3.1 字体引入

在 `index.html` 的 `<head>` 中添加：

```html
<link rel="stylesheet" href="lib/fonts/inter.css">
```

`web/lib/fonts/inter.css` 内容：

```css
/* Inter — 从 Google Fonts 下载 woff2 到本地 */
@font-face {
  font-family: 'Inter';
  font-style: normal;
  font-weight: 100 900;
  font-display: swap;
  src: url('inter-variable.woff2') format('woff2');
}
```

字体文件获取：从 [Google Fonts](https://fonts.google.com/specimen/Inter) 下载 Inter 可变字体 woff2（约 150KB），放置到 `web/lib/fonts/inter-variable.woff2`。

### 3.2 字体栈

```css
:root {
  --font-sans: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-mono: "SF Mono", "Fira Code", "Cascadia Code", Consolas, monospace;
}
```

### 3.3 排版变量

```css
:root {
  /* Font sizes */
  --f-hero: 48px;
  --f-display-lg: 56px;
  --f-h1: 48px;
  --f-h2: 36px;
  --f-h3: 28px;
  --f-h4: 22px;
  --f-h5: 18px;
  --f-subtitle: 18px;
  --f-body: 16px;
  --f-body-sm: 14px;
  --f-caption: 13px;
  --f-micro: 12px;
  --f-button: 14px;

  /* Line heights */
  --lh-hero: 1.05;
  --lh-display: 1.10;
  --lh-h1: 1.15;
  --lh-h2: 1.20;
  --lh-h3: 1.25;
  --lh-h4: 1.30;
  --lh-h5: 1.40;
  --lh-body: 1.55;
  --lh-body-sm: 1.50;
  --lh-caption: 1.40;
  --lh-button: 1.30;

  /* Font weights */
  --fw-regular: 400;
  --fw-medium: 500;
  --fw-semibold: 600;
  --fw-bold: 700;

  /* Letter spacing */
  --ls-hero: -2px;
  --ls-display: -1px;
  --ls-h1: -0.5px;
  --ls-h2: -0.5px;
  --ls-uppercase: 1px;
}
```

### 3.4 全局排版规则

```css
html, body {
  font-family: var(--font-sans);
  font-size: var(--f-body);
  line-height: var(--lh-body);
  font-weight: var(--fw-regular);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* Headings reset */
h1, h2, h3, h4, h5, h6 {
  font-weight: var(--fw-semibold);
  color: var(--c-ink);
  margin: 0;
}

/* Code */
code, pre, .font-mono {
  font-family: var(--font-mono);
}
```

---

## 4. 间距与布局系统

### 4.1 间距变量

```css
:root {
  /* 4px base grid */
  --s-xxs: 4px;
  --s-xs: 8px;
  --s-sm: 12px;
  --s-md: 16px;
  --s-lg: 20px;
  --s-xl: 24px;
  --s-xxl: 32px;
  --s-xxxl: 40px;
  --s-section-sm: 48px;
  --s-section: 64px;
  --s-section-lg: 96px;
  --s-hero: 120px;
}
```

### 4.2 布局尺寸变量

```css
:root {
  --sidebar-w: 240px;
  --topbar-h: 52px;
  --tree-indent: 16px;
  --tree-node-h: 28px;
  --search-h: 36px;
  --input-h: 40px;
  --button-h: 36px;
}
```

### 4.3 间距覆盖表

| 选择器 | 当前 padding/margin | 目标值 | 说明 |
|---|---|---|---|
| `.sidebar-header` | `12px 16px` | `12px 16px` | 保留（高度由内容撑开） |
| `.search-box` | `8px 12px` | `var(--s-xs) var(--s-sm)` → `8px 12px` | 保留 |
| `.sidebar-footer` | `12px` | `var(--s-sm)` → `12px` | 保留 |
| `.topbar` | `0 16px` | `0 var(--s-lg)` → `0 20px` | 增加 |
| `.welcome-page` | `48px 48px 64px` | `var(--s-section)` → `64px` | 统一 |
| `.welcome-hero` | `40px 0 48px` | `var(--s-xxxl) 0 var(--s-section-sm)` → `40px 0 48px` | 微调 |
| `.section-label` | `margin-bottom: 8px` | `margin-bottom: var(--s-xs)` → `8px` | 保留 |
| `.open-dir-section` | `margin-bottom: 40px` | `margin-bottom: var(--s-section-sm)` → `48px` | 增加 |
| `.mounted-dirs` | `margin-bottom: 40px` | `margin-bottom: var(--s-section-sm)` → `48px` | 增加 |
| `.recent-files` | `margin-bottom: 40px` | `margin-bottom: var(--s-section-sm)` → `48px` | 增加 |
| `.modal` | `28px 32px` | `var(--s-xxl) var(--s-xxxl)` → `32px 40px` | 增加 |
| `.modal-input` | `margin-bottom: 20px` | `margin-bottom: var(--s-lg)` → `20px` | 保留 |

---

## 5. 圆角与阴影体系

### 5.1 圆角变量

```css
:root {
  --r-xs: 4px;
  --r-sm: 6px;
  --r-md: 8px;
  --r-lg: 12px;
  --r-xl: 16px;
  --r-xxl: 20px;
  --r-xxxl: 24px;
  --r-full: 9999px;
}
```

### 5.2 圆角覆盖表

| 选择器 | 当前值 | 目标值 | 说明 |
|---|---|---|---|
| `.search-input` | `var(--radius)` (8px) | `var(--r-md)` (8px) | 一致 |
| `.nav-btn` | `var(--radius)` (8px) | `var(--r-md)` (8px) | 一致 |
| `.tree-item` | `var(--radius-sm)` (4px) | `var(--r-sm)` (6px) | **增大** |
| `.mount-card` | `var(--radius)` (8px) | `var(--r-lg)` (12px) | **增大** |
| `.recent-item` | `var(--radius)` (8px) | `var(--r-sm)` (6px) | **减小** |
| `.search-results` | `var(--radius)` (8px) | `var(--r-md)` (8px) | 一致 |
| `.modal` | `var(--radius-lg)` (16px) | `var(--r-xl)` (16px) | 一致 |
| `.toast` | `var(--radius)` (8px) | `var(--r-md)` (8px) | 一致 |
| `.public-badge` | `100px` | `var(--r-full)` (9999px) | **统一** |
| `.mount-badge` | 未定义 | `var(--r-full)` (9999px) | **新增** |
| `.outline-toggle-btn` | `var(--radius-sm)` (4px) | `var(--r-sm)` (6px) | **增大** |

### 5.3 阴影变量

```css
:root {
  --shadow-sm: rgba(15, 15, 15, 0.06) 0px 1px 2px;
  --shadow-md: rgba(15, 15, 15, 0.08) 0px 4px 12px;
  --shadow-lg: rgba(15, 15, 15, 0.12) 0px 8px 24px;
  --shadow-float: rgba(15, 15, 15, 0.20) 0px 24px 48px -8px;
}
```

### 5.4 阴影覆盖表

| 选择器 | 当前值 | 目标值 |
|---|---|---|
| `.search-results` | `var(--shadow)` (1px 3px) | `var(--shadow-md)` (0 4px 12px) |
| `.toast` | `var(--shadow)` (1px 3px) | `var(--shadow-md)` (0 4px 12px) |
| `.modal` | `var(--shadow-lg)` (10px 40px) | `var(--shadow-lg)` (0 8px 24px) |
| `.mount-card:hover` | `0 2px 8px rgba(79,70,229,0.08)` | `var(--shadow-sm)` + border `var(--c-hairline-strong)` |
| `.graph-container` | 未定义 | `var(--shadow-sm)` |

---

## 6. 组件重构规格

### 6.1 侧边栏

#### 6.1.1 整体容器

```css
.sidebar {
  width: var(--sidebar-w);           /* 240px */
  min-width: var(--sidebar-w);
  background: var(--c-bg-sidebar);   /* #f6f5f4 */
  border-right: 1px solid var(--c-border);
  display: flex;
  flex-direction: column;
  transition: width 0.2s ease;
  overflow: hidden;
  height: 100vh;
}
```

#### 6.1.2 Sidebar Header

```css
.sidebar-header {
  display: flex;
  align-items: center;
  gap: var(--s-sm);                  /* 12px */
  padding: var(--s-sm) var(--s-md);  /* 12px 16px */
  min-height: 48px;
  /* 移除 border-bottom */
}

.logo {
  font-size: var(--f-body-sm);       /* 14px */
  font-weight: var(--fw-semibold);   /* 600 */
  color: var(--c-ink);
  cursor: pointer;
  white-space: nowrap;
  /* 移除渐变 text-fill-color */
}
```

**HTML 变更：** 移除 `<h2>` 包裹，改为 `<div>`：

```html
<div class="sidebar-header">
  <div class="logo" onclick="navigateHome()">nas-md</div>
</div>
```

#### 6.1.3 搜索框

```css
.search-box {
  padding: var(--s-xs) var(--s-sm);  /* 8px 12px */
  position: relative;
}

.search-input {
  width: 100%;
  height: var(--search-h);           /* 36px */
  padding: var(--s-sm) var(--s-md) var(--s-sm) 36px;  /* 左 padding 留出图标空间 */
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);        /* 8px */
  font-size: var(--f-body-sm);       /* 14px */
  background: var(--c-canvas);       /* #ffffff */
  color: var(--c-ink);
  outline: none;
  transition: border-color 0.15s ease;
}

.search-input::placeholder {
  color: var(--c-muted);
}

.search-input:focus {
  border: 2px solid var(--c-primary);
  padding-left: 35px;                /* 补偿边框加粗 */
}
```

**HTML 变更：** 在 `.search-box` 中添加搜索图标 SVG：

```html
<div class="search-box">
  <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--c-steel)" stroke-width="2">
    <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
  </svg>
  <input type="text" id="search-input" placeholder="搜索笔记..." oninput="doSearch()" class="search-input">
  <div id="search-results" class="search-results"></div>
</div>
```

```css
.search-icon {
  position: absolute;
  left: 20px;                        /* 12px box padding + 8px gap */
  top: 50%;
  transform: translateY(-50%);
  pointer-events: none;
  stroke: var(--c-steel);
}
```

#### 6.1.4 文件树

```css
.file-tree {
  flex: 1;
  overflow-y: auto;
  padding: var(--s-xs) 0;             /* 8px 0 */
}

/* 挂载点行 */
.mount-name {
  flex: 1;
  padding: var(--s-xs) 0;            /* 8px 0 */
  font-weight: var(--fw-semibold);   /* 600 */
  font-size: var(--f-body-sm);       /* 14px */
  color: var(--c-steel);             /* #787671 */
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--s-xs);                  /* 8px */
  user-select: none;
  border-radius: var(--r-sm);       /* 6px */
}

.mount-name:hover {
  background: var(--c-bg-hover);
}

/* 树节点 */
.tree-item {
  padding: var(--s-xxs) var(--s-md) var(--s-xxs) var(--s-lg);  /* 4px 16px 4px 20px */
  height: var(--tree-node-h);        /* 28px */
  font-size: var(--f-body-sm);       /* 14px */
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--s-xs);                  /* 8px */
  border-radius: var(--r-sm);       /* 6px */
  margin: 1px var(--s-xs) 1px 0;     /* 1px 8px 1px 0 */
  color: var(--c-ink);
  transition: background-color 0.15s ease;
}

.tree-item:hover {
  background: var(--c-bg-hover);
}

.tree-item.active {
  background: var(--c-bg-active);
  font-weight: var(--fw-medium);     /* 500 */
  color: var(--c-ink);
  /* 左侧 3px 紫色竖线通过 box-shadow 实现 */
  box-shadow: inset 3px 0 0 var(--c-primary);
}

.tree-item.folder {
  font-weight: var(--fw-medium);     /* 500 */
}

/* 子级缩进 */
.tree-sub {
  padding-left: var(--tree-indent);   /* 16px */
}

/* 加载状态 */
.tree-loading {
  padding: var(--s-xs) var(--s-md);
  font-size: var(--f-micro);         /* 12px */
  color: var(--c-text-muted);
}
```

**文件树图标替换：** emoji 替换为内联 SVG（16x16）。

在 `app.js` 的 `renderEntries` 函数中，将 emoji 替换为：

```javascript
// 文件夹折叠图标
const folderIcon = `<svg class="tree-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="transform:rotate(${isExpanded ? 90 : 0}deg);transition:transform 0.15s"><polyline points="9 18 15 12 9 6"/></svg>`;

// 文件夹图标
const folderOpenIcon = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--c-steel)" stroke-width="1.5"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`;

// 文件图标
const fileIcon = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--c-steel)" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;
```

**展开/折叠动画：** 在 `tree-sub` 上添加：

```css
.tree-sub {
  overflow: hidden;
  transition: max-height 0.2s ease, opacity 0.15s ease;
}
.tree-sub.collapsed {
  max-height: 0;
  opacity: 0;
}
```

#### 6.1.5 侧边栏底部

```css
.sidebar-footer {
  padding: var(--s-sm);              /* 12px */
  border-top: 1px solid var(--c-border);
  display: flex;
  gap: var(--s-sm);                  /* 12px */
}

.nav-btn {
  flex: auto;
  padding: var(--s-xs) var(--s-sm);  /* 8px 12px */
  background: none;
  border: none;
  border-radius: var(--r-sm);       /* 6px */
  font-size: var(--f-body-sm);       /* 14px */
  font-weight: var(--fw-medium);     /* 500 */
  cursor: pointer;
  color: var(--c-steel);             /* #787671 */
  transition: all 0.15s ease;
  text-align: center;
}

.nav-btn:hover {
  background: var(--c-bg-hover);
  color: var(--c-ink);
}
```

**HTML 变更：** 移除 emoji：

```html
<div class="sidebar-footer">
  <button class="nav-btn" onclick="navigateHome()">首页</button>
  <button class="nav-btn" onclick="showGraph()">图谱</button>
  <button class="nav-btn" onclick="showDashboard()">看板</button>
</div>
```

#### 6.1.6 挂载点移除按钮

```css
.mount-remove-btn {
  background: none;
  border: none;
  font-size: var(--f-body-sm);       /* 14px */
  cursor: pointer;
  color: var(--c-muted);
  padding: var(--s-xxs) var(--s-xs); /* 4px 8px */
  border-radius: var(--r-sm);       /* 6px */
  opacity: 0;
  transition: all 0.15s ease;
  line-height: 1;
}

.mount-remove-btn:hover {
  opacity: 1;
  color: var(--c-danger);
  background: var(--c-bg-hover);
}

.mount-group:hover .mount-remove-btn {
  opacity: 0.6;
}
```

#### 6.1.7 公开标记 Badge

```css
.public-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px var(--s-xs);          /* 1px 8px */
  background: var(--c-tint-lavender);
  color: var(--c-brand-purple-800);
  border-radius: var(--r-full);
  font-size: var(--f-micro);         /* 12px */
  font-weight: var(--fw-semibold);   /* 600 */
}
```

---

### 6.2 顶部栏（Page Header）

#### 6.2.1 整体布局

```css
.topbar {
  height: var(--topbar-h);            /* 52px */
  display: flex;
  align-items: center;
  padding: 0 var(--s-lg);            /* 0 20px */
  gap: var(--s-md);                  /* 16px */
  border-bottom: 1px solid var(--c-border);
  background: var(--c-bg);
}

.breadcrumb {
  flex: 1;
  font-size: var(--f-body-sm);       /* 14px */
  color: var(--c-steel);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: var(--s-xs);                  /* 8px */
}
```

#### 6.2.2 模式切换（Segmented Tab）

```css
.editor-modes {
  display: flex;
  gap: 0;
  /* 移除背景色、圆角、padding */
}

.editor-modes button {
  padding: var(--s-sm) var(--s-md);  /* 12px 16px */
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  border-radius: 0;
  font-size: var(--f-body-sm);       /* 14px */
  font-weight: var(--fw-medium);     /* 500 */
  cursor: pointer;
  color: var(--c-steel);
  transition: all 0.15s ease;
  position: relative;
  bottom: -1px;                      /* 与 topbar border 重叠 */
}

.editor-modes button:hover {
  color: var(--c-ink);
}

.editor-modes button.active {
  color: var(--c-ink);
  border-bottom-color: var(--c-ink);
  background: none;
  box-shadow: none;
}
```

#### 6.2.3 保存按钮

```css
.save-btn {
  padding: var(--s-xs) var(--s-md);  /* 8px 16px */
  background: transparent;
  color: var(--c-steel);
  border: 1px solid var(--c-border-strong);
  border-radius: var(--r-md);       /* 8px */
  font-size: var(--f-body-sm);       /* 14px */
  font-weight: var(--fw-medium);     /* 500 */
  cursor: pointer;
  transition: all 0.15s ease;
  height: var(--button-h);           /* 36px */
}

.save-btn:hover:not(.disabled) {
  color: var(--c-ink);
  border-color: var(--c-ink);
}

/* Dirty 状态：紫色边框 */
.save-btn.dirty {
  color: var(--c-primary);
  border-color: var(--c-primary);
}

.save-btn.dirty:hover {
  color: var(--c-primary-hover);
  border-color: var(--c-primary-hover);
}

.save-btn.disabled {
  opacity: 0.4;
  cursor: default;
}
```

**app.js 变更：** 在 `setEditorMode` 和 `saveFile` 中添加 dirty 类切换：

```javascript
function markDirty() {
  state.dirty = true;
  const btn = $('btn-save');
  if (btn) btn.classList.add('dirty');
}

function markClean() {
  state.dirty = false;
  const btn = $('btn-save');
  if (btn) btn.classList.remove('dirty');
}
```

#### 6.2.4 大纲切换按钮

```css
.outline-toggle-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: var(--s-xs);             /* 8px */
  border-radius: var(--r-sm);       /* 6px */
  color: var(--c-steel);
  display: flex;
  align-items: center;
  transition: all 0.15s ease;
}

.outline-toggle-btn:hover {
  background: var(--c-bg-hover);
  color: var(--c-ink);
}
```

#### 6.2.5 同步指示器

```css
.sync-indicator {
  font-size: var(--f-micro);         /* 12px */
  margin-left: var(--s-xs);           /* 8px */
  cursor: default;
}

.sync-indicator.synced { color: var(--c-success); }
.sync-indicator.syncing { color: var(--c-warning); animation: pulse 1s infinite; }
.sync-indicator.offline { color: var(--c-danger); }
.sync-indicator.conflict { color: var(--c-brand-purple); }
```

---

### 6.3 欢迎页

#### 6.3.1 Hero 区域

```css
.welcome-page {
  padding: var(--s-section);         /* 64px */
  max-width: 640px;
  margin: 0 auto;
  min-height: 100%;
  overflow-y: auto;
}

.welcome-hero {
  text-align: center;
  padding: var(--s-xxxl) 0 var(--s-section-sm);  /* 40px 0 48px */
}

.welcome-logo {
  font-size: var(--f-h1);            /* 48px */
  font-weight: var(--fw-semibold);   /* 600 */
  color: var(--c-ink);
  letter-spacing: var(--ls-h1);      /* -0.5px */
  margin-bottom: var(--s-xs);        /* 8px */
  /* 移除渐变 text-fill-color */
  background: none;
  -webkit-text-fill-color: initial;
}

.welcome-subtitle {
  font-size: var(--f-subtitle);      /* 18px */
  font-weight: var(--fw-regular);    /* 400 */
  color: var(--c-steel);
  margin-bottom: var(--s-md);        /* 16px */
}

.welcome-desc {
  font-size: var(--f-body-sm);       /* 14px */
  color: var(--c-muted);
  line-height: var(--lh-body);       /* 1.55 */
  max-width: 420px;
  margin: 0 auto;
}
```

**HTML 变更：** 移除渐变样式。`.welcome-logo` 从 `<h1>` 改为 `<div>`（语义化可选）：

```html
<div class="welcome-hero">
  <div class="welcome-logo">nas-md</div>
  <p class="welcome-subtitle">个人知识管理系统</p>
  <p class="welcome-desc">轻量、快速的 Markdown 笔记管理器。输入目录路径即可浏览、搜索和编辑你的笔记。</p>
</div>
```

#### 6.3.2 快速操作区（3 列卡片网格）

新增一个 "快速操作" section，使用 pastel tint 卡片：

```css
.quick-actions {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--s-sm);                  /* 12px */
  margin-bottom: var(--s-section-sm); /* 48px */
}

.quick-action-card {
  background: var(--c-canvas);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);       /* 12px */
  padding: var(--s-lg);              /* 20px */
  cursor: pointer;
  transition: all 0.15s ease;
  display: flex;
  flex-direction: column;
  gap: var(--s-sm);                  /* 12px */
}

.quick-action-card:hover {
  border-color: var(--c-hairline-strong);
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}

.quick-action-icon {
  width: 32px;
  height: 32px;
  border-radius: var(--r-md);       /* 8px */
  display: flex;
  align-items: center;
  justify-content: center;
}

.quick-action-icon.tint-sky { background: var(--c-tint-sky); }
.quick-action-icon.tint-mint { background: var(--c-tint-mint); }
.quick-action-icon.tint-lavender { background: var(--c-tint-lavender); }

.quick-action-title {
  font-size: var(--f-body-sm);       /* 14px */
  font-weight: var(--fw-semibold);   /* 600 */
  color: var(--c-ink);
}

.quick-action-desc {
  font-size: var(--f-caption);       /* 13px */
  color: var(--c-steel);
  line-height: var(--lh-caption);    /* 1.40 */
}
```

**HTML 新增：**

```html
<div class="quick-actions">
  <div class="quick-action-card" onclick="document.getElementById('new-dir-path').focus()">
    <div class="quick-action-icon tint-sky">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--c-link)" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
    </div>
    <div class="quick-action-title">打开目录</div>
    <div class="quick-action-desc">浏览并挂载一个本地目录</div>
  </div>
  <div class="quick-action-card" onclick="showNewFile()">
    <div class="quick-action-icon tint-mint">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--c-brand-green)" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
    </div>
    <div class="quick-action-title">新建笔记</div>
    <div class="quick-action-desc">在当前目录下创建新的 Markdown 文件</div>
  </div>
  <div class="quick-action-card" onclick="chooseDirectory()">
    <div class="quick-action-icon tint-lavender">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--c-brand-purple)" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
    </div>
    <div class="quick-action-title">导入文件</div>
    <div class="quick-action-desc">选择目录批量导入现有笔记</div>
  </div>
</div>
```

#### 6.3.3 Section 标题

```css
.section-label {
  display: block;
  font-size: var(--f-caption);       /* 13px */
  font-weight: var(--fw-semibold);   /* 600 */
  color: var(--c-muted);
  margin-bottom: var(--s-xs);        /* 8px */
  text-transform: uppercase;
  letter-spacing: var(--ls-uppercase); /* 1px */
}

.section-title {
  font-size: var(--f-h5);            /* 18px */
  font-weight: var(--fw-semibold);   /* 600 */
  color: var(--c-ink);
  margin-bottom: var(--s-sm);        /* 12px */
  display: flex;
  align-items: center;
  gap: var(--s-xs);                  /* 8px */
}
```

#### 6.3.4 打开目录区域

```css
.open-dir-section {
  margin-bottom: var(--s-section-sm); /* 48px */
}

.open-dir-input-group {
  display: flex;
  gap: var(--s-xs);                  /* 8px */
}

.open-dir-input {
  flex: 2;
  height: var(--input-h);            /* 40px */
  padding: var(--s-sm) var(--s-md);  /* 12px 16px */
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);       /* 8px */
  font-size: var(--f-body-sm);       /* 14px */
  background: var(--c-canvas);
  color: var(--c-ink);
  outline: none;
  transition: border-color 0.15s ease;
  font-family: var(--font-mono);
  cursor: pointer;
}

.open-dir-input:focus {
  border: 2px solid var(--c-primary);
  padding: 11px 15px;                /* 补偿边框加粗 */
}

.open-dir-input::placeholder {
  color: var(--c-muted);
}

.open-dir-name-input {
  flex: 1;
  height: var(--input-h);            /* 40px */
  padding: var(--s-sm) var(--s-md);
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  font-size: var(--f-body-sm);
  background: var(--c-canvas);
  color: var(--c-ink);
  outline: none;
  transition: border-color 0.15s ease;
}

.open-dir-name-input:focus {
  border: 2px solid var(--c-primary);
  padding: 11px 15px;
}

.open-dir-hint {
  font-size: var(--f-micro);         /* 12px */
  color: var(--c-muted);
  margin-top: var(--s-xs);           /* 8px */
}
```

#### 6.3.5 按钮样式

```css
.browse-btn {
  height: var(--input-h);            /* 40px */
  padding: var(--s-sm) var(--s-md);  /* 12px 16px */
  background: var(--c-canvas);
  color: var(--c-ink);
  border: 1px solid var(--c-border-strong);
  border-radius: var(--r-md);       /* 8px */
  font-size: var(--f-body-sm);       /* 14px */
  font-weight: var(--fw-medium);     /* 500 */
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.browse-btn:hover {
  background: var(--c-bg-hover);
  border-color: var(--c-hairline-strong);
}

.primary-btn {
  height: var(--input-h);            /* 40px */
  padding: var(--s-sm) var(--s-lg);  /* 12px 20px */
  background: var(--c-primary);
  color: var(--c-on-primary);
  border: none;
  border-radius: var(--r-md);       /* 8px */
  font-size: var(--f-button);        /* 14px */
  font-weight: var(--fw-medium);     /* 500 */
  cursor: pointer;
  transition: background-color 0.15s ease;
  white-space: nowrap;
}

.primary-btn:hover {
  background: var(--c-primary-hover);
}
```

#### 6.3.6 挂载卡片

```css
.mount-cards {
  display: flex;
  flex-direction: column;
  gap: var(--s-xs);                  /* 8px */
}

.mount-card {
  display: flex;
  align-items: center;
  gap: var(--s-md);                  /* 16px */
  padding: var(--s-sm) var(--s-md);  /* 12px 16px */
  border-radius: var(--r-lg);       /* 12px */
  cursor: pointer;
  transition: all 0.15s ease;
  border: 1px solid var(--c-border);
}

.mount-card:hover {
  border-color: var(--c-hairline-strong);
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}

.mount-card-icon {
  font-size: 24px;
  flex-shrink: 0;
}

.mount-card-info {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.mount-card-top {
  display: flex;
  align-items: center;
  gap: var(--s-xs);                  /* 8px */
}

.mount-card-name {
  font-size: var(--f-body-sm);       /* 14px */
  font-weight: var(--fw-semibold);   /* 600 */
  color: var(--c-ink);
}

.mount-card-path {
  font-size: var(--f-micro);         /* 12px */
  color: var(--c-muted);
  font-family: var(--font-mono);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mount-card-toggle {
  background: none;
  border: none;
  font-size: 16px;
  cursor: pointer;
  padding: var(--s-xs);
  border-radius: var(--r-sm);
  transition: background-color 0.15s ease;
  flex-shrink: 0;
  color: var(--c-steel);
}

.mount-card-toggle:hover {
  background: var(--c-bg-hover);
}
```

#### 6.3.7 最近文件

```css
.recent-files {
  margin-bottom: var(--s-section-sm); /* 48px */
}

.recent-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--s-xs) var(--s-md);  /* 8px 16px */
  height: 36px;
  border-radius: var(--r-sm);       /* 6px */
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.recent-item:hover {
  background: var(--c-bg-hover);
}

.recent-name {
  font-size: var(--f-body-sm);       /* 14px */
  color: var(--c-ink);
}

.recent-time {
  font-size: var(--f-micro);         /* 12px */
  color: var(--c-muted);
}
```

---

### 6.4 Vditor 编辑器样式

#### 6.4.1 亮色模式 CSS 变量

在 `app.css` 末尾添加：

```css
/* === Vditor Light Mode Variables === */
.vditor {
  --border-color: #e5e3df;
  --toolbar-background-color: #f6f5f4;
  --toolbar-icon-color: #787671;
  --toolbar-icon-hover-color: #5645d4;
  --toolbar-height: 35px;
  --textarea-background-color: #ffffff;
  --textarea-text-color: #1a1a1a;
  --panel-background-color: #ffffff;
  --panel-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  --second-color: rgba(120, 118, 113, 0.36);
  --blockquote-color: #787671;
  --heading-border-color: #e5e3df;
  --ir-heading-color: #5645d4;
  --ir-title-color: #bbb8b1;
  --ir-bi-color: #5645d4;
  --ir-link-color: #0075de;
  --ir-bracket-color: #0075de;
  --ir-paren-color: #2a9d99;
  --count-background-color: rgba(86, 69, 212, 0.08);
  --list-mark-color: #5645d4;
}
```

#### 6.4.2 Vditor 硬编码覆盖

```css
/* Code blocks */
.vditor-ir pre.vditor-reset,
.vditor-wysiwyg pre.vditor-reset,
.vditor-sv pre.vditor-reset,
.vditor-preview pre {
  background-color: #f6f5f4 !important;
  border: 1px solid #e5e3df !important;
  border-radius: 8px !important;
}

/* Blockquote */
.vditor-ir blockquote,
.vditor-wysiwyg blockquote,
.vditor-preview blockquote {
  border-left: 3px solid #c8c4be !important;
  background-color: #f6f5f4 !important;
  color: #787671 !important;
}

/* Table header */
.vditor-ir table thead,
.vditor-wysiwyg table thead,
.vditor-preview table thead {
  background-color: #f6f5f4 !important;
}

/* Table border */
.vditor-ir table td,
.vditor-ir table th,
.vditor-wysiwyg table td,
.vditor-wysiwyg table th,
.vditor-preview table td,
.vditor-preview table th {
  border-color: #e5e3df !important;
}

/* IR/WYSIWYG heading prefix markers */
.vditor-ir .vditor-reset > h1:before,
.vditor-ir .vditor-reset > h2:before,
.vditor-ir .vditor-reset > h3:before,
.vditor-ir .vditor-reset > h4:before,
.vditor-ir .vditor-reset > h5:before,
.vditor-ir .vditor-reset > h6:before,
.vditor-wysiwyg > .vditor-reset > h1:before,
.vditor-wysiwyg > .vditor-reset > h2:before,
.vditor-wysiwyg > .vditor-reset > h3:before,
.vditor-wysiwyg > .vditor-reset > h4:before,
.vditor-wysiwyg > .vditor-reset > h5:before,
.vditor-wysiwyg > .vditor-reset > h6:before {
  color: #bbb8b1 !important;
}

/* Tooltip */
.vditor-tooltipped::after {
  background: #37352f !important;
  color: #ffffff !important;
}
.vditor-tooltipped--hover::before,
.vditor-tooltipped:hover::before {
  border-bottom-color: #37352f !important;
}

/* Horizontal rule */
.vditor-ir hr,
.vditor-wysiwyg hr {
  background-color: #e5e3df !important;
}

/* Footnotes */
.vditor-ir div[data-type="footnotes-block"],
.vditor-wysiwyg div[data-type="footnotes-block"] {
  border-top-color: #e5e3df !important;
}

/* Links */
.vditor-ir a,
.vditor-wysiwyg a,
.vditor-preview a {
  color: #0075de !important;
}

/* Inline code */
.vditor-ir code,
.vditor-wysiwyg code,
.vditor-preview code {
  background-color: #f6f5f4 !important;
  color: #5645d4 !important;
}
```

#### 6.4.3 Vditor 内容区排版

```css
/* IR mode body */
.vditor-ir .vditor-reset {
  font-size: 16px;
  line-height: 1.7;
}

/* IR mode headings */
.vditor-ir .vditor-reset > h1 { font-size: 28px; font-weight: 600; line-height: 1.25; }
.vditor-ir .vditor-reset > h2 { font-size: 22px; font-weight: 600; line-height: 1.25; }
.vditor-ir .vditor-reset > h3 { font-size: 18px; font-weight: 600; line-height: 1.30; }
.vditor-ir .vditor-reset > h4 { font-size: 16px; font-weight: 600; line-height: 1.35; }
.vditor-ir .vditor-reset > h5 { font-size: 16px; font-weight: 600; line-height: 1.35; }
.vditor-ir .vditor-reset > h6 { font-size: 16px; font-weight: 600; line-height: 1.35; }

/* SV mode headings */
.vditor-sv .h1 { font-size: 1.75em; font-weight: 600; }
.vditor-sv .h2 { font-size: 1.55em; font-weight: 600; }
.vditor-sv .h3 { font-size: 1.38em; font-weight: 600; }
.vditor-sv .h4 { font-size: 1.25em; font-weight: 600; }
.vditor-sv .h5 { font-size: 1.13em; font-weight: 600; }
.vditor-sv .h6 { font-size: 1em; font-weight: 600; }

/* WYSIWYG mode headings */
.vditor-wysiwyg .vditor-reset > h1 { font-size: 28px; font-weight: 600; }
.vditor-wysiwyg .vditor-reset > h2 { font-size: 22px; font-weight: 600; }
.vditor-wysiwyg .vditor-reset > h3 { font-size: 18px; font-weight: 600; }
.vditor-wysiwyg .vditor-reset > h4 { font-size: 16px; font-weight: 600; }
.vditor-wysiwyg .vditor-reset > h5 { font-size: 16px; font-weight: 600; }
.vditor-wysiwyg .vditor-reset > h6 { font-size: 16px; font-weight: 600; }

/* Preview area */
.vditor-preview .vditor-reset {
  font-size: 16px;
  line-height: 1.7;
}
```

#### 6.4.4 Vditor 大纲栏

```css
.vditor-outline li > span {
  font-size: var(--f-caption);       /* 13px */
  color: var(--c-steel);
  line-height: 28px;
}

.vditor-outline li > span.outline-active {
  color: var(--c-primary);
  font-weight: var(--fw-bold);       /* 700 */
}
```

---

### 6.5 模态框

#### 6.5.1 遮罩

```css
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  display: none;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
  opacity: 0;
  transition: opacity 0.2s ease;
}

.modal-overlay.active {
  display: flex;
  opacity: 1;
}
```

#### 6.5.2 弹窗体

```css
.modal {
  background: var(--c-canvas);
  border-radius: var(--r-xl);       /* 16px */
  padding: var(--s-xxl) var(--s-xxxl);  /* 32px 40px */
  min-width: 400px;
  max-width: 90vw;
  box-shadow: var(--shadow-lg);
  transform: translateY(8px);
  transition: transform 0.2s ease, opacity 0.2s ease;
  opacity: 0;
}

.modal-overlay.active .modal {
  transform: translateY(0);
  opacity: 1;
}
```

#### 6.5.3 弹窗内容

```css
.modal h3 {
  margin-bottom: var(--s-md);        /* 16px */
  font-size: var(--f-h5);            /* 18px */
  font-weight: var(--fw-semibold);   /* 600 */
  color: var(--c-ink);
}

.modal-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--s-md);
}

.modal-header-row h3 {
  margin-bottom: 0;
}

.modal-close {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: var(--c-muted);
  padding: var(--s-xxs);             /* 4px */
  border-radius: var(--r-sm);       /* 6px */
  transition: all 0.15s ease;
  line-height: 1;
}

.modal-close:hover {
  background: var(--c-bg-hover);
  color: var(--c-ink);
}

.modal-input {
  width: 100%;
  height: var(--input-h);            /* 40px */
  padding: var(--s-sm) var(--s-md);
  border: 1px solid var(--c-border-strong);
  border-radius: var(--r-md);       /* 8px */
  font-size: var(--f-body-sm);       /* 14px */
  background: var(--c-canvas);
  color: var(--c-ink);
  outline: none;
  margin-bottom: var(--s-lg);        /* 20px */
  transition: border-color 0.15s ease;
}

.modal-input:focus {
  border: 2px solid var(--c-primary);
  padding: 11px 15px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--s-xs);                  /* 8px */
}

.modal-actions button {
  padding: var(--s-xs) var(--s-md);  /* 8px 16px */
  border: 1px solid var(--c-border-strong);
  border-radius: var(--r-md);       /* 8px */
  background: var(--c-canvas);
  color: var(--c-ink);
  font-size: var(--f-body-sm);       /* 14px */
  cursor: pointer;
  transition: all 0.15s ease;
  height: var(--button-h);           /* 36px */
}

.modal-actions button:hover {
  background: var(--c-bg-hover);
}
```

**JS 变更：** 模态框打开/关闭添加动画类切换：

```javascript
function showNewFile() {
  const modal = $('new-file-modal');
  modal.style.display = '';
  // 强制 reflow 后添加 active 类触发动画
  requestAnimationFrame(() => modal.classList.add('active'));
}

function hideNewFile() {
  const modal = $('new-file-modal');
  modal.classList.remove('active');
  // 等待过渡结束后隐藏
  setTimeout(() => {
    if (!modal.classList.contains('active')) {
      modal.style.display = 'none';
    }
  }, 200);
  $('new-file-name').value = '';
}
```

---

### 6.6 Toast

```css
.toast {
  position: fixed;
  bottom: var(--s-xl);               /* 24px */
  right: var(--s-xl);                /* 24px */
  padding: var(--s-sm) var(--s-lg);  /* 12px 20px */
  background: var(--c-charcoal);     /* #37352f */
  color: var(--c-on-dark);           /* #ffffff */
  border-radius: var(--r-md);       /* 8px */
  font-size: var(--f-body-sm);       /* 14px */
  z-index: 2000;
  box-shadow: var(--shadow-md);
  opacity: 0;
  transform: translateY(8px);
  transition: opacity 0.2s ease, transform 0.2s ease;
  pointer-events: none;
}

.toast.show {
  opacity: 1;
  transform: translateY(0);
}
```

**JS 变更：**

```javascript
function showToast(msg) {
  const el = $('toast');
  el.textContent = msg;
  el.style.display = '';
  // 强制 reflow
  void el.offsetHeight;
  el.classList.add('show');
  if (state.toastTimer) clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => {
    el.classList.remove('show');
    setTimeout(() => {
      if (!el.classList.contains('show')) el.style.display = 'none';
    }, 200);
  }, 2500);
}
```

---

### 6.7 知识图谱页

```css
.graph-page {
  padding: var(--s-lg);              /* 20px */
  height: 100%;
  display: flex;
  flex-direction: column;
}

.graph-page h1 {
  margin-bottom: var(--s-sm);        /* 12px */
  font-size: var(--f-h3);            /* 28px */
}

.graph-container {
  flex: 1;
  min-height: 400px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);       /* 8px */
  background: var(--c-canvas);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}

.graph-container svg {
  width: 100%;
  height: 100%;
}

.graph-node circle {
  stroke: #ffffff;
  stroke-width: 2px;
}

.graph-node text {
  font-size: var(--f-micro);         /* 12px */
  fill: var(--c-ink);
  pointer-events: none;
}

.graph-link {
  stroke: var(--c-border);
  stroke-width: 1.5px;
}
```

---

### 6.8 数据看板页

```css
.dashboard-page {
  padding: var(--s-lg);              /* 20px */
  overflow-y: auto;
}

.dashboard-page h1 {
  margin-bottom: var(--s-md);        /* 16px */
  font-size: var(--f-h3);            /* 28px */
}

.dashboard-page h2 {
  margin: var(--s-xl) 0 var(--s-sm);  /* 24px 0 12px */
  font-size: var(--f-h5);            /* 18px */
  color: var(--c-steel);
}

.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: var(--s-sm);                  /* 12px */
}

.dash-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);       /* 8px */
  padding: var(--s-md);              /* 16px */
  text-align: center;
}

.dash-value {
  font-size: 28px;
  font-weight: var(--fw-bold);       /* 700 */
  color: var(--c-primary);
}

.dash-label {
  font-size: var(--f-body-sm);       /* 14px */
  color: var(--c-steel);
  margin-top: var(--s-xxs);          /* 4px */
}

.dash-recent {
  display: flex;
  flex-direction: column;
  gap: var(--s-xs);                  /* 8px */
}

.dash-recent-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--s-xs) var(--s-sm);  /* 8px 12px */
  background: var(--c-surface);
  border-radius: var(--r-sm);       /* 6px */
  cursor: pointer;
  font-size: var(--f-body-sm);       /* 14px */
  transition: background-color 0.15s ease;
}

.dash-recent-item:hover {
  background: var(--c-bg-hover);
}

.dash-recent-title {
  color: var(--c-link);
  font-weight: var(--fw-medium);     /* 500 */
}

.dash-recent-time {
  color: var(--c-muted);
  font-size: var(--f-micro);         /* 12px */
}
```

---

### 6.9 搜索下拉

```css
.search-results {
  position: absolute;
  top: 44px;
  left: var(--s-sm);                 /* 12px */
  right: var(--s-sm);                /* 12px */
  background: var(--c-canvas);
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);       /* 8px */
  box-shadow: var(--shadow-md);
  max-height: 300px;
  overflow-y: auto;
  z-index: 100;
}

.search-result-item {
  padding: var(--s-xs) var(--s-sm);  /* 8px 12px */
  cursor: pointer;
  border-bottom: 1px solid var(--c-border);
  transition: background-color 0.15s ease;
}

.search-result-item:last-child {
  border-bottom: none;
}

.search-result-item:hover {
  background: var(--c-bg-hover);
}

.result-path {
  display: block;
  font-size: var(--f-body-sm);       /* 14px */
  font-weight: var(--fw-medium);     /* 500 */
  color: var(--c-ink);
}

.result-snippet {
  display: block;
  font-size: var(--f-micro);         /* 12px */
  color: var(--c-steel);
  margin-top: var(--s-xxs);          /* 4px */
}
```

---

### 6.10 全局元素

#### 6.10.1 滚动条

```css
::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: var(--c-border);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--c-muted);
}
```

#### 6.10.2 链接颜色

```css
a {
  color: var(--c-link);
  text-decoration: none;
  transition: color 0.15s ease;
}

a:hover {
  color: var(--c-link-pressed);
}
```

#### 6.10.3 辅助类

```css
.admin-only {
  display: none;
}

body.admin .admin-only {
  display: block;
}

.mount-path-hint {
  font-size: var(--f-micro);         /* 12px */
  color: var(--c-muted);
  font-family: var(--font-mono);
  padding: var(--s-xxs) var(--s-xs) var(--s-xxs);
  display: block;
  opacity: 0.7;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
```

---

## 7. 暗色模式

### 7.1 实现方式

通过 `document.documentElement.classList.toggle('dark')` 切换，偏好保存到 `localStorage`。

**app.js 中添加：**

```javascript
// 初始化暗色模式偏好
if (localStorage.getItem('nasmd_dark') === '1') {
  document.documentElement.classList.add('dark');
}

function toggleDarkMode() {
  const isDark = document.documentElement.classList.toggle('dark');
  localStorage.setItem('nasmd_dark', isDark ? '1' : '0');
}
```

### 7.2 页面级暗色变量

```css
.dark {
  /* Canvas / Surface */
  --c-bg: #191919;
  --c-bg-sidebar: #202020;
  --c-bg-hover: #2a2a2a;
  --c-bg-active: #333333;

  /* Borders */
  --c-border: #333333;
  --c-border-strong: #444444;

  /* Text */
  --c-text: #e0e0e0;
  --c-text-secondary: #a0a0a0;
  --c-text-muted: #666666;

  /* Primary */
  --c-primary: #818cf8;
  --c-primary-hover: #a5b4fc;
  --c-on-primary: #000000;

  /* Link */
  --c-link: #60a5fa;
  --c-link-hover: #93bbfc;

  /* Ink (for active states) */
  --c-ink: #e0e0e0;
  --c-ink-deep: #ffffff;

  /* Shadows (darker) */
  --shadow-sm: rgba(0, 0, 0, 0.20) 0px 1px 2px;
  --shadow-md: rgba(0, 0, 0, 0.30) 0px 4px 12px;
  --shadow-lg: rgba(0, 0, 0, 0.40) 0px 8px 24px;
}
```

### 7.3 Vditor 暗色变量

```css
.dark .vditor {
  --border-color: #333333;
  --toolbar-background-color: #202020;
  --toolbar-icon-color: #a0a0a0;
  --toolbar-icon-hover-color: #818cf8;
  --textarea-background-color: #191919;
  --textarea-text-color: #e0e0e0;
  --panel-background-color: #2a2a2a;
  --panel-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  --second-color: rgba(160, 160, 160, 0.36);
  --blockquote-color: #a0a0a0;
  --heading-border-color: #333333;
  --ir-heading-color: #818cf8;
  --ir-title-color: #666666;
  --ir-bi-color: #818cf8;
  --ir-link-color: #60a5fa;
  --ir-bracket-color: #60a5fa;
  --ir-paren-color: #2a9d99;
  --count-background-color: rgba(129, 140, 248, 0.12);
  --list-mark-color: #818cf8;
}
```

### 7.4 Vditor 暗色硬编码覆盖

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

.dark .vditor-outline li > span {
  color: #a0a0a0;
}

.dark .vditor-outline li > span.outline-active {
  color: #818cf8;
}
```

### 7.5 暗色模式下的 Pastel Tints

暗色模式下 pastel tints 不改变（它们只在欢迎页卡片中使用，暗色模式下可保持原色或降低透明度）。如需暗色适配：

```css
.dark .quick-action-icon.tint-sky { background: rgba(220, 236, 250, 0.15); }
.dark .quick-action-icon.tint-mint { background: rgba(217, 243, 225, 0.15); }
.dark .quick-action-icon.tint-lavender { background: rgba(230, 224, 245, 0.15); }
```

---

## 8. 响应式

### 8.1 断点

```css
/* Desktop: ≥ 1024px — 完整布局，无覆盖 */

/* Tablet: 768px – 1023px */
@media (max-width: 1023px) {
  :root {
    --sidebar-w: 200px;
  }

  .quick-actions {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* Mobile: < 768px */
@media (max-width: 767px) {
  :root {
    --sidebar-w: 280px;
  }

  .sidebar {
    position: fixed;
    z-index: 200;
    height: 100%;
    transform: translateX(-100%);
    transition: transform 0.2s ease;
  }

  .sidebar.open {
    transform: translateX(0);
  }

  .welcome-page {
    padding: var(--s-lg);              /* 20px */
  }

  .welcome-hero {
    padding: var(--s-xl) 0 var(--s-lg);  /* 24px 0 20px */
  }

  .welcome-logo {
    font-size: var(--f-h3);            /* 28px */
  }

  .quick-actions {
    grid-template-columns: 1fr;
  }

  .open-dir-input-group {
    flex-direction: column;
  }

  .open-dir-input,
  .open-dir-name-input {
    flex: none;
  }

  .modal {
    min-width: 0;
    width: 90vw;
    padding: var(--s-lg);              /* 20px */
  }

  .dashboard-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
```

### 8.2 触摸目标

```css
@media (max-width: 767px) {
  .tree-item {
    height: 40px;                    /* 从 28px 增加到 40px */
  }

  .nav-btn {
    min-height: 44px;
  }

  .save-btn {
    min-height: 44px;
  }
}
```

### 8.3 侧边栏移动端展开

**HTML 变更：** 在主内容区添加菜单按钮：

```html
<header class="topbar">
  <button class="menu-toggle" id="menu-toggle" onclick="toggleSidebar()">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/>
    </svg>
  </button>
  <span class="breadcrumb" id="breadcrumb"></span>
  ...
</header>
```

```css
.menu-toggle {
  display: none;
  background: none;
  border: none;
  cursor: pointer;
  padding: var(--s-xxs);
  border-radius: var(--r-sm);
  color: var(--c-steel);
  transition: all 0.15s ease;
}

.menu-toggle:hover {
  background: var(--c-bg-hover);
  color: var(--c-ink);
}

@media (max-width: 767px) {
  .menu-toggle {
    display: flex;
    align-items: center;
    justify-content: center;
  }
}
```

**JS：**

```javascript
function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
}

// 点击主内容区时关闭侧边栏
document.querySelector('.main').addEventListener('click', () => {
  document.getElementById('sidebar').classList.remove('open');
});
```

---

## 9. 实施阶段

### Phase 1：设计令牌 + 全局样式 ✅ 已完成

**修改文件：** `web/app.css`

**任务：**
1. 替换 `:root` 全部变量为 Notion 色彩体系（DESIGN.md 所有色值）
2. 添加 `--f-*`（排版）、`--s-*`（间距）、`--r-*`（圆角）、`--shadow-*`（阴影）变量
3. 替换全局排版规则（body, heading, code, scrollbar, selection）
4. 创建 `web/lib/fonts/inter.css` 并放置字体文件
5. 在 `index.html` 引入 `lib/fonts/inter.css`

**验证标准：**
- 刷新页面，页面颜色从偏冷色调变为暖色调（`#f6f5f4` 侧边栏背景）
- 字体从系统默认变为 Inter
- 所有圆角从 4px/8px/16px 变为 6px/8px/12px
- 阴影从重阴影变为轻阴影
- 控制台无 404 字体加载错误

**预计工作量：** 1-2 天

---

### Phase 2：侧边栏重构 ✅ 已完成

**修改文件：** `web/app.css`（侧边栏部分）、`web/app.js`（`renderSidebar` / `renderEntries`）、`web/index.html`（侧边栏 HTML）

**任务：**
1. 收窄侧边栏到 240px
2. 重写 `.sidebar-header`（移除 border-bottom，移除渐变 logo）
3. 添加搜索图标 SVG，重写搜索框样式
4. 文件树 emoji → 内联 SVG（16x16）
5. 统一文件树缩进为 16px/级
6. 添加展开/折叠动画（max-height transition）
7. 重写底部操作区（移除 emoji，纯文字）
8. 重写挂载点移除按钮样式
9. 重写公开标记 badge

**验证标准：**
- 侧边栏宽度 240px
- 搜索框左侧有搜索图标
- 文件树使用 SVG 图标而非 emoji
- 点击文件夹有平滑展开动画
- 底部按钮无 emoji
- 文件选中态有左侧紫色竖线指示

**预计工作量：** 1 天

---

### Phase 3：顶部栏 + 编辑器区域 ✅ 已完成

**修改文件：** `web/app.css`（topbar 部分）、`web/app.js`（`setEditorMode` / `saveFile`）、`web/editor.js`（Vditor 初始化）

**任务：**
1. 增加 topbar 高度到 52px
2. 模式切换从按钮组改为 segmented tab（下划线式）
3. 保存按钮改为 ghost 样式 + dirty 高亮
4. 添加 Vditor 亮色 CSS 变量
5. 添加 Vditor 硬编码覆盖（代码块、引用块、表格、tooltip、链接、行内代码）
6. 添加 Vditor 内容区排版覆盖（IR/SV/WYSIWYG 标题字号）
7. 更新大纲栏样式

**验证标准：**
- 模式切换为下划线式 tab
- 保存按钮默认灰色边框，dirty 时紫色边框
- Vditor 工具栏背景为 `#f6f5f4`，图标为 `#787671`
- 代码块背景为 `#f6f5f4`，边框为 `#e5e3df`
- 引用块左侧竖线为 `#c8c4be`
- 链接颜色为 `#0075de`（非紫色）
- 行内代码为紫色文字 + 灰色背景

**预计工作量：** 1 天

---

### Phase 4：欢迎页 + 模态框 + Toast ✅ 已完成

**修改文件：** `web/app.css`（welcome / modal / toast 部分）、`web/app.js`（相关函数）、`web/index.html`（欢迎页 HTML）

**任务：**
1. 重写 Hero 区域（移除渐变 logo，改为纯文字 48px semibold）
2. 新增 "快速操作" section（3 列 pastel tint 卡片网格）
3. 重写 section 标题样式（uppercase 13px muted）
4. 重写打开目录区域（统一输入框高度 40px）
5. 重写按钮样式（primary/secondary 对齐 Notion 规范）
6. 重写挂载卡片样式（12px 圆角，hover 上浮）
7. 重写最近文件列表样式
8. 模态框添加进入/退出动画（opacity + translateY transition）
9. Toast 改为 charcoal 背景 + 动画

**验证标准：**
- 欢迎页 logo 为纯文字，无渐变
- 快速操作区 3 列卡片，每张有 pastel tint 图标背景
- 模态框打开时有 200ms 淡入 + 上移动画
- Toast 背景为 `#37352f`，白色文字
- 所有按钮圆角 8px，高度 36px/40px

**预计工作量：** 1 天

---

### Phase 5：暗色模式 + 响应式 ✅ 已完成

**修改文件：** `web/app.css`（暗色变量 + 响应式）、`web/app.js`（暗色模式切换 + 侧边栏折叠）

**任务：**
1. 添加 `.dark` 类变量（页面级 + Vditor）
2. 添加暗色模式切换按钮（在设置页或顶部栏）
3. 添加 `toggleDarkMode()` JS 函数 + localStorage 持久化
4. 添加响应式断点（1023px / 767px）
5. 侧边栏移动端折叠（overlay 模式）
6. 添加菜单按钮（移动端）
7. 移动端触摸目标增大
8. 知识图谱页和看板页的暗色适配

**验证标准：**
- 切换暗色模式后所有组件颜色正确变化
- 暗色模式下 Vditor 编辑器颜色正确
- 暗色模式偏好保存到 localStorage，刷新后恢复
- 767px 以下侧边栏默认隐藏，点击菜单按钮展开
- 768-1023px 侧边栏收窄到 200px
- 移动端文件树节点高度 ≥ 40px

**预计工作量：** 1 天

---

### Phase 6：交互优化 + 测试 ✅ 已完成

**修改文件：** `web/app.js`（快捷键、动画）、`web/files.js`（如有需要）

**任务：**
1. 添加键盘快捷键（Ctrl+K 搜索聚焦、Ctrl+N 新建、Ctrl+S 保存）
2. 文件树 hover 显示操作图标（⋯）
3. 卡片 hover 动画（translateY(-1px)）
4. 跨浏览器测试（Chrome / Edge / Firefox）
5. 功能回归测试（打开/保存/搜索/模式切换/暗色切换）
6. 动画性能检查（无卡顿，≤ 200ms）

**验证标准：**
- Ctrl+K 聚焦搜索框
- 所有已有功能正常工作
- 动画流畅无卡顿
- 无控制台错误

**预计工作量：** 1 天

---

## 10. 风险与注意事项

### 10.1 Vditor CSS 变量覆盖

Vditor 的样式系统基于 CSS 变量，大部分视觉属性可通过 `.vditor` 选择器直接覆盖变量，无需修改 Vditor 源码。少数硬编码值（代码块背景、引用块竖线、表格边框、tooltip 背景、标题前缀标记颜色、链接颜色、行内代码颜色）需要 `!important` 覆盖。暗色模式同理，在 `.dark .vditor` 中重新定义变量即可。

**注意：** Vditor 的 `--second-color` 使用 rgba 格式而非 hex，覆盖时需保持相同格式。

### 10.2 字体加载性能

Inter 字体文件约 150KB（woff2），首次加载可能有 FOUT（无样式字体闪烁）。使用 `font-display: swap` 缓解。如果对性能敏感，可以只加载 400/500/600 三个字重的子集（每个约 50KB），而非完整可变字体。

**子集化方案：**
```css
/* Regular */
@font-face {
  font-family: 'Inter';
  font-weight: 400;
  src: url('inter-regular.woff2') format('woff2');
}
/* Medium */
@font-face {
  font-family: 'Inter';
  font-weight: 500;
  src: url('inter-medium.woff2') format('woff2');
}
/* Semibold */
@font-face {
  font-family: 'Inter';
  font-weight: 600;
  src: url('inter-semibold.woff2') format('woff2');
}
```

### 10.3 暗色模式下的图片

当前版本无图片资源，低优先级。如有暗色模式图片需求，使用 `filter: brightness(0.8)` 快速适配。

### 10.4 向后兼容

重构不涉及后端 API 变更，所有功能保持不变。纯前端视觉层改造。`files.js` 不需要修改。`editor.js` 只需确认 Vditor 初始化配置不受 CSS 变量影响。

### 10.5 动画性能

- 侧边栏展开/折叠使用 `max-height` 过渡在节点过多时可能有性能问题。如遇到，改为 `transform: scaleY` 或简单地使用 `display` 切换
- 模态框和 Toast 动画使用 `opacity` + `transform`，已由 GPU 加速
- 避免在 `scroll` 事件中进行 DOM 操作（当前代码已通过 rAF 节流）

### 10.6 移动端安全区域

如果部署到 iOS Safari，需考虑底部安全区域：

```css
.sidebar-footer {
  padding-bottom: max(12px, env(safe-area-inset-bottom));
}
```

### 10.7 变量命名迁移

旧变量（`--accent`, `--bg-sidebar`, `--text` 等）在重构后不再使用。确保在 `app.js` 中无直接引用旧变量名的 JS 代码（当前代码通过 CSS 变量间接引用，无此问题）。

### 10.8 图谱页颜色

当前图谱节点颜色使用硬编码 `#4a90d9` 和 `#ccc`。重构后改为 CSS 变量：

```css
.graph-node circle {
  fill: var(--c-primary);
}
.graph-node circle[d="0"] {
  fill: var(--c-border);
}
```

如需通过 JS 动态设置，在 `renderGraph` 函数中改为：

```javascript
const nodeColor = d3.select('html').classed('dark') ? '#818cf8' : '#5645d4';
```

---

## 附录 A：文件变更清单

| 文件 | Phase | 变更类型 |
|---|---|---|
| `web/app.css` | 1, 2, 3, 4, 5 | 全文重写 |
| `web/index.html` | 1, 2, 4, 5 | 添加字体引入、侧边栏 HTML 调整、欢迎页 HTML 改造、菜单按钮 |
| `web/app.js` | 2, 3, 4, 5 | 文件树渲染（SVG 图标）、保存按钮 dirty 状态、模态框动画、暗色模式、响应式 |
| `web/editor.js` | 3 | 无需修改（Vditor CSS 变量在 app.css 中覆盖） |
| `web/files.js` | — | 无需修改 |
| `web/lib/fonts/` | 1 | 新增 Inter 字体文件 |

## 附录 B：变量速查表

### 色彩 → 用途

| 变量 | 值 | 用途 |
|---|---|---|
| `--c-primary` | `#5645d4` | 主 CTA 按钮、激活态 |
| `--c-primary-hover` | `#4534b3` | 按钮按下态 |
| `--c-on-primary` | `#ffffff` | 主色上的文字 |
| `--c-bg` | `#ffffff` | 画布背景 |
| `--c-bg-sidebar` | `#f6f5f4` | 侧边栏背景 |
| `--c-bg-hover` | `#f0eeec` | 悬停背景 |
| `--c-bg-active` | `#e5e3df` | 激活/选中背景 |
| `--c-border` | `#e5e3df` | 默认边框 |
| `--c-border-strong` | `#c8c4be` | 强调边框 |
| `--c-text` | `#1a1a1a` | 主文字 |
| `--c-text-secondary` | `#787671` | 次要文字 |
| `--c-text-muted` | `#bbb8b1` | 弱化文字 |
| `--c-link` | `#0075de` | 链接颜色 |
| `--c-charcoal` | `#37352f` | Toast 背景、tooltip 背景 |
| `--c-danger` | `#e03131` | 危险操作 |
| `--c-success` | `#1aae39` | 成功状态 |
| `--c-warning` | `#dd5b00` | 警告状态 |

### 排版 → 用途

| 变量 | 值 | 用途 |
|---|---|---|
| `--f-body` | `16px` | 正文 |
| `--f-body-sm` | `14px` | 次要文本、按钮 |
| `--f-caption` | `13px` | 注释 |
| `--f-micro` | `12px` | 微小标签 |
| `--f-button` | `14px` | 按钮文字 |

### 间距 → 用途

| 变量 | 值 | 用途 |
|---|---|---|
| `--s-xs` | `8px` | 图标与文字间距 |
| `--s-sm` | `12px` | 紧凑间距 |
| `--s-md` | `16px` | 标准间距 |
| `--s-lg` | `20px` | 较大间距 |
| `--s-xl` | `24px` | section 内间距 |
| `--s-xxl` | `32px` | 卡片内边距 |
| `--s-xxxl` | `40px` | 弹窗内边距 |
| `--s-section-sm` | `48px` | section 间距 |

### 圆角 → 用途

| 变量 | 值 | 用途 |
|---|---|---|
| `--r-sm` | `6px` | 标签、小按钮 |
| `--r-md` | `8px` | 按钮、输入框 |
| `--r-lg` | `12px` | 卡片 |
| `--r-xl` | `16px` | 模态框 |
| `--r-full` | `9999px` | 徽章、pill |
