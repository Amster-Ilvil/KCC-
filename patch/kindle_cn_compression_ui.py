# -*- coding: utf-8 -*-
"""Focused UI for KCC Kindle CN's adaptive compression workflow."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QVBoxLayout,
)

from .kindle_cn_compress import CompressionCancelled, compress_sources, summarize_results
from .kindle_cn_scan_processing import ScanProcessOptions


class CompressionWorker(QThread):
    progressChanged = Signal(int, int, str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        sources,
        output_dir,
        *,
        strip_metadata=True,
        strategy="smart",
        verify_pixels=True,
        scan_options=None,
        parent=None,
    ):
        super().__init__(parent)
        self.sources = list(sources)
        self.output_dir = output_dir
        self.strip_metadata = bool(strip_metadata)
        self.strategy = str(strategy)
        self.verify_pixels = bool(verify_pixels)
        self.scan_options = scan_options
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def _cancelled(self):
        return self._cancel_requested

    def _progress(self, done, total, label):
        self.progressChanged.emit(int(done), int(total), str(label))

    def run(self):
        try:
            results = compress_sources(
                self.sources,
                self.output_dir,
                strip_metadata=self.strip_metadata,
                strategy=self.strategy,
                verify_pixels=self.verify_pixels,
                scan_options=self.scan_options,
                progress_cb=self._progress,
                cancel_cb=self._cancelled,
            )
            if self._cancel_requested:
                self.cancelled.emit()
            else:
                self.completed.emit(results)
        except CompressionCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class CompressionOptionsDialog(QDialog):
    """Compact options panel; safe pixel-lossless mode is always the default."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("压缩生成文件")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        title = QLabel("智能压缩")
        title.setStyleSheet("font-size:18px; font-weight:700;")
        subtitle = QLabel(
            "默认只进行像素无损优化。程序会按真实图片格式选择优化器，比较多个候选，"
            "只有更小且逐像素校验通过的结果才会替换临时副本。"
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#6E7781;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        self.strategyBox = QComboBox()
        self.strategyBox.addItem("智能无损（推荐）", ("smart", True))
        self.strategyBox.addItem("快速无损", ("standard", True))
        self.strategyBox.addItem("极限无损（更慢）", ("maximum", True))
        self.strategyBox.addItem("严格无损（保留图片元数据）", ("smart", False))
        self.strategyBox.setToolTip(
            "智能无损会按图片特征选择 OxiPNG 候选；极限模式会尝试更多高强度候选。"
        )
        form.addRow("压缩策略：", self.strategyBox)

        self.verifyBox = QCheckBox("逐像素复核压缩结果")
        self.verifyBox.setChecked(True)
        self.verifyBox.setEnabled(False)
        self.verifyBox.setToolTip("正式压缩固定启用安全复核，防止优化器异常改变画面。")
        form.addRow("安全校验：", self.verifyBox)
        layout.addLayout(form)

        self.scanGroup = QGroupBox("扫描件预处理（可选）")
        self.scanGroup.setCheckable(True)
        self.scanGroup.setChecked(False)
        scan_layout = QVBoxLayout(self.scanGroup)
        warning = QLabel(
            "此功能会改变像素/页面几何，不属于无损压缩。仅在扫描页存在灰底、轻微歪斜或明显空白边时启用。"
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color:#A15C00; font-weight:600;")
        scan_layout.addWidget(warning)

        scan_form = QFormLayout()
        self.autoCropBox = QCheckBox("置信度足够时自动裁除外部空白")
        self.autoCropBox.setChecked(True)
        self.deskewBox = QCheckBox("自动纠正轻微歪斜（最大 ±3°）")
        self.deskewBox.setChecked(True)
        self.preserveColorBox = QCheckBox("保护彩色插图和高饱和区域")
        self.preserveColorBox.setChecked(True)
        self.enhancementBox = QComboBox()
        self.enhancementBox.addItem("轻度纸面/线稿增强（推荐）", "soft")
        self.enhancementBox.addItem("强力纸面/线稿增强", "strong")
        self.enhancementBox.addItem("只裁边/纠斜，不做漂白增强", "none")
        scan_form.addRow("裁边：", self.autoCropBox)
        scan_form.addRow("纠斜：", self.deskewBox)
        scan_form.addRow("图像增强：", self.enhancementBox)
        scan_form.addRow("彩色保护：", self.preserveColorBox)
        scan_layout.addLayout(scan_form)
        layout.addWidget(self.scanGroup)

        foot = QLabel(
            "JPG/JPEG：MozJPEG 无损优化 · PNG：OxiPNG 多候选择小 · "
            "CBZ/ZIP/EPUB：安全解包后逐图优化并重新封装"
        )
        foot.setWordWrap(True)
        foot.setStyleSheet("color:#6E7781; font-size:12px;")
        layout.addWidget(foot)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.startButton = buttons.addButton("开始生成", QDialogButtonBox.ButtonRole.AcceptRole)
        self.startButton.setDefault(True)
        self.startButton.setStyleSheet("padding:7px 18px; font-weight:700;")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        strategy, strip_metadata = self.strategyBox.currentData()
        scan = ScanProcessOptions(
            enabled=self.scanGroup.isChecked(),
            auto_crop=self.autoCropBox.isChecked(),
            deskew=self.deskewBox.isChecked(),
            enhancement=self.enhancementBox.currentData(),
            preserve_color=self.preserveColorBox.isChecked(),
            crop_margin_percent=0.8,
            max_deskew_degrees=3.0,
        ).normalized()
        return {
            "strategy": strategy,
            "strip_metadata": bool(strip_metadata),
            "verify_pixels": True,
            "scan_options": scan,
        }


def _queued_paths(job_list):
    paths = []
    seen = set()
    for index in range(job_list.count()):
        item = job_list.item(index)
        if item is None or job_list.itemWidget(item) is not None:
            continue
        text = item.text().strip()
        if not text:
            continue
        path = Path(text).expanduser()
        if not path.exists():
            continue
        key = os.path.normcase(os.path.abspath(os.fspath(path)))
        if key not in seen:
            seen.add(key)
            paths.append(os.fspath(path))
    return paths


def _choose_sources(window, ui):
    queued = _queued_paths(ui.jobList)
    if queued:
        return queued

    chooser = QMessageBox(window)
    chooser.setWindowTitle("压缩生成文件")
    chooser.setIcon(QMessageBox.Icon.Information)
    chooser.setText("当前转换队列为空")
    chooser.setInformativeText("选择图片/漫画文件，或选择一个图片文件夹。")
    files_button = chooser.addButton("选择文件", QMessageBox.ButtonRole.AcceptRole)
    folder_button = chooser.addButton("选择文件夹", QMessageBox.ButtonRole.ActionRole)
    chooser.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    chooser.exec()
    clicked = chooser.clickedButton()
    start_dir = getattr(ui, "lastPath", "") or str(Path.home())
    if clicked is files_button:
        files, _ = QFileDialog.getOpenFileNames(
            window,
            "选择要处理的文件",
            start_dir,
            "支持的文件 (*.cbz *.zip *.epub *.jpg *.jpeg *.png);;所有文件 (*.*)",
        )
        return files
    if clicked is folder_button:
        folder = QFileDialog.getExistingDirectory(window, "选择图片文件夹", start_dir)
        return [folder] if folder else []
    return []


def install_compression_ui(ui, window):
    """Replace the v1.4 two-choice action with the adaptive v1.5 panel."""
    button = getattr(ui, "losslessCompressButton", None)
    if button is None:
        return

    button.setText("智能压缩生成")
    button.setToolTip(
        "多候选无损压缩并自动选择最小结果；也可显式开启扫描件裁边/纠斜/纸面增强。"
    )
    try:
        button.clicked.disconnect()
    except (RuntimeError, TypeError):
        pass

    def start():
        worker = getattr(ui, "_smartCompressionWorker", None)
        if worker is not None and worker.isRunning():
            QMessageBox.information(window, "智能压缩", "已有压缩任务正在运行。")
            return

        sources = _choose_sources(window, ui)
        if not sources:
            return

        dialog = CompressionOptionsDialog(window)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        options = dialog.values()

        if options["scan_options"].enabled:
            confirm = QMessageBox.warning(
                window,
                "确认扫描件预处理",
                "扫描件预处理会改变图像像素或页面几何。源文件不会被覆盖，但生成文件不再属于“像素无损”。\n\n继续吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

        suggested = getattr(ui, "targetDirectory", "") or getattr(ui, "lastPath", "") or str(Path.home())
        output_dir = QFileDialog.getExistingDirectory(window, "选择输出目录", suggested)
        if not output_dir:
            return

        progress = QProgressDialog("正在分析图片并准备优化…", "取消", 0, 0, window)
        progress.setWindowTitle("智能压缩生成")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()

        worker = CompressionWorker(
            sources,
            output_dir,
            strip_metadata=options["strip_metadata"],
            strategy=options["strategy"],
            verify_pixels=options["verify_pixels"],
            scan_options=options["scan_options"],
            parent=window,
        )
        ui._smartCompressionWorker = worker
        ui._smartCompressionProgress = progress
        button.setEnabled(False)
        window.statusBar().showMessage("正在智能分析、验证并生成压缩文件…")

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
            button.setEnabled(True)
            ui._smartCompressionWorker = None
            ui._smartCompressionProgress = None

        def completed(results):
            cleanup()
            window.statusBar().showMessage("智能压缩完成", 5000)
            QMessageBox.information(window, "处理完成", summarize_results(results))

        def failed(message):
            cleanup()
            window.statusBar().showMessage("智能压缩失败", 5000)
            QMessageBox.critical(window, "处理失败", message)

        def cancelled():
            cleanup()
            window.statusBar().showMessage("已取消智能压缩", 3500)

        progress.canceled.connect(worker.request_cancel)
        worker.progressChanged.connect(update_progress)
        worker.completed.connect(completed)
        worker.failed.connect(failed)
        worker.cancelled.connect(cancelled)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    button.clicked.connect(start)
