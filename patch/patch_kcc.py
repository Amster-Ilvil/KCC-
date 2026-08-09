#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch official KCC v11.0.1 into the Kindle-only Simplified Chinese edition."""
from __future__ import annotations
import re, shutil, sys
from pathlib import Path

EXPECTED_COMMIT = "bd0328a12fe40ab62285d3a8ae3e501f6e41c78b"

def fail(msg): raise SystemExit(f"[错误] {msg}")
def one(text, old, new, label):
    n=text.count(old)
    if n != 1: fail(f"补丁定位失败：{label}（期望 1 处，实际 {n} 处）")
    return text.replace(old,new,1)

def patch_gui(path: Path):
    text=path.read_text(encoding="utf-8")
    if "apply_kindle_cn_ui" in text:
        print("[跳过] KCC_gui.py 已修改"); return
    shutil.copy2(path, path.with_suffix(path.suffix+".official.bak"))
    text=one(text,"from . import KCC_ui_editor\n","from . import KCC_ui_editor\nfrom .kindle_cn_ui import apply_kindle_cn_ui, apply_meta_editor_cn, translate_runtime_message\n","导入中文 UI")

    p=re.compile(r"(class VersionThread\(QThread\):.*?\n    def run\(self\):\n)(.*?)(\n    def setAnswer\(self, dialoganswer\):)",re.S)
    m=p.search(text)
    if not m: fail("无法定位 VersionThread.run")
    text=text[:m.start()]+m.group(1)+"        # Kindle 中文版：启动时不检查更新，不请求公告/推广。\n        return\n"+m.group(3)+text[m.end():]

    text=one(text,"        self.setupUi(MW)\n        self.editor = KCCGUI_MetaEditor()\n","        self.setupUi(MW)\n        apply_kindle_cn_ui(self, MW)\n        self.editor = KCCGUI_MetaEditor()\n","主界面入口")
    text=one(text,"        self.settings = QSettings('ciromattia', 'kcc10')\n","        self.settings = QSettings('KCC-Kindle-CN', 'kcc11-kindle-only')\n","独立设置")

    a=text.find("        self.formats = {"); b=text.find("        self.profiles = {",a)
    if a<0 or b<0: fail("无法定位输出格式块")
    formats='''        self.formats = {  # Kindle-only; keep upstream indexes 0..3 compatible
            "MOBI/AZW3": {'icon': 'MOBI', 'format': 'MOBI'},
            "EPUB（Send to Kindle）": {'icon': 'EPUB', 'format': 'EPUB'},
            "CBZ（旧 Kindle / KOReader）": {'icon': 'CBZ', 'format': 'CBZ'},
            "PDF（Kindle Scribe）": {'icon': 'EPUB', 'format': 'PDF'},
            "KFX（Send to Kindle）": {'icon': 'KFX', 'format': 'KFX'},
        }\n\n'''
    text=text[:a]+formats+text[b:]

    marker="        profilesGUI = [\n"; pos=text.find(marker)
    if pos<0: fail("无法定位 profilesGUI")
    text=text[:pos]+"        # 产品界面和运行配置均只保留 Kindle。\n        self.profiles = {n: d for n, d in self.profiles.items() if n.startswith('Kindle')}\n\n"+text[pos:]
    a=text.find("        profilesGUI = ["); b=text.find("        link_dict = {",a)
    if a<0 or b<0: fail("无法定位设备列表/推广链接")
    profiles='''        profilesGUI = [
            "Kindle Scribe Colorsoft", "Kindle Scribe 3", "Kindle Colorsoft",
            "Kindle Paperwhite 12", "Kindle Scribe 1/2", "Kindle Paperwhite 11",
            "Kindle 11", "Kindle Oasis 9/10", "Separator",
            "Kindle 1324x1986", "Kindle 1920x1920", "Kindle 1860x1920", "Kindle 1240x1860",
            "Kindle 8/10", "Kindle Oasis 8", "Kindle Paperwhite 7/10", "Kindle Voyage",
            "Kindle Paperwhite 5/6", "Kindle 4/5/7", "Kindle Touch", "Kindle Keyboard",
            "Kindle DX", "Kindle 2", "Kindle 1",
        ]\n\n'''
    text=text[:a]+profiles+text[b:]

    a=text.find("        link_dict = {"); b=text.find("        self.tar = TAR in available_archive_tools()",a)
    if a<0 or b<0: fail("无法定位推广块")
    clean='''        statusBarLabel = QLabel("Kindle 专用 · 简体中文 · 无广告/推广")
        statusBarLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        GUI.statusBar.addPermanentWidget(statusBarLabel, 1)
        self.addMessage('<b>提示：</b>可拖入漫画文件、压缩包、PDF 或图片文件夹。', 'info')
        self.addMessage('<b>提示：</b>高级选项默认收起，常用 Kindle 参数已集中显示。', 'info')

'''
    text=text[:a]+clean+text[b:]
    text=text.replace("        GUI.kofiButton.clicked.connect(self.openKofi)\n","")
    text=text.replace("        GUI.humbleButton.clicked.connect(self.openHumble)\n","")
    text=one(text,"        self.versionCheck.start()\n","        # Kindle 中文版：不启动联网检查线程。\n","禁用联网线程")
    text=one(text,'        MW.setWindowTitle("Kindle Comic Converter " + __version__)\n','        MW.setWindowTitle("Kindle 漫画转换器 " + __version__ + " 中文版")\n',"窗口标题")

    text=one(text,"    def addMessage(self, message, icon, replace=False):\n        if icon != '':\n","    def addMessage(self, message, icon, replace=False):\n        message = translate_runtime_message(message)\n        if icon != '':\n","消息翻译")
    text=one(text,"    def showDialog(self, message, kind):\n        if kind == 'error':\n            QMessageBox.critical(MW, 'KCC - Error', message, QMessageBox.StandardButton.Ok)\n","    def showDialog(self, message, kind):\n        message = translate_runtime_message(message)\n        if kind == 'error':\n            QMessageBox.critical(MW, 'KCC - 错误', message, QMessageBox.StandardButton.Ok)\n","对话框翻译")
    text=text.replace("QMessageBox.question(MW, 'KCC - Question', message,","QMessageBox.question(MW, 'KCC - 确认', message,")
    text=text.replace("GUI.croppingPowerLabel.setText('Cropping Power: ' + str(value))","GUI.croppingPowerLabel.setText('裁边强度：' + str(value))")
    text=text.replace("GUI.gammaLabel.setText('Gamma: Auto')","GUI.gammaLabel.setText('Gamma：自动')")
    text=text.replace("GUI.gammaLabel.setText('Gamma: ' + str(value))","GUI.gammaLabel.setText('Gamma：' + str(value))")

    hook="        self.setupUi(self.ui)\n        self.ui.setWindowFlags"
    if hook in text:
        text=text.replace(hook,"        self.setupUi(self.ui)\n        apply_meta_editor_cn(self, self.ui)\n        self.ui.setWindowFlags",1)
    else:
        fail("无法定位元数据编辑器 setupUi")

    path.write_text(text,encoding="utf-8")
    print("[完成] KCC_gui.py")

def patch_setup(path: Path):
    text=path.read_text(encoding="utf-8")
    if "Kindle-only Simplified Chinese edition" in text: return
    shutil.copy2(path,path.with_suffix(path.suffix+".official.bak"))
    text=text.replace("description='Comic and Manga converter for e-book readers.',","description='Kindle-only Simplified Chinese edition based on KCC 11.0.1.',")
    text=text.replace("keywords=['kindle', 'kobo', 'comic', 'manga', 'mobi', 'epub', 'cbz'],","keywords=['kindle', 'comic', 'manga', 'mobi', 'azw3', 'epub'],")
    path.write_text(text,encoding="utf-8")

def main():
    if len(sys.argv)!=2: fail("用法：patch_kcc.py /path/to/kcc-v11.0.1")
    root=Path(sys.argv[1]).expanduser().resolve(); gui=root/"kindlecomicconverter/KCC_gui.py"; setup=root/"setup.py"
    src=Path(__file__).with_name("kindle_cn_ui.py"); dst=root/"kindlecomicconverter/kindle_cn_ui.py"
    if not gui.is_file() or not setup.is_file(): fail("目标不是完整 KCC v11.0.1 源码目录")
    if not src.is_file(): fail("缺少 kindle_cn_ui.py")
    shutil.copy2(src,dst); patch_gui(gui); patch_setup(setup)
    print("[完成] KCC 11.0.1 Kindle 中文专用补丁已应用")
if __name__=="__main__": main()
