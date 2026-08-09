# -*- coding: utf-8 -*-
"""Kindle-only Simplified Chinese UI layer for KCC 11.0.1.

This module deliberately keeps KCC conversion widgets/objects alive and only
re-arranges/presents them. Runtime code can continue to access the original
widget attributes without changes.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QToolButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QFormLayout, QSizePolicy, QScrollArea, QSpacerItem
)

ACCENT = "#2F6FEB"
BG = "#F5F6F8"
CARD = "#FFFFFF"
TEXT = "#1F2328"
MUTED = "#6E7781"
BORDER = "#D8DEE4"
DANGER = "#C62828"

STYLE = f"""
QMainWindow {{ background: {BG}; }}
QWidget {{ color: {TEXT}; font-size: 13px; }}
QFrame#card {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QLabel#pageTitle {{ font-size: 22px; font-weight: 700; }}
QLabel#pageSubtitle {{ color: {MUTED}; font-size: 12px; }}
QLabel#sectionTitle {{ font-size: 15px; font-weight: 700; }}
QLabel#hint {{ color: {MUTED}; font-size: 12px; }}
QPushButton {{
    min-height: 30px;
    border-radius: 8px;
    border: 1px solid {BORDER};
    background: #FFFFFF;
    padding: 2px 12px;
}}
QPushButton:hover {{ background: #F0F4F8; }}
QPushButton:pressed {{ background: #E8EEF5; }}
QPushButton#primaryButton {{
    color: white;
    background: {ACCENT};
    border: 1px solid {ACCENT};
    font-weight: 700;
    min-height: 36px;
}}
QPushButton#primaryButton:hover {{ background: #255FCB; }}
QPushButton#dangerButton {{ color: {DANGER}; }}
QLineEdit, QComboBox, QSpinBox {{
    min-height: 30px;
    border: 1px solid {BORDER};
    border-radius: 7px;
    background: white;
    padding: 0 8px;
}}
QComboBox::drop-down {{ border: 0; width: 24px; }}
QListWidget {{
    background: white;
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 5px;
}}
QProgressBar {{
    border: 1px solid {BORDER};
    border-radius: 7px;
    background: #EEF1F4;
    text-align: center;
    min-height: 24px;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 6px; }}
QCheckBox {{ spacing: 7px; min-height: 25px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; }}
QToolButton#advancedHeader {{
    background: transparent;
    border: none;
    font-weight: 700;
    text-align: left;
    padding: 2px 0;
}}
QStatusBar {{ background: #FFFFFF; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QScrollArea {{ border: none; background: transparent; }}
"""


def _card(title: str, subtitle: str | None = None):
    frame = QFrame()
    frame.setObjectName("card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(10)
    title_label = QLabel(title)
    title_label.setObjectName("sectionTitle")
    lay.addWidget(title_label)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("hint")
        sub.setWordWrap(True)
        lay.addWidget(sub)
    return frame, lay


def _labelled(label: str, widget: QWidget):
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(5)
    cap = QLabel(label)
    cap.setObjectName("hint")
    lay.addWidget(cap)
    lay.addWidget(widget)
    return box


def _safe_text(widget, text):
    if widget is not None:
        try:
            widget.setText(text)
        except Exception:
            pass


def _safe_tip(widget, text):
    if widget is not None:
        try:
            widget.setToolTip(text)
        except Exception:
            pass


def _hide(*widgets):
    for widget in widgets:
        if widget is not None:
            try:
                widget.hide()
            except Exception:
                pass


def _detach_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item and item.layout():
            _detach_layout(item.layout())


def apply_kindle_cn_ui(ui, window):
    """Rebuild the already-created KCC Qt widget tree into a Kindle-first UI."""
    window.setMinimumSize(QSize(900, 650))
    window.resize(1040, 760)
    window.setStyleSheet(STYLE)

    # Remove every item from the original generated top-level grid. Widgets are
    # not deleted; they are re-used below so existing KCC signal wiring remains valid.
    _detach_layout(ui.gridLayout)

    # Hide commercial / external promotional controls completely.
    _hide(getattr(ui, "kofiButton", None), getattr(ui, "humbleButton", None))

    # Friendly Chinese labels for reused KCC controls.
    labels = {
        "fileButton": "添加漫画文件",
        "directoryButton": "添加图片文件夹",
        "clearButton": "清空队列",
        "editorButton": "编辑漫画元数据",
        "labelSpreadsButton": "标记跨页",
        "convertButton": "开始转换",
        "mangaBox": "日漫右翻（推荐）",
        "rotateBox": "跨页处理",
        "qualityBox": "Kindle Panel View 优化",
        "upscaleBox": "适配 Kindle 分辨率",
        "croppingBox": "智能裁边",
        "autocontrastBox": "自动对比度",
        "colorBox": "保留彩色页面",
        "smartCoverCropBox": "智能封面裁切",
        "coverFillBox": "封面填满屏幕",
        "interPanelCropBox": "画格间空白裁切",
        "eraseRainbowBox": "去除扫描彩虹纹",
        "autoLevelBox": "自动黑白阶",
        "webtoonBox": "Webtoon 长条模式",
        "gammaBox": "自定义 Gamma",
        "jpegQualityBox": "自定义 JPEG 质量",
        "spreadShiftBox": "跨页起始侧偏移",
        "noRotateBox": "禁止自动旋转",
        "rotateRightBox": "跨页向右旋转",
        "rotateFirstBox": "优先旋转后拆分",
        "onePageLandscapeBox": "横屏只显示单页",
        "fileFusionBox": "合并输入文件",
        "outputSplit": "拆分大体积输出",
        "metadataTitleBox": "优先使用内嵌标题",
        "keepComicInfoBox": "保留 ComicInfo.xml",
        "defaultOutputFolderBox": "固定输出目录",
        "disableProcessingBox": "跳过图像处理",
        "legacyExtractBox": "兼容旧式解包",
        "tempDirBox": "临时目录放在源文件磁盘",
        "deleteBox": "转换后删除源文件",
        "ebokBox": "标记为电子书（EBOK）",
        "lightnovelBox": "轻小说模式",
        "invertDirectionBox": "反转阅读方向",
        "vertical4PanelBox": "四格漫画纵向 Panel View",
        "maximizeStrips": "最大化条漫分片",
        "mozJpegBox": "JPEG / PNG / mozJPEG",
        "webpBox": "WebP（实验）",
        "forcePngRgbBox": "彩页强制 PNG",
        "pngLegacyBox": "旧 Kindle PNG 兼容",
        "noQuantizeBox": "禁用颜色量化",
        "pdfWidthBox": "PDF 使用设备宽度",
        "chunkSizeCheckBox": "自定义分卷大小",
    }
    for attr, text in labels.items():
        _safe_text(getattr(ui, attr, None), text)

    # Important tooltips. Keep technical three-state behaviour understandable.
    _safe_tip(ui.mangaBox, "日文漫画通常从右向左阅读。启用后 KCC 会按日漫阅读顺序生成 Kindle 页面。")
    _safe_tip(ui.rotateBox, "三态选项：未选=拆分跨页；半选=拆分并额外保留旋转页；已选=只旋转跨页。")
    _safe_tip(ui.croppingBox, "三态选项：未选=关闭；半选=裁白边；已选=裁白边并尝试移除页码。")
    _safe_tip(ui.qualityBox, "为支持的 Kindle 优化虚拟面板/Panel View。")
    _safe_tip(ui.upscaleBox, "按所选 Kindle 的目标分辨率缩放页面，避免设备端再次缩放。")
    _safe_tip(ui.deleteBox, "危险：转换成功后删除源文件。默认保持关闭。")
    _safe_tip(ui.smartCoverCropBox, "宽图作为封面时，尝试自动取出主要封面区域。")
    _safe_tip(ui.coverFillBox, "先按 Kindle 屏幕比例中心裁切，再把封面缩放到目标分辨率。")

    # Header
    shell = QWidget(ui.centralWidget)
    outer = QVBoxLayout(shell)
    outer.setContentsMargins(18, 16, 18, 12)
    outer.setSpacing(14)

    header = QHBoxLayout()
    title_box = QVBoxLayout()
    title = QLabel("Kindle 漫画转换器")
    title.setObjectName("pageTitle")
    subtitle = QLabel("KCC 11.0.1 中文专用版 · Kindle-only · 本地处理")
    subtitle.setObjectName("pageSubtitle")
    title_box.addWidget(title)
    title_box.addWidget(subtitle)
    header.addLayout(title_box)
    header.addStretch(1)
    badge = QLabel("KINDLE")
    badge.setStyleSheet(f"color:{ACCENT}; background:#EAF2FF; border-radius:10px; padding:5px 10px; font-weight:700;")
    header.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
    outer.addLayout(header)

    # Main two-column body.
    body = QHBoxLayout()
    body.setSpacing(14)
    outer.addLayout(body, 1)

    # Left: queue and source tools.
    left_card, left = _card("转换队列", "支持图片文件夹、PDF、CBZ/ZIP/CBR/7z 等 KCC 原有输入格式。可直接拖放。")
    left_card.setMinimumWidth(390)
    ui.jobList.setMinimumHeight(330)
    left.addWidget(ui.jobList, 1)

    row = QHBoxLayout()
    ui.fileButton.setIconSize(QSize(16,16))
    ui.directoryButton.setIconSize(QSize(16,16))
    row.addWidget(ui.fileButton)
    row.addWidget(ui.directoryButton)
    row.addWidget(ui.clearButton)
    left.addLayout(row)

    tool_row = QHBoxLayout()
    tool_row.addWidget(ui.editorButton)
    tool_row.addWidget(ui.labelSpreadsButton)
    left.addLayout(tool_row)
    body.addWidget(left_card, 4)

    # Right: scrollable Kindle settings.
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    right_host = QWidget()
    right = QVBoxLayout(right_host)
    right.setContentsMargins(0, 0, 4, 0)
    right.setSpacing(12)
    scroll.setWidget(right_host)
    body.addWidget(scroll, 6)

    # Kindle / output card
    device_card, device_lay = _card("Kindle 与输出", "设备列表只保留 Kindle。推荐按实际设备选择预设。")
    device_grid = QGridLayout()
    device_grid.setHorizontalSpacing(10)
    device_grid.addWidget(_labelled("Kindle 设备", ui.deviceBox), 0, 0)
    device_grid.addWidget(_labelled("输出格式", ui.formatBox), 0, 1)
    device_lay.addLayout(device_grid)
    ui.deviceHintLabel = QLabel("选择 Kindle 后会自动套用分辨率、Panel View 和默认图像策略。")
    ui.deviceHintLabel.setObjectName("hint")
    ui.deviceHintLabel.setWordWrap(True)
    device_lay.addWidget(ui.deviceHintLabel)
    right.addWidget(device_card)

    # Common settings card
    common_card, common = _card("常用设置")
    common_grid = QGridLayout()
    common_grid.setVerticalSpacing(7)
    common_grid.addWidget(ui.mangaBox, 0, 0)
    common_grid.addWidget(ui.rotateBox, 0, 1)
    common_grid.addWidget(ui.croppingBox, 1, 0)
    common_grid.addWidget(ui.qualityBox, 1, 1)
    common_grid.addWidget(ui.upscaleBox, 2, 0)
    common_grid.addWidget(ui.colorBox, 2, 1)
    common_grid.addWidget(ui.autocontrastBox, 3, 0)
    common_grid.addWidget(ui.smartCoverCropBox, 3, 1)
    common.addLayout(common_grid)
    right.addWidget(common_card)

    # Image optimization card
    image_card, image_lay = _card("图像优化", "这些选项直接复用 KCC 11.0.1 原有图像处理核心。")
    image_grid = QGridLayout()
    image_grid.addWidget(ui.coverFillBox, 0, 0)
    image_grid.addWidget(ui.interPanelCropBox, 0, 1)
    image_grid.addWidget(ui.eraseRainbowBox, 1, 0)
    image_grid.addWidget(ui.autoLevelBox, 1, 1)
    image_grid.addWidget(ui.gammaBox, 2, 0)
    image_grid.addWidget(ui.jpegQualityBox, 2, 1)
    image_lay.addLayout(image_grid)
    image_lay.addWidget(ui.croppingWidget)
    image_lay.addWidget(ui.gammaWidget)
    image_lay.addWidget(ui.jpegQualityWidget)
    right.addWidget(image_card)

    # Book metadata/output card
    meta_card, meta = _card("书籍信息与输出")
    meta_grid = QGridLayout()
    ui.titleEdit.setPlaceholderText("例如：漫画标题 第1卷")
    ui.authorEdit.setPlaceholderText("作者")
    ui.languageEdit.setPlaceholderText("语言，例如 ja / zh-CN")
    meta_grid.addWidget(_labelled("标题", ui.titleEdit), 0, 0)
    meta_grid.addWidget(_labelled("作者", ui.authorEdit), 0, 1)
    meta_grid.addWidget(_labelled("EPUB 语言", ui.languageEdit), 1, 0)
    meta_grid.addWidget(ui.metadataTitleBox, 1, 1)
    meta.addLayout(meta_grid)
    meta.addWidget(ui.outputFolderWidget)
    right.addWidget(meta_card)

    # Advanced collapsible card. Move low-frequency KCC controls here.
    advanced_card, advanced = _card("高级设置")
    adv_header = QToolButton()
    adv_header.setObjectName("advancedHeader")
    adv_header.setText("显示高级选项")
    adv_header.setCheckable(True)
    adv_header.setChecked(False)
    adv_header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    adv_header.setArrowType(Qt.ArrowType.RightArrow)
    advanced.insertWidget(1, adv_header)

    adv_body = QWidget()
    adv_grid = QGridLayout(adv_body)
    adv_grid.setContentsMargins(0, 0, 0, 0)
    adv_grid.setVerticalSpacing(6)
    adv_controls = [
        ui.webtoonBox, ui.lightnovelBox, ui.ebokBox, ui.invertDirectionBox,
        ui.vertical4PanelBox, ui.spreadShiftBox, ui.noRotateBox, ui.rotateRightBox,
        ui.rotateFirstBox, ui.onePageLandscapeBox, ui.maximizeStrips, ui.fileFusionBox,
        ui.outputSplit, ui.keepComicInfoBox, ui.mozJpegBox, ui.webpBox,
        ui.forcePngRgbBox, ui.pngLegacyBox, ui.noQuantizeBox, ui.pdfWidthBox,
        ui.chunkSizeCheckBox, ui.disableProcessingBox, ui.legacyExtractBox,
        ui.tempDirBox, ui.deleteBox,
    ]
    for i, w in enumerate(adv_controls):
        adv_grid.addWidget(w, i // 2, i % 2)
    adv_grid.addWidget(ui.chunkSizeWidget, (len(adv_controls)+1)//2, 0, 1, 2)
    adv_grid.addWidget(ui.customWidget, (len(adv_controls)+3)//2, 0, 1, 2)
    adv_body.hide()
    advanced.addWidget(adv_body)

    def toggle_advanced(checked: bool):
        adv_body.setVisible(checked)
        adv_header.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        adv_header.setText("隐藏高级选项" if checked else "显示高级选项")
    adv_header.toggled.connect(toggle_advanced)
    right.addWidget(advanced_card)
    right.addStretch(1)

    # Bottom action/status region. Repurpose toolWidget because upstream code
    # hides/shows it while progress is active.
    toolbar = QWidget(shell)
    bar = QHBoxLayout(toolbar)
    bar.setContentsMargins(0, 0, 0, 0)
    status = QLabel("准备就绪")
    status.setObjectName("hint")
    bar.addWidget(status)
    bar.addStretch(1)
    ui.convertButton.setObjectName("primaryButton")
    ui.convertButton.setMinimumWidth(170)
    bar.addWidget(ui.convertButton)
    outer.addWidget(toolbar)
    ui.toolWidget = toolbar

    ui.progressBar.setMinimumHeight(30)
    outer.addWidget(ui.progressBar)
    ui.progressBar.hide()

    # Safety styling for destructive option.
    ui.deleteBox.setStyleSheet(f"QCheckBox {{ color: {DANGER}; font-weight: 600; }}")

    # Add shell to the generated centralWidget's retained grid layout.
    ui.gridLayout.addWidget(shell, 0, 0, 1, 2)
    ui.gridLayout.setContentsMargins(0, 0, 0, 0)


def apply_meta_editor_cn(editor, dialog):
    """Translate the visible metadata editor without touching metadata keys."""
    dialog.setWindowTitle("漫画元数据编辑器")
    mapping = {
        "okButton": "保存",
        "cancelButton": "取消",
        "bulkVolumeCheck": "批量递增卷号",
    }
    for attr, text in mapping.items():
        _safe_text(getattr(editor, attr, None), text)
    placeholders = {
        "seriesLine": "系列",
        "volumeLine": "卷号",
        "numberLine": "期号",
        "titleLine": "标题",
        "writerLine": "作者",
        "pencillerLine": "线稿",
        "inkerLine": "勾线",
        "coloristLine": "上色",
    }
    for attr, text in placeholders.items():
        w = getattr(editor, attr, None)
        if w is not None:
            try:
                w.setPlaceholderText(text)
            except Exception:
                pass


_RUNTIME_TRANSLATIONS = [
    ("No files selected! Please choose files to convert.", "未选择文件，请先添加要转换的漫画。"),
    ("Target resolution is not set!", "尚未设置目标分辨率。"),
    ("The process will be interrupted. Please wait.", "正在中止当前转换，请稍候。"),
    ("Unsupported file type for ", "不支持的文件类型："),
    ("Install KindleGen (link)", "安装 KindleGen"),
    ("to enable MOBI conversion for Kindles!", "后才能生成 Kindle MOBI/AZW3。"),
    ("Processing", "正在处理"),
    ("Successfully updated", "已成功更新"),
    ("files.", "个文件。"),
    ("Errors occurred.", "处理过程中出现错误。"),
    ("Failed to save metadata!", "保存元数据失败！"),
]


def translate_runtime_message(message):
    if not isinstance(message, str):
        return message
    out = message
    for old, new in _RUNTIME_TRANSLATIONS:
        out = out.replace(old, new)
    return out
