<p align="center">
  <img src="assets/project_avatar.webp" width="180" alt="KCC Kindle 中文版项目头像">
</p>

<h1 align="center">KCC Kindle 中文版</h1>

<p align="center">基于 <strong>Kindle Comic Converter 11.0.1</strong> 的 Kindle 专用简体中文改造版，面向 macOS Apple Silicon。</p>

<p align="center">
  <img alt="macOS Apple Silicon" src="https://img.shields.io/badge/macOS-Apple%20Silicon-black?logo=apple">
  <a href="https://github.com/ciromattia/kcc"><img alt="KCC upstream" src="https://img.shields.io/badge/upstream-KCC%2011.0.1-2f6feb"></a>
  <a href="https://github.com/ciscoriordan/kindling"><img alt="Kindling" src="https://img.shields.io/badge/MOBI-Kindling%200.31.0-2f6feb"></a>
  <img alt="Chinese UI" src="https://img.shields.io/badge/UI-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-2f6feb">
</p>

> Kindle-only · 简体中文 · Apple Silicon 原生构建 · 内置 MOBI/AZW3 引擎

## 下载

优先从仓库 **Releases** 下载最新版：

- `KCC_11.0.1_Kindle_CN_v1.3_AppleSilicon.dmg` — 推荐安装包
- `Kindle漫画转换器.app.zip` — 独立 App
- `project_avatar.webp` — 项目头像源资源
- `SHA256SUMS.txt` — SHA-256 校验
- `BUILD-INFO.txt` — 构建信息

当前版本：**v1.3.0**

## 项目 / App / DMG 统一头像

项目采用同一张头像作为视觉标识：

- GitHub 项目首页：`assets/project_avatar.webp`
- macOS App：`Contents/Resources/comic2ebook.icns`
- DMG 挂载卷：`.VolumeIcon.icns`

CI 从 `assets/project_avatar.webp.b64` 的固定源数据生成 macOS 全尺寸 iconset，App 完成签名以后，DMG 最终化流程再直接复制 App 内的同一 `.icns` 作为卷图标，并执行二进制比较验证，防止项目头像、App 图标和 DMG 图标发生漂移。

## 主要特性

- 仅保留 Kindle 设备预设，不在产品界面显示 Kobo、reMarkable、Other。
- 移除 Ko-fi / Humble / Donate / 公告等推广入口，并关闭启动公告/推广联网线程。
- 简体中文主界面、运行提示、错误信息和元数据编辑器。
- 全新 macOS 风格界面：转换队列、Kindle 与输出、常用设置、图像优化、书籍信息、高级设置。
- Kindle 设备动态说明与输出格式提示。
- 「标准日漫」「扫描件优化」「刷新设备默认」快捷预设。
- 转换队列实时计数与更清晰的状态提示。
- 项目 / App / DMG 使用统一头像。
- 修复批量转换中“前面任务失败、最后任务成功却显示全部完成”的状态错误。
- 修复 MOBI 多进程工作线程中转换引擎启动 OSError 未捕获的问题。
- 保留 KCC 11.0.1 原有转换核心，避免为了换 UI 破坏裁边、跨页、Panel View、ComicInfo 等成熟逻辑。

## 内置 MOBI/AZW3 引擎

v1.3.0 开始，App **直接内置 Kindling v0.31.0 Apple Silicon arm64**：

```text
Kindle漫画转换器.app/Contents/Resources/tools/kindlegen
```

因此常规 MOBI/AZW3 转换不再要求：

- 安装 Kindle Previewer
- 安装旧 KindleGen
- 安装 Rosetta 2
- 手工设置 PATH

Kindling 提供 KindleGen drop-in compatibility；KCC 继续使用成熟的 EPUB → MOBI 转换流程，底层由原生 arm64 Kindling 接管。

运行时仍保留真正 Amazon KindleGen 的回退和兼容性检测。如果用户显式指定其他 KindleGen，程序会识别其架构并自动拒绝现代 macOS 无法运行的 32 位 i386 / PowerPC 文件。

### Kindling 固定版本

- Repository: `ciscoriordan/kindling`
- Version: `v0.31.0`
- Asset: `kindling-cli-mac-apple-silicon`
- License: MIT

构建时 GitHub Actions 会读取官方 Release Asset 的 SHA-256 digest，并与下载文件进行校验，再将二进制放入 App。Kindling 的 MIT License 同时打包到：

```text
Contents/Resources/licenses/KINDLING-LICENSE.txt
```

## 构建与验证

本仓库不直接复制上游 KCC 全部源码。GitHub Actions 会固定检出官方 `v11.0.1`：

```text
bd0328a12fe40ab62285d3a8ae3e501f6e41c78b
```

随后应用本仓库补丁，并在 **macOS 15 Apple Silicon / arm64** Runner 上重新编译。

自动构建流程包括：

- Python 3.11 arm64
- 源码隐私扫描：阻止本机用户目录、个人邮箱、私钥、常见 Token 和个人账号标识进入提交/构建
- Kindling v0.31.0 Release 下载、版本验证与 SHA-256 digest 校验
- Kindling `arm64` Mach-O 验证
- MOBI/AZW3 resolver 自动测试
- 实际两页测试漫画 EPUB 转换
- 实际两页测试漫画 CBZ 转换
- **实际两页测试漫画 MOBI/AZW3 转换**
- 对生成 MOBI 执行 Kindling `dump` 结构解析
- 从项目头像生成完整 macOS iconset / `.icns`
- PyInstaller 原生 App 构建
- 将 Kindling 和 MIT LICENSE 内置进 App
- 嵌套 Framework / Mach-O 签名
- `codesign --verify --deep --strict`
- 实际 Qt GUI 启动冒烟测试
- `hdiutil` 创建并验证 DMG
- DMG `.VolumeIcon.icns` 与 App `.icns` 一致性验证
- 自动生成 SHA-256

App 使用中性的 Bundle Identifier：`org.kcc.kindlecn`，不把仓库拥有者用户名写入应用元数据。

## 隐私说明

- 不在仓库中保存本机用户名、真实姓名、私人邮箱、访问令牌、API Key、SSH 私钥或用户主目录绝对路径。
- 构建发生在 GitHub 托管 Runner；构建日志中的 `/Users/runner/...` 属于临时 CI 环境，不是开发者本机路径。
- Release 构建信息仅记录版本、架构、依赖摘要、测试状态和校验值。
- `build/privacy_scan.py` 会在 CI 中持续检查常见隐私/密钥泄漏模式。

## 签名说明

当前公开构建的 App 外层使用 **ad-hoc 签名**，用于保证 App Bundle 内部签名结构完整，但不是本项目自己的 Apple Developer ID 公证版本。

首次打开时，如果 macOS 提示无法验证开发者，可在 Finder 中右键 App → **打开**。

需要自行重新签名、重新制作带项目头像的 DMG，或者使用 Developer ID + Notarization 时，见：

[`docs/RELEASE_SIGNING.md`](./docs/RELEASE_SIGNING.md)

## Release Notes

详见 [`RELEASE_NOTES_v1.3.0.md`](./RELEASE_NOTES_v1.3.0.md)。

## About 推荐内容

**Description**

> Kindle Comic Converter 11.0.1 简体中文 Kindle 专用版｜macOS Apple Silicon｜内置 Kindling MOBI/AZW3 引擎｜全新 UI

**Topics**

`kindle` `kcc` `kindle-comic-converter` `kindling` `manga` `comic` `ebook` `epub` `mobi` `azw3` `macos` `apple-silicon` `pyside6` `chinese`

## 上游与许可证

KCC upstream: [`ciromattia/kcc`](https://github.com/ciromattia/kcc) v11.0.1 — ISC License  
Kindling: [`ciscoriordan/kindling`](https://github.com/ciscoriordan/kindling) v0.31.0 — MIT License

本项目保留并随发布包分发相应许可证文本。
