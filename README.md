# KCC Kindle 中文版

基于 **Kindle Comic Converter 11.0.1** 的 Kindle 专用简体中文改造版，面向 macOS Apple Silicon。

[![macOS Apple Silicon](https://img.shields.io/badge/macOS-Apple%20Silicon-black?logo=apple)](https://github.com/Amster-Ilvil/KCC-/actions)
[![KCC upstream](https://img.shields.io/badge/upstream-KCC%2011.0.1-2f6feb)](https://github.com/ciromattia/kcc)
[![Chinese UI](https://img.shields.io/badge/UI-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-2f6feb)](https://github.com/Amster-Ilvil/KCC-)

> Kindle-only · 简体中文 · Apple Silicon 原生构建

## 下载

优先从仓库 **Releases** 下载最新版：

- `KCC_11.0.1_Kindle_CN_v1.2_AppleSilicon.dmg` — 推荐安装包
- `Kindle漫画转换器.app.zip` — 独立 App
- `SHA256SUMS.txt` — SHA-256 校验
- `BUILD-INFO.txt` — 构建信息

当前版本：**v1.2.0**

## 主要特性

- 仅保留 Kindle 设备预设，不在产品界面显示 Kobo、reMarkable、Other。
- 移除 Ko-fi / Humble / Donate / 公告等推广入口，并关闭启动公告/推广联网线程。
- 简体中文主界面、运行提示、错误信息和元数据编辑器。
- 全新 macOS 风格界面：转换队列、Kindle 与输出、常用设置、图像优化、书籍信息、高级设置。
- Kindle 设备动态说明与输出格式提示。
- 「标准日漫」「扫描件优化」「刷新设备默认」快捷预设。
- 转换队列实时计数与更清晰的状态提示。
- Kindle 中文版专用 App 图标。
- KindleGen 运行时解析：优先查找 App 内置路径，再回退 Kindle Previewer 3、用户工具目录和系统 PATH。
- KindleGen 架构自检：自动拒绝现代 macOS 无法运行的 32 位 i386 / PowerPC 版本，避免 MOBI/AZW3 转换线程异常退出。
- 修复批量转换中“前面任务失败、最后任务成功却显示全部完成”的状态错误。
- 修复 MOBI 多进程工作线程中 KindleGen 启动 OSError 未捕获的问题。
- 保留 KCC 11.0.1 原有转换核心，避免为了换 UI 破坏裁边、跨页、Panel View、ComicInfo 等成熟逻辑。

## KindleGen 说明

v1.2.0 已支持真正的 **App 内置 KindleGen 路径**：

`Kindle漫画转换器.app/Contents/Resources/tools/kindlegen`

如果该位置存在可在现代 macOS 执行的 `arm64` 或 `x86_64` KindleGen，程序会优先自动使用。

本项目当前**没有把旧版 KindleGen 2.9 Mac 二进制放入公开 Release**。经检查，该老版本实际转换程序是 32 位 `i386` Mach-O，外层启动器为 `i386/PowerPC`；现代 macOS 已停止支持 32 位 Mac 应用，Apple Silicon 的 Rosetta 2 也不能运行 32 位 Intel 程序。因此原样内置只会让 MOBI/AZW3 转换失败。

如果安装了 Kindle Previewer 3，程序仍会自动检测：

`/Applications/Kindle Previewer 3.app/Contents/lib/fc/bin/kindlegen`

## 构建与验证

本仓库不直接复制上游 KCC 全部源码。GitHub Actions 会固定检出官方 `v11.0.1`：

`bd0328a12fe40ab62285d3a8ae3e501f6e41c78b`

随后应用本仓库补丁，并在 **macOS 15 Apple Silicon / arm64** Runner 上重新编译。

自动构建流程包括：

- Python 3.11 arm64
- KindleGen resolver 自动测试
- 实际两页测试漫画 EPUB 转换
- 实际两页测试漫画 CBZ 转换
- PyInstaller 原生 App 构建
- macOS `.icns` 图标生成
- 嵌套 Framework / Mach-O 签名
- `codesign --verify --deep --strict`
- 实际 Qt GUI 启动冒烟测试
- `hdiutil` 创建并验证 DMG
- 自动生成 SHA-256

## 签名说明

当前公开构建使用 **ad-hoc 签名**，用于保证 App Bundle 内部签名结构完整，但不是 Apple Developer ID 公证版本。

首次打开时，如果 macOS 提示无法验证开发者，可在 Finder 中右键 App → **打开**。

## Release Notes

详见 [`RELEASE_NOTES_v1.2.0.md`](./RELEASE_NOTES_v1.2.0.md)。

## About 推荐内容

**Description**

> Kindle Comic Converter 11.0.1 简体中文 Kindle 专用版｜macOS Apple Silicon｜全新 UI｜KindleGen 兼容检测

**Topics**

`kindle` `kcc` `kindle-comic-converter` `manga` `comic` `ebook` `epub` `mobi` `macos` `apple-silicon` `pyside6` `chinese`

## 上游与许可证

Upstream: [`ciromattia/kcc`](https://github.com/ciromattia/kcc) v11.0.1

本项目保留上游许可证和版权声明。