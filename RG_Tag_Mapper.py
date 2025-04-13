import sys
import math
import json
import base64
from PySide6.QtWidgets import (QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
                               QGraphicsItem, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsLineItem,
                               QMenu, QTreeWidget, QTreeWidgetItem, QDockWidget,
                               QFileDialog, QInputDialog, QToolBar, QMessageBox)
from PySide6.QtGui import QAction, QPainter, QPen, QBrush, QColor, QPixmap, QPainterPath
from PySide6.QtCore import Qt, QRectF, QPointF, QSizeF, QBuffer, QByteArray

def fix_negative_zero(val):
    if abs(val) < 1e-9:
        return 0.0
    return val

# ==========================
# ГРАФИЧЕСКИЕ ОБЪЕКТЫ
# ==========================

class HallItem(QGraphicsRectItem):
    """
    Элемент зала. Локальная система координат зала: (0,0) – верхний левый угол.
    Сохраняет позицию зала в сцене и его размеры (в пикселях).
    """
    def __init__(self, x, y, w, h, name="", number=0):
        super().__init__(0, 0, w, h)
        self.setPos(x, y)
        self.name = name
        self.number = number
        pen = QPen(QColor(0, 0, 255))
        pen.setWidth(2)
        self.setPen(pen)
        self.setBrush(QColor(0, 0, 255, 50))
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemSendsGeometryChanges)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            new_pos = QPointF(value)
            scene = self.scene()
            if scene is not None:
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
            return new_pos
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        menu = QMenu()
        action_edit = menu.addAction("Редактировать зал")
        action_delete = menu.addAction("Удалить зал")
        action = menu.exec(event.screenPos())
        if action == action_edit:
            self.edit_hall()
        elif action == action_delete:
            # Удаляем зал из сцены и из списка в основном окне
            mainwin = self.scene().mainwindow
            self.scene().removeItem(self)
            if self in mainwin.halls:
                mainwin.halls.remove(self)
        event.accept()

    def edit_hall(self):
        mainwin = self.scene().mainwindow
        new_num, ok = QInputDialog.getInt(mainwin, "Редактировать зал", "Новый номер зала:",
                                           self.number, 1, 10000)
        if ok and new_num != self.number:
            # Проверяем уникальность, исключая текущий зал
            if any(h.number == new_num and h is not self for h in mainwin.halls):
                QMessageBox.warning(mainwin, "Ошибка", "Зал с таким номером уже существует!")
                return
            self.number = new_num
        new_name, ok_name = QInputDialog.getText(mainwin, "Редактировать зал", "Новое название зала:", text=self.name)
        if ok_name:
            self.name = new_name

class AnchorItem(QGraphicsEllipseItem):
    """
    Якорь – при создании запрашивается номер и обязательно вводится координата z.
    Отображается как красный кружок; позиция задаётся относительно зала.
    """
    def __init__(self, x, y, number=0, parent_hall=None):
        r = 3
        super().__init__(-r, -r, 2*r, 2*r, parent_hall)
        self.setPos(x, y)
        self.number = number
        self.z = 0  # координата z (в см)
        pen = QPen(QColor(255, 0, 0))
        pen.setWidth(2)
        self.setPen(pen)
        self.setBrush(QColor(255, 0, 0))
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemSendsGeometryChanges)

    def mouseDoubleClickEvent(self, event):
        menu = QMenu()
        action_edit = menu.addAction("Редактировать")
        action_delete = menu.addAction("Удалить")
        action = menu.exec(event.screenPos())
        if action == action_edit:
            self.edit_anchor()
        elif action == action_delete:
            self.scene().removeItem(self)
        event.accept()

    def edit_anchor(self):
        mainwin = self.scene().mainwindow
        new_num, ok = QInputDialog.getInt(mainwin, "Редактировать якорь", "Новый номер якоря:",
                                           self.number, 1, 10000)
        if ok and new_num != self.number:
            if mainwin.anchor_number_exists(new_num):
                QMessageBox.warning(mainwin, "Ошибка", "Якорь с таким номером уже существует!")
                return
            self.number = new_num
        new_z, ok_z = QInputDialog.getDouble(mainwin, "Редактировать якорь", "Новая координата Z (см):",
                                              self.z, -10000.0, 10000.0, 1)
        if ok_z:
            self.z = new_z

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            new_pos = QPointF(value)
            scene = self.scene()
            if scene is not None and self.parentItem() is not None:
                hall = self.parentItem()
                rect = hall.rect()
                if new_pos.x() < 0: new_pos.setX(0)
                if new_pos.y() < 0: new_pos.setY(0)
                if new_pos.x() > rect.width(): new_pos.setX(rect.width())
                if new_pos.y() > rect.height(): new_pos.setY(rect.height())
                step = scene.pixel_per_cm_x * scene.grid_step_cm
                if step > 0:
                    new_x = round(new_pos.x() / step) * step
                    new_y = round(new_pos.y() / step) * step
                    new_pos.setX(new_x)
                    new_pos.setY(new_y)
            return new_pos
        return super().itemChange(change, value)

class RectZoneItem(QGraphicsRectItem):
    """
    Прямоугольная зона. Нижний левый угол – точка отсчёта.
    После создания запрашиваются: номер зоны, тип зоны (Входная зона / Выходная зона)
    и угол поворота (°).
    """
    def __init__(self, bottom_left, w, h, zone_num=0, zone_type="Входная зона", angle=0, parent_hall=None):
        super().__init__(0, -h, w, h, parent_hall)
        self.zone_num = zone_num
        self.zone_type = zone_type
        self.zone_angle = angle  # угол в градусах
        self.setTransformOriginPoint(0, 0)
        self.setRotation(self.zone_angle)
        self.setPos(bottom_left)
        if self.zone_type == "Входная зона":
            pen = QPen(QColor(0, 128, 0), 2)
            brush = QColor(0, 128, 0, 50)
        else:
            pen = QPen(QColor(128, 0, 128), 2)
            brush = QColor(128, 0, 128, 50)
        self.setPen(pen)
        self.setBrush(brush)
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemSendsGeometryChanges)

    def mouseDoubleClickEvent(self, event):
        zones = [item for item in self.scene().items(event.scenePos()) if isinstance(item, RectZoneItem)]
        zones = [z for z in zones if z.contains(z.mapFromScene(event.scenePos()))]
        if zones:
            smaller = [z for z in zones if z is not self and (z.rect().width() * z.rect().height() < self.rect().width() * self.rect().height())]
            if smaller:
                smallest = min(smaller, key=lambda z: z.rect().width() * z.rect().height())
                smallest.mouseDoubleClickEvent(event)
                return
        menu = QMenu()
        action_edit = menu.addAction("Редактировать")
        action_delete = menu.addAction("Удалить")
        action = menu.exec(event.screenPos())
        if action == action_edit:
            self.edit_zone()
        elif action == action_delete:
            self.scene().removeItem(self)
        event.accept()

    def edit_zone(self):
        scene = self.scene()
        if scene is None:
            return
        pixel_per_cm = scene.pixel_per_cm_x
        curr_w = self.rect().width()
        curr_h = self.rect().height()
        curr_angle = self.zone_angle
        new_w, ok1 = QInputDialog.getDouble(self.scene().views()[0], "Редактировать зону", "Ширина (м):",
                                            curr_w/(pixel_per_cm*100), 0.1, 1000, 1)
        if not ok1:
            return
        new_h, ok2 = QInputDialog.getDouble(self.scene().views()[0], "Редактировать зону", "Высота (м):",
                                            curr_h/(pixel_per_cm*100), 0.1, 1000, 1)
        if not ok2:
            return
        new_angle, ok3 = QInputDialog.getDouble(self.scene().views()[0], "Редактировать зону", "Угол поворота (°):",
                                                curr_angle, 0, 90, 1)
        if not ok3:
            return
        new_w_px = new_w * pixel_per_cm * 100
        new_h_px = new_h * pixel_per_cm * 100
        self.setRect(0, -new_h_px, new_w_px, new_h_px)
        self.zone_angle = new_angle
        self.setRotation(new_angle)

    def get_export_data(self):
        scene = self.scene()
        if scene is None or self.parentItem() is None:
            return None
        pixel_per_cm = scene.pixel_per_cm_x
        hall = self.parentItem()
        pos = self.pos()  # нижний левый угол зоны
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

class PlanGraphicsScene(QGraphicsScene):
    def __init__(self):
        super().__init__()
        self.mainwindow = None    # Ссылка на главное окно
        self.pixmap = None        # Загруженное изображение
        self.pixel_per_cm_x = 1.0  # Масштаб: пикселей на см
        self.pixel_per_cm_y = 1.0
        self.grid_step_cm = 20.0   # Шаг сетки (см)
        self.temp_item = None     # Временный элемент (линия или прямоугольник)

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
                    start = self.mainwindow.temp_start_point
                    end = QPointF(pos)
                    dx = abs(end.x() - start.x())
                    dy = abs(end.y() - start.y())
                    if dx >= dy:
                        end.setY(start.y())
                    else:
                        end.setX(start.x())
                    diff = math.hypot(end.x()-start.x(), end.y()-start.y())
                    length_cm, ok = QInputDialog.getDouble(self.mainwindow, "Калибровка масштаба",
                                                            "Введите длину выбранного отрезка (см):", 100.0, 0.1, 10000.0, 1)
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
                    # Значение по умолчанию для шага сетки: 10 см.
                    step, ok = QInputDialog.getInt(self.mainwindow, "Шаг координатной сетки",
                                                   "Укажите шаг сетки (см):", 10, 1, 1000)
                    if ok:
                        self.grid_step_cm = float(step)
                    self.update()  # Перерисовать сцену с новой сеткой.
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
                if hall is not None:
                    local_point = hall.mapFromScene(pos)
                    x = local_point.x()
                    y = local_point.y()
                    anchor = AnchorItem(x, y, 0, hall)
                    num, ok = QInputDialog.getInt(self.mainwindow, "Номер якоря", "Введите номер якоря:", 1, 0, 10000)
                    if ok and self.mainwindow.anchor_number_exists(num):
                        QMessageBox.warning(self.mainwindow, "Ошибка", "Якорь с таким номером уже существует!")
                        self.removeItem(anchor)
                        self.mainwindow.add_mode = None
                        self.mainwindow.statusBar().clearMessage()
                        return
                    if ok:
                        anchor.number = num
                        z_val, ok_z = QInputDialog.getDouble(self.mainwindow, "Координата Z", "Введите координату Z (см):", 0.0, -10000.0, 10000.0, 1)
                        if ok_z:
                            anchor.z = z_val
                        else:
                            self.removeItem(anchor)
                    else:
                        self.removeItem(anchor)
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
                x0 = rect.left(); y0 = rect.top()
                x1 = rect.right(); y1 = rect.bottom()
                if step > 0:
                    x0 = round(x0 / step) * step
                    y0 = round(y0 / step) * step
                    x1 = round(x1 / step) * step
                    y1 = round(y1 / step) * step
                if x1 == x0: x1 = x0 + step
                if y1 == y0: y1 = y0 + step
                w = x1 - x0
                h = y1 - y0
                hall = HallItem(x0, y0, w, h, "", 0)
                self.addItem(hall)
                self.mainwindow.halls.append(hall)
                num, ok = QInputDialog.getInt(self.mainwindow, "Номер зала", "Введите номер зала:", 1, 0, 10000)
                if ok and self.mainwindow.hall_number_exists(num):
                    QMessageBox.warning(self.mainwindow, "Ошибка", "Зал с таким номером уже существует!")
                    self.removeItem(hall)
                    self.mainwindow.halls.remove(hall)
                    self.mainwindow.temp_start_point = None
                    self.mainwindow.add_mode = None
                    self.mainwindow.statusBar().clearMessage()
                    return
                name, ok2 = QInputDialog.getText(self.mainwindow, "Название зала", "Введите название зала:")
                if ok and ok2:
                    hall.number = num
                    hall.name = name
                else:
                    self.removeItem(hall)
                    self.mainwindow.halls.remove(hall)
                self.mainwindow.temp_start_point = None
                self.mainwindow.add_mode = None
                if self.temp_item:
                    self.removeItem(self.temp_item)
                    self.temp_item = None
                self.mainwindow.statusBar().clearMessage()
                self.mainwindow.populate_tree()
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
                x0 = rect.left(); y0 = rect.top()
                x1 = rect.right(); y1 = rect.bottom()
                if step > 0:
                    x0 = round(x0 / step) * step
                    y0 = round(y0 / step) * step
                    x1 = round(x1 / step) * step
                    y1 = round(y1 / step) * step
                if x1 == x0: x1 = x0 + step
                if y1 == y0: y1 = y0 + step
                bottom_left = QPointF(min(x0, x1), max(y0, y1))
                w = abs(x1 - x0)
                h = abs(y1 - y0)
                num, ok1 = QInputDialog.getInt(self.mainwindow, "Номер зоны", "Введите номер зоны:", 1, 0, 10000)
                zone_type, ok2 = QInputDialog.getItem(self.mainwindow, "Тип зоны", "Выберите тип зоны:",
                                                      ["Входная зона", "Выходная зона"], 0, False)
                angle, ok3 = QInputDialog.getDouble(self.mainwindow, "Угол поворота", "Введите угол поворота (°):", 0, 0, 90, 1)
                if ok1 and ok2 and ok3:
                    zone = RectZoneItem(bottom_left, w, h, num, zone_type, angle, hall)
                else:
                    if self.temp_item:
                        self.removeItem(self.temp_item)
                        self.temp_item = None
                self.mainwindow.temp_start_point = None
                self.mainwindow.add_mode = None
                self.mainwindow.current_hall_for_zone = None
                if self.temp_item:
                    self.removeItem(self.temp_item)
                    self.temp_item = None
                self.mainwindow.statusBar().clearMessage()
                self.mainwindow.populate_tree()
                return
        super().mouseReleaseEvent(event)
        if self.mainwindow:
            self.mainwindow.populate_tree()

class PlanEditorMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RG Tags Mapper")
        self.resize(1200, 800)
        self.scene = PlanGraphicsScene()
        self.scene.mainwindow = self
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
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
        act_save = QAction("Сохранить проект", self)
        act_load = QAction("Загрузить проект", self)
        act_export = QAction("Экспорт конфигурации", self)
        act_add_hall = QAction("Добавить зал", self)
        act_add_anchor = QAction("Добавить якорь", self)
        act_add_zone = QAction("Добавить зону", self)
        toolbar.addAction(act_open)
        toolbar.addAction(act_save)
        toolbar.addAction(act_load)
        toolbar.addAction(act_export)
        toolbar.addSeparator()
        toolbar.addAction(act_add_hall)
        toolbar.addAction(act_add_anchor)
        toolbar.addAction(act_add_zone)
        act_open.triggered.connect(self.open_image)
        act_save.triggered.connect(self.save_project)
        act_load.triggered.connect(self.load_project)
        act_export.triggered.connect(self.export_config)
        act_add_hall.triggered.connect(lambda: self.set_mode("hall"))
        act_add_anchor.triggered.connect(lambda: self.set_mode("anchor"))
        act_add_zone.triggered.connect(lambda: self.set_mode("zone"))
        self.add_mode = None   # Режимы: "calibrate", "hall", "anchor", "zone"
        self.temp_start_point = None
        self.current_hall_for_zone = None
        self.halls = []
        self.grid_calibrated = False
        self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
        self.view.wheelEvent = self.handle_wheel_event
        self.statusBar().setMinimumHeight(30)
        self.statusBar().showMessage("Загрузите изображение для начала работы.")
    
    def handle_wheel_event(self, event):
        factor = 1.2 if event.angleDelta().y() > 0 else 1/1.2
        self.view.scale(factor, factor)
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            for item in self.scene.selectedItems():
                if isinstance(item, HallItem):
                    if item in self.halls:
                        self.halls.remove(item)
                self.scene.removeItem(item)
        else:
            super().keyPressEvent(event)
    
    def hall_number_exists(self, num):
        for hall in self.halls:
            if hall.number == num:
                return True
        return False
    
    def anchor_number_exists(self, num):
        for hall in self.halls:
            for child in hall.childItems():
                if isinstance(child, AnchorItem) and child.number == num:
                    return True
        return False
    
    def wrap_text(self, text):
        metrics = self.tree.fontMetrics()
        available_width = self.tree.viewport().width()
        if metrics.horizontalAdvance(text) > available_width:
            return text.replace(", ", ",\n")
        return text
    
    def populate_tree(self):
        self.tree.clear()
        for hall in self.halls:
            room_text = f'Зал {hall.number} "{hall.name}"'
            room_text = self.wrap_text(room_text)
            hall_item = QTreeWidgetItem([room_text])
            self.tree.addTopLevelItem(hall_item)
            rect = hall.rect()
            for obj in hall.childItems():
                if isinstance(obj, AnchorItem):
                    ax = obj.pos().x()
                    ay = obj.pos().y()
                    x_m = fix_negative_zero(round(ax / (self.scene.pixel_per_cm_x * 100), 1))
                    y_m = fix_negative_zero(round((rect.height() - ay) / (self.scene.pixel_per_cm_x * 100), 1))
                    anchor_text = f'Якорь {obj.number} (x={x_m} м, y={y_m} м, z={fix_negative_zero(round(obj.z/100.0, 1))} м)'
                    anchor_text = self.wrap_text(anchor_text)
                    anchor_item = QTreeWidgetItem([anchor_text])
                    hall_item.addChild(anchor_item)
                elif isinstance(obj, RectZoneItem):
                    data = obj.get_export_data()
                    zone_text = (f'Зона {obj.zone_num} ({obj.zone_type}):\n'
                                 f'  x = {data["x"]} м\n'
                                 f'  y = {data["y"]} м\n'
                                 f'  w = {data["w"]} м\n'
                                 f'  h = {data["h"]} м\n'
                                 f'  angle = {data["angle"]}°')
                    zone_text = self.wrap_text(zone_text)
                    zone_item = QTreeWidgetItem([zone_text])
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
            message = "Кликните внутри зала, чтобы добавить якорь."
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
            self.scene.set_background_image(pixmap)
            self.grid_calibrated = False
            self.statusBar().showMessage("Калибровка: Укажите 2 точки на изображении для определения отрезка с известной длиной")
            self.set_mode("calibrate")
    
    def save_project(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Сохранить проект", "", "Файл проекта (*.proj)")
        if not file_path:
            return
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
            "halls": []
        }
        for hall in self.halls:
            hall_data = {
                "num": hall.number,
                "name": hall.name,
                "x_px": hall.pos().x(),
                "y_px": hall.pos().y(),
                "w_px": hall.rect().width(),
                "h_px": hall.rect().height(),
                "objects": []
            }
            for obj in hall.childItems():
                if isinstance(obj, AnchorItem):
                    hall_data["objects"].append({
                        "type": "anchor",
                        "number": obj.number,
                        "x_px": obj.pos().x(),
                        "y_px": obj.pos().y(),
                        "z": obj.z
                    })
                elif isinstance(obj, RectZoneItem):
                    hall_data["objects"].append({
                        "type": "zone",
                        "zone_num": obj.zone_num,
                        "zone_type": obj.zone_type,
                        "bottom_left": {"x": obj.pos().x(), "y": obj.pos().y()},
                        "w_px": obj.rect().width(),
                        "h_px": obj.rect().height(),
                        "zone_angle": obj.zone_angle
                    })
            data["halls"].append(hall_data)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
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
        image_data = data.get("image_data", "")
        if image_data:
            from PySide6.QtCore import QByteArray
            img_bytes = QByteArray.fromBase64(image_data.encode("utf-8"))
            pixmap = QPixmap()
            pixmap.loadFromData(img_bytes, "PNG")
            self.scene.set_background_image(pixmap)
        self.scene.pixel_per_cm_x = data.get("pixel_per_cm_x", 1.0)
        self.scene.pixel_per_cm_y = data.get("pixel_per_cm_y", 1.0)
        self.scene.grid_step_cm = data.get("grid_step_cm", 20.0)
        self.grid_calibrated = True
        for hall_data in data.get("halls", []):
            hall = HallItem(hall_data.get("x_px", 0), hall_data.get("y_px", 0),
                            hall_data.get("w_px", 100), hall_data.get("h_px", 100),
                            hall_data.get("name", ""), hall_data.get("num", 0))
            self.scene.addItem(hall)
            self.halls.append(hall)
            for obj in hall_data.get("objects", []):
                if obj.get("type") == "anchor":
                    anchor = AnchorItem(obj.get("x_px", 0), obj.get("y_px", 0),
                                        obj.get("number", 0), hall)
                    anchor.z = obj.get("z", 0)
                elif obj.get("type") == "zone":
                    bl = obj.get("bottom_left", {"x":0, "y":0})
                    zone = RectZoneItem(QPointF(bl.get("x",0), bl.get("y",0)),
                                          obj.get("w_px", 50), obj.get("h_px", 50),
                                          obj.get("zone_num", 0),
                                          obj.get("zone_type", "Входная зона"),
                                          obj.get("zone_angle", 0),
                                          hall)
        self.populate_tree()
        QMessageBox.information(self, "Загрузка", "Проект успешно загружён.")
        self.statusBar().clearMessage()
    
    def export_config(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Экспорт конфигурации", "", "JSON файлы (*.json)")
        if not file_path:
            return
        config = {"rooms": []}
        for hall in self.halls:
            rect = hall.rect()
            room = {"num": hall.number, "anchors": [], "zones": []}
            for obj in hall.childItems():
                if isinstance(obj, AnchorItem):
                    ax = obj.pos().x()
                    ay = obj.pos().y()
                    x_m = fix_negative_zero(round(ax / (self.scene.pixel_per_cm_x * 100), 1))
                    y_m = fix_negative_zero(round((rect.height() - ay) / (self.scene.pixel_per_cm_x * 100), 1))
                    room["anchors"].append({
                        "id": obj.number,
                        "x": x_m,
                        "y": y_m,
                        "z": fix_negative_zero(round(obj.z/100.0, 1))
                    })
                elif isinstance(obj, RectZoneItem):
                    zone_data = obj.get_export_data()
                    room["zones"].append({
                        "num": obj.zone_num,
                        "enter": zone_data if obj.zone_type=="Входная зона" else {"x":0,"y":0,"w":0,"h":0,"angle":0},
                        "exit": zone_data if obj.zone_type=="Выходная зона" else {"x":0,"y":0,"w":0,"h":0,"angle":0}
                    })
            config["rooms"].append(room)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            QMessageBox.information(self, "Экспорт", "Конфигурация экспортирована в файл.")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать конфигурацию:\n{e}")
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            for item in self.scene.selectedItems():
                if isinstance(item, HallItem):
                    if item in self.halls:
                        self.halls.remove(item)
                self.scene.removeItem(item)
        else:
            super().keyPressEvent(event)
    
    def hall_number_exists(self, num):
        for hall in self.halls:
            if hall.number == num:
                return True
        return False

    def anchor_number_exists(self, num):
        for hall in self.halls:
            for child in hall.childItems():
                if isinstance(child, AnchorItem) and child.number == num:
                    return True
        return False

    def wrap_text(self, text):
        metrics = self.tree.fontMetrics()
        available_width = self.tree.viewport().width()
        if metrics.horizontalAdvance(text) > available_width:
            return text.replace(", ", ",\n")
        return text

    def populate_tree(self):
        self.tree.clear()
        for hall in self.halls:
            room_text = f'Зал {hall.number} "{hall.name}"'
            room_text = self.wrap_text(room_text)
            hall_item = QTreeWidgetItem([room_text])
            self.tree.addTopLevelItem(hall_item)
            rect = hall.rect()
            for obj in hall.childItems():
                if isinstance(obj, AnchorItem):
                    ax = obj.pos().x()
                    ay = obj.pos().y()
                    x_m = fix_negative_zero(round(ax / (self.scene.pixel_per_cm_x * 100), 1))
                    y_m = fix_negative_zero(round((rect.height() - ay) / (self.scene.pixel_per_cm_x * 100), 1))
                    anchor_text = f'Якорь {obj.number} (x={x_m} м, y={y_m} м, z={fix_negative_zero(round(obj.z/100.0, 1))} м)'
                    anchor_text = self.wrap_text(anchor_text)
                    anchor_item = QTreeWidgetItem([anchor_text])
                    hall_item.addChild(anchor_item)
                elif isinstance(obj, RectZoneItem):
                    data = obj.get_export_data()
                    zone_text = (f'Зона {obj.zone_num} ({obj.zone_type}):\n'
                                 f'  x = {data["x"]} м\n'
                                 f'  y = {data["y"]} м\n'
                                 f'  w = {data["w"]} м\n'
                                 f'  h = {data["h"]} м\n'
                                 f'  angle = {data["angle"]}°')
                    zone_text = self.wrap_text(zone_text)
                    zone_item = QTreeWidgetItem([zone_text])
                    hall_item.addChild(zone_item)
            hall_item.setExpanded(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PlanEditorMainWindow()
    window.show()
    sys.exit(app.exec())
