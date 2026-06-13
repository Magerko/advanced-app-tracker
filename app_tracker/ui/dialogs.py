"""Modal dialogs: limit editor, password change, settings and history."""

from __future__ import annotations

import logging
import sys
from typing import Dict, Optional

from PyQt6.QtCore import Qt, QDate, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QIcon
from PyQt6.QtWidgets import (
    QCheckBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QSizePolicy,
    QSpacerItem, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from app_tracker.config import (
    AUTORUN_REGISTRY_NAME,
    DEFAULT_IDLE_THRESHOLD_SECONDS,
    HISTORY_DEFAULT_DAYS,
    SETTING_AUTORUN_ENABLED,
    SETTING_GUARDIAN_ENABLED,
    SETTING_IDLE_THRESHOLD,
    SETTING_MINIMIZE_TO_TRAY,
    SETTING_PASSWORD_HASH,
    SETTING_PASSWORD_PROTECT_EXIT,
    SETTING_START_MINIMIZED,
    SETTING_TERMINATE_ON_LIMIT,
)
from app_tracker.core.database import DatabaseManager
from app_tracker.core.productivity import Productivity
from app_tracker.platform_support import is_autorun_enabled, set_autorun
from app_tracker.security import check_password, hash_password
from app_tracker.utils import format_duration, parse_time_input

log = logging.getLogger(__name__)


class LimitDialog(QDialog):
    def __init__(self, db: DatabaseManager, app_id: int, app_name: str,
                 current: Dict[str, Optional[int]], parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self.app_id = app_id
        self.setWindowTitle(f"Лимиты для {app_name}")
        self.setWindowIcon(QIcon.fromTheme("preferences-system"))

        layout = QFormLayout(self)
        self.daily_input = QLineEdit()
        self.weekly_input = QLineEdit()
        self.daily_input.setPlaceholderText("Например: 1ч 30м, 45м (пусто = без лимита)")
        self.weekly_input.setPlaceholderText("Например: 10ч, 5ч 30м (пусто = без лимита)")
        if current.get("daily"):
            self.daily_input.setText(format_duration(current["daily"]).replace(" ", ""))
        if current.get("weekly"):
            self.weekly_input.setText(format_duration(current["weekly"]).replace(" ", ""))
        layout.addRow("Дневной лимит:", self.daily_input)
        layout.addRow("Недельный лимит:", self.weekly_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        daily = parse_time_input(self.daily_input.text().strip())
        weekly = parse_time_input(self.weekly_input.text().strip())
        if daily is None:
            QMessageBox.warning(self, "Неверный ввод", "Неверный дневной лимит. Формат: 'Xч Yм Zс'.")
            return
        if weekly is None:
            QMessageBox.warning(self, "Неверный ввод", "Неверный недельный лимит. Формат: 'Xч Yм Zс'.")
            return
        self.db.set_limit(self.app_id, daily, weekly)
        super().accept()


class PasswordChangeDialog(QDialog):
    def __init__(self, db: DatabaseManager, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Пароль на выход")
        self.setWindowIcon(QIcon.fromTheme("dialog-password"))
        self.setModal(True)

        layout = QFormLayout(self)
        self.current_input = QLineEdit(echoMode=QLineEdit.EchoMode.Password)
        self.new_input = QLineEdit(echoMode=QLineEdit.EchoMode.Password)
        self.confirm_input = QLineEdit(echoMode=QLineEdit.EchoMode.Password)
        self.has_password = self.db.get_setting(SETTING_PASSWORD_HASH) is not None

        if self.has_password:
            layout.addRow("Текущий пароль:", self.current_input)
        layout.addRow("Новый пароль:", self.new_input)
        layout.addRow("Подтвердите пароль:", self.confirm_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        if self.has_password:
            stored = self.db.get_setting(SETTING_PASSWORD_HASH)
            if isinstance(stored, bytes) and not check_password(stored, self.current_input.text()):
                QMessageBox.warning(self, "Неверный пароль", "Текущий пароль введён неверно.")
                return

        new_pwd = self.new_input.text()
        if not new_pwd:  # empty -> offer to remove an existing password
            if self.has_password:
                reply = QMessageBox.question(
                    self, "Удалить пароль", "Удалить пароль на выход?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.db.set_setting(SETTING_PASSWORD_HASH, None)
                    self.db.set_bool(SETTING_PASSWORD_PROTECT_EXIT, False)
                    QMessageBox.information(self, "Пароль удалён", "Пароль на выход удалён.")
                    super().accept()
            else:
                super().accept()
            return

        if len(new_pwd) < 4:
            QMessageBox.warning(self, "Слишком короткий", "Минимум 4 символа.")
            return
        if new_pwd != self.confirm_input.text():
            QMessageBox.warning(self, "Не совпадают", "Пароли не совпадают.")
            return
        self.db.set_setting(SETTING_PASSWORD_HASH, hash_password(new_pwd))
        QMessageBox.information(self, "Готово", "Пароль на выход установлен.")
        super().accept()


class SettingsDialog(QDialog):
    settingsChanged = pyqtSignal()

    def __init__(self, db: DatabaseManager, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Настройки")
        self.setWindowIcon(QIcon.fromTheme("preferences-system"))
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._build_general(form)
        self._build_limits(form)
        self._build_security(form)
        layout.addLayout(form)
        layout.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _note(text: str) -> QLabel:
        label = QLabel(f"<small><i>{text}</i></small>")
        label.setWordWrap(True)
        return label

    def _build_general(self, form: QFormLayout) -> None:
        form.addRow(QLabel("<b>Общие</b>"))
        self.idle_spin = QSpinBox()
        self.idle_spin.setRange(10, 3600)
        self.idle_spin.setSuffix(" секунд")
        self.idle_spin.setValue(self.db.get_int(SETTING_IDLE_THRESHOLD, DEFAULT_IDLE_THRESHOLD_SECONDS))
        form.addRow("Порог неактивности:", self.idle_spin)

        self.start_min_cb = QCheckBox("Запускать свёрнутым в трей")
        self.start_min_cb.setChecked(self.db.get_bool(SETTING_START_MINIMIZED))
        form.addRow(self.start_min_cb)

        self.minimize_tray_cb = QCheckBox("Сворачивать в трей вместо закрытия")
        self.minimize_tray_cb.setChecked(self.db.get_bool(SETTING_MINIMIZE_TO_TRAY, True))
        form.addRow(self.minimize_tray_cb)
        form.addRow(QLabel(" "))

    def _build_limits(self, form: QFormLayout) -> None:
        form.addRow(QLabel("<b>Контроль лимитов</b>"))
        self.terminate_cb = QCheckBox("Завершать приложение при превышении лимита")
        self.terminate_cb.setChecked(self.db.get_bool(SETTING_TERMINATE_ON_LIMIT))
        form.addRow(self.terminate_cb)
        form.addRow(self._note("Внимание: может привести к потере несохранённых данных."))
        form.addRow(QLabel(" "))

    def _build_security(self, form: QFormLayout) -> None:
        form.addRow(QLabel("<b>Запуск и защита</b>"))
        self.autorun_cb = QCheckBox("Запускать автоматически при старте Windows")
        if sys.platform == "win32":
            self.autorun_cb.setChecked(is_autorun_enabled(AUTORUN_REGISTRY_NAME))
        else:
            self.autorun_cb.setEnabled(False)
            self.autorun_cb.setToolTip("Доступно только в Windows.")
        form.addRow(self.autorun_cb)

        self.guardian_cb = QCheckBox("Защита от закрытия (перезапуск при убийстве)")
        self.guardian_cb.setChecked(self.db.get_bool(SETTING_GUARDIAN_ENABLED))
        form.addRow(self.guardian_cb)
        form.addRow(self._note(
            "Запускает фоновый процесс-сторож, который перезапускает приложение, "
            "если его завершить (например, через Диспетчер задач). Корректный выход "
            "через меню сторож не трогает."
        ))

        self.password_cb = QCheckBox("Требовать пароль для выхода")
        self.password_cb.setChecked(self.db.get_bool(SETTING_PASSWORD_PROTECT_EXIT))
        form.addRow(self.password_cb)
        change_pwd = QPushButton("Установить/сменить пароль…")
        change_pwd.clicked.connect(self._open_password_dialog)
        form.addRow(change_pwd)

    def _open_password_dialog(self) -> None:
        PasswordChangeDialog(self.db, self).exec()
        if self.db.get_setting(SETTING_PASSWORD_HASH) is None:
            self.password_cb.setChecked(False)

    def accept(self) -> None:
        # A password requirement is meaningless without a stored password.
        if self.password_cb.isChecked() and self.db.get_setting(SETTING_PASSWORD_HASH) is None:
            QMessageBox.warning(self, "Нет пароля", "Сначала установите пароль на выход.")
            return

        self.db.set_setting(SETTING_IDLE_THRESHOLD, str(self.idle_spin.value()))
        self.db.set_bool(SETTING_START_MINIMIZED, self.start_min_cb.isChecked())
        self.db.set_bool(SETTING_MINIMIZE_TO_TRAY, self.minimize_tray_cb.isChecked())
        self.db.set_bool(SETTING_TERMINATE_ON_LIMIT, self.terminate_cb.isChecked())
        self.db.set_bool(SETTING_GUARDIAN_ENABLED, self.guardian_cb.isChecked())
        self.db.set_bool(SETTING_PASSWORD_PROTECT_EXIT, self.password_cb.isChecked())

        if sys.platform == "win32":
            desired = self.autorun_cb.isChecked()
            if is_autorun_enabled(AUTORUN_REGISTRY_NAME) != desired:
                if set_autorun(AUTORUN_REGISTRY_NAME, desired):
                    self.db.set_bool(SETTING_AUTORUN_ENABLED, desired)
                else:
                    QMessageBox.warning(self, "Автозапуск", "Не удалось обновить автозапуск.")

        self.settingsChanged.emit()
        super().accept()


class HistoryDialog(QDialog):
    def __init__(self, db: DatabaseManager, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("История использования")
        self.setMinimumSize(720, 460)

        layout = QVBoxLayout(self)
        layout.addLayout(self._build_date_controls())
        layout.addLayout(self._build_summary_row())
        layout.addWidget(self._build_table())
        self.populate()

    def _build_date_controls(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.start_date_edit = QDateEdit(calendarPopup=True)
        self.start_date_edit.setDate(QDate.currentDate().addDays(-HISTORY_DEFAULT_DAYS + 1))
        self.end_date_edit = QDateEdit(calendarPopup=True)
        self.end_date_edit.setDate(QDate.currentDate())
        refresh = QPushButton(QIcon.fromTheme("view-refresh"), "Обновить")
        refresh.clicked.connect(self.populate)
        row.addWidget(QLabel("С:"))
        row.addWidget(self.start_date_edit)
        row.addWidget(QLabel("По:"))
        row.addWidget(self.end_date_edit)
        row.addWidget(refresh)
        row.addStretch()
        return row

    def _build_summary_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.total_label = QLabel("Всего: N/A")
        self.prod_label = QLabel("Продуктивно: N/A")
        self.unprod_label = QLabel("Непродуктивно: N/A")
        row.addWidget(self.total_label)
        row.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        row.addWidget(self.prod_label)
        row.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        row.addWidget(self.unprod_label)
        return row

    def _build_table(self) -> QTableWidget:
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Дата", "Приложение", "Длительность", "Продуктивность", "Путь к файлу"]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(4, 200)
        self.table.setSortingEnabled(True)
        return self.table

    def populate(self) -> None:
        start = self.start_date_edit.date().toPyDate()
        end = self.end_date_edit.date().toPyDate()
        if start > end:
            QMessageBox.warning(self, "Неверный диапазон", "Начальная дата позже конечной.")
            return

        rows = self.db.get_history(start, end)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))

        total = prod = unprod = 0
        for i, (name, path, productivity, date_str, duration) in enumerate(rows):
            prod_enum = Productivity.from_value(productivity)
            total += duration
            if prod_enum == Productivity.PRODUCTIVE:
                prod += duration
            elif prod_enum == Productivity.UNPRODUCTIVE:
                unprod += duration

            duration_item = QTableWidgetItem(format_duration(duration))
            duration_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            prod_item = QTableWidgetItem(prod_enum.label)
            prod_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            prod_item.setBackground(QBrush(QColor(*prod_enum.rgb)))

            self.table.setItem(i, 0, QTableWidgetItem(date_str))
            self.table.setItem(i, 1, QTableWidgetItem(name))
            self.table.setItem(i, 2, duration_item)
            self.table.setItem(i, 3, prod_item)
            self.table.setItem(i, 4, QTableWidgetItem(path))

        self.table.setSortingEnabled(True)
        self.total_label.setText(f"Всего: <b>{format_duration(total)}</b>")
        self.prod_label.setText(f"Продуктивно: <b style='color:#7CFC7C;'>{format_duration(prod)}</b>")
        self.unprod_label.setText(f"Непродуктивно: <b style='color:#FF7C7C;'>{format_duration(unprod)}</b>")
