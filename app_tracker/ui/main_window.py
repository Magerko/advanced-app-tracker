"""The main application window, system tray and overall lifecycle."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

import psutil
from PyQt6.QtCore import (
    Q_ARG, QDateTime, QEvent, QMetaObject, Qt, QThread, QTime, QTimer,
)
from PyQt6.QtGui import QAction, QBrush, QColor, QPalette
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QMainWindow, QMenu, QMessageBox, QSizePolicy, QSpacerItem,
    QSystemTrayIcon, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from app_tracker.config import (
    APP_NAME,
    DEFAULT_IDLE_THRESHOLD_SECONDS,
    SETTING_CLOSE_HINT_SHOWN,
    SETTING_GUARDIAN_ENABLED,
    SETTING_IDLE_THRESHOLD,
    SETTING_MINIMIZE_TO_TRAY,
    SETTING_PASSWORD_HASH,
    SETTING_PASSWORD_PROTECT_EXIT,
)
from app_tracker.core.database import DatabaseManager
from app_tracker.core.productivity import PRODUCTIVITY_COLORS, Productivity
from app_tracker.core.tracker import TrackerWorker
from app_tracker.security import check_password
from app_tracker.security.guardian import Guardian
from app_tracker.ui.dialogs import HistoryDialog, LimitDialog, SettingsDialog
from app_tracker.ui.graphs import GraphWidget
from app_tracker.ui.theme import app_icon
from app_tracker.utils import format_duration

log = logging.getLogger(__name__)

_LIMIT_EXCEEDED_COLOR = QColor(255, 100, 100)


class MainWindow(QMainWindow):
    def __init__(self, db_manager: DatabaseManager) -> None:
        super().__init__()
        self.db = db_manager
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setMinimumSize(860, 600)

        self._quitting = False
        self._shutdown_done = False
        self.usage_summary: dict = {}
        self.limits: dict = {}
        self.totals: dict = {}
        self._warnings_shown_today: dict[str, set] = defaultdict(set)

        self.guardian = Guardian(self)
        self._guardian_running = False

        self._build_ui()
        self._create_actions()
        self._create_menu()
        self._create_tray()
        self._start_worker()

        self._setup_midnight_timer()
        if self.db.get_bool(SETTING_GUARDIAN_ENABLED):
            self._set_guardian(True)

    # -- UI construction ------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        usage_tab = QWidget()
        usage_layout = QVBoxLayout(usage_tab)
        usage_layout.addLayout(self._build_summary_row())
        usage_layout.addWidget(self._build_table())
        self.tabs.addTab(usage_tab, "Текущее использование")

        self.graph_tab = GraphWidget(self.db)
        self.tabs.addTab(self.graph_tab, "Графики")

        self.status_label = QLabel("Инициализация…")
        self.statusBar().addPermanentWidget(self.status_label)

    def _build_summary_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.total_label = QLabel("Сегодня: N/A")
        self.prod_label = QLabel("Продуктивно: N/A")
        self.unprod_label = QLabel("Непродуктивно: N/A")
        row.addWidget(self.total_label)
        row.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        row.addWidget(self.prod_label)
        row.addSpacerItem(QSpacerItem(10, 20))
        row.addWidget(self.unprod_label)
        return row

    def _build_table(self) -> QTableWidget:
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["Приложение", "Продуктивно?", "Сегодня", "Неделя",
             "Дн. лимит", "Нед. лимит", "Путь к файлу"]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        for col, mode in {
            0: QHeaderView.ResizeMode.Interactive,
            6: QHeaderView.ResizeMode.Stretch,
        }.items():
            header.setSectionResizeMode(col, mode)
        for col in (1, 2, 3, 4, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(0, 160)
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self._open_limit_dialog)
        return self.table

    def _create_actions(self) -> None:
        self.pause_action = QAction("Приостановить отслеживание", self)
        self.pause_action.triggered.connect(self._toggle_pause)
        self.limit_action = QAction("Установить/изменить лимит", self)
        self.limit_action.triggered.connect(self._open_limit_dialog)
        self.toggle_prod_action = QAction("Переключить продуктивность", self)
        self.toggle_prod_action.triggered.connect(self._toggle_productivity)
        self.set_unknown_action = QAction("Статус 'Неизвестно'", self)
        self.set_unknown_action.triggered.connect(self._set_unknown)
        self.history_action = QAction("Просмотр истории", self)
        self.history_action.triggered.connect(self._show_history)
        self.settings_action = QAction("Настройки", self)
        self.settings_action.triggered.connect(self._show_settings)
        self.exit_action = QAction("Выход", self)
        self.exit_action.triggered.connect(self._request_quit)

    def _create_menu(self) -> None:
        menu = self.menuBar()
        file_menu = menu.addMenu("&Файл")
        file_menu.addAction(self.settings_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        actions_menu = menu.addMenu("&Действия")
        actions_menu.addAction(self.pause_action)
        actions_menu.addAction(self.history_action)

        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.table.addAction(self.limit_action)
        self.table.addAction(self.toggle_prod_action)
        self.table.addAction(self.set_unknown_action)

    def _create_tray(self) -> None:
        self.tray_icon = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            log.warning("System tray not available.")
            return
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.windowIcon())
        self.tray_icon.setToolTip(APP_NAME)

        menu = QMenu(self)
        show_action = QAction("Показать", self)
        show_action.triggered.connect(self._show_from_tray)
        menu.addAction(show_action)
        menu.addAction(self.pause_action)
        menu.addSeparator()
        menu.addAction(self.exit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    # -- worker thread --------------------------------------------------------
    def _start_worker(self) -> None:
        self.worker_thread = QThread(self)
        self.worker = TrackerWorker(self.db)
        self.worker.moveToThread(self.worker_thread)
        self.worker.usageUpdated.connect(self._update_ui)
        self.worker.limitWarning.connect(self._on_limit_warning)
        self.worker.statusChanged.connect(self._on_status)
        self.worker.requestTerminateApp.connect(self._terminate_app)
        self.worker_thread.started.connect(self.worker.start_tracking)
        self.worker_thread.start()

    def _invoke_worker(self, method: str, *args) -> None:
        QMetaObject.invokeMethod(
            self.worker, method, Qt.ConnectionType.QueuedConnection, *args
        )

    # -- UI updates -----------------------------------------------------------
    def _update_ui(self, usage_summary: dict, limits: dict, totals: dict) -> None:
        if self._quitting:
            return
        self.usage_summary = usage_summary
        self.limits = limits
        self.totals = totals
        self._update_summary_labels()
        self._populate_table(usage_summary)

    def _update_summary_labels(self) -> None:
        self.total_label.setText(f"Сегодня: <b>{format_duration(self.totals.get('today', 0))}</b>")
        self.prod_label.setText(
            f"Продуктивно: <b style='color:#7CFC7C;'>{format_duration(self.totals.get('prod_today', 0))}</b>"
        )
        self.unprod_label.setText(
            f"Непродуктивно: <b style='color:#FF7C7C;'>{format_duration(self.totals.get('unprod_today', 0))}</b>"
        )

    def _find_row(self, app_id: int) -> int:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == app_id:
                return row
        return -1

    def _populate_table(self, summary: dict) -> None:
        self.table.setSortingEnabled(False)
        active_id = getattr(self.worker, "current_app_id", None)

        for app_id, data in summary.items():
            today = data.get("today_display", data.get("today", 0))
            week = data.get("week_display", data.get("week", 0))
            prod = data.get("prod", Productivity.UNKNOWN)
            limit = self.limits.get(app_id, {})
            daily, weekly = limit.get("daily"), limit.get("weekly")

            row = self._find_row(app_id)
            if row == -1:
                row = self.table.rowCount()
                self.table.insertRow(row)

            name_item = QTableWidgetItem(data.get("name", "N/A"))
            name_item.setData(Qt.ItemDataRole.UserRole, app_id)
            self.table.setItem(row, 0, name_item)
            self._ensure_checkbox(row, app_id, prod)
            self.table.setItem(row, 2, QTableWidgetItem(format_duration(today)))
            self.table.setItem(row, 3, QTableWidgetItem(format_duration(week)))
            self.table.setItem(row, 4, QTableWidgetItem(format_duration(daily) if daily else "-"))
            self.table.setItem(row, 5, QTableWidgetItem(format_duration(weekly) if weekly else "-"))
            self.table.setItem(row, 6, QTableWidgetItem(data.get("path", "N/A")))
            self._style_row(row, prod, today, week, daily, weekly)

        self._prune_table(summary, active_id)
        self.table.setSortingEnabled(True)

    def _ensure_checkbox(self, row: int, app_id: int, prod: Productivity) -> None:
        widget = self.table.cellWidget(row, 1)
        checkbox = widget.findChild(QCheckBox) if widget else None
        if checkbox is None:
            checkbox = QCheckBox()
            checkbox.setProperty("app_id", app_id)
            checkbox.stateChanged.connect(self._on_productivity_toggled)
            container = QWidget()
            box = QHBoxLayout(container)
            box.addWidget(checkbox)
            box.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(row, 1, container)
        checkbox.blockSignals(True)
        checkbox.setChecked(prod == Productivity.PRODUCTIVE)
        checkbox.blockSignals(False)

    def _prune_table(self, summary: dict, active_id) -> None:
        """Drop rows for apps no longer present or with zero recorded time."""
        keep = set()
        for app_id, data in summary.items():
            if app_id == active_id:
                keep.add(app_id)
            elif data.get("today", 0) or data.get("week", 0):
                keep.add(app_id)

        for row in range(self.table.rowCount() - 1, -1, -1):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) not in keep:
                self.table.removeRow(row)

    def _style_row(self, row, prod, today, week, daily, weekly) -> None:
        exceeded = bool(
            (daily and daily > 0 and today >= daily)
            or (weekly and weekly > 0 and week >= weekly)
        )
        if exceeded:
            bg = _LIMIT_EXCEEDED_COLOR
            fg = QColor(Qt.GlobalColor.black)
        else:
            bg = QColor(*PRODUCTIVITY_COLORS[prod])
            fg = (QColor(Qt.GlobalColor.black) if prod != Productivity.UNKNOWN
                  else self.palette().color(QPalette.ColorRole.Text))

        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item is None:
                item = QTableWidgetItem()
                self.table.setItem(row, col, item)
            item.setBackground(QBrush(bg))
            item.setForeground(QBrush(fg))

            widget = self.table.cellWidget(row, col)
            if widget:
                pal = widget.palette()
                pal.setColor(QPalette.ColorRole.Window, bg)
                pal.setColor(QPalette.ColorRole.WindowText, fg)
                widget.setAutoFillBackground(True)
                widget.setPalette(pal)

    # -- productivity editing -------------------------------------------------
    def _on_productivity_toggled(self, _state: int) -> None:
        checkbox = self.sender()
        if not isinstance(checkbox, QCheckBox):
            return
        app_id = checkbox.property("app_id")
        new_prod = Productivity.PRODUCTIVE if checkbox.isChecked() else Productivity.UNPRODUCTIVE
        self._apply_productivity(app_id, new_prod)

    def _set_unknown(self) -> None:
        app_id = self._selected_app_id()
        if app_id is not None:
            self._apply_productivity(app_id, Productivity.UNKNOWN)

    def _apply_productivity(self, app_id: int, prod: Productivity) -> None:
        if app_id is None or not self.db.set_app_productivity(app_id, prod):
            QMessageBox.warning(self, "Ошибка", f"Не удалось обновить статус (ID {app_id}).")
            return
        if app_id in self.usage_summary:
            self.usage_summary[app_id]["prod"] = prod
        self._recompute_totals()
        self._update_summary_labels()

        row = self._find_row(app_id)
        if row != -1:
            self._ensure_checkbox(row, app_id, prod)
            data = self.usage_summary.get(app_id, {})
            today = data.get("today_display", data.get("today", 0))
            week = data.get("week_display", data.get("week", 0))
            limit = self.limits.get(app_id, {})
            self._style_row(row, prod, today, week, limit.get("daily"), limit.get("weekly"))

    def _recompute_totals(self) -> None:
        totals = {"today": 0, "week": 0, "prod_today": 0, "prod_week": 0,
                  "unprod_today": 0, "unprod_week": 0}
        for data in self.usage_summary.values():
            today = data.get("today_display", data.get("today", 0))
            week = data.get("week_display", data.get("week", 0))
            prod = data.get("prod", Productivity.UNKNOWN)
            totals["today"] += today
            totals["week"] += week
            if prod == Productivity.PRODUCTIVE:
                totals["prod_today"] += today
                totals["prod_week"] += week
            elif prod == Productivity.UNPRODUCTIVE:
                totals["unprod_today"] += today
                totals["unprod_week"] += week
        self.totals = totals

    # -- selection helpers ----------------------------------------------------
    def _selected_app_id(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Нет выбора", "Сначала выберите приложение в таблице.")
            return None
        item = self.table.item(rows[0].row(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _open_limit_dialog(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Нет выбора", "Выберите приложение в таблице.")
            return
        item = self.table.item(rows[0].row(), 0)
        if not item:
            return
        app_id = item.data(Qt.ItemDataRole.UserRole)
        LimitDialog(self.db, app_id, item.text(), self.limits.get(app_id, {}), self).exec()

    def _toggle_productivity(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        widget = self.table.cellWidget(rows[0].row(), 1)
        checkbox = widget.findChild(QCheckBox) if widget else None
        if checkbox:
            checkbox.click()

    # -- limit warnings -------------------------------------------------------
    def _on_limit_warning(self, app_id: int, name: str, kind: str, usage: int, limit: int) -> None:
        base_kind = kind.split("-")[0]
        is_warn = kind.endswith("-warn")
        if not is_warn and app_id in self._warnings_shown_today[base_kind]:
            return
        if not is_warn:
            self._warnings_shown_today[base_kind].add(app_id)

        usage_str, limit_str = format_duration(usage), format_duration(limit)
        messages = {
            "daily-warn": ("Предупреждение о лимите", f"Близко к дневному лимиту: {name}.\n{usage_str} / {limit_str}", False),
            "daily": ("Лимит превышен", f"Дневной лимит ПРЕВЫШЕН: {name}!\n{usage_str} / {limit_str}", True),
            "weekly-warn": ("Предупреждение о лимите", f"Близко к недельному лимиту: {name}.\n{usage_str} / {limit_str}", False),
            "weekly": ("Лимит превышен", f"Недельный лимит ПРЕВЫШЕН: {name}!\n{usage_str} / {limit_str}", True),
        }
        title, message, critical = messages.get(kind, ("Лимит", name, False))
        icon = (QSystemTrayIcon.MessageIcon.Critical if critical
                else QSystemTrayIcon.MessageIcon.Warning)

        if self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.showMessage(title, message, icon, 5000)
        elif critical:
            QMessageBox.critical(self, title, message)
        else:
            QMessageBox.warning(self, title, message)

    def _on_status(self, text: str) -> None:
        self.status_label.setText(f"Статус: {text}")
        if self.tray_icon:
            self.tray_icon.setToolTip(f"{APP_NAME}\n{text}")

    # -- actions --------------------------------------------------------------
    def _toggle_pause(self) -> None:
        if getattr(self.worker, "is_paused", False):
            self._invoke_worker("resume_tracking")
            self.pause_action.setText("Приостановить отслеживание")
        else:
            self._invoke_worker("pause_tracking")
            self.pause_action.setText("Возобновить отслеживание")

    def _show_history(self) -> None:
        HistoryDialog(self.db, self).exec()

    def _show_settings(self) -> None:
        dialog = SettingsDialog(self.db, self)
        dialog.settingsChanged.connect(self._apply_settings)
        dialog.exec()

    def _apply_settings(self) -> None:
        threshold = self.db.get_int(SETTING_IDLE_THRESHOLD, DEFAULT_IDLE_THRESHOLD_SECONDS)
        self._invoke_worker("set_idle_threshold", Q_ARG(int, threshold))
        self._invoke_worker("reload_settings")
        self._set_guardian(self.db.get_bool(SETTING_GUARDIAN_ENABLED))

    def _terminate_app(self, pid: int) -> None:
        if not pid or not psutil.pid_exists(pid):
            return
        name = "приложение"
        try:
            proc = psutil.Process(pid)
            name = proc.name()
            proc.terminate()
            log.info("Sent terminate to %s (PID %s).", name, pid)
        except psutil.AccessDenied:
            self._tray_or_box("Ошибка", f"Нет прав завершить {name}.", critical=True)
        except psutil.NoSuchProcess:
            pass
        except psutil.Error as exc:
            self._tray_or_box("Ошибка", f"Ошибка завершения {name}: {exc}", critical=True)

    def _tray_or_box(self, title: str, message: str, *, critical: bool = False) -> None:
        if self.tray_icon and self.tray_icon.isVisible():
            icon = (QSystemTrayIcon.MessageIcon.Critical if critical
                    else QSystemTrayIcon.MessageIcon.Information)
            self.tray_icon.showMessage(title, message, icon, 5000)
        elif critical:
            QMessageBox.critical(self, title, message)
        else:
            QMessageBox.information(self, title, message)

    # -- midnight reset -------------------------------------------------------
    def _setup_midnight_timer(self) -> None:
        self._reset_daily_warnings()  # also schedules the next reset

    def _reset_daily_warnings(self) -> None:
        if self._quitting:
            return
        self._warnings_shown_today["daily"].clear()
        if date.today().weekday() == 0:
            self._warnings_shown_today["weekly"].clear()
        self._schedule_midnight()

    def _schedule_midnight(self) -> None:
        now = QDateTime.currentDateTime()
        midnight = QDateTime(now.date().addDays(1), QTime(0, 0, 1))
        msecs = max(5000, now.msecsTo(midnight))
        QTimer.singleShot(msecs, self._reset_daily_warnings)

    # -- guardian -------------------------------------------------------------
    def _set_guardian(self, enabled: bool) -> None:
        if enabled and not self._guardian_running:
            self.guardian.start()
            self._guardian_running = True
            log.info("Guardian enabled.")
        elif not enabled and self._guardian_running:
            self.guardian.stop()
            self._guardian_running = False
            log.info("Guardian disabled.")

    # -- tray / window lifecycle ---------------------------------------------
    def _on_tray_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _should_minimize_to_tray(self) -> bool:
        return (
            not self._quitting
            and self.tray_icon is not None
            and self.tray_icon.isVisible()
            and self.db.get_bool(SETTING_MINIMIZE_TO_TRAY, True)
        )

    def _show_close_hint(self) -> None:
        if self.db.get_bool(SETTING_CLOSE_HINT_SHOWN) or not self.tray_icon:
            return
        self.tray_icon.showMessage(
            APP_NAME, "Приложение свёрнуто в трей и продолжает отслеживание.",
            QSystemTrayIcon.MessageIcon.Information, 4000,
        )
        self.db.set_bool(SETTING_CLOSE_HINT_SHOWN, True)

    def changeEvent(self, event) -> None:
        if (
            event.type() == QEvent.Type.WindowStateChange
            and self.isMinimized()
            and self._should_minimize_to_tray()
        ):
            QTimer.singleShot(0, self.hide)
            self._show_close_hint()
        super().changeEvent(event)

    def closeEvent(self, event) -> None:
        if self._quitting:
            self._shutdown()
            event.accept()
            QApplication.quit()
            return

        if self._should_minimize_to_tray():
            event.ignore()
            self.hide()
            self._show_close_hint()
            return

        # No tray to hide into -> treat the close button as a quit request.
        if not self._confirm_exit_password():
            event.ignore()
            return
        self._quitting = True
        self._shutdown()
        event.accept()
        QApplication.quit()

    def _request_quit(self) -> None:
        """Explicit quit (menu / tray). Verifies the exit password first."""
        if not self._confirm_exit_password():
            return
        self._quitting = True
        self.close()  # -> closeEvent sees _quitting and tears everything down

    def _confirm_exit_password(self) -> bool:
        if not self.db.get_bool(SETTING_PASSWORD_PROTECT_EXIT):
            return True
        stored = self.db.get_setting(SETTING_PASSWORD_HASH)
        if not isinstance(stored, bytes):
            return True
        pwd, ok = QInputDialog.getText(
            self, "Требуется пароль", "Введите пароль для выхода:",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return False
        if check_password(stored, pwd):
            return True
        QMessageBox.warning(self, "Неверный пароль", "Введён неверный пароль.")
        return False

    def _shutdown(self) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True
        log.info("Shutting down")

        if self._guardian_running:
            self.guardian.stop()
            self._guardian_running = False
        if self.tray_icon:
            self.tray_icon.hide()

        if self.worker_thread.isRunning():
            QMetaObject.invokeMethod(
                self.worker, "stop_tracking", Qt.ConnectionType.BlockingQueuedConnection
            )
            self.worker_thread.quit()
            if not self.worker_thread.wait(3000):
                log.warning("Worker thread did not stop; terminating.")
                self.worker_thread.terminate()
                self.worker_thread.wait()

        self.db.close()
        log.info("Shutdown complete.")
