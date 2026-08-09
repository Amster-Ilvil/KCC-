# -*- coding: utf-8 -*-
"""Second-stage UX enhancements for the Kindle-only KCC UI.

Kept separate from the base layout so the upstream KCC controller stays easy to
rebase and audit.
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSystemTrayIcon,
)

from .kindle_cn_compress import CompressionCancelled, compress_sources, summarize_results

ACCENT = "#2F6FEB"
MUTED = "#6E7781"
_TRAY_PATCHED = False


class _CompressionWorker(QThread):
    progressChanged = Signal(int, int, str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, sources, output_dir, strip_metadata, parent=None):
        super().__init__(parent)
        self.sources = list(sources)
        self.output_dir = output_dir
        self.strip_metadata = bool(strip_metadata)
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def _is_cancelled(self):
        return self._cancel_requested

    def _progress(self, done, total, label):
        self.progressChanged.emit(int(done), int(total), str(label))

    def run(self):
        try:
            result = compress_sources(
                self.sources,
                self.output_dir,
                strip_metadata=self.strip_metadata,
                progress_cb=self._progress,
                cancel_cb=self._is_cancelled,
            )
            if self._cancel_requested:
                self.cancelled.emit()
            else:
                self.completed.emit(result)
        except CompressionCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


def _set_check(widget, state):
    if widget is not None and widget.isEnabled():
        widget.setCheckState(state)


def _source_count(job_list):
    return len(_queued_source_paths(job_list))


def _queued_source_paths(job_list):
    paths = []
    seen = set()
    for i in range(job_list.count()):
        item = job_list.item(i)
        if item is None or job_list.itemWidget(item) is not None:
            continue
        text = item.text().strip()
        if not text:
            continue
        path = Path(text).expanduser()
        if not path.exists():
            continue
        key = os.path.normcase(os.path.abspath(os.fspath(path)))
        if key in seen:
            continue
        seen.add(key)
        paths.append(os.fspath(path))
    return paths


def _install_safe_tray_show():
    """Avoid meaningless tray warnings on offscreen/headless Qt platforms."""
    global _TRAY_PATCHED
    if _TRAY_PATCHED:
        return
    original_show = QSystemTrayIcon.show

    def safe_show(tray):
        if tray.isSystemTrayAvailable() and not tray.icon().isNull():
            return original_show(tray)
        return None

    QSystemTrayIcon.show = safe_show
    _TRAY_PATCHED = True


def _select_compression_sources(window, ui):
    queued = _queued_source_paths(ui.jobList)
    if queued:
        return queued

    chooser = QMessageBox(window)
    chooser.setWindowTitle("压缩生成文件")
    chooser.setIcon(QMessageBox.Icon.Information)
    chooser.setText("当前转换队列为空。请选择要无损压缩的来源。")
    chooser.setInformativeText("支持 JPG/JPEG/PNG、CBZ/ZIP/EPUB 和图片文件夹。")
    files_button = chooser.addButton("选择文件", QMessageBox.ButtonRole.AcceptRole)
    folder_button = chooser.addButton("选择文件夹", QMessageBox.ButtonRole.ActionRole)
    chooser.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    chooser.exec()
    clicked = chooser.clickedButton()

    start_dir = getattr(ui, "lastPath", "") or str(Path.home())
    if clicked is files_button:
        files, _ = QFileDialog.getOpenFileNames(
            window,
            "选择要无损压缩的文件",
            start_dir,
            "支持的文件 (*.cbz *.zip *.epub *.jpg *.jpeg *.png);;所有文件 (*.*)",
        )
        return files
    if clicked is folder_button:
        folder = QFileDialog.getExistingDirectory(window, "选择图片文件夹", start_dir)
        return [folder] if folder else []
    return []


def install_enhancements(ui, window):
    """Add queue statistics, device guidance, presets and lossless compression."""
    try:
        window.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
    except Exception:
        pass
    _install_safe_tray_show()

    # --- Queue summary -----------------------------------------------------
    queue_parent = ui.jobList.parentWidget()
    queue_layout = queue_parent.layout() if queue_parent else None
    ui.queueSummaryLabel = QLabel("尚未添加任务")
    ui.queueSummaryLabel.setStyleSheet(f"color:{MUTED}; font-size:12px;")
    if queue_layout is not None:
        queue_layout.insertWidget(2, ui.queueSummaryLabel)

    def update_queue_summary():
        count = _source_count(ui.jobList)
        if count == 0:
            ui.queueSummaryLabel.setText("尚未添加任务 · 可直接拖放漫画文件或图片文件夹")
        else:
            ui.queueSummaryLabel.setText(f"已加入 {count} 个转换任务")

    def schedule_queue_update(*_):
        QTimer.singleShot(0, update_queue_summary)
        QTimer.singleShot(40, update_queue_summary)

    model = ui.jobList.model()
    model.rowsInserted.connect(schedule_queue_update)
    model.rowsRemoved.connect(schedule_queue_update)
    model.modelReset.connect(schedule_queue_update)
    QTimer.singleShot(0, update_queue_summary)

    # --- Device / format guidance -----------------------------------------
    def device_text(name: str) -> str:
        if "Colorsoft" in name:
            return "彩色 Kindle：建议保留彩色页面；设备预设会自动启用对应彩色策略。"
        if "Scribe" in name:
            return "Kindle Scribe：大屏阅读优先保留高分辨率；PDF 适合部分扫描漫画，常规漫画也可使用 EPUB/MOBI。"
        if "Paperwhite 12" in name:
            return "Paperwhite 12：推荐保持“适配 Kindle 分辨率”和 Panel View 优化。"
        if "Paperwhite 11" in name:
            return "Paperwhite 11：推荐保持设备缩放与 Panel View 优化，日漫建议启用右翻。"
        if "Oasis" in name:
            return "Kindle Oasis：推荐使用设备预设缩放；跨页可按阅读习惯选择拆分或旋转。"
        if "Voyage" in name:
            return "Kindle Voyage：建议使用设备预设分辨率并启用智能裁边。"
        if name:
            return "已使用 Kindle 专用预设；建议先保持默认参数，仅按漫画类型调整右翻、裁边和跨页。"
        return "选择 Kindle 后会自动套用分辨率、Panel View 和默认图像策略。"

    def format_text(name: str) -> str:
        if "MOBI/AZW3" in name:
            return "MOBI/AZW3 使用 App 内置 Kindling 引擎生成，适合 USB 侧载。"
        if "Send to Kindle" in name and "EPUB" in name:
            return "EPUB（Send to Kindle）适合通过 Amazon 的 Send to Kindle 流程发送。"
        if name.startswith("PDF"):
            return "PDF 更适合 Scribe 或希望保留页面外观的扫描资料。"
        if name.startswith("KFX"):
            return "KFX 流程用于 Kindle 专用输出；保持 KCC 默认图像优化设置更稳。"
        if name.startswith("CBZ"):
            return "CBZ 主要用于兼容旧工作流或第三方阅读器，不是新款 Kindle 的首选。"
        return ""

    ui.formatHintLabel = QLabel("")
    ui.formatHintLabel.setWordWrap(True)
    ui.formatHintLabel.setStyleSheet(f"color:{MUTED}; font-size:12px;")
    device_parent = ui.deviceHintLabel.parentWidget()
    if device_parent and device_parent.layout():
        device_parent.layout().addWidget(ui.formatHintLabel)

    def refresh_device_hint(*_):
        ui.deviceHintLabel.setText(device_text(ui.deviceBox.currentText()))
        ui.formatHintLabel.setText(format_text(ui.formatBox.currentText()))

    ui.deviceBox.currentTextChanged.connect(refresh_device_hint)
    ui.formatBox.currentTextChanged.connect(refresh_device_hint)
    QTimer.singleShot(0, refresh_device_hint)

    # --- Quick presets -----------------------------------------------------
    preset_row = QHBoxLayout()
    preset_row.setSpacing(8)

    standard_btn = QPushButton("标准日漫")
    scan_btn = QPushButton("扫描件优化")
    device_btn = QPushButton("刷新设备默认")
    compress_btn = QPushButton("压缩生成文件")
    ui.losslessCompressButton = compress_btn

    standard_btn.setToolTip("应用保守的日漫推荐设置，不启用删除源文件等危险选项。")
    scan_btn.setToolTip("加强白边/页码裁切与黑白阶处理，适合扫描漫画。")
    device_btn.setToolTip("重新应用当前 Kindle 设备的 KCC 原生默认格式、缩放和彩色策略。")
    compress_btn.setToolTip(
        "独立无损压缩：JPEG 使用 MozJPEG 无损优化，PNG 优先使用 OxiPNG；"
        "支持文件夹、JPG/PNG、CBZ/ZIP/EPUB，生成新文件且不覆盖源文件。"
    )
    compress_btn.setStyleSheet(
        "QPushButton { padding: 7px 12px; font-weight: 600; }"
        f"QPushButton:hover {{ color: {ACCENT}; }}"
    )

    def standard_preset():
        _set_check(ui.mangaBox, Qt.CheckState.Checked)
        _set_check(ui.croppingBox, Qt.CheckState.PartiallyChecked)
        _set_check(ui.smartCoverCropBox, Qt.CheckState.Checked)
        if ui.qualityBox.isEnabled():
            _set_check(ui.qualityBox, Qt.CheckState.Checked)
        if ui.upscaleBox.isEnabled():
            _set_check(ui.upscaleBox, Qt.CheckState.Checked)
        _set_check(ui.deleteBox, Qt.CheckState.Unchecked)
        window.statusBar().showMessage("已应用“标准日漫”推荐设置", 3500)

    def scan_preset():
        _set_check(ui.mangaBox, Qt.CheckState.Checked)
        _set_check(ui.croppingBox, Qt.CheckState.Checked)
        _set_check(ui.autoLevelBox, Qt.CheckState.Checked)
        _set_check(ui.autocontrastBox, Qt.CheckState.Unchecked)
        _set_check(ui.smartCoverCropBox, Qt.CheckState.Checked)
        _set_check(ui.deleteBox, Qt.CheckState.Unchecked)
        window.statusBar().showMessage("已应用“扫描件优化”设置", 3500)

    def device_defaults():
        try:
            ui.changeDevice()
            window.statusBar().showMessage("已刷新当前 Kindle 设备默认设置", 3500)
        except Exception as exc:
            window.statusBar().showMessage(f"刷新设备设置失败：{exc}", 5000)

    def start_lossless_compression():
        current = getattr(ui, "_compressionWorker", None)
        if current is not None and current.isRunning():
            QMessageBox.information(window, "压缩生成文件", "已有压缩任务正在运行。")
            return

        sources = _select_compression_sources(window, ui)
        if not sources:
            return

        mode_items = [
            "体积优先（像素无损，清理无关 EXIF/XMP）",
            "严格无损（保留图片元数据）",
        ]
        mode, ok = QInputDialog.getItem(
            window,
            "压缩模式",
            "选择压缩策略：",
            mode_items,
            0,
            False,
        )
        if not ok:
            return
        strip_metadata = mode == mode_items[0]

        suggested = getattr(ui, "targetDirectory", "") or getattr(ui, "lastPath", "") or str(Path.home())
        output_dir = QFileDialog.getExistingDirectory(window, "选择压缩文件输出目录", suggested)
        if not output_dir:
            return

        progress = QProgressDialog("正在准备无损压缩…", "取消", 0, 0, window)
        progress.setWindowTitle("压缩生成文件")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        progress.show()

        worker = _CompressionWorker(sources, output_dir, strip_metadata, window)
        ui._compressionWorker = worker
        ui._compressionProgress = progress
        compress_btn.setEnabled(False)
        window.statusBar().showMessage("正在无损压缩并生成新文件…")

        def update_progress(done, total, label):
            progress.setLabelText(label)
            if total > 0:
                if progress.maximum() != total:
                    progress.setRange(0, total)
                progress.setValue(min(done, total))
            else:
                progress.setRange(0, 0)

        def cleanup():
            progress.close()
            compress_btn.setEnabled(True)
            ui._compressionWorker = None
            ui._compressionProgress = None

        def completed(results):
            cleanup()
            window.statusBar().showMessage("无损压缩完成", 5000)
            QMessageBox.information(window, "压缩完成", summarize_results(results))

        def failed(message):
            cleanup()
            window.statusBar().showMessage("压缩失败", 5000)
            QMessageBox.critical(window, "压缩失败", message)

        def cancelled():
            cleanup()
            window.statusBar().showMessage("已取消压缩", 3500)

        progress.canceled.connect(worker.request_cancel)
        worker.progressChanged.connect(update_progress)
        worker.completed.connect(completed)
        worker.failed.connect(failed)
        worker.cancelled.connect(cancelled)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    standard_btn.clicked.connect(standard_preset)
    scan_btn.clicked.connect(scan_preset)
    device_btn.clicked.connect(device_defaults)
    compress_btn.clicked.connect(start_lossless_compression)
    preset_row.addWidget(standard_btn)
    preset_row.addWidget(scan_btn)
    preset_row.addWidget(device_btn)
    preset_row.addWidget(compress_btn)

    if device_parent and device_parent.layout():
        device_parent.layout().addLayout(preset_row)


def enhance_meta_editor(editor, dialog):
    """Finish translating generated labels/tooltips in the metadata editor."""
    labels = {
        "label_1": "系列：",
        "label_2": "卷号：",
        "label_8": "标题：",
        "label_3": "编号：",
        "label_4": "作者：",
        "label_5": "线稿：",
        "label_6": "勾线：",
        "label_7": "上色：",
    }
    for attr, text in labels.items():
        widget = getattr(editor, attr, None)
        if widget is not None:
            widget.setText(text)

    editor.bulkVolumeCheck.setText("批量卷号")
    editor.bulkVolumeCheck.setToolTip(
        "批量修改卷号：输入 5 表示从 5 开始递增；输入 1-10 表示范围；"
        "输入 1, 3, 5 表示指定值。分配前会按文件名排序。"
    )
    dialog.setMinimumWidth(470)


_MORE_TRANSLATIONS = (
    ("The new version is available!", "有新版本可用。"),
    ("Your KindleGen is outdated!", "当前 KindleGen 版本较旧。"),
    ("MOBI conversion might fail.", "MOBI/AZW3 转换可能失败。"),
    ("Install 7z", "安装 7z"),
    ("to enable CBZ/CBR/ZIP/etc processing.", "后可处理 CBZ/CBR/ZIP 等压缩格式。"),
    ("CBR files in selection are read-only.", "所选 CBR 文件为只读，无法写入元数据。"),
    ("Editing", "正在编辑"),
    ("files", "个文件"),
    ("Some files failed to save:", "部分文件保存失败："),
    ("field must be a number.", "字段必须为数字。"),
    ("Conversion completed", "转换完成"),
    ("Conversion failed", "转换失败"),
    ("Processing images", "正在处理图像"),
    ("Creating EPUB", "正在创建 EPUB"),
    ("Creating MOBI", "正在创建 MOBI/AZW3"),
)


def translate_more(message):
    if not isinstance(message, str):
        return message
    out = message
    for old, new in _MORE_TRANSLATIONS:
        out = out.replace(old, new)
    return out
