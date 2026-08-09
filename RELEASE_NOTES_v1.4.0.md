# KCC Kindle 中文版 v1.4.0

基于官方 Kindle Comic Converter 11.0.1 的 Kindle 专用简体中文版本。

## 新增：压缩生成文件

主界面新增 **“压缩生成文件”**，用于在不走 Kindle 分辨率重采样的情况下，对现有漫画图片和漫画容器做本地无损体积优化，再生成一个新的文件。

支持：

- 图片文件夹 → CBZ
- JPG / JPEG / PNG → CBZ
- 多张独立图片 → 单个 CBZ
- CBZ / ZIP → 同格式优化副本
- EPUB → 保持 EPUB 规范的优化副本

### 压缩模式

- **体积优先（像素无损）**：允许清理不影响渲染的 EXIF/XMP 等元数据。
- **严格无损**：保留 JPEG 图片 markers/元数据，优先保证附加信息完整。

### JPEG

使用 KCC 已有 `mozjpeg-lossless-optimization` / MozJPEG lossless jpegtran 路径，只优化 JPEG 熵编码、Huffman 表和 progressive 结构，不改变 JPEG quality、不缩放、不重新采样。

### PNG

正式 Apple Silicon App 内置 **OxiPNG 10.1.1 arm64**。使用无损优化和 `--strip safe`；明确不使用 OxiPNG 官方说明为技术上有损的 `--alpha`。

如果开发环境没有 OxiPNG，仍有 Pillow PNG optimize 后备，并在采用候选结果前验证像素一致性。

### 容器安全与兼容

- 源文件不覆盖、不删除。
- ZIP 解包带路径穿越保护。
- 已有 CBZ/ZIP/EPUB 如果优化后反而更大，自动保留原容器内容到新的输出文件。
- EPUB 保证 `mimetype` 第一项并保持 `ZIP_STORED`。
- 压缩在独立 QThread 中执行，支持取消，不阻塞主界面。

## Apple Silicon 回归验证

专项 CI 在 macOS 15 arm64 上实际完成：

- OxiPNG 10.1.1 从官方 crate 固定构建；
- OxiPNG Mach-O 架构验证为 arm64；
- JPEG 与 PNG 实际压缩；
- 输出图片与原图逐像素比对；
- CBZ 解包/优化/重新封装；
- EPUB `mimetype` 顺序和存储方式验证；
- 多张图片合并 CBZ；
- 压缩 UI 模块导入；
- 原 KCC EPUB / CBZ / MOBI/AZW3 回归测试；
- Kindling v0.31.0 实际 MOBI 生成；
- PyInstaller App 构建；
- App 深度 codesign 验证；
- Qt GUI 启动冒烟测试；
- DMG 创建与验证。

专项压力样本由一张未优化 JPEG 和一张 `compress_level=0` PNG 构成，原始图片合计 4,447,036 字节，生成 CBZ 为 68,749 字节，2/2 图片均实际变小且逐像素一致。该数字用于验证压缩链路，并不代表普通漫画都能获得相同比例。

## 继续保留

- Kindle-only 设备预设
- 简体中文 UI
- 无启动广告/推广联网
- 内置 Kindling v0.31.0 Apple Silicon MOBI/AZW3 引擎
- 统一项目/App/DMG 头像
- 标准日漫、扫描件优化、刷新设备默认快捷设置
- 批量转换错误状态修复
