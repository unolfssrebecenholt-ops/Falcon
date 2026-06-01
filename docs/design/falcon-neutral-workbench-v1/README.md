# Falcon Neutral Workbench V1

## 目的

这份参考用于评审 Falcon 控制台的新视觉方向：降低当前界面的青绿/薄荷色占比，改成更中性、客观、舒适、耐看的本地生产工具界面。

## 设计方向

- 背景使用接近中性的浅灰白，不再用大面积青绿渐变。
- 侧栏使用浅中性灰，当前项用低饱和冷蓝提示。
- 主操作使用冷钴蓝，待处理状态使用少量琥珀色，成功状态只保留很小的绿色点。
- 组件以 1px 中性边框、6-8px 圆角和紧凑密度为主，避免玻璃感、大投影、装饰光斑和营销页式大标题。
- 页面应像可信赖的工作台，而不是品牌落地页或后台模板。

## Image2 状态

已按 `~/.codex/image2.toml` 读取私有配置并请求 `base_url + endpoint`，没有打印或提交 API key。当前中转返回 `403 Forbidden error code: 1010`，因此这次保留 Image2 prompt，并生成本地 fallback mockup 供审核。

## 文件

- `image2-prompt.txt`：可在 Image2 relay 恢复后直接重跑的提示词。
- `mockup.html`：本地 HTML/CSS fallback 源文件。
- `falcon-neutral-workbench-v1.png`：从 `mockup.html` 渲染出的审核图。
