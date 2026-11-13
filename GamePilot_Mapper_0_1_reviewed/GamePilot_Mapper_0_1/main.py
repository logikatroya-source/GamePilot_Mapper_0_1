import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pyautogui
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QPen
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QTabWidget, QMessageBox, QLineEdit, QDoubleSpinBox,
    QCheckBox, QPlainTextEdit, QScrollArea, QComboBox, QSlider, QGroupBox,
    QFormLayout
)

from vision.resource_detector import ResourceDetector
from mapping.landmark_tracker import LandmarkTracker
from core.location_store import LocationStore

ROOT = Path(__file__).resolve().parent


def to_qpixmap(rgb):
    rgb = np.ascontiguousarray(rgb)
    h, w, ch = rgb.shape
    image = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(image)


class MapView(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(420, 420)
        self.observations = []
        self.base = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#101923"))
        painter.setPen(QPen(QColor("#263746"), 1))
        for x in range(0, self.width(), 28):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 28):
            painter.drawLine(0, y, self.width(), y)
        painter.setPen(QColor("#9fb3c8"))
        painter.drawText(12, 20, "Локальная схема наблюдений · условный масштаб")
        cx, cy = self.width() // 2, self.height() // 2
        if self.base:
            painter.setBrush(QColor("#55b8f0"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(cx - 7, cy - 7, 14, 14)
            painter.setPen(QColor("#d8e8f5"))
            painter.drawText(cx + 10, cy + 4, "БАЗА")
        painter.setPen(QPen(QColor("#eee"), 1))
        for item in self.observations:
            x = max(6, min(self.width() - 6, int(cx + item.get("x", 0))))
            y = max(26, min(self.height() - 6, int(cy + item.get("y", 0))))
            painter.setBrush(QColor("#c5a5ff"))
            painter.drawEllipse(x - 4, y - 4, 8, 8)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GamePilot Mapper 0.1")
        self.resize(1180, 800)
        self.setMinimumSize(900, 640)
        self.store = LocationStore()
        self.tracker = LandmarkTracker()
        self.detector = ResourceDetector(ROOT / "assets" / "rough_stone_t1.png")
        self.last_frame = None
        self._capture_pending = False
        self._capture_was_visible = True

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.capture_frame)

        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        # Scanner
        scanner = QWidget()
        sl = QVBoxLayout(scanner)
        toolbar = QHBoxLayout()
        self.capture_btn = QPushButton("Сделать снимок")
        self.capture_btn.clicked.connect(self.capture_frame)
        self.auto_box = QCheckBox("Автонаблюдение · 2 сек.")
        self.auto_box.toggled.connect(self.toggle_auto)
        toolbar.addWidget(self.capture_btn)
        toolbar.addWidget(self.auto_box)
        toolbar.addStretch(1)
        sl.addLayout(toolbar)

        self.preview = QLabel("Нажми «Сделать снимок» для захвата экрана")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(640, 420)
        self.preview.setStyleSheet(
            "background:#080d13;color:#9fb3c8;border:1px solid #334155;border-radius:10px;"
        )
        scroll = QScrollArea()
        scroll.setWidget(self.preview)
        scroll.setWidgetResizable(True)
        sl.addWidget(scroll, 1)

        controls = QGroupBox("Поиск ресурса")
        form = QFormLayout(controls)
        threshold_row = QHBoxLayout()
        self.threshold = QSlider(Qt.Orientation.Horizontal)
        self.threshold.setRange(50, 98)
        self.threshold.setValue(78)
        self.threshold_value = QLabel("0.78")
        self.threshold.valueChanged.connect(
            lambda value: self.threshold_value.setText(f"{value / 100:.2f}")
        )
        threshold_row.addWidget(self.threshold, 1)
        threshold_row.addWidget(self.threshold_value)
        form.addRow("Порог совпадения", threshold_row)
        self.scan_btn = QPushButton("Найти грубый камень T1")
        self.scan_btn.clicked.connect(self.scan_resources)
        form.addRow(self.scan_btn)
        self.scan_status = QLabel("Рамки — кандидаты, а не подтверждённые ресурсы.")
        self.scan_status.setWordWrap(True)
        form.addRow(self.scan_status)
        sl.addWidget(controls)
        tabs.addTab(scanner, "Сканер")

        # Map / profiles
        map_tab = QWidget()
        ml = QVBoxLayout(map_tab)
        self.map_view = MapView()
        ml.addWidget(self.map_view, 1)
        profile_row = QHBoxLayout()
        self.loc_name = QLineEdit("Location_001")
        self.loc_name.setPlaceholderText("Название профиля")
        create_btn = QPushButton("Создать профиль")
        create_btn.clicked.connect(self.new_location)
        self.profile_combo = QComboBox()
        self.refresh_profiles()
        load_btn = QPushButton("Открыть")
        load_btn.clicked.connect(self.open_location)
        base_btn = QPushButton("Отметить базу")
        base_btn.clicked.connect(self.set_base)
        profile_row.addWidget(self.loc_name, 1)
        profile_row.addWidget(create_btn)
        profile_row.addWidget(self.profile_combo, 1)
        profile_row.addWidget(load_btn)
        profile_row.addWidget(base_btn)
        ml.addLayout(profile_row)
        self.map_status = QLabel(
            "Карта пока экспериментальная: координаты не привязаны к игровому миру."
        )
        self.map_status.setWordWrap(True)
        ml.addWidget(self.map_status)
        tabs.addTab(map_tab, "Карта и профили")

        # Resource library
        res = QWidget()
        rl = QVBoxLayout(res)
        rl.addWidget(QLabel("Библиотека распознавания"))
        rl.addWidget(QLabel("Грубый камень T1 · предоставленный шаблон"))
        sample = QLabel()
        sample.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sample.setPixmap(
            QPixmap(str(ROOT / "assets" / "rough_stone_t1.png")).scaled(
                220, 180, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        )
        rl.addWidget(sample)
        note = QLabel(
            "Изображение наведения хранится как справочный материал. "
            "Проверка текста «Грубый камень» и распознавание зачарования пока не реализованы."
        )
        note.setWordWrap(True)
        rl.addWidget(note)
        rl.addStretch(1)
        tabs.addTab(res, "Ресурсы")

        # Journal
        logs = QWidget()
        ll = QVBoxLayout(logs)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        ll.addWidget(self.log)
        tabs.addTab(logs, "Журнал")

        self.setStyleSheet("""
            QMainWindow,QWidget { background:#111827; color:#e5edf5; font-size:13px; }
            QPushButton { background:#26384c; border:1px solid #40566d; border-radius:7px; padding:9px 13px; }
            QPushButton:hover { background:#34516d; }
            QPushButton:disabled { color:#778899; background:#1c2938; }
            QLineEdit,QComboBox,QPlainTextEdit { background:#0b1220; border:1px solid #40566d; border-radius:6px; padding:7px; }
            QTabWidget::pane { border:1px solid #334155; border-radius:8px; }
            QTabBar::tab { background:#1e293b; padding:10px 18px; margin-right:3px; }
            QTabBar::tab:selected { background:#075985; }
            QGroupBox { border:1px solid #334155; border-radius:8px; margin-top:9px; padding:8px; }
            QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 5px; }
            QSlider::groove:horizontal { height:5px; background:#334155; border-radius:2px; }
            QSlider::handle:horizontal { background:#38bdf8; width:14px; margin:-5px 0; border-radius:7px; }
        """)
        self.log_line("Mapper запущен. Только видимое наблюдение: программа не отправляет игровые команды.")
        self.statusBar().showMessage("Режим наблюдения · управление персонажем отключено")

    def log_line(self, message):
        self.log.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {message}")
        # Prevent unbounded UI log growth during long observation sessions.
        doc = self.log.document()
        if doc.blockCount() > 2000:
            cursor = self.log.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            for _ in range(doc.blockCount() - 1500):
                cursor.select(cursor.SelectionType.LineUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()

    def capture_frame(self):
        if self._capture_pending:
            return
        self._capture_pending = True
        self.capture_btn.setEnabled(False)
        self._capture_was_visible = self.isVisible()
        if self._capture_was_visible:
            self.hide()
            QApplication.processEvents()
        # Give the desktop compositor time to remove the application window.
        QTimer.singleShot(180, self._finish_capture)

    def _finish_capture(self):
        try:
            shot = pyautogui.screenshot().convert("RGB")
            rgb = np.asarray(shot)
            self.last_frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            self.preview.setPixmap(to_qpixmap(rgb))
            self.preview.resize(self.preview.pixmap().size())
            tracking = self.tracker.update(self.last_frame)
            if self.store.data is not None:
                self.store.add_observation({
                    "time": time.time(),
                    "screen_size": [shot.width, shot.height],
                    "tracking": tracking,
                })
                self.store.data["odometry"] = {
                    "dx": tracking["total_dx"], "dy": tracking["total_dy"]
                }
                self.store.save()
                self.map_view.observations = [
                    {"x": -tracking["total_dx"] * 0.15, "y": -tracking["total_dy"] * 0.15}
                ] if tracking["tracked"] else self.map_view.observations
                self.map_view.update()
            self.scan_status.setText(f"Снимок получен: {shot.width}×{shot.height}")
            self.log_line(f"Получен снимок экрана {shot.width}×{shot.height}.")
        except Exception as exc:
            self.log_line(f"Ошибка захвата экрана: {exc}")
            self.scan_status.setText(f"Не удалось получить снимок: {exc}")
            QMessageBox.warning(self, "Ошибка захвата", str(exc))
        finally:
            if self._capture_was_visible:
                self.show()
                self.raise_()
                self.activateWindow()
            self._capture_pending = False
            self.capture_btn.setEnabled(True)

    def scan_resources(self):
        if self.last_frame is None:
            self.capture_frame()
            self.log_line("Сначала получи снимок; поиск запустится после его появления.")
            return
        try:
            threshold = self.threshold.value() / 100.0
            hits = self.detector.detect(self.last_frame, threshold=threshold)
            display = self.last_frame.copy()
            for score, x, y, w, h in hits:
                cv2.rectangle(display, (x, y), (x + w, y + h), (60, 220, 120), 2)
                cv2.putText(display, f"T1 {score:.2f}", (x, max(18, y - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (60, 220, 120), 1, cv2.LINE_AA)
            rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
            self.preview.setPixmap(to_qpixmap(rgb))
            self.preview.resize(self.preview.pixmap().size())
            self.scan_status.setText(
                f"Кандидатов найдено: {len(hits)} · порог {threshold:.2f}. "
                "Каждую рамку нужно проверить визуально."
            )
            self.log_line(f"Сканирование T1: {len(hits)} кандидатов.")
            if self.store.data is not None:
                now = time.time()
                for score, x, y, w, h in hits:
                    self.store.add_resource({
                        "type": "rough_stone", "tier": "T1",
                        "screen_box": [x, y, w, h], "confidence": score,
                        "state": "candidate", "time": now,
                    })
        except Exception as exc:
            self.log_line(f"Ошибка распознавания: {exc}")
            QMessageBox.warning(self, "Ошибка распознавания", str(exc))

    def toggle_auto(self, enabled):
        if enabled:
            self.timer.start(2000)
            self.log_line("Включено периодическое наблюдение.")
        else:
            self.timer.stop()
            self.log_line("Периодическое наблюдение остановлено.")

    def refresh_profiles(self):
        self.profile_combo.clear()
        self.profile_combo.addItems(self.store.list_profiles())

    def new_location(self):
        name = self.loc_name.text().strip()
        try:
            self.store.create(name)
        except FileExistsError as exc:
            QMessageBox.information(self, "Профиль уже существует", str(exc) + ". Выбери его в списке и нажми «Открыть».")
            self.refresh_profiles()
            return
        except Exception as exc:
            QMessageBox.warning(self, "Не удалось создать профиль", str(exc))
            return
        self.tracker.reset()
        self.map_view.base = False
        self.map_view.observations = []
        self.map_view.update()
        self.refresh_profiles()
        self.profile_combo.setCurrentText(self.store.name)
        self.map_status.setText(f"Создан профиль «{self.store.name}».")
        self.log_line(f"Создан профиль локации: {self.store.name}.")

    def open_location(self):
        name = self.profile_combo.currentText()
        if not name:
            return
        try:
            self.store.load(name)
            self.tracker.reset()
            self.map_view.base = bool(self.store.data.get("base_set"))
            odom = self.store.data.get("odometry", {})
            self.map_view.observations = ([{"x": -float(odom.get("dx", 0)) * 0.15,
                                            "y": -float(odom.get("dy", 0)) * 0.15}]
                                          if self.store.data.get("observations") else [])
            self.map_view.update()
            self.map_status.setText(f"Открыт профиль «{self.store.name}».")
            self.log_line(f"Открыт профиль: {self.store.name}.")
        except Exception as exc:
            QMessageBox.warning(self, "Не удалось открыть профиль", str(exc))

    def set_base(self):
        if self.store.data is None:
            self.new_location()
        if self.store.data is not None:
            self.store.set_base()
            self.map_view.base = True
            self.map_view.update()
            self.map_status.setText("База отмечена как стартовая точка профиля, не как точная игровая координата.")
            self.log_line("Пользователь отметил базовую точку.")

    def closeEvent(self, event):
        self.timer.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
