# macOS 重新签名与 DMG 发布

本文用于 `Kindle漫画转换器.app` 的本地重新签名和 DMG 重新制作。项目头像、App 图标和 DMG 卷图标统一使用 App 内的：

```text
Kindle漫画转换器.app/Contents/Resources/comic2ebook.icns
```

> 不要把 Apple ID、App 专用密码、证书私钥或 notarytool 凭据提交到 Git。

## 1. Ad-hoc 重新签名

适用于自己使用、测试或没有 Apple Developer ID 的情况。

```bash
APP="/完整路径/Kindle漫画转换器.app"

xattr -cr "$APP" || true

# 先签所有 Mach-O 文件，包括内置 Kindling。
while IFS= read -r -d '' f; do
  if /usr/bin/file "$f" | grep -q 'Mach-O'; then
    /usr/bin/codesign --force --sign - --timestamp=none "$f"
  fi
done < <(find "$APP/Contents" -type f -print0)

# 再从最深层开始签 Framework bundle。
while IFS= read -r bundle; do
  [ -n "$bundle" ] && /usr/bin/codesign --force --sign - --timestamp=none "$bundle"
done < <(
  find "$APP/Contents" -type d -name '*.framework' -print \
    | awk '{ print length, $0 }' \
    | sort -rn \
    | cut -d' ' -f2-
)

# 最后签 App 外层。
/usr/bin/codesign --force --sign - --timestamp=none "$APP"

# 严格验证。
/usr/bin/codesign --verify --deep --strict --verbose=2 "$APP"
/usr/bin/codesign --verify --strict --verbose=2 \
  "$APP/Contents/Resources/tools/kindlegen"
```

验证主程序架构：

```bash
/usr/bin/file "$APP/Contents/MacOS/Kindle Comic Converter"
```

Apple Silicon 版应包含：

```text
Mach-O 64-bit executable arm64
```

## 2. 用同一头像重新制作 DMG

下面命令会同时保证：

- DMG 内的 App 使用项目头像；
- 挂载后的 DMG 卷使用同一 `.VolumeIcon.icns`；
- DMG 中带有拖到 `Applications` 的快捷方式。

```bash
APP="/完整路径/Kindle漫画转换器.app"
OUT="$HOME/Desktop/KCC_11.0.1_Kindle_CN_v1.3_AppleSilicon.dmg"
STAGE="$(mktemp -d)"

cleanup() {
  rm -rf "$STAGE"
}
trap cleanup EXIT

# 复制已签名 App。
ditto "$APP" "$STAGE/Kindle漫画转换器.app"

# Finder 的 Applications 快捷方式。
ln -s /Applications "$STAGE/Applications"

# DMG 卷头像与 App 使用完全相同的 icns。
cp "$APP/Contents/Resources/comic2ebook.icns" "$STAGE/.VolumeIcon.icns"

# 给卷目录设置 Custom Icon 属性。SetFile 属于 Xcode Command Line Tools；
# 没有 SetFile 时仍会保留 .VolumeIcon.icns，只是 Finder 可能显示默认卷图标。
if command -v SetFile >/dev/null 2>&1; then
  SetFile -a C "$STAGE"
elif [ -x /usr/bin/SetFile ]; then
  /usr/bin/SetFile -a C "$STAGE"
fi

rm -f "$OUT"
hdiutil create \
  -volname "Kindle漫画转换器" \
  -srcfolder "$STAGE" \
  -ov \
  -format UDZO \
  "$OUT"

hdiutil verify "$OUT"
echo "完成：$OUT"
```

### 验证 DMG 中确实包含头像

```bash
DMG="$HOME/Desktop/KCC_11.0.1_Kindle_CN_v1.3_AppleSilicon.dmg"
MOUNT="$(mktemp -d)"

hdiutil attach -readonly -nobrowse -mountpoint "$MOUNT" "$DMG"

ls -lh "$MOUNT/.VolumeIcon.icns"
ls -lh "$MOUNT/Kindle漫画转换器.app/Contents/Resources/comic2ebook.icns"

cmp \
  "$MOUNT/.VolumeIcon.icns" \
  "$MOUNT/Kindle漫画转换器.app/Contents/Resources/comic2ebook.icns"

hdiutil detach "$MOUNT"
rmdir "$MOUNT"
```

`cmp` 没有输出并返回 0，表示 DMG 卷图标和 App 图标是同一个文件内容。

## 3. Developer ID 正式签名（可选）

如果有 Apple Developer Program 的 `Developer ID Application` 证书，建议使用正式签名而不是 ad-hoc。

先查看可用身份：

```bash
security find-identity -v -p codesigning
```

设置证书名称：

```bash
IDENTITY="Developer ID Application: YOUR NAME (TEAMID)"
APP="/完整路径/Kindle漫画转换器.app"
```

然后按与 ad-hoc 相同的顺序签名，只把签名命令替换为：

```bash
/usr/bin/codesign \
  --force \
  --options runtime \
  --timestamp \
  --sign "$IDENTITY" \
  "目标文件或Bundle"
```

所有嵌套 Mach-O、Framework 签完以后，再签 App 外层：

```bash
/usr/bin/codesign \
  --force \
  --options runtime \
  --timestamp \
  --sign "$IDENTITY" \
  "$APP"

/usr/bin/codesign --verify --deep --strict --verbose=2 "$APP"
spctl --assess --type execute --verbose=4 "$APP"
```

随后按第 2 节重新创建 DMG，并给 DMG 本身签名：

```bash
DMG="$HOME/Desktop/KCC_11.0.1_Kindle_CN_v1.3_AppleSilicon.dmg"

/usr/bin/codesign \
  --force \
  --timestamp \
  --sign "$IDENTITY" \
  "$DMG"
```

## 4. Apple Notarization（可选）

只需在自己的 Mac Keychain 中保存一次公证凭据：

```bash
xcrun notarytool store-credentials "KCC_NOTARY" \
  --apple-id "YOUR_APPLE_ID" \
  --team-id "YOUR_TEAM_ID" \
  --password "YOUR_APP_SPECIFIC_PASSWORD"
```

不要把上述真实值写进仓库。

提交并等待公证：

```bash
DMG="$HOME/Desktop/KCC_11.0.1_Kindle_CN_v1.3_AppleSilicon.dmg"

xcrun notarytool submit "$DMG" \
  --keychain-profile "KCC_NOTARY" \
  --wait

xcrun stapler staple "$DMG"
xcrun stapler validate "$DMG"
spctl --assess --type open --context context:primary-signature --verbose=4 "$DMG"
```

## 5. 发布前最低检查

```bash
APP="/完整路径/Kindle漫画转换器.app"
DMG="$HOME/Desktop/KCC_11.0.1_Kindle_CN_v1.3_AppleSilicon.dmg"

/usr/bin/codesign --verify --deep --strict --verbose=2 "$APP"
/usr/bin/file "$APP/Contents/MacOS/Kindle Comic Converter"
"$APP/Contents/Resources/tools/kindlegen" --version
hdiutil verify "$DMG"
shasum -a 256 "$DMG"
```

当前项目 CI 仍默认使用 ad-hoc 签名；Developer ID 与公证凭据不存储在仓库中。
