﻿# RG_Tag_Mapper.py — fixed context menus, anchor priority, Z in meters on add, multi_id only with extras
import sys, math, json, base64, os, copy, posixpath
import paramiko
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsLineItem, QMenu, QTreeWidget,
    QTreeWidgetItem, QDockWidget, QFileDialog, QToolBar, QMessageBox, QDialog,
    QFormLayout, QDialogButtonBox, QSpinBox, QDoubleSpinBox, QLineEdit, QComboBox,
    QLabel, QInputDialog, QCheckBox, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QGroupBox, QStyle, QTextBrowser, QHeaderView, QAbstractItemView
)
from PySide6.QtGui import (
    QAction, QPainter, QPen, QBrush, QColor, QPixmap, QPainterPath, QFont,
    QPdfWriter, QPageSize, QCursor, QKeySequence, QIcon, QPalette
)
from PySide6.QtCore import Qt, QRectF, QPointF, QSizeF, QBuffer, QByteArray, QTimer, QPoint, QSize
from datetime import datetime
from mutagen.mp3 import MP3

def fix_negative_zero(val):
    return 0.0 if abs(val) < 1e-9 else val

# ---------------------------------------------------------------------------
# Audio helpers and widgets
# ---------------------------------------------------------------------------
def extract_track_id(filename: str) -> int:
    name = os.path.splitext(os.path.basename(filename))[0]
    digits = ''.join(ch for ch in name if ch.isdigit())
    return int(digits) if digits else 0


def parse_additional_ids(text: str):
    ids = []
    for token in text.split(','):
        token = token.strip()
        if not token:
            continue
        try:
            ids.append(int(token))
        except ValueError:
            continue
    return ids


def load_audio_file_info(path: str):
    try:
        audio = MP3(path)
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    duration_ms = int(round(audio.info.length * 1000)) if audio.info.length else 0
    try:
        size_bytes = os.path.getsize(path)
    except OSError:
        size_bytes = 0
    with open(path, 'rb') as fh:
        encoded = base64.b64encode(fh.read()).decode('ascii')
    return {
        'filename': os.path.basename(path),
        'data': encoded,
        'duration_ms': duration_ms,
        'size': size_bytes
    }


def format_audio_menu_line(info) -> str | None:
    if not isinstance(info, dict):
        return None
    filename = info.get('filename') or "(без названия)"
    audio_line = f"Аудиотрек: {filename}"
    duration_ms = int(info.get('duration_ms') or 0)
    if duration_ms > 0:
        total_seconds = max(duration_ms // 1000, 0)
        minutes, seconds = divmod(total_seconds, 60)
        audio_line += f" ({minutes:02d}:{seconds:02d})"
    return audio_line


class AudioTrackWidget(QWidget):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.main_file_info = None
        self.secondary_file_info = None
        self.display_name = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel("Аудио трек")
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

        main_row = QWidget()
        main_row_layout = QHBoxLayout(main_row)
        main_row_layout.setContentsMargins(0, 0, 0, 0)
        main_row_layout.addWidget(QLabel("Файл:"))
        self.main_file_label = QLabel("Не выбран")
        main_row_layout.addWidget(self.main_file_label)
        main_row_layout.addStretch(1)
        self.select_button = QPushButton("Выбрать MP3…")
        self.select_button.clicked.connect(self._select_main_file)
        main_row_layout.addWidget(self.select_button)
        self.clear_main_button = QPushButton("Очистить")
        self.clear_main_button.clicked.connect(self._clear_main_file)
        main_row_layout.addWidget(self.clear_main_button)
        layout.addWidget(main_row)

        self.settings_container = QGroupBox()
        self.settings_container.setTitle("")
        self.settings_layout = QFormLayout(self.settings_container)
        self.settings_layout.setContentsMargins(0, 0, 0, 0)
        self.track_id_label = QLabel("-")
        self.settings_layout.addRow("ID трека:", self.track_id_label)

        sec_widget = QWidget()
        sec_layout = QHBoxLayout(sec_widget)
        sec_layout.setContentsMargins(0, 0, 0, 0)
        self.secondary_label = QLabel("Не выбран")
        sec_layout.addWidget(self.secondary_label)
        sec_layout.addStretch(1)
        self.secondary_button = QPushButton("Добавить MP3…")
        self.secondary_button.clicked.connect(self._select_secondary_file)
        sec_layout.addWidget(self.secondary_button)
        self.clear_secondary_button = QPushButton("Очистить")
        self.clear_secondary_button.clicked.connect(self._clear_secondary_file)
        sec_layout.addWidget(self.clear_secondary_button)
        self.settings_layout.addRow("Доп. аудиотрек:", sec_widget)

        self.extra_ids_edit = QLineEdit()
        self.extra_ids_edit.setPlaceholderText("Например: 101, 131")
        self.settings_layout.addRow("Дополнительные ID:", self.extra_ids_edit)

        self.interruptible_box = QCheckBox("Прерываемый")
        self.interruptible_box.setChecked(True)
        self.reset_box = QCheckBox("Сброс")
        self.play_once_box = QCheckBox("Играть единожды")
        flags_widget = QWidget()
        flags_layout = QHBoxLayout(flags_widget)
        flags_layout.setContentsMargins(0, 0, 0, 0)
        flags_layout.addWidget(self.interruptible_box)
        flags_layout.addWidget(self.reset_box)
        flags_layout.addWidget(self.play_once_box)
        flags_layout.addStretch(1)
        self.settings_layout.addRow(flags_widget)

        layout.addWidget(self.settings_container)

        self._update_state()
        if data:
            self.set_data(data)

    def set_data(self, data):
        if not data:
            self._clear_main_file()
            return
        self.main_file_info = {
            'filename': data.get('filename'),
            'data': data.get('data'),
            'duration_ms': data.get('duration_ms', 0),
            'size': data.get('size', 0)
        }
        self.display_name = data.get('display_name', "") if isinstance(data, dict) else ""
        self.secondary_file_info = None
        if data.get('secondary'):
            sec = data['secondary']
            self.secondary_file_info = {
                'filename': sec.get('filename'),
                'data': sec.get('data'),
                'duration_ms': sec.get('duration_ms', 0),
                'size': sec.get('size', 0)
            }
        self.extra_ids_edit.setText(', '.join(str(x) for x in data.get('extra_ids', [])))
        self.interruptible_box.setChecked(data.get('interruptible', True))
        self.reset_box.setChecked(data.get('reset', False))
        self.play_once_box.setChecked(data.get('play_once', False))
        self._update_state()

    def get_data(self):
        if not self.main_file_info:
            return None
        result = {
            'filename': self.main_file_info['filename'],
            'data': self.main_file_info['data'],
            'duration_ms': self.main_file_info.get('duration_ms', 0),
            'size': self.main_file_info.get('size', 0),
            'extra_ids': parse_additional_ids(self.extra_ids_edit.text()),
            'interruptible': self.interruptible_box.isChecked(),
            'reset': self.reset_box.isChecked(),
            'play_once': self.play_once_box.isChecked()
        }
        name_text = (self.display_name or "").strip()
        if name_text:
            result['display_name'] = name_text
        if self.secondary_file_info:
            result['secondary'] = {
                'filename': self.secondary_file_info['filename'],
                'data': self.secondary_file_info['data'],
                'duration_ms': self.secondary_file_info.get('duration_ms', 0),
                'size': self.secondary_file_info.get('size', 0)
            }
        return result

    def _select_main_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбрать аудио", "", "MP3 файлы (*.mp3)")
        if not path:
            return
        try:
            info = load_audio_file_info(path)
        except ValueError as err:
            QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить аудио:\n{err}")
            return
        self.main_file_info = info
        self.display_name = ""
        if not self.interruptible_box.isChecked():
            self.interruptible_box.setChecked(True)
        self._update_state()

    def _select_secondary_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбрать дополнительный аудио", "", "MP3 файлы (*.mp3)")
        if not path:
            return
        try:
            info = load_audio_file_info(path)
        except ValueError as err:
            QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить аудио:\n{err}")
            return
        self.secondary_file_info = info
        self._update_state()

    def _clear_main_file(self):
        self.main_file_info = None
        self.secondary_file_info = None
        self.display_name = ""
        self.extra_ids_edit.clear()
        self.interruptible_box.setChecked(True)
        self.reset_box.setChecked(False)
        self.play_once_box.setChecked(False)
        self._update_state()

    def _clear_secondary_file(self):
        self.secondary_file_info = None
        self._update_state()

    def _update_state(self):
        has_main = self.main_file_info is not None
        self.clear_main_button.setEnabled(has_main)
        self.settings_container.setVisible(has_main)
        self.secondary_button.setEnabled(has_main)
        self.clear_secondary_button.setEnabled(has_main and self.secondary_file_info is not None)
        if has_main:
            filename = self.main_file_info.get('filename', 'Не выбран')
            self.main_file_label.setText(filename)
            self.track_id_label.setText(filename)
        else:
            self.main_file_label.setText("Не выбран")
            self.track_id_label.setText("-")
        if self.secondary_file_info:
            self.secondary_label.setText(self.secondary_file_info.get('filename', ''))
        else:
            self.secondary_label.setText("Не выбран")

# ---------------------------------------------------------------------------
# Track list dock
# ---------------------------------------------------------------------------
class TracksListWidget(QWidget):
    HEADER_LABELS = [
        "Зал / Трек",
        "Аудиофайл",
        "Играть единожды",
        "Сброс",
        "Прерываемый",
        "Номер зала",
        "Доп. ID",
        "Имя",
    ]

    def __init__(self, mainwindow):
        super().__init__(mainwindow)
        self.mainwindow = mainwindow
        self._updating = False
        self._pending_snapshot = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(len(self.HEADER_LABELS))
        self.tree.setHeaderLabels(self.HEADER_LABELS)
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.setStyleSheet(
            """
            QTreeWidget { background-color: transparent; }
            QTreeWidget QLineEdit {
                background-color: #ffffff;
                color: #000000;
                selection-background-color: palette(highlight);
                selection-color: palette(highlighted-text);
            }
            """
        )

        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(24)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.Interactive)

        self._adjust_audio_column_width()
        self._adjust_name_column_width()

        layout.addWidget(self.tree)

    def refresh(self):
        if not hasattr(self.mainwindow, "halls"):
            return
        self._updating = True
        try:
            self.tree.clear()
            halls = sorted(
                self.mainwindow.halls,
                key=lambda h: self._normalize_sort_key(getattr(h, "number", 0))
            )
            if not halls:
                return
            for hall in halls:
                hall_title = f"Зал {hall.number}"
                if hall.name:
                    hall_title += f" — {hall.name}"
                hall_item = QTreeWidgetItem([hall_title])
                hall_item.setData(0, Qt.UserRole, {"type": "hall", "hall": hall.number})
                hall_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.tree.addTopLevelItem(hall_item)
                hall_item.setFirstColumnSpanned(True)
                hall_item.setExpanded(True)

                if hall.audio_settings:
                    self._add_track_item(hall_item, hall, hall.audio_settings, True, None)

                for track_id, info in self._sorted_track_items(hall.zone_audio_tracks):
                    self._add_track_item(hall_item, hall, info, False, track_id)
        finally:
            self._updating = False
        self._adjust_name_column_width()

    @staticmethod
    def _normalize_sort_key(value):
        try:
            return 0, int(value)
        except (TypeError, ValueError):
            return 1, str(value)

    def _sorted_track_items(self, track_map):
        if not track_map:
            return []
        try:
            items = list(track_map.items())
        except AttributeError:
            return []
        items.sort(key=lambda item: self._normalize_sort_key(item[0]))
        return items

    def _add_track_item(self, parent_item, hall, info, is_hall_track, track_id):
        if not isinstance(info, dict):
            return
        item = QTreeWidgetItem(parent_item)
        title = f"Зал {hall.number}: основной трек" if is_hall_track else f"Зона {track_id}"
        item.setText(0, title)
        item.setText(1, str(info.get('filename', '') or ''))
        item.setText(2, "")
        item.setText(3, "")
        item.setText(4, "")
        item.setText(5, str(hall.number))
        item.setText(6, "")
        item.setText(7, str(info.get('display_name', '') or ''))

        extras = info.get('extra_ids') if isinstance(info.get('extra_ids'), list) else []
        extras_text = ", ".join(str(x) for x in extras)
        item.setText(6, extras_text)

        item.setCheckState(2, Qt.Checked if info.get('play_once') else Qt.Unchecked)
        item.setCheckState(3, Qt.Checked if info.get('reset') else Qt.Unchecked)
        item.setCheckState(4, Qt.Checked if info.get('interruptible', True) else Qt.Unchecked)

        payload = {
            "type": "track",
            "hall": hall.number,
            "is_hall_track": is_hall_track
        }
        if not is_hall_track:
            payload["track_id"] = track_id
        item.setData(0, Qt.UserRole, payload)
        item.setData(5, Qt.UserRole, hall.number)

        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable | Qt.ItemIsUserCheckable
        item.setFlags(flags)

    def _resolve_track(self, payload):
        hall_number = payload.get("hall")
        hall = next((h for h in self.mainwindow.halls if h.number == hall_number), None)
        if hall is None:
            return None, None, None
        if payload.get("is_hall_track"):
            return hall, hall.audio_settings, None
        track_id = payload.get("track_id")
        return hall, hall.zone_audio_tracks.get(track_id), track_id

    def _ensure_snapshot(self):
        if self._pending_snapshot is None:
            self._pending_snapshot = self.mainwindow.capture_state()

    def _commit_snapshot(self):
        if self._pending_snapshot is None:
            return
        self.mainwindow.push_undo_state(self._pending_snapshot)
        self._pending_snapshot = None

    def _on_item_changed(self, item, column):
        if self._updating:
            return
        payload = item.data(0, Qt.UserRole)
        if not isinstance(payload, dict) or payload.get("type") != "track":
            return

        if column == 1:
            changed = self._handle_filename_change(payload, item.text(1))
        elif column == 2:
            changed = self._handle_flag_change(payload, 'play_once', item.checkState(2), False)
        elif column == 3:
            changed = self._handle_flag_change(payload, 'reset', item.checkState(3), False)
        elif column == 4:
            changed = self._handle_flag_change(payload, 'interruptible', item.checkState(4), True)
        elif column == 5:
            changed = self._handle_hall_number_change(payload, item.text(5))
        elif column == 6:
            changed = self._handle_extra_ids_change(payload, item.text(6))
        elif column == 7:
            changed = self._handle_display_name_change(payload, item.text(7))
        else:
            changed = False

        self.refresh()
        if changed:
            self._commit_snapshot()
        else:
            self._pending_snapshot = None

    def _adjust_audio_column_width(self):
        header = self.tree.header()
        metrics = header.fontMetrics()
        label = self.HEADER_LABELS[1]
        width = metrics.horizontalAdvance(label) + 20
        header.resizeSection(1, width)

    def _adjust_name_column_width(self):
        header = self.tree.header()
        metrics = header.fontMetrics()
        label_width = metrics.horizontalAdvance(self.HEADER_LABELS[-1]) + 20

        max_text_width = 0

        def _iterate(item):
            nonlocal max_text_width
            max_text_width = max(max_text_width, metrics.horizontalAdvance(item.text(7)))
            for idx in range(item.childCount()):
                _iterate(item.child(idx))

        for index in range(self.tree.topLevelItemCount()):
            _iterate(self.tree.topLevelItem(index))

        base_width = max(label_width, int(metrics.averageCharWidth() * 18))
        if max_text_width:
            base_width = max(base_width, max_text_width + 20)
        header.resizeSection(7, base_width)

    def _handle_filename_change(self, payload, new_value):
        hall, info, _ = self._resolve_track(payload)
        if info is None:
            return False
        new_name = (new_value or "").strip()
        current = info.get('filename', '') or ''
        if not new_name:
            QMessageBox.warning(self, "Ошибка", "Название аудиофайла не может быть пустым.")
            return False
        if new_name == current:
            return False
        self._ensure_snapshot()
        info['filename'] = new_name
        return True

    def _handle_display_name_change(self, payload, new_value):
        hall, info, _ = self._resolve_track(payload)
        if info is None:
            return False
        new_name = (new_value or "").strip()
        current = info.get('display_name', '') or ''
        if new_name == current:
            return False
        self._ensure_snapshot()
        if new_name:
            info['display_name'] = new_name
        elif 'display_name' in info:
            info.pop('display_name', None)
        return True

    def _handle_flag_change(self, payload, key, state, default):
        hall, info, _ = self._resolve_track(payload)
        if info is None:
            return False
        new_value = state == Qt.Checked
        current_value = info.get(key, default)
        if bool(current_value) == new_value and (key in info or new_value == default):
            return False
        self._ensure_snapshot()
        info[key] = new_value
        return True

    def _handle_hall_number_change(self, payload, value):
        hall, info, track_id = self._resolve_track(payload)
        if hall is None or info is None:
            return False
        try:
            new_hall_number = int(str(value).strip())
        except (TypeError, ValueError):
            QMessageBox.warning(self, "Ошибка", "Номер зала должен быть числом.")
            return False
        if new_hall_number == hall.number:
            return False
        target = next((h for h in self.mainwindow.halls if h.number == new_hall_number), None)
        if target is None:
            QMessageBox.warning(self, "Ошибка", f"Зал с номером {new_hall_number} не найден.")
            return False
        self._ensure_snapshot()
        if payload.get('is_hall_track'):
            hall.audio_settings = None
            target.audio_settings = info
        else:
            hall.zone_audio_tracks.pop(track_id, None)
            target.zone_audio_tracks[track_id] = info
        return True

    def _handle_extra_ids_change(self, payload, text):
        hall, info, _ = self._resolve_track(payload)
        if info is None:
            return False
        parsed = parse_additional_ids(text or "")
        current = info.get('extra_ids', [])
        if parsed == current:
            return False
        self._ensure_snapshot()
        info['extra_ids'] = parsed
        return True

# ---------------------------------------------------------------------------
# Universal parameter dialog
# ---------------------------------------------------------------------------
class ParamDialog(QDialog):
    def __init__(self, title, fields, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.widgets = {}
        layout = QFormLayout(self)
        for f in fields:
            lbl, t, d = f["label"], f["type"], f.get("default")
            if t == "int":
                w = QSpinBox()
                w.setRange(f.get("min", 0), f.get("max", 10000))
                w.setValue(d or 0)
            elif t == "float":
                w = QDoubleSpinBox()
                w.setRange(f.get("min", 0.0), f.get("max", 10000.0))
                w.setDecimals(f.get("decimals", 1))
                w.setValue(d or 0.0)
            elif t == "string":
                w = QLineEdit()
                if d is not None:
                    w.setText(str(d))
            elif t == "combo":
                w = QComboBox()
                for o in f.get("options", []):
                    w.addItem(o)
                if d in f.get("options", []):
                    w.setCurrentIndex(f["options"].index(d))
            elif t == "bool":
                w = QCheckBox()
                w.setChecked(bool(d))
            else:
                w = QLineEdit()
            self.widgets[lbl] = w
            layout.addRow(QLabel(lbl), w)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def getValues(self):
        out = {}
        for lbl, w in self.widgets.items():
            if isinstance(w, (QSpinBox, QDoubleSpinBox)):
                out[lbl] = w.value()
            elif isinstance(w, QLineEdit):
                out[lbl] = w.text()
            elif isinstance(w, QComboBox):
                out[lbl] = w.currentText()
            elif isinstance(w, QCheckBox):
                out[lbl] = w.isChecked()
            else:
                out[lbl] = w.text()
        return out

# ---------------------------------------------------------------------------
# Dialog to lock objects
# ---------------------------------------------------------------------------
class LockDialog(QDialog):
    def __init__(self, lh, lz, la, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Закрепить объекты")
        layout = QFormLayout(self)
        self.cb_h = QCheckBox("Закрепить залы"); self.cb_h.setChecked(lh)
        self.cb_z = QCheckBox("Закрепить зоны"); self.cb_z.setChecked(lz)
        self.cb_a = QCheckBox("Закрепить якоря"); self.cb_a.setChecked(la)
        layout.addRow(self.cb_h); layout.addRow(self.cb_z); layout.addRow(self.cb_a)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def values(self):
        return self.cb_h.isChecked(), self.cb_z.isChecked(), self.cb_a.isChecked()

# ---------------------------------------------------------------------------
# Initial parameter getters
# ---------------------------------------------------------------------------
def getHallParameters(default_num=1, default_name="", default_w=1.0, default_h=1.0, scene=None):
    fields = [
        {"label": "Номер зала", "type": "int", "default": default_num, "min": 0, "max": 10000},
        {"label": "Название зала", "type": "string", "default": default_name},
        {"label": "Ширина (м)", "type": "float", "default": default_w, "min": 0.1, "max": 1000.0, "decimals":1},
        {"label": "Высота (м)", "type": "float", "default": default_h, "min": 0.1, "max": 1000.0, "decimals":1}
    ]
    dlg = ParamDialog("Введите параметры зала", fields)
    if dlg.exec() == QDialog.Accepted:
        v = dlg.getValues()
        return v["Номер зала"], v["Название зала"], v["Ширина (м)"], v["Высота (м)"]
    return None

# Z ВВОДИМ В МЕТРАХ
def getAnchorParameters(default_num=1, default_z_m=0.0, default_extras="", default_bound=False):
    fields = [
        {"label": "Номер якоря", "type": "int", "default": default_num, "min": 0, "max": 10000},
        {"label": "Координата Z (м)", "type": "float", "default": default_z_m, "min": -100.0, "max": 100.0, "decimals": 1},
        {"label": "Дополнительные залы (через запятую)", "type": "string", "default": default_extras},
        {"label": "Переходный", "type": "bool", "default": default_bound}
    ]
    dlg = ParamDialog("Введите параметры якоря", fields)
    if dlg.exec() == QDialog.Accepted:
        v = dlg.getValues()
        extras = [int(tok) for tok in v["Дополнительные залы (через запятую)"].split(",") if tok.strip().isdigit()]
        return v["Номер якоря"], float(v["Координата Z (м)"]), extras, v["Переходный"]
    return None

def getZoneParameters(default_num=1, default_type="Входная зона", default_angle=0):
    dt = default_type.replace(" зона", "")
    fields = [
        {"label": "Номер зоны", "type": "int", "default": default_num, "min": 0, "max": 10000},
        {"label": "Тип зоны", "type": "combo", "default": dt, "options": ["Входная", "Выходная", "Переходная"]},
        {"label": "Угол поворота (°)", "type": "int", "default": default_angle, "min": -90, "max": 90}
    ]
    dlg = ParamDialog("Введите параметры зоны", fields)
    if dlg.exec() == QDialog.Accepted:
        v = dlg.getValues()
        zt = v["Тип зоны"]
        full = {"Входная":"Входная зона","Выходная":"Выходная зона","Переходная":"Переходная"}[zt]
        return v["Номер зоны"], full, v["Угол поворота (°)"]
    return None

# ---------------------------------------------------------------------------
# Edit dialogs with audio controls
# ---------------------------------------------------------------------------
class HallEditDialog(QDialog):
    def __init__(self, hall_item, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Редактировать зал")
        layout = QVBoxLayout(self)

        form = QFormLayout()
        layout.addLayout(form)

        self.num_spin = QSpinBox()
        self.num_spin.setRange(0, 10000)
        self.num_spin.setValue(hall_item.number)
        form.addRow("Номер зала", self.num_spin)

        self.name_edit = QLineEdit()
        self.name_edit.setText(hall_item.name)
        form.addRow("Название зала", self.name_edit)

        ppcm = hall_item.scene().pixel_per_cm_x if hall_item.scene() else 1.0
        width_m = hall_item.rect().width()/(ppcm*100)
        height_m = hall_item.rect().height()/(ppcm*100)

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setDecimals(1)
        self.width_spin.setRange(0.1, 1000.0)
        self.width_spin.setValue(width_m)
        form.addRow("Ширина (м)", self.width_spin)

        self.height_spin = QDoubleSpinBox()
        self.height_spin.setDecimals(1)
        self.height_spin.setRange(0.1, 1000.0)
        self.height_spin.setValue(height_m)
        form.addRow("Высота (м)", self.height_spin)

        self.audio_widget = AudioTrackWidget(self, hall_item.audio_settings)
        layout.addWidget(self.audio_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        return {
            'number': self.num_spin.value(),
            'name': self.name_edit.text(),
            'width': self.width_spin.value(),
            'height': self.height_spin.value(),
            'audio': self.audio_widget.get_data()
        }


class ZoneEditDialog(QDialog):
    def __init__(self, zone_item, audio_data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Редактировать зону")
        layout = QVBoxLayout(self)

        form = QFormLayout()
        layout.addLayout(form)

        self.num_spin = QSpinBox()
        self.num_spin.setRange(0, 10000)
        self.num_spin.setValue(zone_item.zone_num)
        form.addRow("Номер зоны", self.num_spin)

        self.type_combo = QComboBox()
        options = ["Входная", "Выходная", "Переходная"]
        for opt in options:
            self.type_combo.addItem(opt)
        current = zone_item.zone_type.replace(" зона", "")
        if current in options:
            self.type_combo.setCurrentIndex(options.index(current))
        form.addRow("Тип зоны", self.type_combo)

        data = zone_item.get_export_data() or {"x":0.0,"y":0.0,"w":0.0,"h":0.0,"angle":0}

        self.x_spin = QDoubleSpinBox()
        self.x_spin.setDecimals(1)
        self.x_spin.setRange(-1000.0, 1000.0)
        self.x_spin.setValue(data['x'])

        self.y_spin = QDoubleSpinBox()
        self.y_spin.setDecimals(1)
        self.y_spin.setRange(-1000.0, 1000.0)
        self.y_spin.setValue(data['y'])

        self.w_spin = QDoubleSpinBox()
        self.w_spin.setDecimals(1)
        self.w_spin.setRange(0.0, 1000.0)
        self.w_spin.setValue(data['w'])

        self.h_spin = QDoubleSpinBox()
        self.h_spin.setDecimals(1)
        self.h_spin.setRange(0.0, 1000.0)
        self.h_spin.setValue(data['h'])

        form.addRow("Координата X (м)", self.x_spin)
        form.addRow("Координата Y (м)", self.y_spin)
        form.addRow("Ширина (м)", self.w_spin)
        form.addRow("Высота (м)", self.h_spin)

        self.angle_spin = QSpinBox()
        self.angle_spin.setRange(-90, 90)
        self.angle_spin.setValue(int(data['angle']))
        form.addRow("Угол поворота (°)", self.angle_spin)

        self._stored_audio_data = copy.deepcopy(audio_data) if audio_data else None
        self.audio_widget = AudioTrackWidget(self, audio_data)
        layout.addWidget(self.audio_widget)

        self._audio_controls_enabled = False
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        self._on_type_changed(self.type_combo.currentText())

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        full_type = {"Входная": "Входная зона", "Выходная": "Выходная зона", "Переходная": "Переходная"}[self.type_combo.currentText()]
        audio_data = self.audio_widget.get_data() if self._audio_controls_enabled else self._stored_audio_data
        if audio_data:
            audio_data = copy.deepcopy(audio_data)
            self._stored_audio_data = copy.deepcopy(audio_data)
        else:
            self._stored_audio_data = None
        return {
            'zone_num': self.num_spin.value(),
            'zone_type': full_type,
            'x': self.x_spin.value(),
            'y': self.y_spin.value(),
            'w': self.w_spin.value(),
            'h': self.h_spin.value(),
            'angle': self.angle_spin.value(),
            'audio': audio_data
        }

    def _on_type_changed(self, text: str):
        is_entry_zone = text == "Входная"
        if is_entry_zone:
            if not self._audio_controls_enabled:
                if self._stored_audio_data:
                    self.audio_widget.set_data(copy.deepcopy(self._stored_audio_data))
                else:
                    self.audio_widget.set_data(None)
            self.audio_widget.setVisible(True)
            self.audio_widget.setEnabled(True)
            self._audio_controls_enabled = True
        else:
            if self._audio_controls_enabled:
                self._stored_audio_data = self.audio_widget.get_data()
            self.audio_widget.setVisible(False)
            self.audio_widget.setEnabled(False)
            self._audio_controls_enabled = False

# ---------------------------------------------------------------------------
# HallItem
# ---------------------------------------------------------------------------
class HallItem(QGraphicsRectItem):
    def __init__(self, x, y, w_px, h_px, name="", number=0, scene=None):
        super().__init__(0, 0, w_px, h_px)
        self.setPos(x, y)
        self.name, self.number = name, number
        self.scene_ref = scene
        self.setPen(QPen(QColor(0,0,255),2)); self.setBrush(QColor(0,0,255,50))
        self.setFlags(QGraphicsItem.ItemIsMovable|QGraphicsItem.ItemIsSelectable|QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(-w_px*h_px); self.tree_item = None
        self.audio_settings = None
        self.zone_audio_tracks = {}
        self._undo_snapshot = None
        self._undo_initial_pos = None

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        painter.save()
        font = QFont(); font.setBold(True); painter.setFont(font)
        fill = self.pen().color(); outline = QColor(180,180,180)
        rect = self.rect()
        pos = rect.bottomLeft() + QPointF(2,-2)
        path = QPainterPath(); path.addText(pos, font, str(self.number))
        painter.setPen(QPen(outline,2)); painter.drawPath(path); painter.fillPath(path, fill)
        painter.restore()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            new = QPointF(value)
            sr = self.scene().sceneRect(); r = self.rect()
            new.setX(max(sr.left(), min(new.x(), sr.right()-r.width())))
            new.setY(max(sr.top(), min(new.y(), sr.bottom()-r.height())))
            step = self.scene().pixel_per_cm_x * self.scene().grid_step_cm
            if step>0:
                new.setX(round(new.x()/step)*step)
                new.setY(round(new.y()/step)*step)
            delta = new - self.pos()
            if not delta.isNull():
                scene = self.scene()
                if scene:
                    mw = getattr(scene, "mainwindow", None)
                    if mw:
                        for anchor in mw.anchors:
                            if anchor.main_hall_number == self.number or self.number in anchor.extra_halls:
                                anchor.moveBy(delta.x(), delta.y())
            return new
        return super().itemChange(change, value)

    # Unified menu
    def open_menu(self, global_pos: QPoint):
        if not self.scene(): return
        mw = self.scene().mainwindow
        ppcm = self.scene().pixel_per_cm_x
        menu = QMenu()
        hall_title = f"Зал {self.number}"
        if self.name:
            hall_title += f" — {self.name}"
        header = menu.addAction(hall_title); header.setEnabled(False)
        audio_info_text = self._get_audio_info_text()
        if audio_info_text:
            audio_line = menu.addAction(audio_info_text)
            audio_line.setEnabled(False)
        edit = menu.addAction("Редактировать зал")
        delete = menu.addAction("Удалить зал")
        act = menu.exec(global_pos)
        if act == edit:
            dlg = HallEditDialog(self, mw)
            if dlg.exec() == QDialog.Accepted:
                prev_state = mw.capture_state()
                values = dlg.values()
                new_num = values['number']
                new_name = values['name']
                new_w_m = values['width']
                new_h_m = values['height']
                self.audio_settings = values['audio']
                old = self.number
                for a in mw.anchors:
                    if a.main_hall_number == old:
                        a.main_hall_number = new_num
                    a.extra_halls = [new_num if x==old else x for x in a.extra_halls]
                self.number, self.name = new_num, new_name
                w_px = new_w_m * ppcm * 100
                h_px = new_h_m * ppcm * 100
                self.prepareGeometryChange()
                self.setRect(0, 0, w_px, h_px)
                self.setZValue(-w_px*h_px)
                mw.last_selected_items = []
                mw.populate_tree()
                mw.push_undo_state(prev_state)
        elif act == delete:
            anchors_rel = [a for a in mw.anchors if a.main_hall_number==self.number or self.number in a.extra_halls]
            zones_rel = [z for z in self.childItems() if isinstance(z, RectZoneItem)]
            if anchors_rel or zones_rel:
                cnt_a, cnt_z = len(anchors_rel), len(zones_rel)
                resp = QMessageBox.question(mw, "Подтвердить",
                                            f"В зале {self.number} {cnt_a} якорей и {cnt_z} зон.\nУдалить?",
                                            QMessageBox.Yes|QMessageBox.No)
                if resp != QMessageBox.Yes:
                    return
            prev_state = mw.capture_state()
            for z in zones_rel:
                z.scene().removeItem(z)
            for a in anchors_rel:
                if a.main_hall_number == self.number:
                    if a.extra_halls:
                        a.main_hall_number = a.extra_halls.pop(0)
                    else:
                        mw.anchors.remove(a); a.scene().removeItem(a)
                else:
                    a.extra_halls.remove(self.number)
            mw.halls.remove(self); self.scene().removeItem(self)
            mw.last_selected_items = []; mw.populate_tree()
            mw.push_undo_state(prev_state)

    def _get_audio_info_text(self) -> str | None:
        return format_audio_menu_line(self.audio_settings)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.scene():
            anchor = _top_anchor(self.scene(), event.scenePos())
            if anchor:
                event.ignore()
                return
            zone = _smallest_zone(self.scene(), event.scenePos())
            if zone:
                event.ignore()
                return
            mw = self.scene().mainwindow
            if mw and not getattr(mw, "_restoring_state", False):
                self._undo_initial_pos = QPointF(self.pos())
                self._undo_snapshot = mw.capture_state()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.scene():
            anchor = _top_anchor(self.scene(), event.scenePos())
            if anchor:
                anchor.open_menu(event.screenPos())
                event.accept()
                return
            zone = _smallest_zone(self.scene(), event.scenePos())
            if zone:
                zone.open_menu(event.screenPos())
                event.accept()
                return
        self.open_menu(event.screenPos())
        event.accept()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton and self.scene():
            if self._undo_snapshot is not None and self._undo_initial_pos is not None:
                if self.pos() != self._undo_initial_pos:
                    mw = self.scene().mainwindow
                    if mw:
                        mw.push_undo_state(self._undo_snapshot)
        self._undo_snapshot = None
        self._undo_initial_pos = None

    def contextMenuEvent(self, event):
        # ПКМ: приоритет — якорь, затем (внутренняя) зона, затем зал
        if self.scene():
            anchor = _top_anchor(self.scene(), event.scenePos())
            if anchor:
                anchor.open_menu(event.screenPos())
                event.accept()
                return
            zone = _smallest_zone(self.scene(), event.scenePos())
            if zone:
                zone.open_menu(event.screenPos())
                event.accept()
                return
        self.open_menu(event.screenPos())
        event.accept()

# ---------------------------------------------------------------------------
# AnchorItem
# ---------------------------------------------------------------------------
class AnchorItem(QGraphicsEllipseItem):
    def __init__(self, x, y, number=0, main_hall_number=None, scene=None):
        r = 3
        super().__init__(-r,-r,2*r,2*r)
        self.setPos(x,y); self.number = number; self.z = 0
        self.main_hall_number = main_hall_number; self.extra_halls = []; self.bound = False
        self.setPen(QPen(QColor(255,0,0),2)); self.setBrush(QBrush(QColor(255,0,0)))
        self.setFlags(QGraphicsItem.ItemIsMovable|QGraphicsItem.ItemIsSelectable|QGraphicsItem.ItemSendsGeometryChanges)
        self.tree_item = None
        self.update_zvalue()
        self._undo_snapshot = None
        self._undo_initial_pos = None

    def update_zvalue(self):
        anchor_number = float(self.number) if isinstance(self.number, (int, float)) else 0.0
        self.setZValue(10000.0 + anchor_number * 0.001)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        painter.save()
        font = QFont(); font.setBold(True); painter.setFont(font)
        fill = self.pen().color(); outline = QColor(180,180,180)
        br = self.boundingRect()
        pos = QPointF(br.center().x()-br.width()/2, br.top()-4)
        path = QPainterPath(); path.addText(pos, font, str(self.number))
        painter.setPen(QPen(outline,2)); painter.drawPath(path); painter.fillPath(path, fill)
        painter.restore()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            new = QPointF(value)
            step = self.scene().pixel_per_cm_x * self.scene().grid_step_cm
            if step>0:
                new.setX(round(new.x()/step)*step)
                new.setY(round(new.y()/step)*step)
            return new
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.update_zvalue()
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.update_zvalue()
            scene = self.scene()
            if scene and not (event.modifiers() & Qt.ControlModifier):
                scene.clearSelection()
            self.setSelected(True)
            if scene:
                mw = scene.mainwindow
                if mw and not getattr(mw, "_restoring_state", False):
                    self._undo_initial_pos = QPointF(self.scenePos())
                    self._undo_snapshot = mw.capture_state()
        super().mousePressEvent(event)
        event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.update_zvalue()
        super().mouseMoveEvent(event)
        event.accept()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.update_zvalue()
        if event.button() == Qt.LeftButton and self.scene():
            if self._undo_snapshot is not None and self._undo_initial_pos is not None:
                if self.scenePos() != self._undo_initial_pos:
                    mw = self.scene().mainwindow
                    if mw:
                        mw.push_undo_state(self._undo_snapshot)
        self._undo_snapshot = None
        self._undo_initial_pos = None
        event.accept()

    def mouseDoubleClickEvent(self, event):
        # Всегда открываем меню якоря при двойном клике по якорю
        self.update_zvalue()
        self.open_menu(event.screenPos())
        event.accept()

    def contextMenuEvent(self, event):
        # ПКМ на якоре — его же меню, даже если он перекрыт другими
        self.update_zvalue()
        self.open_menu(event.screenPos())
        event.accept()

    def open_menu(self, global_pos: QPoint):
        if not self.scene(): return
        mw = self.scene().mainwindow
        hall = next((h for h in mw.halls if h.number==self.main_hall_number), None)
        if not hall: return
        ppcm = self.scene().pixel_per_cm_x
        local = hall.mapFromScene(self.scenePos())
        x_m = round(local.x()/(ppcm*100),1)
        y_m = round((hall.rect().height()-local.y())/(ppcm*100),1)
        z_m = round(self.z/100.0,1)
        ids = [str(self.main_hall_number)] + [str(x) for x in self.extra_halls]
        halls_str = ("зал "+ids[0] if len(ids)==1 else "залы "+",".join(ids))

        menu = QMenu()
        header = menu.addAction(f"Якорь {self.number} ({halls_str})"); header.setEnabled(False)
        edit = menu.addAction("Редактировать"); delete = menu.addAction("Удалить")
        act = menu.exec(global_pos)
        if act == edit:
            fields = [
                {"label": "Номер якоря", "type": "int", "default": self.number, "min": 0, "max": 10000},
                {"label":"Координата X (м)","type":"float","default":x_m,"min":-1000.0,"max":10000,"decimals":1},
                {"label":"Координата Y (м)","type":"float","default":y_m,"min":-1000.0,"max":10000,"decimals":1},
                {"label":"Координата Z (м)","type":"float","default":z_m,"min":-100,"max":100,"decimals":1},
                {"label":"Доп. залы","type":"string","default":",".join(str(x) for x in self.extra_halls)},
                {"label":"Переходный","type":"bool","default":self.bound}
            ]
            dlg = ParamDialog("Редактировать якорь", fields, mw)
            if dlg.exec() == QDialog.Accepted:
                prev_state = mw.capture_state()
                v = dlg.getValues()
                self.number = v["Номер якоря"]
                x2, y2, z2 = v["Координата X (м)"], v["Координата Y (м)"], v["Координата Z (м)"]
                self.bound = v["Переходный"]
                self.extra_halls = [int(tok) for tok in v["Доп. залы"].split(",") if tok.strip().isdigit()]
                self.z = int(round(z2*100))
                px = x2 * ppcm * 100
                py = hall.rect().height() - y2 * ppcm * 100
                self.setPos(hall.mapToScene(QPointF(px, py)))
                self.update_zvalue()
                mw.last_selected_items = []; mw.populate_tree()
                mw.push_undo_state(prev_state)
        elif act == delete:
            confirm = QMessageBox.question(
                mw,
                "Подтвердить",
                f"Удалить якорь {self.number} ({halls_str})?",
                QMessageBox.Yes | QMessageBox.No
            )
            if confirm != QMessageBox.Yes:
                return
            prev_state = mw.capture_state()
            mw.anchors.remove(self); self.scene().removeItem(self)
            mw.last_selected_items = []; mw.populate_tree()
            mw.push_undo_state(prev_state)

# ---------------------------------------------------------------------------
# ZoneItem
# ---------------------------------------------------------------------------
class RectZoneItem(QGraphicsRectItem):
    _ZONE_RGB = {
        "Входная зона": (0, 128, 0),
        "Входная": (0, 128, 0),
        "Выходная зона": (128, 0, 128),
        "Выходная": (128, 0, 128),
        "Переходная": (0, 102, 204),
        "Переходная зона": (0, 102, 204),
    }

    def __init__(self, bl, w, h, zone_num=0, zone_type="Входная зона", angle=0, parent_hall=None):
        super().__init__(0, -h, w, h, parent_hall)
        self.zone_num, self.zone_type, self.zone_angle = zone_num, zone_type, angle
        self.setTransformOriginPoint(0,0); self.setRotation(-angle); self.setPos(bl)
        self._apply_zone_palette()
        self.setFlags(QGraphicsItem.ItemIsMovable|QGraphicsItem.ItemIsSelectable|QGraphicsItem.ItemSendsGeometryChanges)
        self.tree_item = None
        self.update_zvalue()
        self._undo_snapshot = None
        self._undo_initial_pos = None

    def update_zvalue(self):
        hall = self.parentItem()
        hall_number = hall.number if isinstance(hall, HallItem) and hasattr(hall, 'number') else 0
        zone_number = self.zone_num if isinstance(self.zone_num, (int, float)) else 0
        self.setZValue(5000.0 + float(hall_number) * 0.1 + float(zone_number) * 0.001)

    def _apply_zone_palette(self):
        rgb = self._ZONE_RGB.get(self.zone_type)
        if not rgb:
            rgb = self._ZONE_RGB["Входная зона"]
        base_color = QColor(*rgb)
        self.setPen(QPen(base_color, 2))
        fill_color = QColor(base_color)
        fill_color.setAlpha(50)
        self.setBrush(QBrush(fill_color))

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        painter.save()
        font = QFont(); font.setBold(True); painter.setFont(font)
        fill = self.pen().color(); outline = QColor(180,180,180)
        rect = self.rect()
        pos = rect.bottomLeft() + QPointF(2,-2)
        path = QPainterPath(); path.addText(pos, font, str(self.zone_num))
        painter.setPen(QPen(outline,2)); painter.drawPath(path); painter.fillPath(path, fill)
        painter.restore()

    def get_display_type(self):
        return {"Входная зона":"входная","Выходная зона":"выходная","Переходная":"переходная"}[self.zone_type]

    def get_export_data(self):
        scene = self.scene(); hall = self.parentItem()
        if not scene or not hall: return None
        ppcm = scene.pixel_per_cm_x
        pos = self.pos(); hh = hall.rect().height()
        return {
            "x": fix_negative_zero(round(pos.x()/(ppcm*100),1)),
            "y": fix_negative_zero(round((hh-pos.y())/(ppcm*100),1)),
            "w": fix_negative_zero(round(self.rect().width()/(ppcm*100),1)),
            "h": fix_negative_zero(round(self.rect().height()/(ppcm*100),1)),
            "angle": fix_negative_zero(round(self.zone_angle,1))
        }

    def open_menu(self, global_pos: QPoint):
        scene = self.scene(); 
        if not scene: return
        mw = scene.mainwindow
        data = self.get_export_data()
        if data is None: return
        menu = QMenu()
        hall = self.parentItem()
        hall_suffix = ""
        if isinstance(hall, HallItem):
            hall_suffix = f" — зал {hall.number}"
        header = menu.addAction(f"Зона {self.zone_num} ({self.get_display_type()}){hall_suffix}"); header.setEnabled(False)
        audio_info = None
        if isinstance(hall, HallItem):
            audio_info = hall.zone_audio_tracks.get(self.zone_num)
        if (
            not audio_info
            and self.zone_type in ("Переходная", "Переходная зона")
            and mw
        ):
            for candidate in mw.halls:
                same_number = candidate.number == self.zone_num
                if not same_number:
                    try:
                        same_number = int(candidate.number) == int(self.zone_num)
                    except (TypeError, ValueError):
                        same_number = False
                if same_number and candidate.audio_settings:
                    audio_info = candidate.audio_settings
                    break
        if audio_info:
            audio_line = format_audio_menu_line(audio_info)
            if audio_line:
                track_action = menu.addAction(audio_line)
                track_action.setEnabled(False)
        edit = menu.addAction("Редактировать"); delete = menu.addAction("Удалить")
        act = menu.exec(global_pos)
        if act == edit:
            hall = self.parentItem()
            if not hall:
                return
            current_audio = hall.zone_audio_tracks.get(self.zone_num) if hall else None
            dlg = ZoneEditDialog(self, current_audio, mw)
            if dlg.exec() == QDialog.Accepted:
                prev_state = mw.capture_state()
                values = dlg.values()
                old_num = self.zone_num
                self.zone_num = values['zone_num']
                self.zone_type = values['zone_type']
                self.zone_angle = values['angle']
                self.update_zvalue()
                self._apply_zone_palette()
                ppcm = scene.pixel_per_cm_x
                w_px = values['w'] * ppcm * 100
                h_px = values['h'] * ppcm * 100
                self.prepareGeometryChange()
                self.setRect(0, -h_px, w_px, h_px)
                self.setTransformOriginPoint(0,0)
                self.setRotation(-self.zone_angle)
                px = values['x'] * ppcm * 100
                py = hall.rect().height() - values['y'] * ppcm * 100
                self.setPos(QPointF(px, py))
                self.update_zvalue()
                audio_data = values['audio']
                if audio_data:
                    hall.zone_audio_tracks[self.zone_num] = audio_data
                else:
                    hall.zone_audio_tracks.pop(self.zone_num, None)
                if old_num != self.zone_num:
                    others = [z for z in hall.childItems() if isinstance(z, RectZoneItem) and z.zone_num == old_num and z is not self]
                    if not others:
                        hall.zone_audio_tracks.pop(old_num, None)
                mw.last_selected_items = []
                mw.populate_tree()
                mw.push_undo_state(prev_state)
        elif act == delete:
            confirm = QMessageBox.question(
                mw,
                "Подтвердить",
                f"Удалить зону {self.zone_num} ({self.get_display_type()})?",
                QMessageBox.Yes | QMessageBox.No
            )
            if confirm != QMessageBox.Yes:
                return
            prev_state = mw.capture_state()
            hall = self.parentItem()
            if hall:
                others = [z for z in hall.childItems() if isinstance(z, RectZoneItem) and z.zone_num == self.zone_num and z is not self]
                if not others:
                    hall.zone_audio_tracks.pop(self.zone_num, None)
            scene.removeItem(self)
            mw.last_selected_items = []; mw.populate_tree()
            mw.push_undo_state(prev_state)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.scene():
            anchor = _top_anchor(self.scene(), event.scenePos())
            if anchor:
                event.ignore()
                return
            smaller = _smallest_zone(self.scene(), event.scenePos(), exclude=self, max_area=_zone_area(self))
            if smaller:
                event.ignore()
                return
            mw = self.scene().mainwindow
            if mw and not getattr(mw, "_restoring_state", False):
                self._undo_initial_pos = QPointF(self.scenePos())
                self._undo_snapshot = mw.capture_state()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        scene = self.scene()
        if scene:
            anchor = _top_anchor(scene, event.scenePos())
            if anchor:
                anchor.open_menu(event.screenPos())
                event.accept()
                return
            smaller = _smallest_zone(scene, event.scenePos(), exclude=self, max_area=_zone_area(self))
            if smaller:
                smaller.open_menu(event.screenPos())
                event.accept()
                return
        self.open_menu(event.screenPos())
        event.accept()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton and self.scene():
            if self._undo_snapshot is not None and self._undo_initial_pos is not None:
                if self.scenePos() != self._undo_initial_pos:
                    mw = self.scene().mainwindow
                    if mw:
                        mw.push_undo_state(self._undo_snapshot)
        self._undo_snapshot = None
        self._undo_initial_pos = None

    def contextMenuEvent(self, event):
        # ПКМ: приоритет — якорь → меньшая зона → текущая зона
        scene = self.scene()
        if scene:
            anchor = _top_anchor(scene, event.scenePos())
            if anchor:
                anchor.open_menu(event.screenPos())
                event.accept()
                return
            smaller = _smallest_zone(scene, event.scenePos(), exclude=self, max_area=_zone_area(self))
            if smaller:
                smaller.open_menu(event.screenPos())
                event.accept()
                return
        self.open_menu(event.screenPos())
        event.accept()


def _zone_area(zone):
    rect = zone.boundingRect()
    return abs(rect.width() * rect.height())

def _top_anchor(scene, pos):
    if scene is None:
        return None
    # Точное попадание по форме якоря; возьмем верхний по Z
    for item in scene.items(pos, Qt.ContainsItemShape):
        if isinstance(item, AnchorItem):
            return item
    return None

def _smallest_zone(scene, pos, exclude=None, max_area=None):
    if scene is None:
        return None
    best = None
    best_area = None
    for item in scene.items(pos, Qt.IntersectsItemShape):
        if isinstance(item, RectZoneItem) and item is not exclude:
            rect = item.boundingRect()
            area = abs(rect.width() * rect.height())
            if max_area is not None and area >= max_area:
                continue
            if best is None or area < best_area:
                best = item
                best_area = area
    return best

# ---------------------------------------------------------------------------
# Custom view and scene
# ---------------------------------------------------------------------------
class MyGraphicsView(QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)
        self._panning = False
        self._pan_start = QPoint()
        self.viewport().setCursor(Qt.ArrowCursor)

    def mousePressEvent(self, event):
        scene = self.scene()
        mw = scene.mainwindow if scene else None
        if event.button() in (Qt.LeftButton, Qt.MiddleButton):
            should_pan = False
            if event.button() == Qt.MiddleButton:
                should_pan = True
            elif event.button() == Qt.LeftButton:
                if not (mw and mw.add_mode):
                    point = event.position().toPoint()
                    if self.itemAt(point) is None:
                        should_pan = True
            if should_pan:
                self._panning = True
                self._pan_start = event.position().toPoint()
                self.viewport().setCursor(Qt.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            pos = event.position().toPoint()
            delta = pos - self._pan_start
            self._pan_start = pos
            hbar = self.horizontalScrollBar()
            vbar = self.verticalScrollBar()
            hbar.setValue(hbar.value() - delta.x())
            vbar.setValue(vbar.value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning and event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._panning = False
            self.viewport().setCursor(Qt.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)
        try:
            QTimer.singleShot(0, self.scene().mainwindow.update_tree_selection)
        except:
            pass

class PlanGraphicsScene(QGraphicsScene):
    def __init__(self):
        super().__init__()
        self.mainwindow=None; self.pixmap=None
        self.pixel_per_cm_x=1.0; self.pixel_per_cm_y=1.0
        self.grid_step_cm=20.0; self.temp_item=None

    def set_background_image(self, pix):
        self.pixmap = pix
        self.setSceneRect(0, 0, pix.width(), pix.height())
        if self.mainwindow:
            self.mainwindow._reset_background_cache()

    def drawBackground(self, painter, rect):
        if self.pixmap:
            painter.drawPixmap(0, 0, self.pixmap)
        step = self.pixel_per_cm_x * self.grid_step_cm
        if step <= 0:
            return
        left = int(rect.left()) - (int(rect.left()) % int(step))
        top = int(rect.top()) - (int(rect.top()) % int(step))
        right = int(rect.right()); bottom = int(rect.bottom())
        pen = QPen(QColor(0,0,0,50)); pen.setWidth(0)
        painter.setPen(pen)
        x = left
        while x <= right:
            painter.drawLine(x, top, x, bottom)
            x += step
        y = top
        while y <= bottom:
            painter.drawLine(left, y, right, y)
            y += step

    def finishCalibration(self, start, end):
        mw = self.mainwindow
        if not mw:
            return
        prev_state = mw.capture_state()
        diff = math.hypot(end.x()-start.x(), end.y()-start.y())
        length_cm, ok = QInputDialog.getDouble(
            mw, "Калибровка масштаба",
            "Введите длину отрезка (см):", 100.0, 0.1, 10000.0, 1
        )
        if ok and length_cm:
            scale = diff / length_cm
            self.pixel_per_cm_x = self.pixel_per_cm_y = scale
        mw.add_mode = None; mw.temp_start_point = None
        if self.temp_item:
            self.removeItem(self.temp_item); self.temp_item = None
        mw.statusBar().showMessage("Калибровка завершена."); mw.grid_calibrated = True
        step, ok = QInputDialog.getInt(
            mw, "Шаг сетки", "Укажите шаг (см):", 10, 1, 1000
        )
        if ok: self.grid_step_cm = float(step)
        mw.resnap_objects(); self.update()
        mw.push_undo_state(prev_state)

    def mousePressEvent(self, event):
        mw = self.mainwindow; pos = event.scenePos()
        if mw and mw.add_mode:
            m = mw.add_mode
            if m == "calibrate":
                if not mw.temp_start_point:
                    mw.temp_start_point = pos
                    self.temp_item = QGraphicsLineItem()
                    pen = QPen(QColor(255,0,0),2)
                    self.temp_item.setPen(pen); self.addItem(self.temp_item)
                    self.temp_item.setLine(pos.x(), pos.y(), pos.x(), pos.y())
                else:
                    QTimer.singleShot(0, lambda: self.finishCalibration(mw.temp_start_point, pos))
                return
            if m == "hall":
                if not mw.temp_start_point:
                    mw.temp_start_point = pos
                    self.temp_item = QGraphicsRectItem()
                    pen = QPen(QColor(0,0,255),2); pen.setStyle(Qt.DashLine)
                    self.temp_item.setPen(pen); self.temp_item.setBrush(QColor(0,0,0,0))
                    self.addItem(self.temp_item)
                    self.temp_item.setRect(QRectF(pos, QSizeF(0,0)))
                return
            if m == "zone":
                if not mw.temp_start_point:
                    hall = next((h for h in mw.halls if h.contains(h.mapFromScene(pos))), None)
                    if not hall: return
                    mw.current_hall_for_zone = hall; mw.temp_start_point = pos
                    self.temp_item = QGraphicsRectItem()
                    pen = QPen(QColor(0,128,0),2); pen.setStyle(Qt.DashLine)
                    self.temp_item.setPen(pen); self.temp_item.setBrush(QColor(0,0,0,0))
                    self.addItem(self.temp_item)
                    self.temp_item.setRect(QRectF(pos, QSizeF(0,0)))
                return
            if m == "anchor":
                hall = next((h for h in mw.halls if h.contains(h.mapFromScene(pos))), None)
                if not hall:
                    QMessageBox.warning(mw, "Ошибка", "Не найден зал для якоря."); return
                params = mw.get_anchor_parameters()
                if not params:
                    mw.add_mode=None; mw.statusBar().clearMessage(); return
                prev_state = mw.capture_state()
                num, z_m, extras, bound = params  # z в метрах
                a = AnchorItem(pos.x(), pos.y(), num, main_hall_number=hall.number, scene=self)
                a.z = int(round(z_m * 100))       # храним в см
                a.extra_halls, a.bound = extras, bound
                self.addItem(a); mw.anchors.append(a)
                mw.add_mode=None; mw.statusBar().clearMessage(); mw.populate_tree()
                mw.push_undo_state(prev_state)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        mw = self.mainwindow
        if mw and mw.add_mode in ("hall","zone") and mw.temp_start_point:
            start = mw.temp_start_point; pos = event.scenePos()
            if mw.add_mode == "zone" and mw.current_hall_for_zone:
                hall = mw.current_hall_for_zone
                local = hall.mapFromScene(pos)
                local.setX(max(0,min(local.x(), hall.rect().width())))
                local.setY(max(0,min(local.y(), hall.rect().height())))
                pos = hall.mapToScene(local)
            if self.temp_item:
                self.temp_item.setRect(QRectF(start, pos).normalized())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        mw = self.mainwindow; pos = event.scenePos()
        if mw and mw.add_mode == "hall" and mw.temp_start_point:
            start, end = mw.temp_start_point, pos
            rect = QRectF(start, end).normalized()
            step = self.pixel_per_cm_x * self.grid_step_cm
            x0,y0,x1,y1 = rect.left(),rect.top(),rect.right(),rect.bottom()
            if step>0:
                x0,y0=round(x0/step)*step,round(y0/step)*step
                x1,y1=round(x1/step)*step,round(y1/step)*step
            if x1==x0: x1=x0+step
            if y1==y0: y1=y0+step
            w_px, h_px = x1-x0, y1-y0
            prev_state = mw.capture_state()
            hall = HallItem(x0, y0, w_px, h_px, "", 0, scene=self)
            self.addItem(hall); mw.halls.append(hall)
            # prompt parameters
            w_m = w_px/(self.pixel_per_cm_x*100)
            h_m = h_px/(self.pixel_per_cm_x*100)
            params = getHallParameters(1, "", w_m, h_m, self)
            if not params:
                self.removeItem(hall); mw.halls.remove(hall)
            else:
                num, name, new_w_m, new_h_m = params
                hall.number, hall.name = num, name
                # resize if needed
                w2_px = new_w_m * self.pixel_per_cm_x * 100
                h2_px = new_h_m * self.pixel_per_cm_x * 100
                hall.prepareGeometryChange()
                hall.setRect(0,0,w2_px,h2_px)
                hall.setZValue(-w2_px*h2_px)
                mw.push_undo_state(prev_state)
            mw.last_selected_items=[]; mw.populate_tree()
            mw.temp_start_point=None; mw.add_mode=None
            if self.temp_item: self.removeItem(self.temp_item); self.temp_item=None
            return

        if mw and mw.add_mode == "zone" and mw.temp_start_point:
            hall = mw.current_hall_for_zone
            if not hall:
                mw.temp_start_point=None; mw.add_mode=None
                if self.temp_item: self.removeItem(self.temp_item); self.temp_item=None
                return
            lr = QRectF(hall.mapFromScene(mw.temp_start_point), hall.mapFromScene(pos)).normalized()
            step = self.pixel_per_cm_x * self.grid_step_cm
            x0,y0,x1,y1 = lr.left(),lr.top(),lr.right(),lr.bottom()
            if step>0:
                x0,y0=round(x0/step)*step,round(y0/step)*step
                x1,y1=round(x1/step)*step,round(y1/step)*step
            if x1==x0: x1=x0+step
            if y1==y0: y1=y0+step
            bl = QPointF(min(x0,x1), max(y0,y1))
            w_pix, h_pix = abs(x1-x0), abs(y1-y0)
            params = getZoneParameters(1, "Входная зона", 0)
            if not params:
                if self.temp_item: self.removeItem(self.temp_item); self.temp_item=None
                mw.temp_start_point=None; mw.add_mode=None
                return
            prev_state = mw.capture_state()
            num, zt, ang = params
            RectZoneItem(bl, w_pix, h_pix, num, zt, ang, hall)
            mw.last_selected_items=[]; mw.populate_tree()
            mw.temp_start_point=None; mw.add_mode=None; mw.current_hall_for_zone=None
            if self.temp_item: self.removeItem(self.temp_item); self.temp_item=None
            mw.push_undo_state(prev_state)
            return

        super().mouseReleaseEvent(event)
        try:
            mw.populate_tree()
            handled = False
            if (event.button() == Qt.LeftButton and mw and not mw.add_mode):
                down = event.buttonDownScenePos(Qt.LeftButton) if hasattr(event, "buttonDownScenePos") else pos
                diff = pos - down
                if abs(diff.x()) < 2 and abs(diff.y()) < 2:
                    items_at = [it for it in self.items(pos, Qt.IntersectsItemShape)
                                 if it.flags() & QGraphicsItem.ItemIsSelectable]
                    if items_at:
                        def item_area(it):
                            if isinstance(it, QGraphicsRectItem):
                                rect = it.rect()
                                return abs(rect.width()*rect.height())
                            br = it.boundingRect()
                            return abs(br.width()*br.height())
                        def priority(it):
                            return 0 if isinstance(it, (AnchorItem, RectZoneItem)) else 1
                        chosen = min(items_at, key=lambda it: (item_area(it), priority(it)))
                        if not (event.modifiers() & Qt.ControlModifier):
                            for selected in list(self.selectedItems()):
                                if selected is not chosen:
                                    selected.setSelected(False)
                        chosen.setSelected(True)
                        mw.last_selected_items = list(self.selectedItems()) or [chosen]
                        mw.on_scene_selection_changed()
                        handled = True
            if not handled and not self.selectedItems():
                clicked = self.itemAt(pos, self.views()[0].transform())
                if clicked:
                    clicked.setSelected(True)
                    mw.last_selected_items=[clicked]; mw.on_scene_selection_changed()
        except: pass

# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class PlanEditorMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RG Tags Mapper"); self.resize(1200,800)

        self._icons_dir = os.path.join(os.path.dirname(__file__), "icons")
        self._apply_app_icon()

        dark_color = QColor("#e3e3e3")
        palette = self.palette()
        palette.setColor(QPalette.Window, dark_color)
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        self._readme_path = os.path.join(os.path.dirname(__file__), "readme.md")
        self._cached_readme_text = None
        self._cached_version = None

        self.scene = PlanGraphicsScene(); self.scene.mainwindow=self
        self.scene.selectionChanged.connect(self.on_scene_selection_changed)
        self.view = MyGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)

        central_widget = QWidget()
        central_widget.setObjectName("centralContainer")
        central_layout = QVBoxLayout(central_widget)
        margin = 8
        central_layout.setContentsMargins(margin, margin, margin, margin)

        central_frame = QWidget()
        central_frame.setObjectName("centralFrame")
        frame_layout = QVBoxLayout(central_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.addWidget(self.view)

        central_widget.setStyleSheet(
            """
            QWidget#centralContainer {
                background-color: rgba(255, 255, 255, 25);
            }
            QWidget#centralFrame {
                border: none;
                border-radius: 8px;
                background-color: rgba(255, 255, 255, 235);
            }
            QWidget#centralFrame > * {
                background-color: transparent;
            }
            """
        )
        central_layout.addWidget(central_frame)
        self.setCentralWidget(central_widget)

        self.tree = QTreeWidget(); self.tree.setHeaderLabel("Объекты"); self.tree.setWordWrap(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.on_tree_context_menu)
        self.tree.itemDoubleClicked.connect(self.on_tree_item_double_clicked)

        dock_container = QWidget()
        dock_container.setObjectName("dockContainer")
        dock_layout = QVBoxLayout(dock_container)
        dock_layout.setContentsMargins(margin, margin, margin, margin)

        dock_frame = QWidget()
        dock_frame.setObjectName("dockFrame")
        dock_frame_layout = QVBoxLayout(dock_frame)
        dock_frame_layout.setContentsMargins(0, 0, 0, 0)
        dock_frame_layout.addWidget(self.tree)

        dock_container.setStyleSheet(
            """
            QWidget#dockContainer {
                background-color: rgba(255, 255, 255, 25);
            }
            QWidget#dockFrame {
                border: none;
                border-radius: 8px;
                background-color: rgba(255, 255, 255, 235);
            }
            QWidget#dockFrame > * {
                background-color: transparent;
            }
            QTreeWidget {
                background-color: transparent;
            }
            """
        )
        dock_layout.addWidget(dock_frame)

        dock = QDockWidget("Список объектов", self); dock.setWidget(dock_container)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self.objects_dock = dock

        self.tracks_panel = TracksListWidget(self)

        tracks_container = QWidget()
        tracks_container.setObjectName("tracksDockContainer")
        tracks_layout = QVBoxLayout(tracks_container)
        tracks_layout.setContentsMargins(margin, margin, margin, margin)

        tracks_frame = QWidget()
        tracks_frame.setObjectName("tracksDockFrame")
        tracks_frame_layout = QVBoxLayout(tracks_frame)
        tracks_frame_layout.setContentsMargins(0, 0, 0, 0)
        tracks_frame_layout.addWidget(self.tracks_panel)

        tracks_container.setStyleSheet(
            """
            QWidget#tracksDockContainer {
                background-color: rgba(255, 255, 255, 25);
            }
            QWidget#tracksDockFrame {
                border: none;
                border-radius: 8px;
                background-color: rgba(255, 255, 255, 235);
            }
            QWidget#tracksDockFrame > * {
                background-color: transparent;
            }
            QTreeWidget {
                background-color: transparent;
            }
            """
        )
        tracks_layout.addWidget(tracks_frame)

        tracks_dock = QDockWidget("Список треков", self)
        tracks_dock.setWidget(tracks_container)
        tracks_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        tracks_dock.setAllowedAreas(Qt.TopDockWidgetArea | Qt.BottomDockWidgetArea)
        self.addDockWidget(Qt.TopDockWidgetArea, tracks_dock)
        tracks_dock.hide()
        self.tracks_dock = tracks_dock

        self._create_actions()
        self._create_menus()
        self._create_toolbars()

        self.objects_dock.visibilityChanged.connect(self._on_objects_dock_visibility_changed)
        self.tracks_dock.visibilityChanged.connect(self._on_tracks_dock_visibility_changed)

        self.add_mode = None; self.temp_start_point = None
        self.current_hall_for_zone = None
        self.halls = []; self.anchors = []
        self.grid_calibrated = False
        self.lock_halls = False; self.lock_zones = False; self.lock_anchors = False
        self.last_selected_items = []
        self.current_project_file = None
        self.undo_stack = []
        self._undo_limit = 30
        self._restoring_state = False
        self._undo_bg_cache_key = None
        self._undo_bg_image = ""
        self._saved_state_snapshot = None

        self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.view.setDragMode(QGraphicsView.NoDrag)
        self.view.wheelEvent = self.handle_wheel_event
        self.statusBar().setMinimumHeight(30)
        self.statusBar().showMessage("Загрузите изображение для начала работы.")
        self.update_undo_action()
        self.populate_tracks_table()

    def _apply_app_icon(self):
        icon_path = os.path.join(self._icons_dir, "app.png")
        if not os.path.exists(icon_path):
            return
        icon = QIcon(icon_path)
        self.setWindowIcon(icon)
        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(icon)

    def _create_actions(self):
        def load_icon(filename: str, fallback: QStyle.StandardPixmap | None = None):
            path = os.path.join(self._icons_dir, filename)
            if os.path.exists(path):
                return QIcon(path)
            if fallback is not None:
                return self.style().standardIcon(fallback)
            return QIcon()

        self.action_open = QAction(
            load_icon("open.png", QStyle.SP_DialogOpenButton),
            "Новый проект",
            self,
        )
        self.action_open.triggered.connect(self.open_image)

        self.action_save = QAction(
            load_icon("save.png", QStyle.SP_DialogSaveButton),
            "Сохранить проект",
            self,
        )
        self.action_save.triggered.connect(self.save_project)

        self.action_save_as = QAction(
            "Сохранить проект как…",
            self,
        )
        self.action_save_as.triggered.connect(self.save_project_as)

        self.action_load = QAction(
            load_icon("load.png", QStyle.SP_DialogOpenButton),
            "Загрузить проект",
            self,
        )
        self.action_load.triggered.connect(self.load_project)

        self.action_import = QAction(
            load_icon("import.png", QStyle.SP_DialogOpenButton),
            "Импорт конфигурации",
            self,
        )
        self.action_import.triggered.connect(self.show_import_menu)

        self.action_export = QAction(
            load_icon("export.png", QStyle.SP_DialogSaveButton),
            "Экспорт конфигурации",
            self,
        )
        self.action_export.triggered.connect(self.show_export_menu)

        self.action_upload = QAction(
            load_icon("upload.png", QStyle.SP_ArrowUp),
            "Выгрузить на сервер",
            self,
        )
        self.action_upload.triggered.connect(self.upload_config_to_server)

        self.action_pdf = QAction(
            load_icon("pdf.png", QStyle.SP_FileDialogDetailedView),
            "Сохранить в PDF",
            self,
        )
        self.action_pdf.triggered.connect(self.save_to_pdf)

        self.action_calibrate = QAction(
            load_icon("calibration.png", QStyle.SP_ComputerIcon),
            "Выполнить калибровку",
            self,
        )
        self.action_calibrate.triggered.connect(self.perform_calibration)

        self.action_add_hall = QAction(
            load_icon("hall.png", QStyle.SP_FileDialogNewFolder),
            "Добавить зал",
            self,
        )
        self.action_add_hall.triggered.connect(lambda: self.set_mode("hall"))

        self.action_add_anchor = QAction(
            load_icon("anchor.png", QStyle.SP_FileDialogNewFolder),
            "Добавить якорь",
            self,
        )
        self.action_add_anchor.triggered.connect(lambda: self.set_mode("anchor"))

        self.action_add_zone = QAction(
            load_icon("zone.png", QStyle.SP_FileDialogNewFolder),
            "Добавить зону",
            self,
        )
        self.action_add_zone.triggered.connect(lambda: self.set_mode("zone"))

        self.act_lock = QAction(
            load_icon("lock.png", QStyle.SP_DialogCloseButton),
            "Закрепить объекты",
            self,
        )
        self.act_lock.triggered.connect(self.lock_objects)

        self.undo_action = QAction(
            load_icon("undo.png", QStyle.SP_ArrowBack),
            "Отменить",
            self,
        )
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.setEnabled(False)
        self.undo_action.triggered.connect(self.undo_last_action)

        self.action_help = QAction("Справка по RG Tags Mapper", self)
        self.action_help.triggered.connect(self.show_help_contents)

        self.action_about = QAction("О приложении...", self)
        self.action_about.triggered.connect(self.show_about_dialog)

        self.action_toggle_objects_dock = QAction("Окно \"Список объектов\"", self)
        self.action_toggle_objects_dock.setCheckable(True)
        self.action_toggle_objects_dock.setChecked(True)
        self.action_toggle_objects_dock.toggled.connect(self._toggle_objects_dock)

        self.action_toggle_tracks_dock = QAction("Окно \"Список треков\"", self)
        self.action_toggle_tracks_dock.setCheckable(True)
        self.action_toggle_tracks_dock.setChecked(False)
        self.action_toggle_tracks_dock.toggled.connect(self._toggle_tracks_dock)

    def _create_menus(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("Файл")
        file_menu.addAction(self.action_open)
        file_menu.addSeparator()
        file_menu.addAction(self.action_save)
        file_menu.addAction(self.action_save_as)
        file_menu.addAction(self.action_load)
        file_menu.addSeparator()
        file_menu.addAction(self.action_import)
        file_menu.addAction(self.action_export)
        file_menu.addAction(self.action_upload)
        file_menu.addAction(self.action_pdf)

        edit_menu = menu_bar.addMenu("Правка")
        edit_menu.addAction(self.undo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_lock)

        tools_menu = menu_bar.addMenu("Инструменты")
        tools_menu.addAction(self.action_calibrate)
        tools_menu.addSeparator()
        tools_menu.addAction(self.action_add_hall)
        tools_menu.addAction(self.action_add_anchor)
        tools_menu.addAction(self.action_add_zone)

        view_menu = menu_bar.addMenu("Вид")
        view_menu.addAction(self.action_toggle_objects_dock)
        view_menu.addAction(self.action_toggle_tracks_dock)

        help_menu = menu_bar.addMenu("Справка")
        help_menu.addAction(self.action_help)
        help_menu.addSeparator()
        help_menu.addAction(self.action_about)

        menu_bar.setStyleSheet(
            """
            QMenuBar {
                background-color: rgba(255, 255, 255, 235);
                border-bottom: 1px solid #b8b8b8;
                padding: 4px 6px;
            }
            QMenuBar::item {
                padding: 4px 10px;
                border-radius: 4px;
            }
            QMenuBar::item:selected {
                background-color: rgba(240, 240, 240, 220);
            }
            """
        )

    def _create_toolbars(self):
        base_icon_size = QSize(48, 48)
        scale_factor = 1.2
        icon_size = QSize(
            int(round(base_icon_size.width() * scale_factor)),
            int(round(base_icon_size.height() * scale_factor)),
        )

        file_toolbar = QToolBar("Файл", self)
        file_toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        file_toolbar.setIconSize(icon_size)
        file_toolbar.addAction(self.action_open)
        self._add_toolbar_group_separator(file_toolbar)
        file_toolbar.addAction(self.action_save)
        file_toolbar.addAction(self.action_load)
        self._add_toolbar_group_separator(file_toolbar)
        file_toolbar.addAction(self.action_import)
        file_toolbar.addAction(self.action_export)
        file_toolbar.addAction(self.action_upload)
        file_toolbar.addAction(self.action_pdf)
        self.addToolBar(file_toolbar)
        self.file_toolbar = file_toolbar

        tools_toolbar = QToolBar("Инструменты", self)
        tools_toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        tools_toolbar.setIconSize(icon_size)
        tools_toolbar.addAction(self.action_calibrate)
        self._add_toolbar_group_separator(tools_toolbar)
        tools_toolbar.addAction(self.action_add_hall)
        tools_toolbar.addAction(self.action_add_anchor)
        tools_toolbar.addAction(self.action_add_zone)
        self._add_toolbar_group_separator(tools_toolbar)
        tools_toolbar.addAction(self.act_lock)
        self._add_toolbar_group_separator(tools_toolbar)
        tools_toolbar.addAction(self.undo_action)
        self.addToolBar(tools_toolbar)
        self.tools_toolbar = tools_toolbar

        toolbar_stylesheet = (
            """
            QToolBar {
                background-color: rgba(255, 255, 255, 235);
                border-top: 1px solid #c6c6c6;
                border-bottom: 1px solid #a9a9a9;
                padding: 3px 8px;
            }
            QToolBar::separator {
                width: 1px;
                background-color: #b5b5b5;
                margin: 0 6px;
            }
            QToolBar QToolButton {
                margin: 2px 4px;
                padding: 2px 4px;
                border-radius: 4px;
            }
            QToolBar QToolButton:hover {
                background-color: rgba(240, 240, 240, 220);
            }
            QToolBar QToolButton:pressed {
                background-color: rgba(225, 225, 225, 220);
            }
            """
        )
        self._toolbar_stylesheet = toolbar_stylesheet

    def _toggle_objects_dock(self, visible: bool):
        if getattr(self, "objects_dock", None) is None:
            return
        self.objects_dock.setVisible(visible)

    def _on_objects_dock_visibility_changed(self, visible: bool):
        if getattr(self, "action_toggle_objects_dock", None) is None:
            return
        self.action_toggle_objects_dock.blockSignals(True)
        self.action_toggle_objects_dock.setChecked(visible)
        self.action_toggle_objects_dock.blockSignals(False)

        for toolbar in (getattr(self, "file_toolbar", None), getattr(self, "tools_toolbar", None)):
            if toolbar is None:
                continue
            toolbar.setMovable(False)
            toolbar.setContentsMargins(6, 3, 6, 3)
            if toolbar.layout():
                toolbar.layout().setSpacing(8)
            toolbar.setStyleSheet(getattr(self, "_toolbar_stylesheet", ""))

    def _toggle_tracks_dock(self, visible: bool):
        if getattr(self, "tracks_dock", None) is None:
            return
        self.tracks_dock.setVisible(visible)

    def _on_tracks_dock_visibility_changed(self, visible: bool):
        if getattr(self, "action_toggle_tracks_dock", None) is None:
            return
        self.action_toggle_tracks_dock.blockSignals(True)
        self.action_toggle_tracks_dock.setChecked(visible)
        self.action_toggle_tracks_dock.blockSignals(False)

    def _load_readme_text(self) -> str | None:
        if self._cached_readme_text is not None:
            return self._cached_readme_text
        if not os.path.exists(self._readme_path):
            return None
        try:
            with open(self._readme_path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            return None
        self._cached_readme_text = text
        return text

    def _get_app_version(self) -> str:
        if self._cached_version is not None:
            return self._cached_version
        if not os.path.exists(self._readme_path):
            self._cached_version = "неизвестна"
            return self._cached_version
        try:
            with open(self._readme_path, "r", encoding="utf-8") as fh:
                first_line = fh.readline().strip()
        except OSError:
            first_line = ""
        self._cached_version = first_line or "неизвестна"
        return self._cached_version

    def show_help_contents(self):
        text = self._load_readme_text()
        if text is None:
            QMessageBox.warning(self, "Справка", "Не удалось загрузить файл справки.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Справка по RG Tags Mapper")
        layout = QVBoxLayout(dialog)

        browser = QTextBrowser(dialog)
        if hasattr(browser, "setMarkdown"):
            browser.setMarkdown(text)
        else:
            browser.setPlainText(text)
        browser.setOpenExternalLinks(True)
        layout.addWidget(browser)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)

        dialog.resize(700, 500)
        dialog.exec()

    def show_about_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("О приложении")
        layout = QVBoxLayout(dialog)

        icon_path = os.path.join(self._icons_dir, "app.png")
        if os.path.exists(icon_path):
            logo_label = QLabel(dialog)
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                logo_label.setPixmap(pixmap.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                logo_label.setAlignment(Qt.AlignCenter)
                layout.addWidget(logo_label)

        title_label = QLabel("RG Tags Mapper", dialog)
        title_font = QFont(title_label.font())
        title_font.setPointSize(title_font.pointSize() + 2)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        version_label = QLabel(f"Версия {self._get_app_version()}", dialog)
        version_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(version_label)

        copyright_label = QLabel("Copyright (C) 2025, RadioGuide LLC", dialog)
        copyright_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(copyright_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)

        dialog.resize(400, 300)
        dialog.exec()

    def _toolbar_group_spacing(self, toolbar: QToolBar) -> int:
        base_spacing = toolbar.style().pixelMetric(QStyle.PM_ToolBarItemSpacing, None, toolbar)
        if base_spacing <= 0:
            base_spacing = max(8, toolbar.iconSize().width() // 4)
        return base_spacing

    def _add_toolbar_group_separator(self, toolbar: QToolBar):
        toolbar.addSeparator()
        spacer = QWidget(toolbar)
        spacer.setFixedWidth(self._toolbar_group_spacing(toolbar))
        spacer.setAttribute(Qt.WA_TransparentForMouseEvents)
        spacer.setFocusPolicy(Qt.NoFocus)
        toolbar.addWidget(spacer)

    def _reset_background_cache(self):
        self._undo_bg_cache_key = None
        self._undo_bg_image = ""

    def capture_state(self):
        data = {
            "image_data": "",
            "pixel_per_cm_x": self.scene.pixel_per_cm_x,
            "pixel_per_cm_y": self.scene.pixel_per_cm_y,
            "grid_step_cm": self.scene.grid_step_cm,
            "grid_calibrated": self.grid_calibrated,
            "lock_halls": self.lock_halls,
            "lock_zones": self.lock_zones,
            "lock_anchors": self.lock_anchors,
            "current_project_file": self.current_project_file,
            "halls": [],
            "anchors": []
        }
        if self.scene.pixmap:
            cache_key = self.scene.pixmap.cacheKey()
            if self._undo_bg_cache_key == cache_key and self._undo_bg_image:
                data["image_data"] = self._undo_bg_image
            else:
                buf = QBuffer(); buf.open(QBuffer.WriteOnly)
                self.scene.pixmap.save(buf, "PNG")
                encoded = buf.data().toBase64().data().decode()
                data["image_data"] = encoded
                self._undo_bg_cache_key = cache_key
                self._undo_bg_image = encoded
        else:
            self._reset_background_cache()
        for hall in self.halls:
            hall_data = {
                "num": hall.number,
                "name": hall.name,
                "x_px": hall.pos().x(),
                "y_px": hall.pos().y(),
                "w_px": hall.rect().width(),
                "h_px": hall.rect().height(),
                "audio": copy.deepcopy(hall.audio_settings) if hall.audio_settings else None,
                "zone_audio": {str(k): copy.deepcopy(v) for k, v in hall.zone_audio_tracks.items()}
            }
            zones = []
            for child in hall.childItems():
                if isinstance(child, RectZoneItem):
                    zones.append({
                        "zone_num": child.zone_num,
                        "zone_type": child.zone_type,
                        "zone_angle": child.zone_angle,
                        "bottom_left_x": child.pos().x(),
                        "bottom_left_y": child.pos().y(),
                        "w_px": child.rect().width(),
                        "h_px": child.rect().height()
                    })
            hall_data["zones"] = zones
            data["halls"].append(hall_data)
        for anchor in self.anchors:
            anchor_data = {
                "number": anchor.number,
                "z": anchor.z,
                "x": anchor.scenePos().x(),
                "y": anchor.scenePos().y(),
                "main_hall": anchor.main_hall_number,
                "extra_halls": list(anchor.extra_halls),
                "bound": anchor.bound
            }
            data["anchors"].append(anchor_data)
        return data

    def restore_state(self, state):
        if not state:
            return
        self._restoring_state = True
        try:
            self.scene.clear()
            self.scene.temp_item = None
            self.halls.clear()
            self.anchors.clear()
            image_data = state.get("image_data") or ""
            if image_data:
                ba = QByteArray.fromBase64(image_data.encode())
                pix = QPixmap()
                pix.loadFromData(ba, "PNG")
                self.scene.set_background_image(pix)
            else:
                self.scene.pixmap = None
                self.scene.setSceneRect(0, 0, 1000, 1000)
                self._reset_background_cache()
            self.scene.pixel_per_cm_x = state.get("pixel_per_cm_x", 1.0)
            self.scene.pixel_per_cm_y = state.get("pixel_per_cm_y", 1.0)
            self.scene.grid_step_cm = state.get("grid_step_cm", 20.0)
            self.grid_calibrated = state.get("grid_calibrated", False)
            self.lock_halls = state.get("lock_halls", False)
            self.lock_zones = state.get("lock_zones", False)
            self.lock_anchors = state.get("lock_anchors", False)
            self.current_project_file = state.get("current_project_file")
            for hall_data in state.get("halls", []):
                hall = HallItem(
                    hall_data.get("x_px", 0.0),
                    hall_data.get("y_px", 0.0),
                    hall_data.get("w_px", 0.0),
                    hall_data.get("h_px", 0.0),
                    hall_data.get("name", ""),
                    hall_data.get("num", 0),
                    scene=self.scene
                )
                hall.audio_settings = copy.deepcopy(hall_data.get("audio")) if hall_data.get("audio") else None
                zone_audio_raw = hall_data.get("zone_audio") or {}
                hall.zone_audio_tracks = {int(k): copy.deepcopy(v) for k, v in zone_audio_raw.items()}
                self.scene.addItem(hall)
                self.halls.append(hall)
                for zone_data in hall_data.get("zones", []):
                    bl = QPointF(zone_data.get("bottom_left_x", 0.0), zone_data.get("bottom_left_y", 0.0))
                    RectZoneItem(
                        bl,
                        zone_data.get("w_px", 0.0),
                        zone_data.get("h_px", 0.0),
                        zone_data.get("zone_num", 0),
                        zone_data.get("zone_type", "Входная зона"),
                        zone_data.get("zone_angle", 0.0),
                        hall
                    )
            for anchor_data in state.get("anchors", []):
                anchor = AnchorItem(
                    anchor_data.get("x", 0.0),
                    anchor_data.get("y", 0.0),
                    anchor_data.get("number", 0),
                    main_hall_number=anchor_data.get("main_hall"),
                    scene=self.scene
                )
                anchor.z = anchor_data.get("z", 0)
                anchor.extra_halls = list(anchor_data.get("extra_halls", []))
                anchor.bound = bool(anchor_data.get("bound", False))
                self.scene.addItem(anchor)
                self.anchors.append(anchor)
            if not image_data:
                rect = self.scene.itemsBoundingRect()
                if rect.isValid():
                    margin = 100
                    self.scene.setSceneRect(rect.adjusted(-margin, -margin, margin, margin))
            self.add_mode = None
            self.temp_start_point = None
            self.current_hall_for_zone = None
            self.apply_lock_flags()
            self.populate_tree()
            self.statusBar().clearMessage()
        finally:
            self._restoring_state = False

    def push_undo_state(self, state=None):
        if self._restoring_state:
            return
        snapshot = state if state is not None else self.capture_state()
        if snapshot is None:
            return
        self.undo_stack.append(snapshot)
        if len(self.undo_stack) > self._undo_limit:
            self.undo_stack.pop(0)
        self.update_undo_action()

    def undo_last_action(self):
        if not self.undo_stack:
            return
        state = self.undo_stack.pop()
        self.restore_state(state)
        self.update_undo_action()
        self.statusBar().showMessage("Последнее действие отменено.", 3000)

    def update_undo_action(self):
        if hasattr(self, "undo_action"):
            self.undo_action.setEnabled(bool(self.undo_stack))

    # Parameter getters...
    def get_anchor_parameters(self):
        default = 1 if not self.anchors else max(a.number for a in self.anchors)+1
        return getAnchorParameters(default, 0.0, "", False)  # Z по умолчанию в метрах
    def get_zone_parameters(self):
        default = 1
        if self.current_hall_for_zone:
            zs = [ch for ch in self.current_hall_for_zone.childItems() if isinstance(ch,RectZoneItem)]
            if zs: default = max(z.zone_num for z in zs)+1
        return getZoneParameters(default, "Входная зона", 0)

    # Locking
    def lock_objects(self):
        dlg = LockDialog(self.lock_halls, self.lock_zones, self.lock_anchors, self)
        if dlg.exec() == QDialog.Accepted:
            prev_state = self.capture_state()
            self.lock_halls, self.lock_zones, self.lock_anchors = dlg.values()
            self.apply_lock_flags()
            self.push_undo_state(prev_state)
    def apply_lock_flags(self):
        for h in self.halls: h.setFlag(QGraphicsItem.ItemIsMovable, not self.lock_halls)
        for h in self.halls:
            for ch in h.childItems():
                if isinstance(ch,RectZoneItem):
                    ch.setFlag(QGraphicsItem.ItemIsMovable, not self.lock_zones)
        for a in self.anchors: a.setFlag(QGraphicsItem.ItemIsMovable, not self.lock_anchors)

    # PDF export
    def save_to_pdf(self):
        fp,_ = QFileDialog.getSaveFileName(self, "Сохранить в PDF", "", "PDF files (*.pdf)")
        if not fp: return
        writer = QPdfWriter(fp); writer.setPageSize(QPageSize(QPageSize.A4)); writer.setResolution(300)
        painter = QPainter(writer); self.scene.render(painter); painter.end()
        QMessageBox.information(self, "PDF сохранён", "PDF успешно сохранён.")

    # Calibration
    def perform_calibration(self):
        if not self.scene.pixmap:
            QMessageBox.warning(self, "Ошибка", "Сначала загрузите изображение!"); return
        confirm_text = (
            "Для калибровки  координатной сетки необходимо будет указать на плане 2 точки, "
            "обозначив отрезок известной длины. После этого задать реальную длину отрезка в см. "
            "Продолжить?"
        )
        reply = QMessageBox.question(
            self,
            "Калибровка",
            confirm_text,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return
        self.set_mode("calibrate")
        self.statusBar().showMessage("Укажите 2 точки на плане для обозначения отрезка известной длины")
    def resnap_objects(self):
        step = self.scene.pixel_per_cm_x * self.scene.grid_step_cm
        for h in self.halls:
            p = h.pos(); h.setPos(round(p.x()/step)*step, round(p.y()/step)*step)
        for a in self.anchors:
            p = a.scenePos(); a.setPos(round(p.x()/step)*step, round(p.y()/step)*step)
        self.populate_tree(); self.statusBar().showMessage("Координаты пересчитаны.")

    # Selection sync
    def on_scene_selection_changed(self):
        try: items = self.scene.selectedItems()
        except: return
        if items:
            self.last_selected_items = items
            for it in items:
                if hasattr(it, 'tree_item') and it.tree_item:
                    it.tree_item.setSelected(True)
        else:
            for it in self.last_selected_items:
                if hasattr(it, 'tree_item') and it.tree_item:
                    it.tree_item.setSelected(True)

    def update_tree_selection(self):
        try: items = [i for i in self.scene.items() if i.isSelected()]
        except: return
        if items:
            self.last_selected_items = items
            def clear(n):
                n.setSelected(False)
                for i in range(n.childCount()): clear(n.child(i))
            for i in range(self.tree.topLevelItemCount()): clear(self.tree.topLevelItem(i))
            for it in items:
                if hasattr(it, 'tree_item') and it.tree_item:
                    it.tree_item.setSelected(True)
        else:
            for it in self.last_selected_items:
                if hasattr(it, 'tree_item') and it.tree_item:
                    it.tree_item.setSelected(True)

    # Tree context/double click handlers
    def on_tree_context_menu(self, point: QPoint):
        item = self.tree.itemAt(point)
        if not item: return
        self.handle_tree_item_action(item, self.tree.viewport().mapToGlobal(point))

    def on_tree_item_double_clicked(self, item: QTreeWidgetItem, col: int):
        self.handle_tree_item_action(item, QCursor.pos())

    def handle_tree_item_action(self, item: QTreeWidgetItem, global_pos: QPoint):
        data = item.data(0, Qt.UserRole)
        if not data: return
        tp = data.get("type")
        if tp == "hall":
            hall = data["ref"]
            if hall and hall.scene(): hall.open_menu(global_pos)
        elif tp == "anchor":
            anchor = data["ref"]
            if anchor and anchor.scene(): anchor.open_menu(global_pos)
        elif tp == "zone_group":
            zones = data["ref"]  # list of RectZoneItem
            zones = [z for z in zones if z.scene() is not None]
            if not zones: return
            if len(zones) == 1:
                zones[0].open_menu(global_pos)
                return
            # submenu to choose which zone in group
            menu = QMenu()
            for z in zones:
                label = f'Зона {z.zone_num} ({z.get_display_type()})'
                act = menu.addAction(label)
                act.triggered.connect(lambda checked=False, z=z: z.open_menu(global_pos))
            menu.exec(global_pos)

    # Misc
    def handle_wheel_event(self, event):
        factor = 1.2 if event.angleDelta().y()>0 else 1/1.2
        self.view.scale(factor, factor)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            items = list(self.scene.selectedItems())
            if not items:
                return
            prev_state = self.capture_state()
            changed = False
            for it in items:
                if isinstance(it, RectZoneItem):
                    hall = it.parentItem()
                    if hall:
                        others = [z for z in hall.childItems() if isinstance(z, RectZoneItem) and z.zone_num == it.zone_num and z is not it]
                        if not others:
                            hall.zone_audio_tracks.pop(it.zone_num, None)
                if isinstance(it,HallItem) and it in self.halls:
                    self.halls.remove(it)
                    changed = True
                elif isinstance(it, AnchorItem) and it in self.anchors:
                    self.anchors.remove(it)
                    changed = True
                else:
                    changed = changed or isinstance(it, RectZoneItem)
                self.scene.removeItem(it)
            if changed:
                self.populate_tree()
                self.push_undo_state(prev_state)
            return
        else:
            super().keyPressEvent(event)

    def populate_tracks_table(self):
        panel = getattr(self, "tracks_panel", None)
        if panel is None:
            return
        panel.refresh()

    def populate_tree(self):
        self.last_selected_items = []
        self.tree.clear()
        # halls
        for h in self.halls:
            wm = h.rect().width()/(self.scene.pixel_per_cm_x*100)
            hm = h.rect().height()/(self.scene.pixel_per_cm_x*100)
            rt = (f'Зал {h.number} "{h.name}" ({wm:.1f} x {hm:.1f} м)'
                  if h.name.strip() else f'Зал {h.number} ({wm:.1f} x {hm:.1f} м)')
            hi = QTreeWidgetItem([rt]); h.tree_item = hi; self.tree.addTopLevelItem(hi)
            hi.setData(0, Qt.UserRole, {"type":"hall","ref":h})

            # anchors under hall
            for a in self.anchors:
                if a.main_hall_number==h.number or h.number in a.extra_halls:
                    lp = h.mapFromScene(a.scenePos())
                    xm = fix_negative_zero(round(lp.x()/(self.scene.pixel_per_cm_x*100),1))
                    ym = fix_negative_zero(round((h.rect().height()-lp.y())/(self.scene.pixel_per_cm_x*100),1))
                    at = f'Якорь {a.number} (x={xm} м, y={ym} м, z={fix_negative_zero(round(a.z/100,1))} м)'
                    ai = QTreeWidgetItem([at]); a.tree_item = ai; hi.addChild(ai)
                    ai.setData(0, Qt.UserRole, {"type":"anchor","ref":a})

            # zones grouped by num
            zones_by_num = {}
            for ch in h.childItems():
                if isinstance(ch,RectZoneItem):
                    zones_by_num.setdefault(ch.zone_num, []).append(ch)

            for num, zlist in zones_by_num.items():
                # compose one-line text as before
                default = {"x":0,"y":0,"w":0,"h":0,"angle":0}
                enter = default.copy(); exitz = default.copy(); bound = False
                for z in zlist:
                    data = z.get_export_data()
                    if z.zone_type in ("Входная зона","Переходная"):
                        enter = data
                    if z.zone_type == "Выходная зона":
                        exitz = data
                    if z.zone_type == "Переходная":
                        bound = True
                zt = (f"Зона {num}: enter: x = {enter['x']} м, y = {enter['y']} м, "
                      f"w = {enter['w']} м, h = {enter['h']} м, angle = {enter['angle']}°; "
                      f"exit: x = {exitz['x']} м, y = {exitz['y']} м, "
                      f"w = {exitz['w']} м, h = {exitz['h']} м, angle = {exitz['angle']}°")
                zi = QTreeWidgetItem([zt]); hi.addChild(zi)
                # link every zone to the same item? Keep mapping via UserRole
                zi.setData(0, Qt.UserRole, {"type":"zone_group","ref":zlist})
                # also set back-reference for sync highlighting (any zone in this group will highlight this row)
                for z in zlist: z.tree_item = zi

            hi.setExpanded(True)

        self.populate_tracks_table()

    def set_mode(self, mode):
        if not self.grid_calibrated and mode!="calibrate":
            QMessageBox.information(self,"Внимание","Сначала выполните калибровку!"); return
        self.add_mode = mode; self.temp_start_point = None; self.current_hall_for_zone = None
        msgs = {"hall":"Выделите зал.","anchor":"Кликните в зал.","zone":"Выделите зону.","calibrate":"Укажите 2 точки."}
        self.statusBar().showMessage(msgs.get(mode,""))

    def _has_active_project(self) -> bool:
        pixmap = getattr(self.scene, "pixmap", None)
        if pixmap is not None and not pixmap.isNull():
            return True
        return bool(self.halls or self.anchors)

    def _has_unsaved_changes(self) -> bool:
        if not self._has_active_project():
            return False
        current_state = self.capture_state()
        if self._saved_state_snapshot is None:
            return bool(
                current_state.get("image_data")
                or current_state.get("halls")
                or current_state.get("anchors")
            )
        return current_state != self._saved_state_snapshot

    def _mark_state_as_saved(self):
        self._saved_state_snapshot = self.capture_state()

    def _confirm_save_discard(self, question: str) -> bool:
        if not self._has_unsaved_changes():
            return True
        reply = QMessageBox.question(
            self,
            "Сохранить проект",
            question,
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if reply == QMessageBox.Cancel:
            return False
        if reply == QMessageBox.Save:
            return self.save_project()
        return True

    def _confirm_save_before_new_project(self) -> bool:
        if not self._has_active_project():
            return True
        return self._confirm_save_discard("Сохранить текущий проект перед созданием нового?")

    def _confirm_save_before_load(self) -> bool:
        if not self._has_active_project():
            return True
        return self._confirm_save_discard("Сохранить текущий проект перед загрузкой другого?")

    def open_image(self):
        if not self._confirm_save_before_new_project():
            return
        message = (
            "Для создания нового проекта загрузите план помещения в формате jpg, png, bmp, "
            "после чего выполните калибровку координатной сетки, указав на плане 2 точки, "
            "образующие отрезок известной длины. Продолжить?"
        )
        reply = QMessageBox.question(
            self,
            "Новый проект",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return
        fp, _ = QFileDialog.getOpenFileName(
            self,
            "Выбор плана помещения",
            "",
            "Изображения (*.png *.jpg *.bmp)",
        )
        if not fp:
            return
        pix = QPixmap(fp)
        if pix.isNull():
            QMessageBox.warning(self, "Ошибка", "Не удалось загрузить.")
            return
        prev_state = self.capture_state()
        self.scene.clear(); self.halls.clear(); self.anchors.clear()
        self.scene.pixmap = None
        self._reset_background_cache()
        self.scene.set_background_image(pix)
        self.grid_calibrated = False
        self.current_project_file = None
        self._saved_state_snapshot = None
        self.statusBar().showMessage("Калибровка: укажите 2 точки")
        self.set_mode("calibrate")
        self.push_undo_state(prev_state)

    def _collect_project_data(self):
        buf_data = ""
        if self.scene.pixmap:
            buf = QBuffer(); buf.open(QBuffer.WriteOnly)
            self.scene.pixmap.save(buf,"PNG")
            buf_data = buf.data().toBase64().data().decode()
        data = {
            "image_data": buf_data,
            "pixel_per_cm_x": self.scene.pixel_per_cm_x,
            "pixel_per_cm_y": self.scene.pixel_per_cm_y,
            "grid_step_cm": self.scene.grid_step_cm,
            "lock_halls": self.lock_halls,
            "lock_zones": self.lock_zones,
            "lock_anchors": self.lock_anchors,
            "halls": [], "anchors": []
        }
        for h in self.halls:
            hd = {
                "num": h.number, "name": h.name,
                "x_px": h.pos().x(), "y_px": h.pos().y(),
                "w_px": h.rect().width(), "h_px": h.rect().height()
            }
            if h.audio_settings:
                hd["audio"] = h.audio_settings
            if h.zone_audio_tracks:
                hd["zone_audio"] = {str(k): v for k, v in h.zone_audio_tracks.items()}
            zs = []
            for ch in h.childItems():
                if isinstance(ch,RectZoneItem):
                    zs.append({
                        "zone_num": ch.zone_num,
                        "zone_type": ch.zone_type,
                        "zone_angle": ch.zone_angle,
                        "bottom_left_x": ch.pos().x(),
                        "bottom_left_y": ch.pos().y(),
                        "w_px": ch.rect().width(),
                        "h_px": ch.rect().height()
                    })
            hd["zones"] = zs; data["halls"].append(hd)
        for a in self.anchors:
            ad = {
                "number": a.number, "z": a.z,
                "x": a.scenePos().x(), "y": a.scenePos().y(),
                "main_hall": a.main_hall_number,
                "extra_halls": a.extra_halls
            }
            if a.bound: ad["bound"] = True
            data["anchors"].append(ad)
        return data

    def _save_project_file(self, fp, data):
        try:
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить:\n{e}")
            return False
        QMessageBox.information(self, "Сохранено", "Проект сохранён.")
        return True

    def save_project(self):
        target = self.current_project_file
        if not target:
            target, _ = QFileDialog.getSaveFileName(self, "Сохранить проект", "", "*.proj")
            if not target:
                return False
        data = self._collect_project_data()
        if self._save_project_file(target, data):
            self.current_project_file = target
            self._mark_state_as_saved()
            return True
        return False

    def save_project_as(self):
        fp, _ = QFileDialog.getSaveFileName(self, "Сохранить проект как", "", "*.proj")
        if not fp:
            return False
        data = self._collect_project_data()
        if self._save_project_file(fp, data):
            self.current_project_file = fp
            self._mark_state_as_saved()
            return True
        return False

    def show_import_menu(self):
        menu = QMenu(self)
        rooms_action = menu.addAction("Импортировать объекты")
        tracks_action = menu.addAction("Импортировать аудиофайлы")
        global_pos = QCursor.pos()
        if not self.rect().contains(self.mapFromGlobal(global_pos)):
            global_pos = self.mapToGlobal(self.rect().center())
        chosen = menu.exec(global_pos)
        if chosen == rooms_action:
            self.import_rooms_config()
        elif chosen == tracks_action:
            self.import_tracks_config()

    def show_export_menu(self):
        menu = QMenu(self)
        rooms_action = menu.addAction("Экспортировать объекты")
        tracks_action = menu.addAction("Экспортировать аудиофайлы")
        global_pos = QCursor.pos()
        if not self.rect().contains(self.mapFromGlobal(global_pos)):
            global_pos = self.mapToGlobal(self.rect().center())
        chosen = menu.exec(global_pos)
        if chosen == rooms_action:
            self.export_rooms_config()
        elif chosen == tracks_action:
            self.export_tracks_config()

    def import_rooms_config(self):
        fp, _ = QFileDialog.getOpenFileName(self, "Импорт объектов", "", "JSON файлы (*.json)")
        if not fp:
            return
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось прочитать файл:\n{e}")
            return
        rooms = data.get("rooms") if isinstance(data, dict) else None
        if not isinstance(rooms, list):
            QMessageBox.warning(self, "Ошибка", "Выбранный файл не соответствует формату rooms.json.")
            return

        ppcm = self.scene.pixel_per_cm_x or 0.0
        if ppcm <= 0:
            QMessageBox.warning(self, "Ошибка", "Перед импортом объектов выполните калибровку масштаба.")
            return

        prev_state = self.capture_state()
        hall_map = {h.number: h for h in self.halls}
        zone_audio_backup = {h.number: copy.deepcopy(h.zone_audio_tracks) for h in self.halls if h.zone_audio_tracks}
        existing_zone_count = sum(1 for h in self.halls for ch in h.childItems() if isinstance(ch, RectZoneItem))
        existing_anchor_count = len(self.anchors)
        changed = bool(existing_zone_count or existing_anchor_count)

        for hall in self.halls:
            for child in list(hall.childItems()):
                if isinstance(child, RectZoneItem):
                    child.scene().removeItem(child)
            hall.zone_audio_tracks.clear()
        for anchor in list(self.anchors):
            self.scene.removeItem(anchor)
        self.anchors.clear()

        missing_halls: list[int] = []
        for room in rooms:
            if not isinstance(room, dict):
                continue
            try:
                hall_number = int(room.get("num"))
            except (TypeError, ValueError):
                continue
            hall = hall_map.get(hall_number)
            if hall is None:
                missing_halls.append(hall_number)
                continue

            width = room.get("width")
            height = room.get("height")
            try:
                width_m = float(width)
                height_m = float(height)
            except (TypeError, ValueError):
                width_m = height_m = None
            if width_m and width_m > 0 and height_m and height_m > 0:
                w_px = width_m * ppcm * 100
                h_px = height_m * ppcm * 100
                hall.prepareGeometryChange()
                hall.setRect(0, 0, w_px, h_px)
                hall.setZValue(-w_px * h_px)
                changed = True

            created_zone_numbers: set[int] = set()

            def add_zone(section: dict | None, zone_type: str) -> bool:
                if not isinstance(section, dict):
                    return False
                try:
                    w_m = float(section.get("w", 0))
                    h_m = float(section.get("h", 0))
                    x_m = float(section.get("x", 0))
                    y_m = float(section.get("y", 0))
                    angle = float(section.get("angle", 0))
                except (TypeError, ValueError):
                    return False
                if w_m <= 0 or h_m <= 0:
                    return False
                w_px = w_m * ppcm * 100
                h_px = h_m * ppcm * 100
                px = x_m * ppcm * 100
                py = hall.rect().height() - y_m * ppcm * 100
                RectZoneItem(QPointF(px, py), w_px, h_px, zone_number, zone_type, angle, hall)
                return True

            zones = room.get("zones") if isinstance(room.get("zones"), list) else []
            for zone in zones:
                if not isinstance(zone, dict):
                    continue
                try:
                    zone_number = int(zone.get("num"))
                except (TypeError, ValueError):
                    continue
                bound = bool(zone.get("bound", False))
                if bound:
                    if add_zone(zone.get("enter"), "Переходная"):
                        created_zone_numbers.add(zone_number)
                        changed = True
                else:
                    entered = add_zone(zone.get("enter"), "Входная зона")
                    exited = add_zone(zone.get("exit"), "Выходная зона")
                    if entered or exited:
                        created_zone_numbers.add(zone_number)
                        changed = True

            anchors = room.get("anchors") if isinstance(room.get("anchors"), list) else []
            for anchor_data in anchors:
                if not isinstance(anchor_data, dict):
                    continue
                try:
                    anchor_id = int(anchor_data.get("id"))
                    x_m = float(anchor_data.get("x", 0))
                    y_m = float(anchor_data.get("y", 0))
                    z_m = float(anchor_data.get("z", 0))
                except (TypeError, ValueError):
                    continue
                px = x_m * ppcm * 100
                py = hall.rect().height() - y_m * ppcm * 100
                scene_pos = hall.mapToScene(QPointF(px, py))
                anchor_item = AnchorItem(scene_pos.x(), scene_pos.y(), anchor_id, main_hall_number=hall.number, scene=self.scene)
                anchor_item.z = int(round(z_m * 100))
                if anchor_data.get("bound"):
                    anchor_item.bound = True
                self.scene.addItem(anchor_item)
                self.anchors.append(anchor_item)
                changed = True

            saved_audio = zone_audio_backup.get(hall_number, {})
            if saved_audio:
                for zone_id in created_zone_numbers:
                    audio_info = saved_audio.get(zone_id)
                    if audio_info:
                        hall.zone_audio_tracks[zone_id] = copy.deepcopy(audio_info)

        if missing_halls:
            missing_str = ", ".join(str(n) for n in sorted(set(missing_halls)))
            QMessageBox.warning(self, "Предупреждение", f"В проекте отсутствуют залы: {missing_str}. Объекты этих залов не были импортированы.")

        self.populate_tree()
        if changed or rooms:
            self.push_undo_state(prev_state)
        self.statusBar().showMessage("Импорт объектов завершён.", 5000)
        QMessageBox.information(self, "Импорт", "Импорт объектов завершён.")

    def _build_audio_info_from_track(self, track: dict, file_sizes: dict[str, int] | None = None):
        filename = track.get("audio")
        if not filename:
            return None
        try:
            base_id = int(track.get("id"))
        except (TypeError, ValueError):
            base_id = None
        size_bytes = 0
        if isinstance(file_sizes, dict) and filename in file_sizes:
            try:
                size_bytes = int(file_sizes.get(filename, 0) or 0)
            except (TypeError, ValueError):
                size_bytes = 0
        if size_bytes <= 0:
            try:
                size_bytes = int(track.get("size") or 0)
            except (TypeError, ValueError):
                size_bytes = 0
        extras = []
        for value in track.get("multi_id", []) or []:
            try:
                extra_id = int(value)
            except (TypeError, ValueError):
                continue
            if base_id is not None and extra_id == base_id:
                continue
            extras.append(extra_id)
        info = {
            "filename": filename,
            "data": "",
            "duration_ms": int(track.get("duration_ms", 0) or 0),
            "size": size_bytes,
            "extra_ids": extras,
            "interruptible": bool(track.get("term", True)),
            "reset": bool(track.get("reset", False)),
            "play_once": bool(track.get("play_once", False))
        }
        name_value = track.get("name")
        if isinstance(name_value, str) and name_value.strip():
            info["display_name"] = name_value.strip()
        if track.get("audio2"):
            sec_size = 0
            if isinstance(file_sizes, dict) and track["audio2"] in file_sizes:
                try:
                    sec_size = int(file_sizes.get(track["audio2"], 0) or 0)
                except (TypeError, ValueError):
                    sec_size = 0
            info["secondary"] = {
                "filename": track["audio2"],
                "data": "",
                "duration_ms": 0,
                "size": sec_size
            }
        return info

    def import_tracks_config(self):
        fp, _ = QFileDialog.getOpenFileName(self, "Импорт аудиофайлов", "", "JSON файлы (*.json)")
        if not fp:
            return
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось прочитать файл:\n{e}")
            return
        tracks = data.get("tracks") if isinstance(data, dict) else None
        if not isinstance(tracks, list):
            QMessageBox.warning(self, "Ошибка", "Выбранный файл не соответствует формату tracks.json.")
            return

        file_sizes: dict[str, int] = {}
        files_section = data.get("files") if isinstance(data, dict) else None
        if isinstance(files_section, list):
            for entry in files_section:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name")
                if not isinstance(name, str) or not name:
                    continue
                try:
                    size_value = int(entry.get("size") or 0)
                except (TypeError, ValueError):
                    continue
                file_sizes[name] = max(size_value, file_sizes.get(name, 0), 0)

        prev_state = self.capture_state()
        hall_map = {h.number: h for h in self.halls}
        had_audio = any(h.audio_settings or h.zone_audio_tracks for h in self.halls)
        for hall in self.halls:
            hall.audio_settings = None
            hall.zone_audio_tracks.clear()

        changed = had_audio
        unmatched_halls: set[int] = set()
        unmatched_zones: set[int] = set()

        for entry in tracks:
            if not isinstance(entry, dict):
                continue
            try:
                track_id = int(entry.get("id"))
            except (TypeError, ValueError):
                continue
            audio_info = self._build_audio_info_from_track(entry, file_sizes)
            if not audio_info:
                continue
            target_hall = None
            room_id = entry.get("room_id")
            if isinstance(room_id, (int, float)):
                target_hall = hall_map.get(int(room_id))
            if target_hall is None:
                target_hall = hall_map.get(track_id)
            if entry.get("hall"):
                if target_hall is None:
                    unmatched_halls.add(track_id)
                    continue
                target_hall.audio_settings = audio_info
                changed = True
                continue
            if target_hall is None:
                possible = [h for h in self.halls if any(isinstance(ch, RectZoneItem) and ch.zone_num == track_id for ch in h.childItems())]
                if len(possible) == 1:
                    target_hall = possible[0]
                else:
                    unmatched_zones.add(track_id)
                    continue
            target_hall.zone_audio_tracks[track_id] = audio_info
            changed = True

        warnings = []
        if unmatched_halls:
            hall_list = ", ".join(str(x) for x in sorted(unmatched_halls))
            warnings.append(f"Залы: {hall_list}")
        if unmatched_zones:
            zone_list = ", ".join(str(x) for x in sorted(unmatched_zones))
            warnings.append(f"Зоны: {zone_list}")
        if warnings:
            QMessageBox.warning(self, "Предупреждение", "Не найдены объекты для следующих идентификаторов:\n" + "\n".join(warnings))

        self.populate_tree()
        if changed or tracks:
            self.push_undo_state(prev_state)
        self.statusBar().showMessage("Импорт аудиофайлов завершён.", 5000)
        QMessageBox.information(self, "Импорт", "Импорт аудиофайлов завершён.")

    def load_project(self):
        if not self._confirm_save_before_load():
            return
        fp,_ = QFileDialog.getOpenFileName(self,"Загрузить проект","","*.proj")
        if not fp: return
        prev_state = self.capture_state()
        try:
            with open(fp,"r",encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self,"Ошибка",f"Ошибка чтения:\n{e}"); return
        self.scene.clear(); self.halls.clear(); self.anchors.clear()
        self.scene.pixmap = None
        self._reset_background_cache()
        buf_data = data.get("image_data","")
        if buf_data:
            ba = QByteArray.fromBase64(buf_data.encode())
            pix = QPixmap(); pix.loadFromData(ba,"PNG")
            self.scene.set_background_image(pix)
        self.scene.pixel_per_cm_x = data.get("pixel_per_cm_x",1.0)
        self.scene.pixel_per_cm_y = data.get("pixel_per_cm_y",1.0)
        self.scene.grid_step_cm   = data.get("grid_step_cm",20.0)
        self.lock_halls   = data.get("lock_halls",False)
        self.lock_zones   = data.get("lock_zones",False)
        self.lock_anchors = data.get("lock_anchors",False)
        self.grid_calibrated = True
        for hd in data.get("halls",[]):
            h = HallItem(
                hd.get("x_px",0), hd.get("y_px",0),
                hd.get("w_px",100), hd.get("h_px",100),
                hd.get("name",""), hd.get("num",0),
                scene=self.scene
            )
            h.audio_settings = hd.get("audio")
            zone_audio_raw = hd.get("zone_audio", {})
            if zone_audio_raw:
                h.zone_audio_tracks = {int(k): v for k, v in zone_audio_raw.items()}
            self.scene.addItem(h); self.halls.append(h)
            for zd in hd.get("zones",[]):
                bl = QPointF(zd.get("bottom_left_x",0), zd.get("bottom_left_y",0))
                RectZoneItem(
                    bl, zd.get("w_px",0), zd.get("h_px",0),
                    zd.get("zone_num",0),
                    zd.get("zone_type","Входная зона"),
                    zd.get("zone_angle",0), h
                )
        for ad in data.get("anchors",[]):
            a = AnchorItem(
                ad.get("x",0), ad.get("y",0),
                ad.get("number",0),
                main_hall_number=ad.get("main_hall"),
                scene=self.scene
            )
            a.z = ad.get("z",0)
            a.extra_halls = ad.get("extra_halls",[])
            if ad.get("bound"): a.bound = True
            self.scene.addItem(a); self.anchors.append(a)
        self.apply_lock_flags(); self.populate_tree()
        self.current_project_file = fp
        QMessageBox.information(self,"Загружено","Проект загружен.")
        self.statusBar().clearMessage()
        self.push_undo_state(prev_state)
        self._mark_state_as_saved()

    def export_rooms_config(self):
        fp, _ = QFileDialog.getSaveFileName(self, "Экспорт объектов", "", "JSON файлы (*.json)")
        if not fp:
            return

        rooms_json_text, _ = self._prepare_export_payload()
        try:
            with open(fp, "w", encoding="utf-8") as f:
                f.write(rooms_json_text)
            self.statusBar().showMessage("Экспорт объектов завершён.", 5000)
            QMessageBox.information(self, "Экспорт", "Экспорт объектов завершён.")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать:\n{e}")

    def export_tracks_config(self):
        fp, _ = QFileDialog.getSaveFileName(self, "Экспорт аудиофайлов", "tracks.json", "JSON файлы (*.json)")
        if not fp:
            return

        _, tracks_data = self._prepare_export_payload()
        try:
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(tracks_data, f, ensure_ascii=False, indent=4)
            self.statusBar().showMessage("Экспорт аудиофайлов завершён.", 5000)
            QMessageBox.information(self, "Экспорт", "Экспорт аудиофайлов завершён.")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать:\n{e}")

    def upload_config_to_server(self):
        rooms_json_text, tracks_data = self._prepare_export_payload()
        dialog = QDialog(self)
        dialog.setWindowTitle("Выгрузка на сервер")
        form_layout = QFormLayout(dialog)

        host_edit = QLineEdit(dialog)
        host_edit.setPlaceholderText("example.com")
        form_layout.addRow("Хост:", host_edit)

        login_edit = QLineEdit(dialog)
        login_edit.setPlaceholderText("user")
        form_layout.addRow("Логин:", login_edit)

        target_dir_edit = QLineEdit(dialog)
        target_dir_edit.setPlaceholderText("~/rg_mapper (символ ~ разворачивается автоматически)")
        form_layout.addRow("Каталог на сервере:", target_dir_edit)

        port_spin = QSpinBox(dialog)
        port_spin.setRange(1, 65535)
        port_spin.setValue(22)
        form_layout.addRow("Порт:", port_spin)

        password_edit = QLineEdit(dialog)
        password_edit.setEchoMode(QLineEdit.Password)
        password_edit.setPlaceholderText("Пароль для ключа (если требуется)")
        form_layout.addRow("Пароль к ключу:", password_edit)

        key_widget = QWidget(dialog)
        key_layout = QHBoxLayout(key_widget)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_path_edit = QLineEdit(key_widget)
        key_path_edit.setPlaceholderText("~/.ssh/id_rsa")
        key_layout.addWidget(key_path_edit)
        browse_button = QPushButton("Обзор…", key_widget)

        def browse_key_file():
            filename, _ = QFileDialog.getOpenFileName(
                self,
                "Выберите приватный ключ SSH",
                os.path.expanduser("~/.ssh"),
                "OpenSSH ключи (*.pem *.key *.rsa *.ssh);;Все файлы (*)",
            )
            if filename:
                key_path_edit.setText(filename)

        browse_button.clicked.connect(browse_key_file)
        key_layout.addWidget(browse_button)
        form_layout.addRow("Файл ключа:", key_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form_layout.addRow(buttons)

        if dialog.exec() != QDialog.Accepted:
            return

        host = host_edit.text().strip()
        username = login_edit.text().strip()
        remote_dir = target_dir_edit.text().strip()
        key_path = key_path_edit.text().strip()
        port = port_spin.value()
        passphrase = password_edit.text() or None

        if not host or not username or not key_path:
            QMessageBox.warning(
                self,
                "Выгрузка на сервер",
                "Заполните хост, логин и путь к ключу для подключения.",
            )
            return

        try:
            with open(key_path, "rb") as _key_file:
                _key_file.read(1)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Выгрузка на сервер",
                f"Не удалось открыть файл ключа:\n{exc}",
            )
            return

        try:
            if key_path.lower().endswith(".ppk"):
                ppk_loader = None
                import_error = None
                try:
                    from paramiko.ppk import PPKKey as _PPKKey
                    ppk_loader = _PPKKey
                except ModuleNotFoundError as exc:
                    import_error = exc
                    try:
                        from paramiko_ppk import PPKKey as _PPKKey  # type: ignore
                        ppk_loader = _PPKKey
                    except ModuleNotFoundError as exc_ppk:
                        import_error = exc_ppk
                if ppk_loader is None:
                    raise ModuleNotFoundError(
                        "Поддержка ключей PPK недоступна. Установите пакет paramiko-ppk."
                    ) from import_error

                key_obj = ppk_loader.from_file(key_path, password=passphrase)
            else:
                key_obj = paramiko.RSAKey.from_private_key_file(key_path, password=passphrase)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Выгрузка на сервер",
                f"Не удалось загрузить ключ:\n{exc}",
            )
            return

        ssh = None
        sftp = None
        tracks_json_text = json.dumps(tracks_data, ensure_ascii=False, indent=4)
        rooms_bytes = rooms_json_text.encode("utf-8")
        tracks_bytes = tracks_json_text.encode("utf-8")

        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                hostname=host,
                port=port,
                username=username,
                pkey=key_obj,
                allow_agent=False,
                look_for_keys=False,
            )
            sftp = ssh.open_sftp()

            remote_dir_clean = remote_dir.replace("\\", "/").strip()
            remote_dir_effective = remote_dir_clean
            if remote_dir_effective and remote_dir_effective not in (".", "./"):
                try:
                    if remote_dir_effective.startswith("~"):
                        remote_dir_effective = sftp.normalize(remote_dir_effective)
                    sftp.listdir(remote_dir_effective)
                except IOError as exc:
                    raise IOError(f"Каталог {remote_dir_clean} недоступен: {exc}") from exc
                rooms_remote_path = posixpath.join(remote_dir_effective, "rooms.json")
                tracks_remote_path = posixpath.join(remote_dir_effective, "tracks.json")
            else:
                rooms_remote_path = "rooms.json"
                tracks_remote_path = "tracks.json"

            with sftp.file(rooms_remote_path, "wb") as remote_rooms:
                remote_rooms.write(rooms_bytes)
                remote_rooms.flush()
            with sftp.file(tracks_remote_path, "wb") as remote_tracks:
                remote_tracks.write(tracks_bytes)
                remote_tracks.flush()

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Выгрузка на сервер",
                f"Ошибка при передаче данных:\n{exc}",
            )
            self.statusBar().showMessage("Ошибка выгрузки конфигурации.", 7000)
            return
        finally:
            if sftp is not None:
                try:
                    sftp.close()
                except Exception:
                    pass
            if ssh is not None:
                try:
                    ssh.close()
                except Exception:
                    pass

        self.statusBar().showMessage("Конфигурация выгружена на сервер.", 7000)
        QMessageBox.information(self, "Выгрузка на сервер", "Конфигурация успешно передана на сервер.")

    def _prepare_export_payload(self) -> tuple[str, dict]:
        config = {"rooms": []}
        audio_files_map: dict[str, int] = {}
        track_entries_map: dict[str, dict] = {}

        def _bytes_from_b64(b64str: str) -> int:
            if not b64str:
                return 0
            try:
                return len(base64.b64decode(b64str.encode("ascii")))
            except Exception:
                return 0

        def _extract_size(info: dict | None) -> int:
            if not isinstance(info, dict):
                return 0
            try:
                size_val = int(info.get("size") or 0)
            except (TypeError, ValueError):
                size_val = 0
            if size_val <= 0:
                size_val = _bytes_from_b64(info.get("data", ""))
            return max(size_val, 0)

        def collect_audio_files(info: dict | None):
            if not isinstance(info, dict):
                return
            name = info.get("filename")
            if isinstance(name, str) and name:
                size_bytes = _extract_size(info)
                audio_files_map[name] = max(audio_files_map.get(name, 0), size_bytes)
            secondary = info.get("secondary")
            if isinstance(secondary, dict):
                sec_name = secondary.get("filename")
                if isinstance(sec_name, str) and sec_name:
                    size_bytes2 = _extract_size(secondary)
                    audio_files_map[sec_name] = max(audio_files_map.get(sec_name, 0), size_bytes2)

        def create_track_entry(info: dict | None, room_id: int, is_hall: bool):
            if not isinstance(info, dict):
                return None
            filename = info.get("filename")
            if not filename:
                return None
            base_id = extract_track_id(filename)
            extras = [i for i in info.get("extra_ids", []) if isinstance(i, int)]

            entry = {
                "audio": filename,
                "hall": is_hall,
                "id": base_id,
                "name": "",
                "play_once": bool(info.get("play_once", False)),
                "reset": bool(info.get("reset", False)),
                "room_id": room_id,
                "term": bool(info.get("interruptible", True))
            }

            if extras:
                seen = set()
                merged = []
                for mid in [base_id] + extras:
                    if mid in seen:
                        continue
                    seen.add(mid)
                    merged.append(mid)
                entry["multi_id"] = merged

            secondary = info.get("secondary")
            if isinstance(secondary, dict) and secondary.get("filename"):
                entry["audio2"] = secondary["filename"]
            return entry

        def register_track_entry(entry: dict | None):
            if not isinstance(entry, dict):
                return
            key = entry.get("audio")
            if not key:
                return
            existing = track_entries_map.get(key)
            if existing is None:
                track_entries_map[key] = entry
                return

            existing["hall"] = bool(existing.get("hall")) or bool(entry.get("hall"))

            new_room = entry.get("room_id")
            old_room = existing.get("room_id")
            if isinstance(new_room, int):
                if not isinstance(old_room, int):
                    existing["room_id"] = new_room
                else:
                    existing["room_id"] = min(old_room, new_room)

            if entry.get("audio2") and not existing.get("audio2"):
                existing["audio2"] = entry["audio2"]

            existing["play_once"] = bool(existing.get("play_once")) or bool(entry.get("play_once"))
            existing["reset"] = bool(existing.get("reset")) or bool(entry.get("reset"))
            existing["term"] = bool(existing.get("term", True)) and bool(entry.get("term", True))

            combined_ids: set[int] = set()
            for value in (existing.get("id"), entry.get("id")):
                if isinstance(value, int):
                    combined_ids.add(value)
            for seq in (existing.get("multi_id"), entry.get("multi_id")):
                if isinstance(seq, list):
                    for value in seq:
                        if isinstance(value, int):
                            combined_ids.add(value)
            base_id = existing.get("id")
            if isinstance(base_id, int) and base_id in combined_ids:
                combined_ids.remove(base_id)
            if combined_ids:
                existing["multi_id"] = sorted(combined_ids)
            elif "multi_id" in existing:
                existing.pop("multi_id")

        # === rooms.json ===
        for h in self.halls:
            w_m = fix_negative_zero(round(h.rect().width() / (self.scene.pixel_per_cm_x * 100), 1))
            h_m = fix_negative_zero(round(h.rect().height() / (self.scene.pixel_per_cm_x * 100), 1))

            room = {
                "num": h.number,
                "width": w_m,
                "height": h_m,
                "anchors": [],
                "zones": []
            }

            for a in self.anchors:
                if a.main_hall_number == h.number or h.number in a.extra_halls:
                    lp = h.mapFromScene(a.scenePos())
                    xm = fix_negative_zero(round(lp.x() / (self.scene.pixel_per_cm_x * 100), 1))
                    ym = fix_negative_zero(round((h.rect().height() - lp.y()) / (self.scene.pixel_per_cm_x * 100), 1))
                    ae = {"id": a.number, "x": xm, "y": ym, "z": fix_negative_zero(round(a.z / 100, 1))}
                    if a.bound:
                        ae["bound"] = True
                    room["anchors"].append(ae)

            zones: dict[int, dict] = {}
            default = {"x": 0, "y": 0, "w": 0, "h": 0, "angle": 0}
            for ch in h.childItems():
                if isinstance(ch, RectZoneItem):
                    n = ch.zone_num
                    if n not in zones:
                        zones[n] = {"num": n, "enter": default.copy(), "exit": default.copy()}
                    dz = ch.get_export_data()
                    if ch.zone_type == "Входная зона":
                        zones[n]["enter"] = dz
                    elif ch.zone_type == "Выходная зона":
                        zones[n]["exit"] = dz
                    elif ch.zone_type == "Переходная":
                        zones[n]["enter"] = dz
                        zones[n]["bound"] = True

            for z in zones.values():
                room["zones"].append(z)

            config["rooms"].append(room)

            if h.audio_settings:
                collect_audio_files(h.audio_settings)
                register_track_entry(create_track_entry(h.audio_settings, h.number, True))
            for _, audio_info in sorted(h.zone_audio_tracks.items()):
                if not audio_info:
                    continue
                collect_audio_files(audio_info)
                register_track_entry(create_track_entry(audio_info, h.number, False))

        rooms_strs = []
        for room in config["rooms"]:
            lines = [
                "{",
                f'"num": {room["num"]},',
                f'"width": {room["width"]},',
                f'"height": {room["height"]},',
                '"anchors": ['
            ]
            alines = []
            for a in room["anchors"]:
                s = f'{{ "id": {a["id"]}, "x": {a["x"]}, "y": {a["y"]}, "z": {a["z"]}'
                if a.get("bound"):
                    s += ', "bound": true'
                s += " }"
                alines.append(s)
            lines.append(",\n".join(alines))
            lines.append("],")
            lines.append('"zones": [')
            zlines = []
            for z in room["zones"]:
                zl = "{"
                zl += f'\n"num": {z["num"]},'
                zl += (
                    f'\n"enter": {{ "x": {z["enter"]["x"]}, "y": {z["enter"]["y"]}, '
                    f'"w": {z["enter"]["w"]}, "h": {z["enter"]["h"]}, '
                    f'"angle": {z["enter"]["angle"]} }},'
                )
                zl += (
                    f'\n"exit":  {{ "x": {z["exit"]["x"]}, "y": {z["exit"]["y"]}, '
                    f'"w": {z["exit"]["w"]}, "h": {z["exit"]["h"]}, '
                    f'"angle": {z["exit"]["angle"]} }}'
                )
                if z.get("bound"):
                    zl += ',\n"bound": true'
                zl += "\n}"
                zlines.append(zl)
            lines.append(",\n".join(zlines))
            lines.append("]")
            lines.append("}")
            rooms_strs.append("\n".join(lines))

        rooms_json_text = '{\n"rooms": [\n' + ",\n".join(rooms_strs) + "\n]\n}"

        track_entries = list(track_entries_map.values())

        def _sort_key(item: dict):
            room_id = item.get("room_id")
            if not isinstance(room_id, int):
                try:
                    room_id = int(room_id)
                except (TypeError, ValueError):
                    room_id = 0
            return (
                room_id,
                not bool(item.get("hall")),
                item.get("id", 0),
                item.get("audio", "")
            )

        track_entries.sort(key=_sort_key)
        files_list = [{"name": name, "size": audio_files_map[name]} for name in sorted(audio_files_map)]
        tracks_data = {
            "files": files_list,
            "langs": [],
            "tracks": track_entries,
            "version": datetime.now().strftime("%y%m%d")
        }

        return rooms_json_text, tracks_data

    def closeEvent(self, event):
        if not self._confirm_save_discard("Сохранить текущий проект перед выходом?"):
            event.ignore(); return
        try: self.scene.selectionChanged.disconnect(self.on_scene_selection_changed)
        except: pass
        self.view.setScene(None); event.accept()

if __name__ == "__main__":
    app = QApplication(os.getenv("QT_FORCE_STDERR_LOGGING") and sys.argv or sys.argv)
    icons_dir = os.path.join(os.path.dirname(__file__), "icons")
    app_icon_path = os.path.join(icons_dir, "app.png")
    if os.path.exists(app_icon_path):
        app.setWindowIcon(QIcon(app_icon_path))
    window = PlanEditorMainWindow()
    window.show()
    sys.exit(app.exec())
