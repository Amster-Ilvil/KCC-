# KCC Kindle 中文版 v1.2.0

基于官方 Kindle Comic Converter 11.0.1 的 Kindle 专用简体中文版本。

## 本次更新

- 删除底部状态栏“无广告/推广”字样，仅保留“Kindle 专用 · 简体中文”。
- 新增 KindleGen 运行时解析层：App 内置路径优先，其次 Kindle Previewer 3、用户工具目录和系统 PATH。
- 新增 KindleGen 架构检查，阻止现代 macOS 误调用 32 位 i386/PowerPC 版本导致转换线程崩溃。
- MOBI/AZW3 在 KindleGen 缺失或不兼容时改为明确中文提示，不再把可选组件问题当成应用启动错误。
- 修复批量转换状态错误：前面的任务失败、最后一个任务成功时，不再错误显示“全部任务完成”。
- 修复 MOBI 多进程工作线程中 KindleGen 启动 OSError 未被捕获的问题。
- 继续保留 KCC 11.0.1 原有图像处理、裁边、跨页、Panel View、ComicInfo 与 Kindle 输出核心。

## 关于旧版 Mac KindleGen

用户提供的 KindleGen 2.9 Mac 包经检查，其中实际转换程序为 32 位 i386 Mach-O，外层启动器为 i386/PowerPC。现代 macOS 已停止运行 32 位 Mac 应用，Apple Silicon 的 Rosetta 2 也只支持 64 位 Intel 应用，因此该文件无法作为 Apple Silicon 版 KCC 的可运行内置组件。

v1.2.0 已把“兼容的内置 KindleGen”接口做好：若后续提供可在现代 macOS 执行的 x86_64 或 arm64 KindleGen，可放入 App `Contents/Resources/tools/kindlegen`，程序会优先自动识别使用。

## 构建

- macOS Apple Silicon arm64
- PyInstaller 原生构建
- ad-hoc codesign + strict verify
- Qt GUI 启动冒烟测试
- DMG `hdiutil verify`

> 当前并非 Apple Developer ID 公证版本，首次启动可能需要在 Finder 中右键应用 → 打开。
