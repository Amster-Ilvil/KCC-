# KCC Kindle 中文版 v1.1.0

基于官方 **Kindle Comic Converter 11.0.1** 的 Kindle 专用简体中文版本。

## 主要变化

- 仅保留 Kindle 设备预设，移除 Kobo / reMarkable / Other 产品入口。
- 移除 Ko-fi、Humble、Donate、公告等推广入口，并关闭启动更新/公告联网线程。
- 简体中文主界面、提示、错误信息与元数据编辑器。
- 全新 macOS 风格界面：转换队列、Kindle 与输出、常用设置、图像优化、书籍信息、高级设置。
- 新增 Kindle 设备动态说明与输出格式提示。
- 新增「标准日漫」「扫描件优化」「刷新设备默认」快捷预设。
- 新增转换队列实时计数与更清晰的状态提示。
- 新增 Kindle 中文版 App 图标。
- 保留 KCC 11.0.1 原有转换核心：裁边、跨页、Panel View、ComicInfo、KindleGen、图像处理等。

## macOS 构建

- 原生架构：Apple Silicon `arm64`
- 构建环境：GitHub macOS 15 ARM Runner
- Python：3.11 arm64
- 签名：ad-hoc
- 已通过：`codesign --verify --deep --strict`
- 已通过：真实 Qt GUI 启动冒烟测试
- 已通过：DMG `hdiutil verify`

## 下载文件

Release Assets 中提供：

- `KCC_11.0.1_Kindle_CN_v1.1_AppleSilicon.dmg` — 推荐安装包
- `Kindle漫画转换器.app.zip` — 独立 App 压缩包
- `SHA256SUMS.txt` — SHA-256 校验值
- `BUILD-INFO.txt` — 构建信息

## 注意

当前版本使用 ad-hoc 签名，不是 Apple Developer ID 公证版本。首次打开时 macOS 可能提示无法验证开发者，可在 Finder 中右键 App →「打开」。

## 上游

Upstream: `ciromattia/kcc` v11.0.1  
固定提交：`bd0328a12fe40ab62285d3a8ae3e501f6e41c78b`

本项目保留上游许可证与版权声明。