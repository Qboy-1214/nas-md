# Mermaid 图表全屏查看设计

## 目标

为 Mermaid 图表增强工具栏补充“单独全屏”能力，同时保留现有代码/图表切换、缩放、拖动、主题切换和下载功能。全屏操作只改变查看层，不修改 Markdown 内容，也不影响 Vditor Undo/Redo 快照。

## 交互决策

- 工具栏新增全屏图标按钮，进入全屏后图标和标题切换为退出全屏。
- 点击按钮时优先调用浏览器原生 Fullscreen API。
- 原生 API 不可用、调用失败或权限被拒绝时，回退到应用内全屏查看层。
- `Esc` 退出全屏；原生全屏由 `fullscreenchange` 同步状态，应用内全屏由全局键盘监听处理。
- 全屏时工具栏仍可操作，图表仍可缩放、拖动、切换主题和下载。
- 退出全屏后恢复原 overlay 位置、图表变换和当前图表/代码模式。

## 实现边界

- 只修改 Mermaid enhancer 及其必要样式，不修改 Vditor 源码。
- 原生全屏的目标是当前 Mermaid overlay item，而不是整个编辑器，避免影响侧栏和其它编辑内容。
- 应用内回退层使用现有 overlay item 的全屏 CSS 状态，避免把 Mermaid DOM 移出 Vditor，降低重渲染和 Undo 耦合风险。
- 全屏状态保存在当前 Mermaid block 的运行时状态中，不写入 Markdown 或 localStorage。
- 原生 Fullscreen API 的异常必须被捕获并触发应用内回退，不得阻断工具栏其它功能。

## 验收标准

1. 普通 Mermaid 图表显示全屏按钮，点击后进入全屏查看。
2. 支持原生 Fullscreen API 时优先使用原生全屏；失败时应用内全屏仍可用。
3. 全屏期间代码/图表切换、缩放、拖动、主题切换、SVG/PNG 下载和复制代码仍可用。
4. 点击退出按钮或按 `Esc` 后恢复普通布局。
5. 切换文件、重新渲染 Mermaid 或执行 Undo/Redo 后，不出现嵌套 Vditor block、重复图表或全屏状态泄漏。
6. 非 Mermaid 内容和 Markdown 文本不受影响。

## 验证方式

- JavaScript 语法检查。
- 浏览器 smoke test：按钮存在、原生 API 成功路径、失败回退路径、Esc 退出、现有控件回归。
- Mermaid Undo/Redo 回归：全屏前后编辑撤回仍保持源码和 SVG 正常。
