# Falcon Balanced Color Workbench V2

## 目的

这版在 V1 的中性、客观、舒适基础上，增加更丰富的状态、按钮和图标色彩。重点不是增加大面积主色，而是让不同操作和状态拥有更清晰的轻量色彩语义。

## 色彩原则

- 保持浅中性底盘，页面主体仍以灰白、蓝灰文字和中性边框为主。
- 主操作使用中等明度钴蓝，不使用深蓝。
- 信息、采集、分析、执行、人工确认分别使用浅蓝、青蓝、琥珀、柔和珊瑚、鼠尾草等轻量色。
- 成功状态使用鼠尾草绿或小面积绿色点，不使用深绿。
- 风险/暂停使用柔和珊瑚，不使用深红、大红。
- 不使用紫色。
- 所有高饱和色只用于按钮、图标、小标签和状态点，不染大面积面板。

## Image2 状态

已按 `~/.codex/image2.toml` 读取私有配置并请求 `base_url + endpoint`，没有打印或提交 API key。当前中转仍返回 `403 Forbidden error code: 1010`，因此这次保留 Image2 prompt，并生成本地 fallback mockup 供审核。

## 文件

- `image2-prompt.txt`：可在 Image2 relay 恢复后直接重跑的提示词。
- `mockup.html`：本地 HTML/CSS fallback 源文件。
- `falcon-balanced-color-workbench-v2.png`：从 `mockup.html` 渲染出的审核图。
