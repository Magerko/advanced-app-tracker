"""The "Графики" tab: a matplotlib pie chart and a pyqtgraph daily-trend bar.

Both backends are optional; a missing one shows a placeholder instead of
crashing the tab.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

import numpy as np
from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QIcon, QPalette
from PyQt6.QtWidgets import (
    QDateEdit, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from app_tracker.config import GRAPH_PIE_MAX_SLICES, HISTORY_DEFAULT_DAYS
from app_tracker.core.database import DatabaseManager
from app_tracker.utils import format_duration

log = logging.getLogger(__name__)

try:
    import matplotlib

    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure

    _MATPLOTLIB_OK = True
except ImportError:
    matplotlib = None  # type: ignore
    FigureCanvas = Figure = None  # type: ignore
    _MATPLOTLIB_OK = False
    log.warning("matplotlib unavailable; pie chart disabled.")

try:
    import pyqtgraph as pg

    _PYQTGRAPH_OK = True
except ImportError:
    pg = None  # type: ignore
    _PYQTGRAPH_OK = False
    log.warning("pyqtgraph unavailable; bar chart disabled.")


class GraphWidget(QWidget):
    def __init__(self, db_manager: DatabaseManager, parent=None) -> None:
        super().__init__(parent)
        self.db = db_manager
        self._loaded_once = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.addLayout(self._build_date_controls())

        charts = QHBoxLayout()
        charts.addWidget(self._build_pie_panel())
        charts.addWidget(self._build_bar_panel())
        layout.addLayout(charts)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _build_date_controls(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.start_date_edit = QDateEdit(calendarPopup=True)
        self.start_date_edit.setDate(QDate.currentDate().addDays(-HISTORY_DEFAULT_DAYS + 1))
        self.end_date_edit = QDateEdit(calendarPopup=True)
        self.end_date_edit.setDate(QDate.currentDate())
        refresh = QPushButton(QIcon.fromTheme("view-refresh"), "Обновить графики")
        refresh.clicked.connect(self.update_graphs)

        row.addWidget(QLabel("Графики с:"))
        row.addWidget(self.start_date_edit)
        row.addWidget(QLabel("по:"))
        row.addWidget(self.end_date_edit)
        row.addWidget(refresh)
        row.addStretch()
        return row

    def _build_pie_panel(self) -> QWidget:
        panel = QWidget()
        box = QVBoxLayout(panel)
        title = QLabel("<b>Распределение использования приложений</b>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(title)

        if _MATPLOTLIB_OK:
            self.pie_figure = Figure(figsize=(5, 4), dpi=100, tight_layout=True)
            self.pie_canvas = FigureCanvas(self.pie_figure)
            self.pie_axes = self.pie_figure.add_subplot(111)
            box.addWidget(self.pie_canvas)
        else:
            self.pie_canvas = None
            placeholder = QLabel("Matplotlib не найден.\nКруговая диаграмма недоступна.")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(placeholder)
        return panel

    def _build_bar_panel(self) -> QWidget:
        panel = QWidget()
        box = QVBoxLayout(panel)
        title = QLabel("<b>Тренд дневного использования</b>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(title)

        if _PYQTGRAPH_OK:
            pg.setConfigOption("background", None)
            pg.setConfigOption("foreground", "w")
            self.bar_widget = pg.PlotWidget()
            self.bar_widget.setBackground(self.palette().color(QPalette.ColorRole.Base))
            self.bar_plot = self.bar_widget.getPlotItem()
            self.bar_plot.setLabel("left", "Использование", units="ч")
            self.bar_plot.setLabel("bottom", "Дата")
            self.bar_plot.showGrid(x=False, y=True, alpha=0.3)
            self.date_axis = pg.DateAxisItem(orientation="bottom")
            self.bar_plot.setAxisItems({"bottom": self.date_axis})
            self.bar_item = None
            box.addWidget(self.bar_widget)
        else:
            self.bar_widget = None
            placeholder = QLabel("pyqtgraph не найден.\nГрафик тренда недоступен.")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(placeholder)
        return panel

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded_once:
            self._loaded_once = True
            self.update_graphs()

    def update_graphs(self) -> None:
        start = self.start_date_edit.date().toPyDate()
        end = self.end_date_edit.date().toPyDate()
        if start > end:
            log.info("Ignoring graph refresh: start date after end date.")
            return
        if self.pie_canvas is not None:
            self._update_pie(start, end)
        if self.bar_widget is not None:
            self._update_bar()

    def _draw_pie_message(self, text: str, color: str) -> None:
        self.pie_axes.clear()
        self.pie_axes.text(0.5, 0.5, text, ha="center", va="center", color=color, fontsize=10)
        self.pie_axes.set_xticks([])
        self.pie_axes.set_yticks([])
        self.pie_canvas.draw()

    def _update_pie(self, start_date, end_date) -> None:
        bg = self.palette().color(QPalette.ColorRole.Base).name()
        fg = self.palette().color(QPalette.ColorRole.WindowText).name()
        self.pie_figure.patch.set_facecolor(bg)
        self.pie_axes.patch.set_facecolor(bg)
        self.pie_axes.clear()
        self.pie_axes.set_title("Распределение использования", color=fg, fontsize=10)

        data = self.db.get_pie_data(start_date, end_date)
        total = sum(item[1] for item in data) if data else 0
        if not data or total == 0:
            self._draw_pie_message("Нет данных за выбранный период", fg)
            return

        data.sort(key=lambda x: x[1], reverse=True)
        threshold = total * 0.02
        labels, sizes, other = [], [], 0
        for name, seconds in data:
            if len(sizes) < GRAPH_PIE_MAX_SLICES and seconds >= threshold:
                labels.append(name)
                sizes.append(seconds)
            else:
                other += seconds
        if other > 0:
            labels.append("Другое")
            sizes.append(other)

        try:
            cmap = matplotlib.colormaps.get_cmap("tab20")
            colors = [cmap(i / max(1, len(sizes))) for i in range(len(sizes))]
            wedges, _ = self.pie_axes.pie(
                sizes, startangle=90, colors=colors,
                wedgeprops={"edgecolor": fg, "linewidth": 0.5},
            )
            legend_labels = [
                f"{label}: {format_duration(size)} ({size / total * 100:.1f}%)"
                for label, size in zip(labels, sizes)
            ]
            legend = self.pie_axes.legend(
                wedges, legend_labels, title="Приложения", loc="center left",
                bbox_to_anchor=(1.02, 0.5), fontsize=8, labelcolor=fg,
                title_fontproperties={"size": 9, "weight": "bold"},
            )
            if legend:
                legend.get_title().set_color(fg)
                legend.get_frame().set_edgecolor(fg)
                legend.get_frame().set_facecolor(bg)
            self.pie_axes.axis("equal")
            self.pie_canvas.draw()
        except Exception:
            log.exception("Failed to render pie chart")
            self._draw_pie_message("Ошибка построения\nдиаграммы", "red")

    def _update_bar(self, num_days: int = 7) -> None:
        base = self.palette().color(QPalette.ColorRole.Base)
        fg = self.palette().color(QPalette.ColorRole.WindowText)
        self.bar_widget.setBackground(base)
        self.bar_plot.getAxis("left").setTextPen(fg)
        self.bar_plot.getAxis("bottom").setTextPen(fg)

        if self.bar_item is not None:
            self.bar_plot.removeItem(self.bar_item)
            self.bar_item = None

        data = self.db.get_daily_totals(num_days)
        if not data:
            return

        timestamps = np.array([time.mktime(d["date"].timetuple()) for d in data])
        hours = np.array([d["seconds"] / 3600.0 for d in data])
        self.bar_item = pg.BarGraphItem(
            x=timestamps, height=hours, width=0.6 * 86400,
            brush=pg.mkBrush(42, 130, 218, 150), pen=pg.mkPen(color=fg, width=1),
        )
        self.bar_plot.addItem(self.bar_item)
        try:
            self.date_axis.setTicks(
                [[(ts, datetime.fromtimestamp(ts).strftime("%m-%d")) for ts in timestamps]]
            )
        except Exception:
            log.debug("Could not set date ticks", exc_info=True)
        self.bar_plot.autoRange()
