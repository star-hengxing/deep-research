# Kami PDF 排版管线

deep-research 的 PDF 生成支持两条管线。`--engine kami`（默认）输出暖色衬线排版，`--engine typst` 回退到原有 Typst 管线。

## 参考版本

- **Kami**: [tw93/Kami](https://github.com/tw93/kami) V1.4.1 "Steadier Hand"（2026-05-05）
  - 参考 commit: `2c2b0cc` (main, 2026-05-06)，V1.4.1 后 1 commit
  - 主要参考文件：`references/design.md`（设计规范）、`CHEATSHEET.md`（组件速查）、`styles.css`（展示页样式）、`assets/templates/long-doc.html`（长文档模板）
- **借鉴内容**：颜色 token（暖色体系 + 墨蓝强调色）、字体规格（衬线层级）、间距系统（4pt 基础单元）、十条设计不变量
- **未直接使用**：Kami 的 HTML 模板文件、WeasyPrint 构建脚本、字体文件（TsangerJinKai02）。CSS 为全新编写，适配 Pandoc 输出的 HTML 结构

## 背景

原始管线（Pandoc + Typst）只有 40 行样式，输出纯白背景 + 无衬线字体，排版控制有限。受 [tw93/Kami](https://github.com/tw93/kami) 设计系统启发，我们尝试将其暖色羊皮纸美学移植到 deep-research。

第一轮尝试直接在 Typst 里实现 Kami 配色（`style-kami.typst` / `template-kami.typst`），但 Typst 的 `show heading` / `set table` 能力有限，只能改字号、字重、颜色，无法实现卡片容器、圆角、阴影等视觉组件，最终效果只是"纯白换暖黄"。

第二轮切换到 HTML + CSS + WeasyPrint 管线，拿到了 CSS 的全部排版能力：`@page` margin boxes（页眉页脚）、`target-counter`（TOC 页码）、`break-inside`（表格行不跨页断裂）、`::before` / `::after` 伪元素等。效果质变。

## 两条管线对比

| 维度 | Typst (`--engine typst`) | Kami (`--engine kami`) |
|------|--------------------------|----------------------|
| 渲染路径 | Markdown → Pandoc → Typst → PDF | Markdown → Pandoc → HTML → WeasyPrint → PDF |
| 样式文件 | `style.typst`（40 行） | `kami.css`（450+ 行）+ `template-kami.html` |
| 页面背景 | 纯白 | `#f5f4ed` 羊皮纸 |
| 字体 | Noto Sans CJK（无衬线） | Noto Serif CJK + Bitstream Charter（衬线） |
| 颜色体系 | 灰度 luma 值 | 暖色 4 级文字色 + 墨蓝强调色 |
| 封面页 | Pandoc 默认（标题居中） | 墨蓝装饰线 + 大号标题 + AUTHOR/DATE 标签 |
| 目录 | Pandoc 默认 | 带页码 + 引导虚线点 + 中文"目录"标题 |
| 表格 | 灰色斑马纹 | 蓝色表头 + 象牙交替行 + 墨蓝上边框 + 跨页表头重复 |
| 页眉页脚 | 无 | running title（右上）+ 居中页码 |
| 代码块 | 浅灰填充 | 象牙底 + 暖色边框 + 圆角 |
| 行内代码 | 无样式 | 浅蓝标签底色 |
| 链接 | 默认蓝 | 墨蓝 + 细下划线 |
| 列表标记 | 默认圆点 | 墨蓝破折号 |
| 依赖 | pandoc, typst | pandoc, weasyprint |

## 使用方式

```bash
# 默认 kami 引擎（推荐）
pixi run deep-research generate

# 指定 typst 引擎回退
pixi run deep-research generate --engine typst

# 生成 HTML（带 kami 样式）
pixi run deep-research generate --format html --engine kami
```

## 文件清单

```
templates/
├── kami.css              ← WeasyPrint 样式（Kami 设计 token 全集）
├── template-kami.html    ← Pandoc HTML 模板（封面 + nav#TOC + 正文结构）
├── style-kami.typst      ← Typst 版 Kami 样式（第一轮实验，已弃用但保留）
├── template-kami.typst   ← Typst 版完整模板（第一轮实验，已弃用但保留）
├── style.typst           ← 原始 Typst 样式（typst 引擎使用）
├── equal-cols.lua        ← Pandoc Lua 过滤器：等宽列
├── pagebreak.lua         ← Pandoc Lua 过滤器：--- → 分页符（仅 typst 管线）
└── report_template.md    ← Markdown 报告模板
```

## Kami CSS 设计 token

所有颜色和字体定义在 `kami.css` 的 `:root` 中：

```css
--parchment:   #f5f4ed;   /* 页面背景 */
--ivory:       #faf9f5;   /* 卡片/代码块底色 */
--warm-sand:   #e8e6dc;   /* 交互表面 */
--near-black:  #141413;   /* 一级文字 */
--dark-warm:   #3d3d3a;   /* 二级文字 */
--olive:       #504e49;   /* 三级文字 */
--stone:       #6b6a64;   /* 四级文字（页眉页脚） */
--brand:       #1B365D;   /* 墨蓝强调色（≤5% 面积） */
--brand-light: #2D5A8A;   /* 链接色 */
--border:      #e8e6dc;   /* 主边框 */
--border-soft: #e5e3d8;   /* 次边框 */
--tag-bg:      #E4ECF5;   /* 标签/表头底色 */

--serif: "Noto Serif CJK SC", "Bitstream Charter", Georgia, serif;
--mono:  "DejaVu Sans Mono", "Fira Code", monospace;
```

## 代码改动

### pdf.py

- 新增 `_kami_available()` 函数检测模板文件是否存在
- `generate_pdf()` 新增 `engine` 参数，默认 `"kami"`
  - `engine="kami"` → `_generate_pdf_kami()`：两步管线 Pandoc→HTML→WeasyPrint
  - `engine="typst"` → `_generate_pdf_typst()`：原始管线 Pandoc+Typst
- `generate_html()` 新增 `engine` 参数，kami 引擎时使用 `template-kami.html` + `kami.css`

### app.py

- `generate` 命令新增 `--engine / -e` 选项，默认 `"kami"`
- 引擎名称传递至 `project.generate_pdf()` / `project.generate_html()`

### project.py

- `generate_pdf()` / `generate_html()` 方法签名新增 `engine` keyword 参数

### runtime/pixi.toml

- 新增 `weasyprint` 依赖（`>=67.0,<68`）

## Windows 兼容性

### WeasyPrint GTK DLL 依赖

WeasyPrint 依赖 GTK3 DLL（`gobject-2.0-0.dll`、`pango-1.0-0.dll` 等），已由 conda 打包在 pixi 环境的 `Library/bin/` 下。WeasyPrint 的 cffi 硬编码了 Unix 风格的名称 `libgobject-2.0-0`，直接调用无法找到。**必须通过 `pixi run` 激活环境后才能正确加载**。

### `--stylesheet` 路径问题（已修复）

WeasyPrint 在 Windows 上不接受 `--stylesheet` 参数传递本地路径（URI 解析问题）。解决方案：pandoc 步骤加 `--embed-resources` 将 CSS 内嵌到 HTML 中，weasyprint 步骤不再需要 `--stylesheet`。此修复已集成到 `_generate_pdf_kami()` 中，Linux/Windows 通用。

## 已知限制

1. **字体依赖**：Kami 管线需要系统安装 `Noto Serif CJK SC` 和 `Bitstream Charter`。Linux 上通常需要 `fonts-noto-cjk` 包。
2. **WeasyPrint 不支持**：`min-height: 100vh`、`overflow-x: auto`、部分 Flexbox 特性。封面布局用绝对定位代替。
3. **TOC 页码**：依赖 WeasyPrint 的 `target-counter(attr(href), page)` CSS 函数，需要 `<nav id="TOC">` 包裹。
4. **Lua 过滤器**：`pagebreak.lua`（`---` → `#pagebreak()`）仅在 Typst 管线中生效，Kami 管线中 `---` 渲染为 `<hr>` 细线。
