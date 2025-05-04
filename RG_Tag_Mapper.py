import sys, math, json, base64
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsLineItem, QMenu, QTreeWidget,
    QTreeWidgetItem, QDockWidget, QFileDialog, QToolBar, QMessageBox, QDialog,
    QFormLayout, QDialogButtonBox, QSpinBox, QDoubleSpinBox, QLineEdit, QComboBox,
    QLabel, QInputDialog, QCheckBox
)
from PySide6.QtGui import (
    QAction, QPainter, QPen, QBrush, QColor, QPixmap, QPainterPath, QFont,
    QPdfWriter, QPageSize
)
from PySide6.QtCore import Qt, QRectF, QPointF, QSizeF, QBuffer, QByteArray, QTimer

def fix_negative_zero(val):
    return 0.0 if abs(val) < 1e-9 else val

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

def getAnchorParameters(default_num=1, default_z=0, default_extras="", default_bound=False):
    fields = [
        {"label": "Номер якоря", "type": "int", "default": default_num, "min": 0, "max": 10000},
        {"label": "Координата Z (см)", "type": "int", "default": default_z, "min": -10000, "max": 10000},
        {"label": "Дополнительные залы (через запятую)", "type": "string", "default": default_extras},
        {"label": "Переходный", "type": "bool", "default": default_bound}
    ]
    dlg = ParamDialog("Введите параметры якоря", fields)
    if dlg.exec() == QDialog.Accepted:
        v = dlg.getValues()
        extras = [int(tok) for tok in v["Дополнительные залы (через запятую)"].split(",") if tok.strip().isdigit()]
        return v["Номер якоря"], v["Координата Z (см)"], extras, v["Переходный"]
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
            return new
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        mw = self.scene().mainwindow
        ppcm = self.scene().pixel_per_cm_x
        menu = QMenu()
        header = menu.addAction(f"Зал {self.number}"); header.setEnabled(False)
        edit = menu.addAction("Редактировать зал")
        delete = menu.addAction("Удалить зал")
        act = menu.exec(event.screenPos())
        if act == edit:
            # current dims in meters
            w_m = self.rect().width()/(ppcm*100)
            h_m = self.rect().height()/(ppcm*100)
            params = getHallParameters(self.number, self.name, w_m, h_m, self.scene())
            if params:
                new_num, new_name, new_w_m, new_h_m = params
                # update anchors references if number changed
                old = self.number
                for a in mw.anchors:
                    if a.main_hall_number == old:
                        a.main_hall_number = new_num
                    a.extra_halls = [new_num if x==old else x for x in a.extra_halls]
                self.number, self.name = new_num, new_name
                # resize in pixels
                w_px = new_w_m * ppcm * 100
                h_px = new_h_m * ppcm * 100
                self.prepareGeometryChange()
                self.setRect(0, 0, w_px, h_px)
                # adjust z-value so stacking remains by area
                self.setZValue(-w_px*h_px)
                mw.last_selected_items = []; mw.populate_tree()
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
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
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
        act = menu.exec(event.screenPos())
        if act == edit:
            fields = [
                {"label": "Номер якоря", "type": "int", "default": self.number, "min": 0, "max": 10000},
                {"label":"Координата X (м)","type":"float","default":x_m,"min":0,"max":10000,"decimals":1},
                {"label":"Координата Y (м)","type":"float","default":y_m,"min":0,"max":10000,"decimals":1},
                {"label":"Координата Z (м)","type":"float","default":z_m,"min":-100,"max":100,"decimals":1},
                {"label":"Доп. залы","type":"string","default":",".join(str(x) for x in self.extra_halls)},
                {"label":"Переходный","type":"bool","default":self.bound}
            ]
            dlg = ParamDialog("Редактировать якорь", fields, mw)
            if dlg.exec() == QDialog.Accepted:
                v = dlg.getValues()
                self.number = v["Номер якоря"]
                x2, y2, z2 = v["Координата X (м)"], v["Координата Y (м)"], v["Координата Z (м)"]
                self.bound = v["Переходный"]
                self.extra_halls = [int(tok) for tok in v["Доп. залы"].split(",") if tok.strip().isdigit()]
                self.z = int(round(z2*100))
                px = x2 * ppcm * 100
                py = hall.rect().height() - y2 * ppcm * 100
                self.setPos(hall.mapToScene(QPointF(px, py)))
                mw.last_selected_items = []; mw.populate_tree()
        elif act == delete:
            mw.anchors.remove(self); self.scene().removeItem(self)
            mw.last_selected_items = []; mw.populate_tree()
        event.accept()

# ---------------------------------------------------------------------------
# ZoneItem
# ---------------------------------------------------------------------------
class RectZoneItem(QGraphicsRectItem):
    def __init__(self, bl, w, h, zone_num=0, zone_type="Входная зона", angle=0, parent_hall=None):
        super().__init__(0, -h, w, h, parent_hall)
        self.zone_num, self.zone_type, self.zone_angle = zone_num, zone_type, angle
        self.setTransformOriginPoint(0,0); self.setRotation(-angle); self.setPos(bl)
        if zone_type in ("Входная зона","Переходная"):
            self.setPen(QPen(QColor(0,128,0),2)); self.setBrush(QBrush(QColor(0,128,0,50)))
        else:
            self.setPen(QPen(QColor(128,0,128),2)); self.setBrush(QBrush(QColor(128,0,128,50)))
        self.setFlags(QGraphicsItem.ItemIsMovable|QGraphicsItem.ItemIsSelectable|QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(-w*h); self.tree_item = None

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

    def mouseDoubleClickEvent(self, event):
        scene = self.scene(); mw = scene.mainwindow
        zlist = [z for z in scene.items(event.scenePos())
                 if isinstance(z,RectZoneItem) and z.contains(z.mapFromScene(event.scenePos()))]
        if zlist:
            smaller = [z for z in zlist if z is not self and (z.rect().width()*z.rect().height() < self.rect().width()*self.rect().height())]
            if smaller:
                min(smaller, key=lambda z: z.rect().width()*z.rect().height()).mouseDoubleClickEvent(event)
                return
        data = self.get_export_data()
        if data is None: return
        x_m, y_m, w_m, h_m, angle = data["x"], data["y"], data["w"], data["h"], data["angle"]
        menu = QMenu()
        header = menu.addAction(f"Зона {self.zone_num} ({self.get_display_type()})"); header.setEnabled(False)
        edit = menu.addAction("Редактировать"); delete = menu.addAction("Удалить")
        act = menu.exec(event.screenPos())
        if act == edit:
            fields = [
                {"label": "Номер зоны", "type": "int", "default": self.zone_num, "min": 0, "max": 10000},
                {"label":"Координата X (м)","type":"float","default":x_m,"min":0,"max":10000,"decimals":1},
                {"label":"Координата Y (м)","type":"float","default":y_m,"min":0,"max":10000,"decimals":1},
                {"label":"Ширина (м)","type":"float","default":w_m,"min":0,"max":10000,"decimals":1},
                {"label":"Высота (м)","type":"float","default":h_m,"min":0,"max":10000,"decimals":1},
                {"label":"Тип зоны","type":"combo","default": self.zone_type.replace(" зона",""),
                 "options":["Входная","Выходная","Переходная"]},
                {"label":"Угол поворота (°)","type":"int","default":int(angle),"min":-90,"max":90}
            ]
            dlg = ParamDialog("Редактировать зону", fields, mw)
            if dlg.exec() == QDialog.Accepted:
                v = dlg.getValues()
                self.zone_num = v["Номер зоны"]
                x2, y2, w2, h2 = v["Координата X (м)"], v["Координата Y (м)"], v["Ширина (м)"], v["Высота (м)"]
                t2 = v["Тип зоны"]
                full = {"Входная":"Входная зона","Выходная":"Выходная зона","Переходная":"Переходная"}[t2]
                ang2 = v["Угол поворота (°)"]
                hall = self.parentItem()
                ppcm = scene.pixel_per_cm_x
                self.setRect(0, -h2*ppcm*100, w2*ppcm*100, h2*ppcm*100)
                self.setTransformOriginPoint(0,0); self.setRotation(-ang2)
                self.zone_type, self.zone_angle = full, ang2
                px = x2 * ppcm * 100
                py = hall.rect().height() - y2 * ppcm * 100
                self.setPos(QPointF(px, py))
                mw.last_selected_items = []; mw.populate_tree()
        elif act == delete:
            scene.removeItem(self)
            mw.last_selected_items = []; mw.populate_tree()
        event.accept()

# ---------------------------------------------------------------------------
# Custom view and scene
# ---------------------------------------------------------------------------
class MyGraphicsView(QGraphicsView):
    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        try: QTimer.singleShot(0, self.scene().mainwindow.update_tree_selection)
        except: pass

class PlanGraphicsScene(QGraphicsScene):
    def __init__(self):
        super().__init__()
        self.mainwindow=None; self.pixmap=None
        self.pixel_per_cm_x=1.0; self.pixel_per_cm_y=1.0
        self.grid_step_cm=20.0; self.temp_item=None

    def set_background_image(self, pix):
        self.pixmap = pix
        self.setSceneRect(0, 0, pix.width(), pix.height())

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
        diff = math.hypot(end.x()-start.x(), end.y()-start.y())
        length_cm, ok = QInputDialog.getDouble(
            self.mainwindow, "Калибровка масштаба",
            "Введите длину отрезка (см):", 100.0, 0.1, 10000.0, 1
        )
        if ok and length_cm:
            scale = diff / length_cm
            self.pixel_per_cm_x = self.pixel_per_cm_y = scale
        mw = self.mainwindow
        mw.add_mode = None; mw.temp_start_point = None
        if self.temp_item:
            self.removeItem(self.temp_item); self.temp_item = None
        mw.statusBar().showMessage("Калибровка завершена."); mw.grid_calibrated = True
        step, ok = QInputDialog.getInt(
            mw, "Шаг сетки", "Укажите шаг (см):", 10, 1, 1000
        )
        if ok: self.grid_step_cm = float(step)
        mw.resnap_objects(); self.update()

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
                num, z, extras, bound = params
                a = AnchorItem(pos.x(), pos.y(), num, main_hall_number=hall.number, scene=self)
                a.z, a.extra_halls, a.bound = z, extras, bound
                self.addItem(a); mw.anchors.append(a)
                mw.add_mode=None; mw.statusBar().clearMessage(); mw.populate_tree()
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
            num, zt, ang = params
            RectZoneItem(bl, w_pix, h_pix, num, zt, ang, hall)
            mw.last_selected_items=[]; mw.populate_tree()
            mw.temp_start_point=None; mw.add_mode=None; mw.current_hall_for_zone=None
            if self.temp_item: self.removeItem(self.temp_item); self.temp_item=None
            return

        super().mouseReleaseEvent(event)
        try:
            mw.populate_tree()
            if not self.selectedItems():
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

        self.scene = PlanGraphicsScene(); self.scene.mainwindow=self
        self.scene.selectionChanged.connect(self.on_scene_selection_changed)
        self.view = MyGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setCentralWidget(self.view)

        self.tree = QTreeWidget(); self.tree.setHeaderLabel("Объекты"); self.tree.setWordWrap(True)
        dock = QDockWidget("Список объектов", self); dock.setWidget(self.tree)
        dock.setFeatures(QDockWidget.DockWidgetMovable|QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

        toolbar = QToolBar("Инструменты", self); self.addToolBar(toolbar)
        act_open = QAction("Открыть изображение", self)
        act_cal = QAction("Выполнить калибровку", self)
        toolbar.addAction(act_open); toolbar.addAction(act_cal); toolbar.addSeparator()
        act_save = QAction("Сохранить проект", self); act_load = QAction("Загрузить проект", self)
        toolbar.addAction(act_save); toolbar.addAction(act_load); toolbar.addSeparator()
        act_add_hall = QAction("Добавить зал", self)
        act_add_anchor = QAction("Добавить якорь", self)
        act_add_zone = QAction("Добавить зону", self)
        toolbar.addAction(act_add_hall); toolbar.addAction(act_add_anchor); toolbar.addAction(act_add_zone)
        self.act_lock = QAction("Закрепить объекты", self); toolbar.addAction(self.act_lock); toolbar.addSeparator()
        act_export = QAction("Экспорт конфигурации", self); toolbar.addAction(act_export)
        act_pdf = QAction("Сохранить в PDF", self); toolbar.addAction(act_pdf)

        act_open.triggered.connect(self.open_image)
        act_cal.triggered.connect(self.perform_calibration)
        act_save.triggered.connect(self.save_project)
        act_load.triggered.connect(self.load_project)
        act_export.triggered.connect(self.export_config)
        act_pdf.triggered.connect(self.save_to_pdf)
        act_add_hall.triggered.connect(lambda: self.set_mode("hall"))
        act_add_anchor.triggered.connect(lambda: self.set_mode("anchor"))
        act_add_zone.triggered.connect(lambda: self.set_mode("zone"))
        self.act_lock.triggered.connect(self.lock_objects)

        self.add_mode = None; self.temp_start_point = None
        self.current_hall_for_zone = None
        self.halls = []; self.anchors = []
        self.grid_calibrated = False
        self.lock_halls = False; self.lock_zones = False; self.lock_anchors = False
        self.last_selected_items = []
        self.current_project_file = None

        self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
        self.view.wheelEvent = self.handle_wheel_event
        self.statusBar().setMinimumHeight(30)
        self.statusBar().showMessage("Загрузите изображение для начала работы.")

    # Parameter getters...
    def get_anchor_parameters(self):
        default = 1 if not self.anchors else max(a.number for a in self.anchors)+1
        return getAnchorParameters(default, 0, "", False)
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
            self.lock_halls, self.lock_zones, self.lock_anchors = dlg.values()
            self.apply_lock_flags()
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
        self.set_mode("calibrate")
        self.statusBar().showMessage("Нажмите на 2 точки для калибровки")
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

    # Misc
    def handle_wheel_event(self, event):
        factor = 1.2 if event.angleDelta().y()>0 else 1/1.2
        self.view.scale(factor, factor)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            for it in self.scene.selectedItems():
                if isinstance(it,HallItem) and it in self.halls: self.halls.remove(it)
                if it in self.anchors: self.anchors.remove(it)
                self.scene.removeItem(it)
        else:
            super().keyPressEvent(event)

    def populate_tree(self):
        self.last_selected_items = []
        self.tree.clear()
        for h in self.halls:
            wm = h.rect().width()/(self.scene.pixel_per_cm_x*100)
            hm = h.rect().height()/(self.scene.pixel_per_cm_x*100)
            rt = (f'Зал {h.number} "{h.name}" ({wm:.1f} x {hm:.1f} м)'
                  if h.name.strip() else f'Зал {h.number} ({wm:.1f} x {hm:.1f} м)')
            hi = QTreeWidgetItem([rt]); h.tree_item = hi; self.tree.addTopLevelItem(hi)
            for a in self.anchors:
                if a.main_hall_number==h.number or h.number in a.extra_halls:
                    lp = h.mapFromScene(a.scenePos())
                    xm = fix_negative_zero(round(lp.x()/(self.scene.pixel_per_cm_x*100),1))
                    ym = fix_negative_zero(round((h.rect().height()-lp.y())/(self.scene.pixel_per_cm_x*100),1))
                    at = f'Якорь {a.number} (x={xm} м, y={ym} м, z={fix_negative_zero(round(a.z/100,1))} м)'
                    ai = QTreeWidgetItem([at]); a.tree_item = ai; hi.addChild(ai)
            zones = {}
            default = {"x":0,"y":0,"w":0,"h":0,"angle":0}
            for ch in h.childItems():
                if isinstance(ch,RectZoneItem):
                    n = ch.zone_num
                    if n not in zones:
                        zones[n] = {"num":n, "enter":default.copy(), "exit":default.copy()}
                    if ch.zone_type in ("Входная зона","Переходная"):
                        zones[n]["enter"] = ch.get_export_data()
                    if ch.zone_type == "Выходная зона":
                        zones[n]["exit"] = ch.get_export_data()
                    if ch.zone_type == "Переходная":
                        zones[n]["bound"] = True
            for z in zones.values():
                zt = (f"Зона {z['num']}: enter: x = {z['enter']['x']} м, y = {z['enter']['y']} м, "
                      f"w = {z['enter']['w']} м, h = {z['enter']['h']} м, angle = {z['enter']['angle']}°; "
                      f"exit: x = {z['exit']['x']} м, y = {z['exit']['y']} м, "
                      f"w = {z['exit']['w']} м, h = {z['exit']['h']} м, angle = {z['exit']['angle']}°")
                zi = QTreeWidgetItem([zt])
                for ch in h.childItems():
                    if isinstance(ch,RectZoneItem) and ch.zone_num==z['num']:
                        ch.tree_item = zi
                hi.addChild(zi)
            hi.setExpanded(True)

    def set_mode(self, mode):
        if not self.grid_calibrated and mode!="calibrate":
            QMessageBox.information(self,"Внимание","Сначала выполните калибровку!"); return
        self.add_mode = mode; self.temp_start_point = None; self.current_hall_for_zone = None
        msgs = {"hall":"Выделите зал.","anchor":"Кликните в зал.","zone":"Выделите зону.","calibrate":"Укажите 2 точки."}
        self.statusBar().showMessage(msgs.get(mode,""))

    def open_image(self):
        fp,_ = QFileDialog.getOpenFileName(self,"Открыть изображение","","Изображения (*.png *.jpg *.bmp)")
        if not fp: return
        pix = QPixmap(fp)
        if pix.isNull():
            QMessageBox.warning(self,"Ошибка","Не удалось загрузить."); return
        self.scene.clear(); self.halls.clear(); self.anchors.clear()
        self.scene.set_background_image(pix)
        self.grid_calibrated = False
        self.statusBar().showMessage("Калибровка: укажите 2 точки")
        self.set_mode("calibrate")

    def save_project(self):
        if not self.current_project_file:
            fp,_ = QFileDialog.getSaveFileName(self,"Сохранить проект","","*.proj")
            if not fp: return
            self.current_project_file = fp
        else:
            fp = self.current_project_file
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
        try:
            with open(fp,"w",encoding="utf-8") as f:
                json.dump(data,f,ensure_ascii=False,indent=4)
            QMessageBox.information(self,"Сохранено","Проект сохранён.")
        except Exception as e:
            QMessageBox.critical(self,"Ошибка",f"Не удалось сохранить:\n{e}")

    def load_project(self):
        fp,_ = QFileDialog.getOpenFileName(self,"Загрузить проект","","*.proj")
        if not fp: return
        try:
            with open(fp,"r",encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self,"Ошибка",f"Ошибка чтения:\n{e}"); return
        self.scene.clear(); self.halls.clear(); self.anchors.clear()
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

    def export_config(self):
        fp,_ = QFileDialog.getSaveFileName(self,"Экспорт JSON","","*.json")
        if not fp: return
        config = {"rooms":[]}
        for h in self.halls:
            room = {"num":h.number, "anchors":[], "zones":[]}
            for a in self.anchors:
                if a.main_hall_number==h.number or h.number in a.extra_halls:
                    lp = h.mapFromScene(a.scenePos())
                    xm = fix_negative_zero(round(lp.x()/(self.scene.pixel_per_cm_x*100),1))
                    ym = fix_negative_zero(round((h.rect().height()-lp.y())/(self.scene.pixel_per_cm_x*100),1))
                    ae = {"id":a.number, "x":xm, "y":ym, "z":fix_negative_zero(round(a.z/100,1))}
                    if a.bound: ae["bound"]=True
                    room["anchors"].append(ae)
            zones = {}
            default = {"x":0,"y":0,"w":0,"h":0,"angle":0}
            for ch in h.childItems():
                if isinstance(ch,RectZoneItem):
                    n = ch.zone_num
                    if n not in zones:
                        zones[n] = {"num":n, "enter":default.copy(), "exit":default.copy()}
                    dz = ch.get_export_data()
                    if ch.zone_type=="Входная зона":
                        zones[n]["enter"] = dz
                    elif ch.zone_type=="Выходная зона":
                        zones[n]["exit"] = dz
                    elif ch.zone_type=="Переходная":
                        zones[n]["enter"]=dz; zones[n]["bound"]=True
            for z in zones.values():
                room["zones"].append(z)
            config["rooms"].append(room)

        result = '{\n"rooms": [\n'
        room_strs = []
        for room in config["rooms"]:
            lines = ['{', f'"num": {room["num"]},', '"anchors": [']
            alines = []
            for a in room["anchors"]:
                s = f'{{ "id": {a["id"]}, "x": {a["x"]}, "y": {a["y"]}, "z": {a["z"]}'
                if a.get("bound"): s += ', "bound": true'
                s += ' }'; alines.append(s)
            lines.append(",\n".join(alines)); lines.append('],'); lines.append('"zones": [')
            zlines = []
            for z in room["zones"]:
                zl = '{'
                zl += f'\n"num": {z["num"]},'
                zl += (f'\n"enter": {{ "x": {z["enter"]["x"]}, "y": {z["enter"]["y"]}, '
                       f'"w": {z["enter"]["w"]}, "h": {z["enter"]["h"]}, '
                       f'"angle": {z["enter"]["angle"]} }},')
                zl += (f'\n"exit":  {{ "x": {z["exit"]["x"]}, "y": {z["exit"]["y"]}, '
                       f'"w": {z["exit"]["w"]}, "h": {z["exit"]["h"]}, '
                       f'"angle": {z["exit"]["angle"]} }}')
                if z.get("bound"): zl += ',\n"bound": true'
                zl += '\n}'; zlines.append(zl)
            lines.append(",\n".join(zlines)); lines.append(']'); lines.append('}')
            room_strs.append("\n".join(lines))
        result += ",\n".join(room_strs) + '\n]\n}'
        try:
            with open(fp,"w",encoding="utf-8") as f: f.write(result)
            QMessageBox.information(self,"Экспорт","Экспорт завершён.")
        except Exception as e:
            QMessageBox.critical(self,"Ошибка",f"Не удалось экспортировать:\n{e}")

    def closeEvent(self, event):
        reply = QMessageBox.question(self,"Сохранить перед выходом?","Сохранить проект?",
                                     QMessageBox.Yes|QMessageBox.No|QMessageBox.Cancel)
        if reply == QMessageBox.Yes:
            self.save_project()
        elif reply == QMessageBox.Cancel:
            event.ignore(); return
        try: self.scene.selectionChanged.disconnect(self.on_scene_selection_changed)
        except: pass
        self.view.setScene(None); event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PlanEditorMainWindow()
    window.show()
    sys.exit(app.exec())
