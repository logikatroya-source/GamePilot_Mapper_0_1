import sys, time, json
from pathlib import Path

import pyautogui
from profile_utils import normalize_profile
from PySide6.QtCore import Qt, QThread, Signal, QPoint
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QSpinBox, QDoubleSpinBox, QGroupBox, QMessageBox,
    QDialog, QScrollArea, QCheckBox, QListWidget, QListWidgetItem, QInputDialog
)

APP_DIR = Path.home() / "GamePilotTestClient"
APP_DIR.mkdir(exist_ok=True)
PROFILE_FILE = APP_DIR / "profile.json"
LOG_FILE = APP_DIR / "gamepilot.log"


class ScreenPicker(QDialog):
    """Shows a screenshot and lets the user mark one screen coordinate."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GamePilot — выбери ресурс")
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.point = None
        self.screen_image = pyautogui.screenshot()
        self.screen_w, self.screen_h = self.screen_image.size

        rgb = self.screen_image.convert("RGB")
        raw = rgb.tobytes("raw", "RGB")
        qimg = QImage(raw, self.screen_w, self.screen_h, self.screen_w * 3,
                      QImage.Format.Format_RGB888).copy()
        self.pixmap = QPixmap.fromImage(qimg)

        self.view = QLabel()
        self.view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.view.setPixmap(self.pixmap)
        self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.view.mousePressEvent = self.pick_point

        scroll = QScrollArea()
        scroll.setWidget(self.view)
        scroll.setWidgetResizable(False)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hint = QLabel("Нажми левой кнопкой мыши точно на ресурс. Esc — отмена.")
        hint.setStyleSheet("color:#cbd5e1; padding:8px;")
        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(scroll)
        self.resize(min(self.screen_w + 40, 1200), min(self.screen_h + 80, 850))

    def pick_point(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        p = event.position().toPoint()
        self.point = (p.x(), p.y())
        self.accept()


class Runner(QThread):
    status = Signal(str)
    finished_run = Signal(str)

    def __init__(self, steps, repeats, interval):
        super().__init__()
        self.steps = [dict(step) for step in steps]
        self.repeats = repeats
        self.interval = interval
        self._stop = False

    def stop(self):
        self._stop = True

    def interruptible_wait(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self._stop:
                return False
            time.sleep(min(0.1, max(0, end - time.monotonic())))
        return not self._stop

    def run(self):
        try:
            self.status.emit("Переключись в тестовый клиент — запуск через 2 секунды")
            if not self.interruptible_wait(2.0):
                self.finished_run.emit("Остановлено до запуска")
                return
            for cycle in range(self.repeats):
                if self._stop:
                    break
                for index, step in enumerate(self.steps):
                    if self._stop:
                        break
                    x, y = int(step["x"]), int(step["y"])
                    name = step.get("name") or f"Точка {index + 1}"
                    count = max(1, int(step.get("clicks", 1)))
                    wait = max(0.0, float(step.get("wait", 3.0)))
                    self.status.emit(
                        f"Цикл {cycle + 1}/{self.repeats} · шаг {index + 1}/{len(self.steps)}: {name}"
                    )
                    pyautogui.click(x, y, clicks=count, interval=0.12)
                    if not self.interruptible_wait(wait):
                        break
                if self._stop:
                    break
                if cycle + 1 < self.repeats and not self.interruptible_wait(self.interval):
                    break
            self.finished_run.emit("Остановлено пользователем" if self._stop else "Сценарий завершён")
        except pyautogui.FailSafeException:
            self._stop = True
            self.finished_run.emit("Аварийная остановка PyAutoGUI: курсор в левом верхнем углу")
        except Exception as e:
            self.finished_run.emit(f"Ошибка: {type(e).__name__}: {e}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GamePilot — Test Client")
        self.setMinimumSize(440, 650)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.steps = []
        self.runner = None

        title = QLabel("GAMEPILOT")
        title.setStyleSheet("font-size:22px;font-weight:800;letter-spacing:2px;color:#7dd3fc;")
        subtitle = QLabel("Видимая автоматизация собственного тестового клиента")
        subtitle.setStyleSheet("color:#94a3b8;")

        self.step_list = QListWidget()
        self.step_list.setMinimumHeight(150)
        self.pick_btn = QPushButton("＋  Добавить точку со снимка экрана")
        self.pick_btn.clicked.connect(self.add_step)
        self.rename_btn = QPushButton("Переименовать")
        self.rename_btn.clicked.connect(self.rename_step)
        self.configure_btn = QPushButton("Настроить шаг")
        self.configure_btn.clicked.connect(self.configure_step)
        self.remove_btn = QPushButton("Удалить")
        self.remove_btn.clicked.connect(self.remove_step)
        self.up_btn = QPushButton("↑")
        self.up_btn.clicked.connect(lambda: self.move_step(-1))
        self.down_btn = QPushButton("↓")
        self.down_btn.clicked.connect(lambda: self.move_step(1))

        points_box = QGroupBox("①  Последовательность точек")
        points_layout = QVBoxLayout(points_box)
        points_layout.addWidget(self.step_list)
        points_layout.addWidget(self.pick_btn)
        edit_row = QHBoxLayout()
        edit_row.addWidget(self.rename_btn)
        edit_row.addWidget(self.configure_btn)
        edit_row.addWidget(self.remove_btn)
        edit_row.addWidget(self.up_btn)
        edit_row.addWidget(self.down_btn)
        points_layout.addLayout(edit_row)

        self.repeats = QSpinBox(); self.repeats.setRange(1, 10000); self.repeats.setValue(10)
        self.clicks = QSpinBox(); self.clicks.setRange(1, 5); self.clicks.setValue(1)
        self.wait_gather = QDoubleSpinBox(); self.wait_gather.setRange(0.1, 300); self.wait_gather.setSingleStep(0.5); self.wait_gather.setValue(5.0)
        self.interval = QDoubleSpinBox(); self.interval.setRange(0, 300); self.interval.setSingleStep(0.5); self.interval.setValue(1.0)
        settings = QGroupBox("②  Параметры по умолчанию для новых точек")
        form = QVBoxLayout(settings)
        for label, widget in [
            ("Количество циклов", self.repeats),
            ("Кликов для новой точки", self.clicks),
            ("Ожидание после клика (сек.)", self.wait_gather),
            ("Пауза между циклами (сек.)", self.interval),
        ]:
            row = QHBoxLayout(); row.addWidget(QLabel(label)); row.addStretch(); row.addWidget(widget); form.addLayout(row)

        self.confirm = QCheckBox("Это мой тестовый клиент; координаты проверены")
        self.confirm.setStyleSheet("color:#cbd5e1;")
        self.start_btn = QPushButton("▶  Запустить сценарий"); self.start_btn.setObjectName("start"); self.start_btn.clicked.connect(self.start_run)
        self.stop_btn = QPushButton("■  Аварийная остановка"); self.stop_btn.setObjectName("stop"); self.stop_btn.setEnabled(False); self.stop_btn.clicked.connect(self.stop_run)
        self.status = QLabel("Статус: готов к настройке"); self.status.setWordWrap(True); self.status.setStyleSheet("color:#93c5fd;padding:8px;")
        save_row = QHBoxLayout()
        save_btn = QPushButton("Сохранить профиль"); load_btn = QPushButton("Загрузить профиль")
        save_btn.clicked.connect(self.save_profile); load_btn.clicked.connect(self.load_profile)
        save_row.addWidget(save_btn); save_row.addWidget(load_btn)

        layout = QVBoxLayout()
        for item in (title, subtitle, points_box, settings, self.confirm, self.start_btn, self.stop_btn, self.status): layout.addWidget(item)
        layout.addLayout(save_row)
        central = QWidget(); central.setLayout(layout); self.setCentralWidget(central)
        self.setStyleSheet("""
            QMainWindow,QWidget { background:#0f172a; color:#e2e8f0; font-size:13px; }
            QGroupBox { border:1px solid #334155; border-radius:8px; margin-top:10px; padding:10px; font-weight:700; }
            QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 5px; }
            QPushButton { background:#334155; border:0; border-radius:7px; padding:9px; color:#f8fafc; }
            QPushButton:hover { background:#475569; }
            QPushButton:disabled { color:#64748b; background:#1e293b; }
            QPushButton#start { background:#0369a1; font-weight:700; }
            QPushButton#stop { background:#991b1b; font-weight:700; }
            QSpinBox,QDoubleSpinBox,QListWidget { background:#1e293b; border:1px solid #475569; border-radius:5px; padding:4px; }
            QCheckBox { spacing:8px; }
        """)
        self.log("GamePilot запущен")

    def log(self, message):
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {message}\n")

    def refresh_steps(self, selected=None):
        self.step_list.clear()
        for i, step in enumerate(self.steps):
            item = QListWidgetItem(f"{i+1}. {step['name']}  —  ({step['x']}, {step['y']}) · {step['clicks']} клик. · ожидание {step['wait']} с")
            self.step_list.addItem(item)
        if selected is not None and 0 <= selected < len(self.steps): self.step_list.setCurrentRow(selected)

    def add_step(self):
        self.hide(); QApplication.processEvents(); time.sleep(0.25)
        try:
            dlg = ScreenPicker(self)
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.point:
                default_name = f"Ресурс {len(self.steps) + 1}"
                name, ok = QInputDialog.getText(self, "Название точки", "Название ресурса:", text=default_name)
                if ok:
                    self.steps.append({"name": name.strip() or default_name, "x": dlg.point[0], "y": dlg.point[1], "clicks": self.clicks.value(), "wait": self.wait_gather.value()})
                    self.refresh_steps(len(self.steps)-1)
                    self.status.setText("Точка добавлена. Проверь её на снимке/в клиенте.")
                    self.log(f"Добавлена точка {self.steps[-1]}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка захвата экрана", str(e))
        self.show(); self.raise_()

    def rename_step(self):
        i = self.step_list.currentRow()
        if i < 0: return
        name, ok = QInputDialog.getText(self, "Переименовать точку", "Название:", text=self.steps[i]["name"])
        if ok:
            self.steps[i]["name"] = name.strip() or self.steps[i]["name"]
            self.refresh_steps(i)

    def configure_step(self):
        i = self.step_list.currentRow()
        if i < 0: return
        step = self.steps[i]
        clicks, ok = QInputDialog.getInt(self, "Клики шага", "Количество кликов:", int(step["clicks"]), 1, 5)
        if not ok: return
        wait, ok = QInputDialog.getDouble(self, "Ожидание шага", "Ожидание после клика (сек.):", float(step["wait"]), 0.1, 300.0, 1)
        if ok:
            step["clicks"] = clicks
            step["wait"] = wait
            self.refresh_steps(i)
            self.log(f"Настроен шаг {step}")

    def remove_step(self):
        i = self.step_list.currentRow()
        if i >= 0:
            removed = self.steps.pop(i); self.refresh_steps(min(i, len(self.steps)-1)); self.log(f"Удалена точка {removed}")

    def move_step(self, delta):
        i = self.step_list.currentRow(); j = i + delta
        if 0 <= i < len(self.steps) and 0 <= j < len(self.steps):
            self.steps[i], self.steps[j] = self.steps[j], self.steps[i]
            self.refresh_steps(j)

    def set_running(self, running):
        for w in (self.pick_btn, self.rename_btn, self.configure_btn, self.remove_btn, self.up_btn, self.down_btn): w.setEnabled(not running)
        self.start_btn.setEnabled(not running); self.stop_btn.setEnabled(running)

    def start_run(self):
        if not self.steps:
            QMessageBox.warning(self, "Нет точек", "Добавь хотя бы одну точку ресурса."); return
        if not self.confirm.isChecked():
            QMessageBox.warning(self, "Подтверждение", "Подтверди, что это твой тестовый клиент и координаты проверены."); return
        self.runner = Runner(self.steps, self.repeats.value(), self.interval.value())
        self.runner.status.connect(self.on_status)
        self.runner.finished_run.connect(self.run_finished)
        self.set_running(True)
        self.status.setText("Статус: запуск через 2 секунды. Переключись в тестовый клиент.")
        self.log(f"Запуск сценария: {len(self.steps)} точек, {self.repeats.value()} циклов")
        self.runner.start()

    def on_status(self, message):
        self.status.setText("Статус: " + message)
        self.log(message)

    def stop_run(self):
        if self.runner and self.runner.isRunning():
            self.runner.stop(); self.status.setText("Статус: отправлена команда остановки…"); self.log("Запрошена остановка")

    def run_finished(self, message):
        self.status.setText("Статус: " + message); self.set_running(False); self.log(message)

    def save_profile(self):
        data = {"version": 2, "steps": self.steps, "repeats": self.repeats.value(), "clicks": self.clicks.value(), "gather_wait": self.wait_gather.value(), "interval": self.interval.value()}
        PROFILE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.status.setText(f"Профиль сохранён: {PROFILE_FILE}"); self.log("Профиль сохранён")

    def load_profile(self):
        if not PROFILE_FILE.exists():
            QMessageBox.information(self, "Профиль", "Сохранённых профилей пока нет."); return
        try:
            data = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
            normalized = normalize_profile(data)
            self.steps = normalized["steps"]
            self.repeats.setValue(normalized["repeats"]); self.clicks.setValue(normalized["clicks"])
            self.wait_gather.setValue(normalized["gather_wait"]); self.interval.setValue(normalized["interval"])
            self.refresh_steps(); self.status.setText("Статус: профиль загружен"); self.log("Профиль загружен")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка профиля", str(e)); self.log(f"Ошибка загрузки профиля: {e}")


if __name__ == "__main__":
    pyautogui.FAILSAFE = True  # Move mouse to upper-left corner for emergency PyAutoGUI stop.
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
