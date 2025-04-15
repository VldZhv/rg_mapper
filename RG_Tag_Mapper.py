import sys, math, json, base64
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsLineItem, QMenu, QTreeWidget,
    QTreeWidgetItem, QDockWidget, QFileDialog, QToolBar, QMessageBox, QDialog,
    QFormLayout, QDialogButtonBox, QSpinBox, QDoubleSpinBox, QLineEdit, QComboBox,
    QLabel, QInputDialog, QCheckBox
)
from PySide6.QtGui import QAction, QPainter, QPen, QBrush, QColor, QPixmap, QPainterPath, QFont
from PySide6.QtCore import Qt, QRectF, QPointF, QSizeF, QBuffer, QByteArray, QTimer

def fix_negative_zero(val):
    if abs(val) < 1e-9:
        return 0.0
    return val

# ===========================================================================
# Универсальный диалог для ввода параметров объектов (зала, якоря, зоны)
# ===========================================================================
class ParamDialog(QDialog):
    def __init__(self, title, fields, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.fields = fields
        self.widgets = {}
        layout = QFormLayout(self)
        for field in fields:
            label_text = field["label"]
            field_type = field["type"]
            default = field.get("default")
            if field_type == "int":
                widget = QSpinBox()
                widget.setMinimum(field.get("min", 0))
                widget.setMaximum(field.get("max", 10000))
                widget.setValue(default if default is not None else 1)
            elif field_type == "float":
                widget = QDoubleSpinBox()
                widget.setMinimum(field.get("min", 0.0))
                widget.setMaximum(field.get("max", 10000.0))
                widget.setDecimals(field.get("decimals", 1))
                widget.setValue(default if default is not None else 0.0)
            elif field_type == "string":
                widget = QLineEdit()
                if default is not None:
                    widget.setText(str(default))
            elif field_type == "combo":
                widget = QComboBox()
                for option in field.get("options", []):
                    widget.addItem(option)
                if default is not None and default in field.get("options", []):
                    index = field["options"].index(default)
                    widget.setCurrentIndex(index)
            elif field_type == "bool":
                widget = QCheckBox()
                widget.setChecked(True if default else False)
            else:
                widget = QLineEdit()
            self.widgets[field["label"]] = widget
            layout.addRow(QLabel(label_text), widget)
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addRow(self.button_box)

    def getValues(self):
        values = {}
        for field in self.fields:
            label = field["label"]
            field_type = field["type"]
            widget = self.widgets[label]
            if field_type in ("int", "float"):
                values[label] = widget.value()
            elif field_type == "string":
                values[label] = widget.text()
            elif field_type == "combo":
                values[label] = widget.currentText()
            elif field_type == "bool":
                values[label] = widget.isChecked()
            else:
                values[label] = widget.text()
        return values

# ===========================================================================
# Функции для ввода параметров объектов
# ===========================================================================
def getHallParameters(default_num=1, default_name=""):
    fields = [
        {"label": "Номер зала", "type": "int", "default": default_num, "min": 0, "max": 10000},
        {"label": "Название зала", "type": "string", "default": default_name}
    ]
    dialog = ParamDialog("Введите параметры зала", fields)
    if dialog.exec() == QDialog.Accepted:
        vals = dialog.getValues()
        return vals["Номер зала"], vals["Название зала"]
    return None

def getAnchorParameters(default_num=1, default_z=0, default_extras="", default_bound=False):
    fields = [
        {"label": "Номер якоря", "type": "int", "default": default_num, "min": 0, "max": 10000},
        {"label": "Координата Z (см)", "type": "int", "default": default_z, "min": -10000, "max": 10000},
        {"label": "Дополнительные залы (через запятую)", "type": "string", "default": default_extras},
        {"label": "Переходный", "type": "bool", "default": default_bound}
    ]
    dialog = ParamDialog("Введите параметры якоря", fields)
    if dialog.exec() == QDialog.Accepted:
        vals = dialog.getValues()
        extras_str = vals["Дополнительные залы (через запятую)"]
        extras = []
        if extras_str.strip():
            for token in extras_str.split(","):
                token = token.strip()
                try:
                    extras.append(int(token))
                except:
                    pass
        return vals["Номер якоря"], vals["Координата Z (см)"], extras, vals["Переходный"]
    return None

def getZoneParameters(default_num=1, default_type="Входная зона", default_angle=0):
    display_type = default_type
    if default_type == "Входная зона":
        display_type = "Входная"
    elif default_type == "Выходная зона":
        display_type = "Выходная"
    fields = [
        {"label": "Номер зоны", "type": "int", "default": default_num, "min": 0, "max": 10000},
        {"label": "Тип зоны", "type": "combo", "default": display_type, "options": ["Входная", "Выходная", "Переходная"]},
        {"label": "Угол поворота (°)", "type": "int", "default": default_angle, "min": -90, "max": 90}
    ]
    dialog = ParamDialog("Введите параметры зоны", fields)
    if dialog.exec() == QDialog.Accepted:
        vals = dialog.getValues()
        zone_type = vals["Тип зоны"]
        if zone_type == "Входная":
            zone_type = "Входная зона"
        elif zone_type == "Выходная":
            zone_type = "Выходная зона"
        return vals["Номер зоны"], zone_type, vals["Угол поворота (°)"]
    return None

# ===========================================================================
# Графические объекты
# ===========================================================================
class HallItem(QGraphicsRectItem):
    def __init__(self, x, y, w, h, name="", number=0):
        super().__init__(0, 0, w, h)
        self.setPos(x, y)
        self.name = name
        self.number = number
        pen = QPen(QColor(0, 0, 255))
        pen.setWidth(2)
        self.setPen(pen)
        self.setBrush(QColor(0, 0, 255, 50))
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(- (w * h))
        self.tree_item = None

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        painter.save()
        font = QFont()
        font.setBold(True)
        painter.setFont(font)
        fill_color = self.pen().color()
        outline_color = QColor(180, 180, 180)
        rect = self.rect()
        # Номер зала отрисовывается в левом нижнем углу с отступом
        pos = rect.bottomLeft() + QPointF(2, -2)
        path = QPainterPath()
        path.addText(pos, painter.font(), str(self.number))
        outline_pen = QPen(outline_color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(outline_pen)
        painter.drawPath(path)
        painter.setPen(Qt.NoPen)
        painter.fillPath(path, fill_color)
        painter.restore()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            new_pos = QPointF(value)
            try:
                scene = self.scene()
                if scene:
                    rect = self.rect()
                    scene_rect = scene.sceneRect()
                    if new_pos.x() < scene_rect.left():
                        new_pos.setX(scene_rect.left())
                    if new_pos.y() < scene_rect.top():
                        new_pos.setY(scene_rect.top())
                    if new_pos.x() + rect.width() > scene_rect.right():
                        new_pos.setX(scene_rect.right() - rect.width())
                    if new_pos.y() + rect.height() > scene_rect.bottom():
                        new_pos.setY(scene_rect.bottom() - rect.height())
                    step = scene.pixel_per_cm_x * scene.grid_step_cm
                    if step > 0:
                        new_x = round(new_pos.x() / step) * step
                        new_y = round(new_pos.y() / step) * step
                        new_pos.setX(new_x)
                        new_pos.setY(new_y)
            except RuntimeError:
                pass
            return new_pos
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        menu = QMenu()
        header_text = f"Зал {self.number}"
        header_action = menu.addAction(header_text)
        header_action.setEnabled(False)
        action_edit = menu.addAction("Редактировать зал")
        action_delete = menu.addAction("Удалить зал")
        action = menu.exec(event.screenPos())
        if action == action_edit:
            params = self.scene().mainwindow.get_hall_parameters_edit(self.number, self.name)
            if params is None:
                return
            num, name = params
            self.number = num
            self.name = name
        elif action == action_delete:
            self.delete_object()
        event.accept()

    def delete_object(self):
        mainwin = self.scene().mainwindow
        self.setParentItem(None)
        self.scene().removeItem(self)
        if self in mainwin.halls:
            mainwin.halls.remove(self)

class AnchorItem(QGraphicsEllipseItem):
    def __init__(self, x, y, number=0, main_hall_number=None):
        r = 3
        super().__init__(-r, -r, 2*r, 2*r)
        self.setPos(x, y)
        self.number = number
        self.z = 0
        self.main_hall_number = main_hall_number
        self.extra_halls = []
        self.bound = False
        pen = QPen(QColor(255, 0, 0))
        pen.setWidth(2)
        self.setPen(pen)
        self.setBrush(QColor(255, 0, 0))
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemSendsGeometryChanges)
        self.tree_item = None

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        painter.save()
        font = QFont()
        font.setBold(True)
        painter.setFont(font)
        fill_color = self.pen().color()
        outline_color = QColor(180, 180, 180)
        br = self.boundingRect()
        # Поднимаем номер якоря чуть выше, чтобы он не перекрывал круг.
        pos = QPointF(br.center().x() - br.width()/2, br.top() - 2)
        path = QPainterPath()
        path.addText(pos, painter.font(), str(self.number))
        outline_pen = QPen(outline_color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(outline_pen)
        painter.drawPath(path)
        painter.setPen(Qt.NoPen)
        painter.fillPath(path, fill_color)
        painter.restore()

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self.update()

    def mouseDoubleClickEvent(self, event):
        hall_ids = []
        if self.main_hall_number is not None:
            hall_ids.append(str(self.main_hall_number))
        if self.extra_halls:
            hall_ids.extend(str(num) for num in self.extra_halls)
        if len(hall_ids) == 1:
            halls_str = f"зал {hall_ids[0]}"
        elif hall_ids:
            halls_str = "залы " + ",".join(hall_ids)
        else:
            halls_str = ""
        if halls_str:
            header_text = f"Якорь {self.number} ({halls_str})"
        else:
            header_text = f"Якорь {self.number}"
        menu = QMenu()
        header_action = menu.addAction(header_text)
        header_action.setEnabled(False)
        action_edit = menu.addAction("Редактировать")
        action_delete = menu.addAction("Удалить")
        action = menu.exec(event.screenPos())
        if action == action_edit:
            cur_extras = ",".join(str(x) for x in self.extra_halls)
            params = self.scene().mainwindow.get_anchor_parameters_edit(self.number, self.z, cur_extras, self.bound)
            if params is None:
                return
            num, z, extras, bound_flag = params
            self.number = num
            self.z = z
            self.extra_halls = extras
            self.bound = bound_flag
        elif action == action_delete:
            self.delete_object()
        event.accept()

    def delete_object(self):
        self.setParentItem(None)
        self.scene().removeItem(self)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            new_pos = QPointF(value)
            try:
                scene = self.scene()
                if scene:
                    step = scene.pixel_per_cm_x * scene.grid_step_cm
                    if step > 0:
                        new_x = round(new_pos.x() / step) * step
                        new_y = round(new_pos.y() / step) * step
                        new_pos.setX(new_x)
                        new_pos.setY(new_y)
            except RuntimeError:
                pass
            return new_pos
        return super().itemChange(change, value)

class RectZoneItem(QGraphicsRectItem):
    def __init__(self, bottom_left, w, h, zone_num=0, zone_type="Входная зона", angle=0, parent_hall=None):
        super().__init__(0, -h, w, h, parent_hall)
        self.zone_num = zone_num
        self.zone_type = zone_type
        self.zone_angle = angle
        self.setTransformOriginPoint(0, 0)
        self.setRotation(-self.zone_angle)
        self.setPos(bottom_left)
        if self.zone_type in ("Входная зона", "Переходная"):
            pen = QPen(QColor(0, 128, 0), 2)
            brush = QColor(0, 128, 0, 50)
        else:
            pen = QPen(QColor(128, 0, 128), 2)
            brush = QColor(128, 0, 128, 50)
        self.setPen(pen)
        self.setBrush(brush)
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(- (w * h))
        self.tree_item = None

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        painter.save()
        font = QFont()
        font.setBold(True)
        painter.setFont(font)
        fill_color = self.pen().color()
        outline_color = QColor(180, 180, 180)
        rect = self.rect()
        # Номер зоны отрисовывается в левом нижнем углу с отступом 2 пикселя
        pos = rect.bottomLeft() + QPointF(2, -2)
        path = QPainterPath()
        path.addText(pos, painter.font(), str(self.zone_num))
        outline_pen = QPen(outline_color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(outline_pen)
        painter.drawPath(path)
        painter.setPen(Qt.NoPen)
        painter.fillPath(path, fill_color)
        painter.restore()

    def get_display_type(self):
        mapping = {"Входная зона": "входная", "Выходная зона": "выходная", "Переходная": "переходная"}
        return mapping.get(self.zone_type, self.zone_type.lower())

    def mouseDoubleClickEvent(self, event):
        zones = [item for item in self.scene().items(event.scenePos()) if isinstance(item, RectZoneItem)]
        zones = [z for z in zones if z.contains(z.mapFromScene(event.scenePos()))]
        if zones:
            smaller = [z for z in zones if z is not self and (z.rect().width()*z.rect().height() < self.rect().width()*self.rect().height())]
            if smaller:
                smallest = min(smaller, key=lambda z: z.rect().width()*z.rect().height())
                smallest.mouseDoubleClickEvent(event)
                return
        header_text = f"Зона {self.zone_num} ({self.get_display_type()})"
        menu = QMenu()
        header_action = menu.addAction(header_text)
        header_action.setEnabled(False)
        action_edit = menu.addAction("Редактировать")
        action_delete = menu.addAction("Удалить")
        action = menu.exec(event.screenPos())
        if action == action_edit:
            params = self.scene().mainwindow.get_zone_parameters_edit(self.zone_num, self.zone_type, self.zone_angle)
            if params is None:
                return
            num, zone_type, angle = params
            self.zone_num = num
            self.zone_type = zone_type
            self.zone_angle = angle
            self.setRotation(-self.zone_angle)
        elif action == action_delete:
            self.delete_object()
        event.accept()

    def delete_object(self):
        self.setParentItem(None)
        self.scene().removeItem(self)

    def get_export_data(self):
        scene = self.scene()
        if scene is None or not self.parentItem():
            return None
        pixel_per_cm = scene.pixel_per_cm_x
        hall = self.parentItem()
        pos = self.pos()
        hall_height = hall.rect().height()
        x_m = pos.x() / (pixel_per_cm * 100)
        y_m = (hall_height - pos.y()) / (pixel_per_cm * 100)
        w_m = self.rect().width() / (pixel_per_cm * 100)
        h_m = self.rect().height() / (pixel_per_cm * 100)
        return {
            "x": fix_negative_zero(round(x_m, 1)),
            "y": fix_negative_zero(round(y_m, 1)),
            "w": fix_negative_zero(round(w_m, 1)),
            "h": fix_negative_zero(round(h_m, 1)),
            "angle": fix_negative_zero(round(self.zone_angle, 1))
        }

class MyGraphicsView(QGraphicsView):
    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        try:
            QTimer.singleShot(0, self.scene().mainwindow.update_tree_selection)
        except RuntimeError:
            pass

class PlanGraphicsScene(QGraphicsScene):
    def __init__(self):
        super().__init__()
        self.mainwindow = None
        self.pixmap = None
        self.pixel_per_cm_x = 1.0
        self.pixel_per_cm_y = 1.0
        self.grid_step_cm = 20.0
        self.temp_item = None

    def set_background_image(self, pixmap):
        self.pixmap = pixmap
        self.setSceneRect(0, 0, pixmap.width(), pixmap.height())

    def drawBackground(self, painter, rect):
        if self.pixmap:
            painter.drawPixmap(0, 0, self.pixmap)
        step = self.pixel_per_cm_x * self.grid_step_cm
        if step <= 0:
            return
        left = int(rect.left()) - (int(rect.left()) % int(step))
        top = int(rect.top()) - (int(rect.top()) % int(step))
        right = int(rect.right())
        bottom = int(rect.bottom())
        pen = QPen(QColor(0, 0, 0, 50))
        pen.setWidth(0)
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
        diff = math.hypot(end.x()-start.x(), end.y()-start.y())
        length_cm, ok = QInputDialog.getDouble(
            self.mainwindow, "Калибровка масштаба",
            "Введите длину выбранного отрезка (см):", 100.0, 0.1, 10000.0, 1
        )
        if ok and length_cm != 0:
            scale = diff / length_cm
            self.pixel_per_cm_x = scale
            self.pixel_per_cm_y = scale
        self.mainwindow.add_mode = None
        self.mainwindow.temp_start_point = None
        if self.temp_item:
            self.removeItem(self.temp_item)
            self.temp_item = None
        self.mainwindow.statusBar().showMessage("Калибровка завершена.")
        self.mainwindow.grid_calibrated = True
        step, ok = QInputDialog.getInt(
            self.mainwindow, "Шаг координатной сетки",
            "Укажите шаг сетки (см):", 10, 1, 1000
        )
        if ok:
            self.grid_step_cm = float(step)
        self.mainwindow.resnap_objects()
        self.update()

    def mousePressEvent(self, event):
        if self.mainwindow and self.mainwindow.add_mode:
            mode = self.mainwindow.add_mode
            pos = event.scenePos()
            if mode == "calibrate":
                if self.mainwindow.temp_start_point is None:
                    self.mainwindow.temp_start_point = pos
                    self.temp_item = QGraphicsLineItem()
                    pen = QPen(QColor(255, 0, 0))
                    pen.setWidth(2)
                    self.temp_item.setPen(pen)
                    self.addItem(self.temp_item)
                    self.temp_item.setLine(pos.x(), pos.y(), pos.x(), pos.y())
                else:
                    QTimer.singleShot(0, lambda: self.finishCalibration(self.mainwindow.temp_start_point, pos))
                return
            elif mode == "hall":
                if self.mainwindow.temp_start_point is None:
                    self.mainwindow.temp_start_point = pos
                    self.temp_item = QGraphicsRectItem()
                    pen = QPen(QColor(0, 0, 255))
                    pen.setStyle(Qt.DashLine)
                    pen.setWidth(2)
                    self.temp_item.setPen(pen)
                    self.temp_item.setBrush(QColor(0, 0, 0, 0))
                    self.addItem(self.temp_item)
                    self.temp_item.setRect(QRectF(pos, QSizeF(0, 0)))
                return
            elif mode == "zone":
                if self.mainwindow.temp_start_point is None:
                    hall = None
                    for h in self.mainwindow.halls:
                        if h.contains(h.mapFromScene(pos)):
                            hall = h
                            break
                    if hall is None:
                        return
                    self.mainwindow.current_hall_for_zone = hall
                    self.mainwindow.temp_start_point = pos
                    self.temp_item = QGraphicsRectItem()
                    pen = QPen(QColor(0, 128, 0))
                    pen.setStyle(Qt.DashLine)
                    pen.setWidth(2)
                    self.temp_item.setPen(pen)
                    self.temp_item.setBrush(QColor(0, 0, 0, 0))
                    self.addItem(self.temp_item)
                    self.temp_item.setRect(QRectF(pos, QSizeF(0, 0)))
                return
            elif mode == "anchor":
                hall = None
                for h in self.mainwindow.halls:
                    if h.contains(h.mapFromScene(pos)):
                        hall = h
                        break
                if hall is None:
                    QMessageBox.warning(self.mainwindow, "Ошибка", "Не найден зал, в котором можно создать якорь.")
                    return
                params = self.mainwindow.get_anchor_parameters()
                if params is None:
                    self.mainwindow.add_mode = None
                    self.mainwindow.statusBar().clearMessage()
                    return
                num, z, extras, bound_flag = params
                anchor = AnchorItem(pos.x(), pos.y(), num, main_hall_number=hall.number)
                anchor.z = z
                anchor.extra_halls = extras
                anchor.bound = bound_flag
                self.addItem(anchor)
                self.mainwindow.anchors.append(anchor)
                self.mainwindow.add_mode = None
                self.mainwindow.statusBar().clearMessage()
                self.mainwindow.populate_tree()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.mainwindow and self.mainwindow.add_mode:
            mode = self.mainwindow.add_mode
            if mode in ("hall", "zone") and self.mainwindow.temp_start_point:
                start = self.mainwindow.temp_start_point
                pos = event.scenePos()
                if mode == "zone" and self.mainwindow.current_hall_for_zone:
                    hall = self.mainwindow.current_hall_for_zone
                    local = hall.mapFromScene(pos)
                    if local.x() < 0: local.setX(0)
                    if local.y() < 0: local.setY(0)
                    if local.x() > hall.rect().width(): local.setX(hall.rect().width())
                    if local.y() > hall.rect().height(): local.setY(hall.rect().height())
                    pos = hall.mapToScene(local)
                if self.temp_item:
                    rect = QRectF(self.mainwindow.temp_start_point, pos).normalized()
                    self.temp_item.setRect(rect)
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.mainwindow and self.mainwindow.add_mode:
            mode = self.mainwindow.add_mode
            if mode == "hall" and self.mainwindow.temp_start_point:
                start = self.mainwindow.temp_start_point
                end = event.scenePos()
                rect = QRectF(start, end).normalized()
                step = self.pixel_per_cm_x * self.grid_step_cm
                x0, y0, x1, y1 = rect.left(), rect.top(), rect.right(), rect.bottom()
                if step > 0:
                    x0 = round(x0 / step) * step
                    y0 = round(y0 / step) * step
                    x1 = round(x1 / step) * step
                    y1 = round(y1 / step) * step
                if x1 == x0: x1 = x0 + step
                if y1 == y0: y1 = y0 + step
                w, h = x1 - x0, y1 - y0
                hall = HallItem(x0, y0, w, h, "", 0)
                self.addItem(hall)
                self.mainwindow.halls.append(hall)
                params = self.mainwindow.get_hall_parameters()
                if params is None:
                    hall.setParentItem(None)
                    self.removeItem(hall)
                    self.mainwindow.halls.remove(hall)
                    self.mainwindow.temp_start_point = None
                    self.mainwindow.add_mode = None
                    if self.temp_item:
                        self.removeItem(self.temp_item)
                        self.temp_item = None
                    self.mainwindow.statusBar().clearMessage()
                    return
                num, name = params
                hall.number = num
                hall.name = name
                self.mainwindow.temp_start_point = None
                self.mainwindow.add_mode = None
                if self.temp_item:
                    self.removeItem(self.temp_item)
                    self.temp_item = None
                self.mainwindow.statusBar().clearMessage()
                self.mainwindow.populate_tree()
                if not self.selectedItems():
                    hall.setSelected(True)
                    self.mainwindow.last_selected_items = [hall]
                return
            elif mode == "zone" and self.mainwindow.temp_start_point:
                start = self.mainwindow.temp_start_point
                end = event.scenePos()
                hall = self.mainwindow.current_hall_for_zone
                if hall is None:
                    self.mainwindow.temp_start_point = None
                    self.mainwindow.add_mode = None
                    if self.temp_item:
                        self.removeItem(self.temp_item)
                        self.temp_item = None
                    return
                rect = QRectF(hall.mapFromScene(start), hall.mapFromScene(end)).normalized()
                step = self.pixel_per_cm_x * self.grid_step_cm
                x0, y0, x1, y1 = rect.left(), rect.top(), rect.right(), rect.bottom()
                if step > 0:
                    x0 = round(x0 / step) * step
                    y0 = round(y0 / step) * step
                    x1 = round(x1 / step) * step
                    y1 = round(y1 / step) * step
                if x1 == x0: x1 = x0 + step
                if y1 == y0: y1 = y0 + step
                bottom_left = QPointF(min(x0, x1), max(y0, y1))
                w, h = abs(x1 - x0), abs(y1 - y0)
                params = self.mainwindow.get_zone_parameters()
                if params is None:
                    if self.temp_item:
                        self.removeItem(self.temp_item)
                        self.temp_item = None
                    self.mainwindow.temp_start_point = None
                    self.mainwindow.add_mode = None
                    self.mainwindow.statusBar().clearMessage()
                    return
                num, zone_type, angle = params
                zone = RectZoneItem(bottom_left, w, h, num, zone_type, angle, hall)
                self.mainwindow.temp_start_point = None
                self.mainwindow.add_mode = None
                self.mainwindow.current_hall_for_zone = None
                if self.temp_item:
                    self.removeItem(self.temp_item)
                    self.temp_item = None
                self.mainwindow.statusBar().clearMessage()
                self.mainwindow.populate_tree()
                if not self.selectedItems():
                    zone.setSelected(True)
                    self.mainwindow.last_selected_items = [zone]
                return
        super().mouseReleaseEvent(event)
        try:
            if self.mainwindow:
                self.mainwindow.populate_tree()
                if not self.selectedItems():
                    clicked_item = self.itemAt(event.scenePos(), self.views()[0].transform())
                    if clicked_item:
                        clicked_item.setSelected(True)
                        self.mainwindow.last_selected_items = [clicked_item]
                        self.mainwindow.on_scene_selection_changed()
        except RuntimeError:
            pass

def format_simple_obj(obj):
    return '{ "x": ' + str(obj["x"]) + ', "y": ' + str(obj["y"]) + ', "w": ' + str(obj["w"]) + ', "h": ' + str(obj["h"]) + ', "angle": ' + str(obj["angle"]) + ' }'

def format_zone(zone):
    s = '{\n'
    s += '"num": ' + str(zone["num"]) + ',\n'
    s += '"enter": ' + format_simple_obj(zone["enter"]) + ',\n'
    s += '"exit": ' + format_simple_obj(zone["exit"])
    if "bound" in zone and zone["bound"]:
        s += ',\n"bound": true'
    s += '\n}'
    return s

def format_anchor(anchor):
    s = '{ "id": ' + str(anchor["id"]) + ', "x": ' + str(anchor["x"]) + ', "y": ' + str(anchor["y"]) + ', "z": ' + str(anchor["z"])
    if "bound" in anchor and anchor["bound"]:
        s += ', "bound": true'
    s += ' }'
    return s

class PlanEditorMainWindow(QMainWindow):
    def get_hall_parameters(self):
        default_num = 1
        if self.halls:
            default_num = max(hall.number for hall in self.halls) + 1
        return getHallParameters(default_num=default_num, default_name="")

    def get_hall_parameters_edit(self, current_number, current_name):
        return getHallParameters(default_num=current_number, default_name=current_name)

    def get_anchor_parameters(self):
        default_num = 1
        if self.anchors:
            default_num = max(anchor.number for anchor in self.anchors) + 1
        return getAnchorParameters(default_num=default_num, default_z=0, default_extras="", default_bound=False)

    def get_anchor_parameters_edit(self, current_number, current_z, current_extras="", current_bound=False):
        return getAnchorParameters(default_num=current_number, default_z=current_z, default_extras=current_extras, default_bound=current_bound)

    def get_zone_parameters(self):
        default_num = 1
        if self.current_hall_for_zone:
            zones = [child for child in self.current_hall_for_zone.childItems() if isinstance(child, RectZoneItem)]
            if zones:
                default_num = max(zone.zone_num for zone in zones) + 1
        return getZoneParameters(default_num=default_num, default_type="Входная зона", default_angle=0)

    def get_zone_parameters_edit(self, current_number, current_zone_type, current_angle):
        return getZoneParameters(default_num=current_number, default_type=current_zone_type, default_angle=current_angle)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("RG Tags Mapper")
        self.resize(1200, 800)
        self.scene = PlanGraphicsScene()
        self.scene.mainwindow = self
        self.scene.selectionChanged.connect(self.on_scene_selection_changed)
        self.view = MyGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setCentralWidget(self.view)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Объекты")
        self.tree.setWordWrap(True)
        dock = QDockWidget("Список объектов", self)
        dock.setWidget(self.tree)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        toolbar = QToolBar("Инструменты", self)
        self.addToolBar(toolbar)
        act_open = QAction("Открыть изображение", self)
        act_calibrate = QAction("Выполнить калибровку", self)
        toolbar.addAction(act_open)
        toolbar.addAction(act_calibrate)
        toolbar.addSeparator()
        act_save = QAction("Сохранить проект", self)
        act_load = QAction("Загрузить проект", self)
        toolbar.addAction(act_save)
        toolbar.addAction(act_load)
        toolbar.addSeparator()
        act_add_hall = QAction("Добавить зал", self)
        act_add_anchor = QAction("Добавить якорь", self)
        act_add_zone = QAction("Добавить зону", self)
        toolbar.addAction(act_add_hall)
        toolbar.addAction(act_add_anchor)
        toolbar.addAction(act_add_zone)
        toolbar.addSeparator()
        act_export = QAction("Экспорт конфигурации", self)
        toolbar.addAction(act_export)
        act_open.triggered.connect(self.open_image)
        act_calibrate.triggered.connect(self.perform_calibration)
        act_save.triggered.connect(self.save_project)
        act_load.triggered.connect(self.load_project)
        act_export.triggered.connect(self.export_config)
        act_add_hall.triggered.connect(lambda: self.set_mode("hall"))
        act_add_anchor.triggered.connect(lambda: self.set_mode("anchor"))
        act_add_zone.triggered.connect(lambda: self.set_mode("zone"))
        self.add_mode = None
        self.temp_start_point = None
        self.current_hall_for_zone = None
        self.halls = []
        self.anchors = []
        self.grid_calibrated = False
        self.last_selected_items = []
        self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
        self.view.wheelEvent = self.handle_wheel_event
        self.statusBar().setMinimumHeight(30)
        self.statusBar().showMessage("Загрузите изображение для начала работы.")
        self.current_project_file = None

    def perform_calibration(self):
        if not self.scene.pixmap:
            QMessageBox.warning(self, "Ошибка", "Сначала загрузите изображение!")
            return
        self.set_mode("calibrate")
        self.statusBar().showMessage("Нажмите на 2 точки на изображении для калибровки")

    def resnap_objects(self):
        grid_step_px = self.scene.pixel_per_cm_x * self.scene.grid_step_cm
        for hall in self.halls:
            pos = hall.pos()
            new_x = round(pos.x() / grid_step_px) * grid_step_px
            new_y = round(pos.y() / grid_step_px) * grid_step_px
            hall.setPos(new_x, new_y)
        for anchor in self.anchors:
            pos = anchor.scenePos()
            new_x = round(pos.x() / grid_step_px) * grid_step_px
            new_y = round(pos.y() / grid_step_px) * grid_step_px
            anchor.setPos(new_x, new_y)
        self.populate_tree()
        self.statusBar().showMessage("Калибровка выполнена и координаты объектов пересчитаны.")

    def on_scene_selection_changed(self):
        try:
            current = self.scene.selectedItems()
        except RuntimeError:
            return
        if current:
            self.last_selected_items = current
            for item in current:
                if hasattr(item, 'tree_item') and item.tree_item is not None:
                    item.tree_item.setSelected(True)
        elif self.last_selected_items:
            for item in self.last_selected_items:
                if hasattr(item, 'tree_item') and item.tree_item is not None:
                    item.tree_item.setSelected(True)

    def update_tree_selection(self):
        try:
            items = [item for item in self.scene.items() if item.isSelected()]
        except RuntimeError:
            return
        if items:
            self.last_selected_items = items
            def clear_tree_selection(item):
                item.setSelected(False)
                for i in range(item.childCount()):
                    clear_tree_selection(item.child(i))
            for i in range(self.tree.topLevelItemCount()):
                clear_tree_selection(self.tree.topLevelItem(i))
            for item in items:
                if hasattr(item, 'tree_item') and item.tree_item is not None:
                    item.tree_item.setSelected(True)
        elif self.last_selected_items:
            for item in self.last_selected_items:
                if hasattr(item, 'tree_item') and item.tree_item is not None:
                    item.tree_item.setSelected(True)

    def handle_wheel_event(self, event):
        factor = 1.2 if event.angleDelta().y() > 0 else 1/1.2
        self.view.scale(factor, factor)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            for item in self.scene.selectedItems():
                if isinstance(item, HallItem) and item in self.halls:
                    self.halls.remove(item)
                if item in self.anchors:
                    self.anchors.remove(item)
                item.setParentItem(None)
                self.scene.removeItem(item)
        else:
            super().keyPressEvent(event)

    def hall_number_exists(self, num):
        for hall in self.halls:
            if hall.number == num:
                return True
        return False

    def anchor_number_exists(self, num):
        return False

    def wrap_text(self, text):
        return text

    def populate_tree(self):
        self.tree.clear()
        for hall in self.halls:
            w_m = hall.rect().width() / (self.scene.pixel_per_cm_x * 100)
            h_m = hall.rect().height() / (self.scene.pixel_per_cm_x * 100)
            if hall.name.strip():
                room_text = f'Зал {hall.number} "{hall.name}" ({w_m:.1f} x {h_m:.1f} м)'
            else:
                room_text = f'Зал {hall.number} ({w_m:.1f} x {h_m:.1f} м)'
            hall_item = QTreeWidgetItem([room_text])
            hall.tree_item = hall_item
            self.tree.addTopLevelItem(hall_item)
            for anchor in self.anchors:
                if (anchor.main_hall_number == hall.number) or (hall.number in anchor.extra_halls):
                    pos = anchor.scenePos()
                    local = hall.mapFromScene(pos)
                    x_m = fix_negative_zero(round(local.x() / (self.scene.pixel_per_cm_x * 100), 1))
                    y_m = fix_negative_zero(round((hall.rect().height() - local.y()) / (self.scene.pixel_per_cm_x * 100), 1))
                    anchor_text = f'Якорь {anchor.number} (x={x_m} м, y={y_m} м, z={fix_negative_zero(round(anchor.z/100.0, 1))} м)'
                    anchor_item = QTreeWidgetItem([anchor_text])
                    anchor.tree_item = anchor_item
                    hall_item.addChild(anchor_item)
            zones_group = {}
            default_zone = {"x": 0, "y": 0, "w": 0, "h": 0, "angle": 0}
            for obj in hall.childItems():
                if isinstance(obj, RectZoneItem):
                    num = obj.zone_num
                    if num not in zones_group:
                        zones_group[num] = {"num": num, "enter": default_zone.copy(), "exit": default_zone.copy()}
                    if obj.zone_type == "Входная зона":
                        zones_group[num]["enter"] = obj.get_export_data()
                    elif obj.zone_type == "Выходная зона":
                        zones_group[num]["exit"] = obj.get_export_data()
                    elif obj.zone_type == "Переходная":
                        zones_group[num]["enter"] = obj.get_export_data()
                        zones_group[num]["exit"] = default_zone.copy()
                        zones_group[num]["bound"] = True
            for zone in zones_group.values():
                zone_text = f"Зона {zone['num']}: enter: x = {zone['enter']['x']} м, y = {zone['enter']['y']} м, w = {zone['enter']['w']} м, h = {zone['enter']['h']} м, angle = {zone['enter']['angle']}°; exit: x = {zone['exit']['x']} м, y = {zone['exit']['y']} м, w = {zone['exit']['w']} м, h = {zone['exit']['h']} м, angle = {zone['exit']['angle']}°"
                zone_item = QTreeWidgetItem([zone_text])
                for obj in hall.childItems():
                    if isinstance(obj, RectZoneItem) and obj.zone_num == zone['num']:
                        obj.tree_item = zone_item
                hall_item.addChild(zone_item)
            hall_item.setExpanded(True)

    def set_mode(self, mode):
        if not self.grid_calibrated and mode != "calibrate":
            QMessageBox.information(self, "Внимание", "Сначала выполните калибровку координатной сетки!")
            return
        self.add_mode = mode
        self.temp_start_point = None
        self.current_hall_for_zone = None
        message = ""
        if mode == "hall":
            message = "Укажите прямоугольную область зала на плане."
        elif mode == "anchor":
            message = "Кликните в пределах какого-либо зала для создания якоря."
        elif mode == "zone":
            message = "Укажите прямоугольную зону внутри зала."
        elif mode == "calibrate":
            message = "Укажите 2 точки на изображении для определения отрезка с известной длиной"
        self.statusBar().showMessage(message)

    def open_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Открыть изображение", "", "Изображения (*.png *.jpg *.bmp)")
        if file_path:
            pixmap = QPixmap(file_path)
            if pixmap.isNull():
                QMessageBox.warning(self, "Ошибка", "Не удалось загрузить изображение. Проверьте файл.")
                return
            self.scene.clear()
            self.halls.clear()
            self.anchors.clear()
            self.scene.set_background_image(pixmap)
            self.grid_calibrated = False
            self.statusBar().showMessage("Калибровка: Укажите 2 точки на изображении для определения отрезка с известной длиной")
            self.set_mode("calibrate")

    def save_project(self):
        if self.current_project_file is None:
            file_path, _ = QFileDialog.getSaveFileName(self, "Сохранить проект", "", "Файл проекта (*.proj)")
            if not file_path:
                return
            self.current_project_file = file_path
        else:
            file_path = self.current_project_file
        image_data = ""
        if self.scene.pixmap:
            buffer = QBuffer()
            buffer.open(QBuffer.WriteOnly)
            self.scene.pixmap.save(buffer, "PNG")
            image_bytes = buffer.data()
            image_data = image_bytes.toBase64().data().decode("utf-8")
        data = {
            "image_data": image_data,
            "pixel_per_cm_x": self.scene.pixel_per_cm_x,
            "pixel_per_cm_y": self.scene.pixel_per_cm_y,
            "grid_step_cm": self.scene.grid_step_cm,
            "halls": [],
            "anchors": []
        }
        for hall in self.halls:
            hall_data = {
                "num": hall.number,
                "name": hall.name,
                "x_px": hall.pos().x(),
                "y_px": hall.pos().y(),
                "w_px": hall.rect().width(),
                "h_px": hall.rect().height()
            }
            zones = []
            for child in hall.childItems():
                if isinstance(child, RectZoneItem):
                    zone_data = {
                        "zone_num": child.zone_num,
                        "zone_type": child.zone_type,
                        "zone_angle": child.zone_angle,
                        "bottom_left_x": child.pos().x(),
                        "bottom_left_y": child.pos().y(),
                        "w_px": child.rect().width(),
                        "h_px": child.rect().height()
                    }
                    zones.append(zone_data)
            hall_data["zones"] = zones
            data["halls"].append(hall_data)
        for anchor in self.anchors:
            anchor_data = {
                "number": anchor.number,
                "z": anchor.z,
                "x": anchor.scenePos().x(),
                "y": anchor.scenePos().y(),
                "main_hall": anchor.main_hall_number,
                "extra_halls": anchor.extra_halls
            }
            if getattr(anchor, "bound", False):
                anchor_data["bound"] = True
            data["anchors"].append(anchor_data)
        try:
            json_str = json.dumps(data, ensure_ascii=False, separators=(',', ': '))
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(json_str)
            QMessageBox.information(self, "Сохранение", "Проект сохранён.")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить проект:\n{e}")

    def load_project(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Загрузить проект", "", "Файл проекта (*.proj)")
        if not file_path:
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка чтения файла:\n{e}")
            return
        self.scene.clear()
        self.halls.clear()
        self.anchors.clear()
        image_data = data.get("image_data", "")
        if image_data:
            img_bytes = QByteArray.fromBase64(image_data.encode("utf-8"))
            pixmap = QPixmap()
            pixmap.loadFromData(img_bytes, "PNG")
            self.scene.set_background_image(pixmap)
        self.scene.pixel_per_cm_x = data.get("pixel_per_cm_x", 1.0)
        self.scene.pixel_per_cm_y = data.get("pixel_per_cm_y", 1.0)
        self.scene.grid_step_cm = data.get("grid_step_cm", 20.0)
        self.grid_calibrated = True
        for hall_data in data.get("halls", []):
            hall = HallItem(
                hall_data.get("x_px", 0),
                hall_data.get("y_px", 0),
                hall_data.get("w_px", 100),
                hall_data.get("h_px", 100),
                hall_data.get("name", ""),
                hall_data.get("num", 0)
            )
            self.scene.addItem(hall)
            self.halls.append(hall)
            for zone_data in hall_data.get("zones", []):
                bottom_left = QPointF(zone_data.get("bottom_left_x", 0), zone_data.get("bottom_left_y", 0))
                zone = RectZoneItem(bottom_left,
                                    zone_data.get("w_px", 0),
                                    zone_data.get("h_px", 0),
                                    zone_data.get("zone_num", 0),
                                    zone_data.get("zone_type", "Входная зона"),
                                    zone_data.get("zone_angle", 0),
                                    hall)
        for anchor_data in data.get("anchors", []):
            anchor = AnchorItem(
                anchor_data.get("x", 0),
                anchor_data.get("y", 0),
                anchor_data.get("number", 0),
                main_hall_number=anchor_data.get("main_hall")
            )
            anchor.z = anchor_data.get("z", 0)
            anchor.extra_halls = anchor_data.get("extra_halls", [])
            if "bound" in anchor_data:
                anchor.bound = anchor_data["bound"]
            self.scene.addItem(anchor)
            self.anchors.append(anchor)
        self.populate_tree()
        self.current_project_file = file_path
        QMessageBox.information(self, "Загрузка", "Проект успешно загружён.")
        self.statusBar().clearMessage()

    def export_config(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Экспорт конфигурации", "", "JSON файлы (*.json)")
        if not file_path:
            return
        config = {"rooms": []}
        for hall in self.halls:
            room = {"num": hall.number, "anchors": [], "zones": []}
            for anchor in self.anchors:
                if (anchor.main_hall_number == hall.number) or (hall.number in anchor.extra_halls):
                    local = hall.mapFromScene(anchor.scenePos())
                    x_m = fix_negative_zero(round(local.x() / (self.scene.pixel_per_cm_x * 100), 1))
                    y_m = fix_negative_zero(round((hall.rect().height() - local.y()) / (self.scene.pixel_per_cm_x * 100), 1))
                    anchor_entry = {
                        "id": anchor.number,
                        "x": x_m,
                        "y": y_m,
                        "z": fix_negative_zero(round(anchor.z/100.0, 1))
                    }
                    if getattr(anchor, "bound", False):
                        anchor_entry["bound"] = True
                    room["anchors"].append(anchor_entry)
            zones_group = {}
            default_zone = {"x": 0, "y": 0, "w": 0, "h": 0, "angle": 0}
            for obj in hall.childItems():
                if isinstance(obj, RectZoneItem):
                    num = obj.zone_num
                    if num not in zones_group:
                        zones_group[num] = {"num": num, "enter": default_zone.copy(), "exit": default_zone.copy()}
                    data_zone = obj.get_export_data()
                    if obj.zone_type == "Входная зона":
                        zones_group[num]["enter"] = data_zone
                    elif obj.zone_type == "Выходная зона":
                        zones_group[num]["exit"] = data_zone
                    elif obj.zone_type == "Переходная":
                        zones_group[num]["enter"] = data_zone
                        zones_group[num]["exit"] = default_zone.copy()
                        zones_group[num]["bound"] = True
            for zone in zones_group.values():
                room["zones"].append(zone)
            config["rooms"].append(room)
        result = '{\n"rooms": [\n'
        rooms_str = []
        for room in config["rooms"]:
            room_lines = []
            room_lines.append('{')
            room_lines.append('"num": ' + str(room["num"]) + ',')
            room_lines.append('"anchors": [')
            anchor_lines = []
            for anchor in room["anchors"]:
                anchor_lines.append(format_anchor(anchor))
            room_lines.append(",\n".join(anchor_lines))
            room_lines.append('],')
            room_lines.append('"zones": [')
            zone_lines = []
            for zone in room["zones"]:
                zone_lines.append(format_zone(zone))
            room_lines.append(",\n".join(zone_lines))
            room_lines.append(']')
            room_lines.append('}')
            rooms_str.append("\n".join(room_lines))
        result += ",\n".join(rooms_str)
        result += "\n]\n}"
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(result)
            QMessageBox.information(self, "Экспорт", "Конфигурация экспортирована в файл.")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать конфигурацию:\n{e}")

    def closeEvent(self, event):
        reply = QMessageBox.question(self, "Сохранение проекта", "Сохранить проект перед выходом?", QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        if reply == QMessageBox.Yes:
            self.save_project()
        elif reply == QMessageBox.Cancel:
            event.ignore()
            return
        try:
            self.scene.selectionChanged.disconnect(self.on_scene_selection_changed)
        except Exception:
            pass
        self.view.setScene(None)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PlanEditorMainWindow()
    window.show()
    sys.exit(app.exec())
