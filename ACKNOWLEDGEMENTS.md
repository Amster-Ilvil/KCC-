# Acknowledgements / 致谢

KCC Kindle 中文版是在 Kindle Comic Converter（KCC）基础上的简体中文 Kindle 专用改造与构建项目。感谢 KCC 多年来的原始设计、维护和社区贡献。

## Upstream / 上游

- Kindle Comic Converter — `ciromattia/kcc`.
- KCC 的主要贡献者包括 Ciro Mattia Gonano、Paweł Jastrzębski、Darodi、Alex Xu 以及其他社区贡献者。

本仓库固定基于 KCC v11.0.1，并保留其成熟的漫画转换核心，同时提供中文界面、Kindle 专用调整、Apple Silicon 构建、发布流程与本地无损压缩等改动。

## Bundled and related tools / 相关工具

- Kindling — `ciscoriordan/kindling`, used as the native Apple Silicon MOBI/AZW3 engine.
- OxiPNG — `oxipng/oxipng`, used for lossless PNG optimization.
- MozJPEG lossless optimization used through the KCC toolchain.
- PySide6 / Qt for Python and the wider Python packaging ecosystem.

感谢所有上述项目的维护者和贡献者。

## License

This repository follows the ISC License for its KCC-derived code and repository-authored modifications. Third-party tools and components retain their respective licenses; corresponding license texts should continue to be distributed with release artifacts where applicable.
