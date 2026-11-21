"""The "Браузер" tab: time spent on websites, by category and by site."""

from __future__ import annotations

import logging

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from app_tracker.browser import reports
from app_tracker.browser.categorizer import (
    CATEGORY_CODE,
    CATEGORY_ENTERTAINMENT,
    CATEGORY_SOCIAL,
    CATEGORY_STUDY,
)
from app_tracker.browser.extension_install import install_extension
from app_tracker.browser.storage import BrowserStorage
from app_tracker.core.database import DatabaseManager
from app_tracker.utils import format_duration

log = logging.getLogger(__name__)

REFRESH_INTERVAL_MS = 30_000

# (label, number of days)
PERIODS = [("Сегодня", 1), ("7 дней", 7), ("30 дней", 30)]

# Text colours for categories, readable on the dark theme.
_CATEGORY_COLORS = {
    CATEGORY_STUDY: QColor(124, 252, 124),
    CATEGORY_CODE: QColor(120, 190, 255),
    CATEGORY_SOCIAL: QColor(255, 124, 124),
    CATEGORY_ENTERTAINMENT: QColor(255, 190, 110),
}


class _SecondsItem(QTableWidgetItem):
    """Shows a duration as text but sorts by the number of seconds."""

    def __init__(self, seconds: int) -> None:
        super().__init__(format_duration(seconds))
        self.seconds = seconds

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, _SecondsItem):
            return self.seconds < other.seconds
        return super().__lt__(other)


class _NumberItem(QTableWidgetItem):
    def __init__(self, value: int) -> None:
        super().__init__(str(value))
        self.value = value

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, _NumberItem):
            return self.value < other.value
        return super().__lt__(other)


def _make_table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.verticalHeader().setVisible(False)
    header = table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    for col in range(1, len(headers)):
        header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
    return table


class BrowserReportWidget(QWidget):
    def __init__(self, db: DatabaseManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.db = db
        # Creating the storage also makes sure the table exists.
        self.storage = BrowserStorage(db)

        self._build_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    # --- layout -------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Период:"))
        self.period_box = QComboBox()
        for label, days in PERIODS:
            self.period_box.addItem(label, days)
        self.period_box.currentIndexChanged.connect(self.refresh)
        top.addWidget(self.period_box)
        top.addStretch(1)
        self.total_label = QLabel()
        top.addWidget(self.total_label)
        top.addStretch(1)
        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self.refresh)
        top.addWidget(refresh_btn)
        layout.addLayout(top)

        splitter = QSplitter()
        self.category_table = _make_table(["Категория", "Время", "%"])
        self.domain_table = _make_table(["Сайт", "Категория", "Время", "Визиты"])
        self.domain_table.setSortingEnabled(True)
        splitter.addWidget(self.category_table)
        splitter.addWidget(self.domain_table)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        empty_row = QHBoxLayout()
        self.empty_label = QLabel(
            "Пока нет данных. Чтобы записывать сайты, установите расширение "
            "для Firefox (кнопка «Установить расширение в Firefox» внизу)."
        )
        self.empty_label.setWordWrap(True)
        empty_row.addWidget(self.empty_label, 1)
        layout.addLayout(empty_row)

        layout.addWidget(self._build_settings_box())

    def _build_settings_box(self) -> QGroupBox:
        box = QGroupBox("Настройки отслеживания браузера")
        row = QHBoxLayout(box)

        self.enabled_box = QCheckBox("Записывать сайты")
        self.enabled_box.setChecked(self.storage.is_enabled())
        self.enabled_box.toggled.connect(self.storage.set_enabled)
        row.addWidget(self.enabled_box)

        row.addWidget(QLabel("Не записывать:"))
        self.ignored_edit = QLineEdit(", ".join(self.storage.ignored_domains()))
        self.ignored_edit.setPlaceholderText("bank.kz, mail.google.com")
        self.ignored_edit.setToolTip(
            "Сайты через запятую. Поддомены тоже не записываются."
        )
        row.addWidget(self.ignored_edit, 1)

        save_btn = QPushButton("Сохранить")
        save_btn.clicked.connect(self._save_ignored)
        row.addWidget(save_btn)

        install_btn = QPushButton("Установить расширение в Firefox")
        install_btn.clicked.connect(self._install_extension)
        row.addWidget(install_btn)
        return box

    # --- actions ------------------------------------------------------------

    def _save_ignored(self) -> None:
        domains = [d for d in self.ignored_edit.text().replace(";", ",").split(",")]
        self.storage.set_ignored_domains(domains)
        self.ignored_edit.setText(", ".join(self.storage.ignored_domains()))

    def _install_extension(self) -> None:
        ok, message = install_extension()
        if ok:
            QMessageBox.information(self, "Расширение для Firefox", message)
        else:
            QMessageBox.warning(self, "Расширение для Firefox", message)

    def refresh(self) -> None:
        try:
            self._refresh()
        except Exception:
            log.exception("Could not refresh the browser report")

    def _refresh(self) -> None:
        days = self.period_box.currentData() or 1
        start, end = reports.period_bounds(days)

        total = reports.total_seconds(self.db, start, end)
        self.total_label.setText(f"Всего в браузере: <b>{format_duration(total)}</b>")

        categories = reports.category_totals(self.db, start, end)
        self.category_table.setRowCount(len(categories))
        for row, (category, seconds) in enumerate(categories):
            share = round(100 * seconds / total) if total else 0
            items = [QTableWidgetItem(category), _SecondsItem(seconds),
                     QTableWidgetItem(f"{share}%")]
            self._color(items[0], category)
            for col, item in enumerate(items):
                self.category_table.setItem(row, col, item)

        domains = reports.domain_totals(self.db, start, end)
        self.domain_table.setSortingEnabled(False)
        self.domain_table.setRowCount(len(domains))
        for row, stat in enumerate(domains):
            items = [QTableWidgetItem(stat.domain), QTableWidgetItem(stat.category),
                     _SecondsItem(stat.seconds), _NumberItem(stat.visits)]
            self._color(items[1], stat.category)
            for col, item in enumerate(items):
                self.domain_table.setItem(row, col, item)
        self.domain_table.setSortingEnabled(True)

        self.empty_label.setVisible(not domains)

    @staticmethod
    def _color(item: QTableWidgetItem, category: str) -> None:
        color = _CATEGORY_COLORS.get(category)
        if color is not None:
            item.setForeground(QBrush(color))
