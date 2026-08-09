# KCC Kindle 中文版

基于 **Kindle Comic Converter 11.0.1** 的 Kindle 专用简体中文改造版。

本仓库不直接复制上游 KCC 全部源码。GitHub Actions 会固定检出官方 `v11.0.1`（提交 `bd0328a12fe40ab62285d3a8ae3e501f6e41c78b`），应用本仓库补丁后，在 **macOS Apple Silicon** Runner 上重新编译。

## 改造目标

- 仅保留 Kindle 设备预设，不在界面显示 Kobo、reMarkable、Other。
- 移除 Ko-fi / Humble / Donate / 公告等推广入口，并关闭启动公告/推广联网请求。
- 简体中文界面与中文运行提示。
- 重新设计 macOS 主界面：转换队列、Kindle 与输出、常用设置、图像优化、书籍信息、高级设置。
- 保留 KCC 11.0.1 原有转换核心，避免为了换 UI 破坏裁边、跨页、Panel View、KindleGen、ComicInfo 等成熟逻辑。
- 自动构建 Apple Silicon `.app` 和 `.dmg`。

## 构建产物

GitHub Actions → **Build macOS Apple Silicon** 完成后，在该次运行的 Artifacts 下载：

- `KCC-Kindle-CN-AppleSilicon`
  - `Kindle漫画转换器.app.zip`
  - `KCC_11.0.1_Kindle_CN_AppleSilicon.dmg`

> 当前构建使用 ad-hoc 签名以保证应用包内部签名结构完整；这不是 Apple Developer ID 公证版本。

## 上游

Upstream: `ciromattia/kcc` v11.0.1

本项目保留上游许可证和版权声明。