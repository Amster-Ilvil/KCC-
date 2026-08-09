# KCC Kindle 中文版 v1.3.0

基于官方 Kindle Comic Converter 11.0.1 的 Kindle 专用简体中文版本。

## 本次核心更新：真正内置 Apple Silicon MOBI/AZW3 引擎

- 内置 **Kindling v0.31.0 Apple Silicon arm64**，无需再安装 Kindle Previewer，也不依赖 Rosetta。
- Kindling 作为 KCC 的 KindleGen 兼容引擎放入：
  `Kindle漫画转换器.app/Contents/Resources/tools/kindlegen`
- 运行时会明确识别 `engine=kindling` 与真实版本 `0.31.0`，不会再把 Kindling 的版本号误拿去和 KindleGen 2.9 比较。
- 保留真实 Amazon KindleGen 回退：若用户通过环境变量或系统路径指定 KindleGen，仍可继续使用。
- 保留 32 位 i386 / PowerPC 拒绝逻辑，避免旧 KindleGen 在现代 macOS 上触发 `Bad CPU type`。

## 构建供应链

- 固定 Kindling Release：`ciscoriordan/kindling` `v0.31.0`。
- 固定资产：`kindling-cli-mac-apple-silicon`。
- CI 下载后验证 Mach-O 为 `arm64`。
- CI 读取 GitHub Release Asset 的 SHA-256 digest，并与实际下载文件逐字节校验。
- App 内同时包含 Kindling 的 MIT LICENSE。

## 真实转换回归测试

v1.3 的 macOS ARM64 CI 不只检查程序能启动，还会实际生成测试漫画并执行：

- EPUB 转换
- CBZ 转换
- MOBI/AZW3 转换（通过内置 Kindling 的 KindleGen 兼容模式）
- 对生成的 MOBI 再执行 Kindling `dump` 结构解析
- 验证 KCC/Kindling 输出日志包含 KindleGen 兼容成功状态 `:I1036:`
- Qt GUI 启动冒烟测试
- `codesign --verify --deep --strict`
- `hdiutil verify` DMG 验证

## 兼容层修复

KCC 上游会用无输入的 `kindlegen -locale en` 作为可用性探测。Kindling 的 KindleGen 兼容模式以 EPUB/OPF 为第一参数，因此 v1.3 将这一步改为由自有 resolver 负责；真正转换时仍保留 KCC 成熟的 EPUB-first KindleGen 调用流程，包括 `-dont_append_source`、`-locale` 和状态码解析。

## 其他保留改进

- Kindle-only 设备列表。
- 简体中文 macOS 风格 UI。
- 底部状态栏仅显示“Kindle 专用 · 简体中文”。
- 去除 Ko-fi / Humble / 公告等推广入口与启动联网公告请求。
- 批量转换聚合错误状态修复。
- MOBI worker OSError 防护。
- 保留 KCC 11.0.1 原有裁边、跨页、Panel View、ComicInfo 与图像处理核心。

## 许可证

KCC 上游继续遵循其 ISC License。内置 Kindling 遵循 MIT License，许可证文本随 App 一起放在 `Contents/Resources/licenses/KINDLING-LICENSE.txt`。

> 当前 App 外层仍为 ad-hoc 签名，并非 Apple Developer ID 公证版本。首次启动如被 Gatekeeper 拦截，可在 Finder 中右键应用 → 打开。
