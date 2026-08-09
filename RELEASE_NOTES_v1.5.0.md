# KCC Kindle 中文版 v1.5.0

本版重点升级“压缩生成文件”和漫画扫描图像处理。基于 v1.4 的像素无损压缩，进一步参考 Colortina、Novel-formatter 与 ImageOptim/OxiPNG/MozJPEG 的成熟思路。

## 智能无损压缩

- 默认改为 **智能无损**：PNG 会根据文件大小、熵、线稿倾向与像素规模决定是否比较 OxiPNG `-o4`、`-o6`、`-o max -z`。
- 新增 **快速无损 / 智能无损 / 极限无损 / 严格无损** 四种策略。
- 多个 PNG 候选全部从同一原图出发，最后按真实文件大小选择最小结果。
- 所有默认无损候选执行解码 RGBA 像素 SHA-256 复核，不一致即拒绝候选。
- JPEG 继续使用 MozJPEG 无损优化，同时自动保护 ICC、EXIF Orientation 和特殊色彩模式相关 markers。
- 不再仅相信扩展名：JPG/PNG 使用 magic bytes 判断真实格式。
- 直接选择的伪 `.jpg` / 真 PNG 会按真实 PNG 写入生成的 CBZ。

## 漫画扫描件预处理

新增独立的 **扫描件预处理** 开关，默认关闭，因为它会改变像素或页面几何，不属于无损压缩。

可选功能：

- 保守自动裁边；
- 最大 ±3° 轻微纠斜；
- 轻度 / 强力纸面与线稿增强；
- 彩色插图和高饱和区域保护。

处理采用 Pillow-only 路径，不给主 GUI 新增 OpenCV/NumPy 依赖。纸白、黑墨、强边缘和高饱和彩色区域会被保护，避免扫描“漂白”把线稿或彩页一起洗掉。

## 稳定性与容器安全

- OxiPNG 子进程支持真正取消；
- ZIP 路径穿越防护继续保留；
- 新增异常 ZIP 文件数和理论展开体积上限；
- 尽量保留 ZIP entry 时间/权限以及 archive comment；
- 已压缩媒体使用 ZIP STORE，文本/XML 使用 Deflate；
- EPUB 保证 `mimetype` 第一项且 `ZIP_STORED`；
- 默认无损模式下，已有 CBZ/ZIP/EPUB 如果最终没有变小，会保留原容器内容到新输出。

## Apple Silicon 自动验证

v1.5 在 macOS 15 arm64 CI 中实际通过：

- OxiPNG 10.1.1 arm64；
- 智能/极限 PNG 多候选；
- JPEG EXIF Orientation 保护；
- JPG/PNG 解码像素完全一致；
- 假 JPG / 真 PNG 的真实格式识别；
- CBZ archive comment；
- EPUB `mimetype` 结构；
- 显式扫描预处理；
- 智能压缩 UI 默认进入安全无损模式；
- 原 KCC EPUB / CBZ / MOBI-AZW3 转换；
- PyInstaller App、codesign、Qt GUI 启动和 DMG 打包。

## 引擎

- KCC upstream: 11.0.1
- PNG: OxiPNG 10.1.1 arm64
- JPEG: mozjpeg-lossless-optimization 1.3.2
- MOBI/AZW3: Kindling 0.31.0 arm64

当前公开构建仍为 ad-hoc 签名，首次运行若被 Gatekeeper 拦截，可在 Finder 中右键 App → 打开。
