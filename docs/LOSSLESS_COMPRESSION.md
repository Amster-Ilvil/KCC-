# 压缩生成文件

本功能独立于 KCC 原有“转换 Kindle 文件”流程，用于对已经存在的漫画图片或漫画容器做**无损体积优化**，然后生成一个新文件。

## 支持输入

- 图片文件夹 → `*_无损压缩.cbz`
- 单个 JPG/JPEG/PNG → `*_无损压缩.cbz`
- 同时选择多张 JPG/JPEG/PNG → 合并为一个 `*_无损压缩.cbz`
- CBZ/ZIP → 同格式新文件
- EPUB → 保持有效 EPUB ZIP 结构的新 EPUB

不会覆盖或删除源文件。

暂不把 CBR/RAR/7Z/PDF 纳入这个独立压缩入口；这些格式仍走 KCC 原有转换流程。

## 两种模式

### 体积优先

界面显示：

> 体积优先（像素无损，清理无关 EXIF/XMP）

目标是在不改变可见图像像素/画面的前提下尽量缩小文件。允许清理与渲染无关的图片元数据。

JPEG 如果检测到 EXIF Orientation 不是正常方向，会自动保留 JPEG markers，避免删除方向信息造成阅读时旋转。

### 严格无损

界面显示：

> 严格无损（保留图片元数据）

JPEG 保留 markers；PNG 尽量保留元数据，只重新组织无损压缩流。

这个模式通常比“体积优先”略大，但适合需要保留图片附加信息的文件。

## JPEG

使用 KCC 已有的 `mozjpeg-lossless-optimization`，底层采用 MozJPEG 的 lossless jpegtran 优化思路：

- 不重新采样；
- 不缩放；
- 不改变 JPEG quality；
- 优化 Huffman 表；
- 可将 baseline JPEG 重组为更高效的 progressive JPEG；
- 只有候选文件确实比原文件小时才替换。

因此这和 KCC 正常转换时“按设备分辨率重新编码 JPEG”是两条不同路径。

## PNG

GitHub macOS 正式构建固定使用：

- OxiPNG `v10.1.1`
- Apple Silicon `arm64`
- MIT License 随 App 打包

使用较高但仍适合桌面批量任务的 `-o 4`。

体积优先模式同时使用：

```text
--strip safe
```

不会启用 OxiPNG 的：

```text
--alpha
```

因为 `--alpha` 会修改完全透明像素的 RGB 值，官方将其明确描述为技术上的有损变换。本项目的“无损”模式不采用它。

如果本地源码开发环境没有 OxiPNG，则回退到 Pillow PNG optimize + `compress_level=9`，并在替换前逐像素验证输出与输入一致。

## CBZ / ZIP

处理流程：

```text
安全解包
→ 逐张 JPEG/PNG 无损优化
→ 已压缩图片保持 ZIP_STORED
→ XML/HTML/文本使用 DEFLATE level 9
→ 生成新容器
```

如果对已有 CBZ/ZIP/EPUB 重新封装后反而不比原文件小，程序会直接把原容器内容复制到新的输出文件，保证“压缩生成文件”不会生成一个更大的替代品。

## EPUB

EPUB 重新封装额外保证：

- `mimetype` 是 ZIP 第一项；
- `mimetype` 使用 `ZIP_STORED`；
- 内容仍为 `application/epub+zip`；
- XHTML/XML/OPF 等非图片文件不改内容；
- 图片只做无损优化。

## 安全

- 所有处理完全在本机执行，不把漫画上传到第三方压缩服务；
- ZIP 解包检查路径穿越，拒绝把文件写到临时目录之外；
- 源文件不删除、不覆盖；
- 压缩过程可取消；
- 大文件在后台 QThread 运行，不阻塞主界面事件循环。

## CI 验证

`.github/workflows/compression-feature-ci.yml` 会在 macOS Apple Silicon 上实际执行：

- OxiPNG 10.1.1 arm64 构建与版本检查；
- JPEG/PNG 压缩；
- 原图与压缩包内图片逐像素比对；
- CBZ 重新封装；
- EPUB `mimetype` 顺序/压缩方式检查；
- 多张独立图片合并 CBZ；
- 压缩 UI 模块导入检查。

## 参考思路

本功能借鉴的是成熟本地图片优化器“按格式选择专用无损引擎”的做法，例如 ImageOptim 组合多个底层优化器。Kxx.moe 的公开网页没有公开其服务端压缩算法，因此本项目没有声称复制其私有后端，而是用可审计的开源工具实现相同目标：**画面不降质、文件尽量小、处理结果可验证**。
