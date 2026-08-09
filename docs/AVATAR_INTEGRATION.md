# 项目头像集成清单

本项目的 GitHub 项目头像、macOS App 图标和 DMG 挂载卷图标统一来自同一个头像源。

## 文件位置

```text
assets/
├── project_avatar.webp.b64       # 固定头像源数据，CI 的单一真源
└── project_avatar.webp           # CI 自动解码并写回，供 GitHub/README 直接预览

build/
└── make_icon.py                  # 从头像源生成 macOS 全尺寸 iconset

.github/workflows/
├── build-macos-arm64.yml         # 主 Apple Silicon 编译、签名、App 打包
├── finalize-avatar-dmg.yml       # DMG 卷图标、最终 DMG 验证和 Release 覆盖
└── rebuild-on-avatar-change.yml  # 头像源变更时触发主编译

docs/
├── AVATAR_INTEGRATION.md         # 本文件
└── RELEASE_SIGNING.md            # Mac 本地重新签名与重新制作 DMG
```

## App 图标生成

主构建原有步骤会运行：

```bash
python ../build/make_icon.py icons/KCCKindle.iconset
iconutil -c icns icons/KCCKindle.iconset -o icons/comic2ebook.icns
```

`build/make_icon.py` 已改为读取：

```text
assets/project_avatar.webp.b64
```

并生成标准 macOS iconset：

```text
icon_16x16.png
icon_16x16@2x.png
icon_32x32.png
icon_32x32@2x.png
icon_128x128.png
icon_128x128@2x.png
icon_256x256.png
icon_256x256@2x.png
icon_512x512.png
icon_512x512@2x.png
```

最终由 `iconutil` 得到：

```text
comic2ebook.icns
```

PyInstaller 打包后对应：

```text
Kindle漫画转换器.app/Contents/Resources/comic2ebook.icns
```

## DMG 图标

主 App 编译、签名完成后，`finalize-avatar-dmg.yml` 下载成功构建的 App，读取：

```text
Kindle漫画转换器.app/Contents/Resources/comic2ebook.icns
```

并复制为 DMG 根目录：

```text
.VolumeIcon.icns
```

随后在可写 DMG 上设置 Finder Custom Icon 属性，再转换为最终 UDZO 压缩 DMG。

最终 CI 会重新挂载 DMG，并执行：

```bash
cmp \
  "$MOUNT/.VolumeIcon.icns" \
  "$MOUNT/Kindle漫画转换器.app/Contents/Resources/comic2ebook.icns"
```

只有两者字节完全一致才算通过。

## GitHub 项目首页头像

`finalize-avatar-dmg.yml` 会把 base64 源解码为正常的：

```text
assets/project_avatar.webp
```

并由 `github-actions[bot]` 在内容发生变化时写回 `main`。

README 使用：

```html
<img src="assets/project_avatar.webp" width="180" alt="KCC Kindle 中文版项目头像">
```

因此仓库首页、App 和 DMG 都来自同一个头像源。

## 以后替换头像

只需要更新：

```text
assets/project_avatar.webp.b64
```

`rebuild-on-avatar-change.yml` 会自动触发 Apple Silicon 主构建；主构建成功后，`finalize-avatar-dmg.yml` 会同步可预览头像并重新制作带同一卷图标的 DMG。

不要手工修改 `assets/project_avatar.webp`，它属于由源数据自动生成的可预览文件。
