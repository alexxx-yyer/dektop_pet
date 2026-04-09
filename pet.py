#!/usr/bin/env python3
"""奇魔小小猪 - 桌面宠物 (macOS 版)"""

import sys
import os
import glob
import math
import random
import subprocess

from PyQt6.QtWidgets import (
    QApplication, QWidget, QMenu, QSystemTrayIcon, QMessageBox
)
from PyQt6.QtGui import (
    QAction, QCursor, QMovie, QPainter, QTransform,
    QPen, QColor, QIcon, QPixmap
)


def _macos_init_app():
    """设置 macOS App 为 accessory 模式，不抢占焦点，不出现在 Dock"""
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApp, NSApplicationActivationPolicyAccessory  # type: ignore
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        pass


def _macos_set_always_on_top(widget):
    """使用 macOS 原生 API 将窗口设置为始终置顶（覆盖所有应用）"""
    if sys.platform != "darwin":
        return
    try:
        import objc  # type: ignore
        view_ptr = widget.winId().__int__()
        ns_view = objc.objc_object(c_void_p=view_ptr)
        ns_window = ns_view.window()
        if ns_window:
            # kCGScreenSaverWindowLevel(1000) 之下, 比 kCGStatusWindowLevel(25) 高
            ns_window.setLevel_(25)
            ns_window.setCollectionBehavior_(
                1 << 0   # canJoinAllSpaces
                | 1 << 4  # stationary
                | 1 << 9  # fullScreenAuxiliary
            )
            # 失焦后也不隐藏
            ns_window.setHidesOnDeactivate_(False)
    except Exception:
        pass
from PyQt6.QtCore import Qt, QTimer, QPoint, QPointF, QRectF


# ---------------------------------------------------------------------------
# 尺寸常量 (DPI 缩放)
# ---------------------------------------------------------------------------
BASE_CANVAS = 120
BASE_GIF = 100
CANVAS_SIZE = BASE_CANVAS
GIF_MAX_SIZE = BASE_GIF
DOCK_PEEK = 30
BOTTOM_MARGIN = 0

SPECIAL_GIFS = {"struggle"}


def get_dpi_scale():
    """获取主屏幕的 DPI 缩放比例，以 96 DPI 为基准 1.0"""
    try:
        app = QApplication.instance()
        screen = app.primaryScreen()
        dpi = screen.logicalDotsPerInch()
        return dpi / 96.0
    except Exception:
        return 1.0


def init_sizes():
    """Call after QApplication is created to apply DPI scaling"""
    global CANVAS_SIZE, GIF_MAX_SIZE, DOCK_PEEK
    scale = get_dpi_scale()
    CANVAS_SIZE = int(BASE_CANVAS * scale)
    GIF_MAX_SIZE = int(BASE_GIF * scale)
    DOCK_PEEK = int(BASE_GIF * scale)


def get_screen_at(x, y):
    """获取坐标 (x, y) 所在屏幕的可用区域。如果不在任何屏幕上，返回最近的屏幕。"""
    app = QApplication.instance()
    screens = app.screens()
    for s in screens:
        geo = QRectF(s.availableGeometry())
        if geo.contains(x, y):
            return geo
    # 找最近的屏幕
    best = None
    best_dist = float('inf')
    for s in screens:
        geo = QRectF(s.availableGeometry())
        cx = geo.x() + geo.width() / 2
        cy = geo.y() + geo.height() / 2
        d = (cx - x) ** 2 + (cy - y) ** 2
        if d < best_dist:
            best_dist = d
            best = geo
    if best is not None:
        return best
    return QRectF(0, 0, 1920, 1080)


def get_current_screen_for_widget(widget):
    """获取宠物窗口中心点所在屏幕的可用区域"""
    cx = widget.x() + widget.width() / 2
    cy = widget.y() + widget.height() / 2
    return get_screen_at(cx, cy)


# ---------------------------------------------------------------------------
# PortalWindow — 灰白色调不规则漩涡传送门
# ---------------------------------------------------------------------------
class PortalWindow(QWidget):
    """灰白色调不规则漩涡传送门"""

    OFFSETS = [0, 8, -5, 12, -9, 15, -3, 10, -7, 6]
    LINE_WIDTHS = [3, 2.5, 2, 3.5, 2, 1.5, 3, 2, 2.5, 1.5]
    START_ANGLES = [0, 40, 80, 120, 160, 200, 240, 280, 320, 350]
    TRIM_ENDS = [10, 20, 15, 25, 10, 30, 5, 20, 15, 10]

    def __init__(self, size):
        super().__init__()
        self._size = size
        self._angle = 0.0
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFixedSize(size, size)

        self._spin_timer = QTimer()
        self._spin_timer.timeout.connect(self._spin_step)
        self._spin_timer.start(30)

    def show_at(self, center_x, center_y):
        self.move(int(center_x - self.width() / 2),
                  int(center_y - self.height() / 2))
        self.show()
        _macos_set_always_on_top(self)

    def _spin_step(self):
        self._angle += 6
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        cx = self.width() / 2
        cy = self.height() / 2
        r = self._size / 2

        painter.translate(cx, cy)
        painter.rotate(self._angle)

        for i in range(10):
            opacity = 0.25 - i * 0.05
            if opacity < 0:
                opacity = 0.05
            color = QColor(200, 200, 200, int(opacity * 360))
            pen = QPen(color, self.LINE_WIDTHS[i])
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)

            arc_r = r + self.OFFSETS[i]
            rect = QRectF(-arc_r, -arc_r, arc_r * 2, arc_r * 2)
            dx = self.OFFSETS[i] * 0.25
            dy = self.OFFSETS[(i + 1) % 10] * 0.25
            start = self.START_ANGLES[i]
            span = 360 - self.TRIM_ENDS[i]
            painter.drawArc(rect.translated(dx, dy),
                            int(start * 16), int(span * 16))

    def closeEvent(self, event):
        self._spin_timer.stop()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# PetWindow — 桌面宠物窗口
# ---------------------------------------------------------------------------
class PetWindow(QWidget):
    """桌面宠物窗口。"""

    def __init__(self, gif_files, action_name,
                 position=None, velocity=None,
                 is_docked=False, dock_side=None,
                 wander_enabled=True, wander_target=None,
                 wander_direction=None, is_idle=False,
                 is_heading_to_portal=False):
        super().__init__()
        self.gif_files = gif_files
        self.current_action_name = action_name
        self._start_position = position

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(CANVAS_SIZE, CANVAS_SIZE)

        # 动画
        self.movie = QMovie(gif_files[action_name])
        self.movie.frameChanged.connect(self.update)
        self._is_idle = is_idle
        if is_idle:
            self.movie.jumpToFrame(0)
            self.movie.setPaused(True)
        else:
            self.movie.start()

        # 拖拽
        self._is_dragging = False
        self._drag_offset = QPoint(0, 0)
        self._press_pos = QPoint(0, 0)
        self._wobble_angle = 0.0
        self._wobble_direction = 1
        self._saved_action = None

        self._wobble_timer = QTimer()
        self._wobble_timer.timeout.connect(self._update_wobble)

        # 物理
        self._velocity = QPointF(0, 0) if velocity is None else velocity
        self._last_mouse_positions = []
        self._physics_timer = QTimer()
        self._physics_timer.timeout.connect(self._physics_step)
        self._friction = 0.92
        self._bounce_factor = 0.25
        self._gravity = 0.5
        if velocity is not None and (abs(velocity.x()) > 0 or abs(velocity.y()) > 0):
            self._physics_timer.start(16)

        # 停靠
        self._is_docked = is_docked
        self._dock_side = dock_side
        self._dock_animating = False
        self._dock_target_x = 0
        self._dock_timer = QTimer()
        self._dock_timer.timeout.connect(self._dock_animate_step)

        # 漫游
        self._wander_enabled = wander_enabled
        self._wander_target = wander_target
        self._wander_stuck_count = 0
        self._wander_last_x = 0
        self._wander_timer = QTimer()
        self._wander_timer.timeout.connect(self._wander_step)
        self._wander_speed = 2.5
        self._wander_direction = wander_direction
        self._is_heading_to_portal = is_heading_to_portal

        self._wander_decide_timer = QTimer()
        self._wander_decide_timer.timeout.connect(self._wander_new_target)

        # 传送
        self._is_teleporting = False
        self._pet_scale = 1.0
        self._pet_rotation = 0.0
        self._portal_window = None
        self._teleport_anim_timer = QTimer()
        self._teleport_anim_timer.timeout.connect(self._teleport_anim_step)
        self._teleport_phase = 0
        self._teleport_tick = 0
        self._teleport_target = None

        # 定位
        if position is not None:
            self.move(position)
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            self.move(random.randint(int(screen.width() * 0.25),
                                     int(screen.width() * 0.75)),
                      int(screen.height() - CANVAS_SIZE))

        # 动作计时器 - 开始漫游
        self.action_timer = QTimer()
        if wander_enabled:
            self._start_wandering()

        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.show()
        _macos_set_always_on_top(self)

    # ---- 空闲/行走 ----

    def _go_idle(self):
        self._is_idle = True
        self.movie.setPaused(True)
        self.update()

    def _go_walking(self):
        self._is_idle = False
        self.movie.setPaused(False)

    # ---- 漫游 ----

    def _start_wandering(self):
        self._wander_enabled = True
        self._wander_target = None
        self._wander_new_target()
        self._go_walking()
        self._wander_timer.start(16)

    def _stop_wandering(self):
        self._wander_enabled = False
        self._wander_target = None
        self._wander_timer.stop()
        self._wander_decide_timer.stop()

    def _wander_new_target(self):
        if not self._wander_enabled or self._is_docked or self._is_dragging or self._is_teleporting:
            return

        vd = get_current_screen_for_widget(self)

        # 有概率传送
        if not self._is_heading_to_portal and random.random() < 0.15:
            self._is_heading_to_portal = False
            self._wander_target = None
            self._go_idle()
            self._wander_decide_timer.start(random.randint(1000, 2000))
            return

        # 随机传送方向
        if random.random() < 0.35:
            self._is_heading_to_portal = True

        pad = GIF_MAX_SIZE + (CANVAS_SIZE - GIF_MAX_SIZE)
        min_x = int(vd.x()) + pad
        max_x = int(vd.x() + vd.width()) - pad
        cur_x = self.x()

        # 选一个不太近的目标
        for _ in range(10):
            tx = random.randint(min_x, max(min_x, max_x))
            if abs(tx - cur_x) > 50:
                break

        ty = max(int(vd.y()), min(self.y(), int(vd.y() + vd.height() - CANVAS_SIZE)))

        self._wander_target = QPointF(tx, ty)
        self._wander_speed = 2.5

        # 确定方向和对应 GIF
        if tx < cur_x:
            target_dir = "left"
        else:
            target_dir = "right"
        self._wander_direction = target_dir

        walk_gif = "walk_left" if target_dir == "left" else "walk_right"

        if walk_gif in self.gif_files and walk_gif != self.current_action_name:
            self.current_action_name = walk_gif
            self.movie.stop()
            self.movie = QMovie(self.gif_files[walk_gif])
            self.movie.frameChanged.connect(self.update)
            self.movie.start()
            self._is_idle = False

        self._wander_decide_timer.start(random.randint(4000, 12000))

    def _wander_step(self):
        if not self._wander_enabled or self._is_dragging:
            return
        if self._is_docked or self._dock_animating:
            return
        if self._physics_timer.isActive():
            return
        if self._is_teleporting:
            return
        if self._wander_target is None:
            return

        pos = QPointF(self.x(), self.y())
        dx = self._wander_target.x() - pos.x()
        dist = abs(dx)

        # 到达目标检测
        if dist < 0.5:
            # 卡住检测
            if abs(self.x() - self._wander_last_x) < 0.5:
                self._wander_stuck_count += 1
            else:
                self._wander_stuck_count = 0
            self._wander_last_x = self.x()

            if self._is_heading_to_portal:
                self._wander_decide_timer.stop()
                if random.randint(300, 800) < 500:
                    self._perform_teleport()
                else:
                    self._is_heading_to_portal = False
                    self._wander_decide_timer.start(random.randint(500, 1500))
                return

            self._go_idle()
            self._wander_decide_timer.start(random.randint(1000, 2000))
            return

        self._wander_last_x = self.x()
        self._wander_stuck_count = 0

        # 确定方向
        new_direction = "left" if dx < 0 else "right"
        if new_direction != self._wander_direction:
            self._wander_direction = new_direction
            walk_gif_name = "walk_left" if new_direction == "left" else "walk_right"
            if walk_gif_name in self.gif_files and walk_gif_name != self.current_action_name:
                self.current_action_name = walk_gif_name
                self.movie.stop()
                self.movie = QMovie(self.gif_files[walk_gif_name])
                self.movie.frameChanged.connect(self.update)
                self.movie.start()
                self._is_idle = False
                self._go_walking()

        # 移动
        step = self._wander_speed if dx > 0 else -self._wander_speed

        vd = get_current_screen_for_widget(self)
        pad = (CANVAS_SIZE - GIF_MAX_SIZE)
        new_x = max(int(vd.x()) - pad, min(int(vd.x() + vd.width()) - CANVAS_SIZE + pad, int(pos.x() + step)))
        self.move(new_x, int(pos.y()))

    # ---- 传送 ----

    def _perform_teleport(self):
        self._is_teleporting = True
        self._is_heading_to_portal = False
        self._stop_wandering()
        self._go_idle()

        # 选目标屏幕
        screens = QApplication.screens()
        pad = CANVAS_SIZE + GIF_MAX_SIZE
        for _ in range(10):
            target_screen = random.choice(screens)
            geo = target_screen.availableGeometry()
            nx = random.randint(int(geo.x()) + pad, max(int(geo.x()) + pad, int(geo.x() + geo.width()) - pad))
            ny = random.randint(int(geo.y()) + pad, max(int(geo.y()) + pad, int(geo.y() + geo.height()) - pad))
            dist = math.sqrt((nx - self.x()) ** 2 + (ny - self.y()) ** 2)
            if dist > 100:
                break

        self._teleport_target = QPoint(nx, ny)
        self._teleport_phase = 0
        self._teleport_tick = 0

        self._portal_window = PortalWindow(GIF_MAX_SIZE)
        self._portal_window.show_at(
            self.x() + CANVAS_SIZE // 2,
            self.y() + CANVAS_SIZE // 2
        )
        self._teleport_anim_timer.start(16)

    def _teleport_anim_step(self):
        self._teleport_tick += 1

        if self._teleport_phase == 0:
            # 缩小阶段
            self._pet_scale = max(0.01, self._pet_scale - 0.02)
            self._pet_rotation += 6
            self.update()
            if self._pet_scale <= 0.01:
                if self._portal_window:
                    self._portal_window.close()
                self.move(self._teleport_target)
                self._portal_window = PortalWindow(GIF_MAX_SIZE)
                self._portal_window.show_at(
                    self._teleport_target.x() + CANVAS_SIZE // 2,
                    self._teleport_target.y() + CANVAS_SIZE // 2
                )
                self._teleport_phase = 1
                self._teleport_tick = 0
        elif self._teleport_phase == 1:
            # 放大阶段
            self._pet_scale = min(1.0, self._pet_scale + 0.02)
            self._pet_rotation -= 6
            self.update()
            if self._pet_scale >= 1.0:
                self._pet_scale = 1.0
                self._pet_rotation = 0.0
                if self._portal_window:
                    self._portal_window.close()
                self._teleport_anim_timer.stop()
                self._is_teleporting = False
                self._start_wandering()

    # ---- 停靠 ----

    def _check_dock(self):
        vd = get_current_screen_for_widget(self)
        x = self.x()
        threshold = 20
        if x - vd.x() < threshold:
            self._dock_to("left")
        elif (vd.x() + vd.width()) - (x + CANVAS_SIZE) < threshold:
            self._dock_to("right")

    def _dock_to(self, side):
        vd = get_current_screen_for_widget(self)
        self._is_docked = True
        self._dock_side = side
        self._dock_animating = True
        self._stop_wandering()

        if side == "left":
            self._dock_target_x = int(vd.x()) - CANVAS_SIZE + DOCK_PEEK
        else:
            self._dock_target_x = int(vd.x() + vd.width()) - DOCK_PEEK

        dock_gif = "walk_right" if side == "left" else "walk_left"
        if dock_gif in self.gif_files and dock_gif != self.current_action_name:
            self.current_action_name = dock_gif
            self.movie.stop()
            self.movie = QMovie(self.gif_files[dock_gif])
            self.movie.frameChanged.connect(self.update)
            self.movie.start()
            self.movie.jumpToFrame(0)
            self.movie.setPaused(True)
            self._is_idle = True

        self._dock_timer.start(16)

    def _dock_animate_step(self):
        current_x = self.x()
        diff = self._dock_target_x - current_x
        if abs(diff) < 2:
            self.move(int(self._dock_target_x), self.y())
            self._dock_timer.stop()
            self._dock_animating = False
            return
        step = int(diff * 0.3)
        if step == 0:
            step = 1 if diff > 0 else -1
        self.move(current_x + step, self.y())

    def _undock(self):
        vd = get_current_screen_for_widget(self)
        self._is_docked = False
        self._dock_animating = True
        if self._dock_side == "left":
            self._dock_target_x = int(vd.x())
        else:
            self._dock_target_x = int(vd.x() + vd.width()) - CANVAS_SIZE
        self._dock_timer.start(16)
        QTimer.singleShot(500, self._start_wandering)

    # ---- 绘制 ----

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        if not self.movie.isValid():
            return
        pixmap = self.movie.currentPixmap()
        if pixmap.isNull():
            return

        target_w = int(GIF_MAX_SIZE * self._pet_scale)
        target_h = int(GIF_MAX_SIZE * self._pet_scale)
        scaled = pixmap.scaled(target_w, target_h,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)

        if abs(self._pet_rotation) > 0.1:
            cx = scaled.width() / 2
            cy = scaled.height() / 2
            transform = QTransform()
            transform.translate(cx, cy)
            transform.rotate(self._pet_rotation)
            transform.translate(-cx, -cy)
            scaled = scaled.transformed(transform, Qt.TransformationMode.SmoothTransformation)

        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)

    # ---- 摇摆 ----

    def _update_wobble(self):
        max_angle = 15
        self._wobble_angle += self._wobble_direction
        if abs(self._wobble_angle) >= max_angle:
            self._wobble_direction *= -1
        self.update()

    # ---- 物理 ----

    def _physics_step(self):
        if hasattr(self, '_physics_bounds'):
            vd = self._physics_bounds
        else:
            vd = get_current_screen_for_widget(self)

        pad = (CANVAS_SIZE - GIF_MAX_SIZE)
        min_x = int(vd.x()) - pad
        min_y = int(vd.y())
        max_x = int(vd.x() + vd.width()) - CANVAS_SIZE + pad
        max_y = int(vd.y() + vd.height()) - CANVAS_SIZE

        pos = QPointF(self.x(), self.y())

        # 重力
        self._velocity = QPointF(self._velocity.x(),
                                 self._velocity.y() + self._gravity)

        # 边界碰撞
        is_falling = True
        if pos.y() + self._velocity.y() >= max_y:
            self._velocity = QPointF(self._velocity.x() * self._friction,
                                     -abs(self._velocity.y()) * self._bounce_factor)
            pos = QPointF(pos.x(), max_y)
            is_falling = False
        if pos.y() + self._velocity.y() <= min_y:
            self._velocity = QPointF(self._velocity.x(),
                                     abs(self._velocity.y()) * self._bounce_factor)
        if pos.x() + self._velocity.x() <= min_x:
            self._velocity = QPointF(abs(self._velocity.x()) * self._bounce_factor,
                                     self._velocity.y())
        if pos.x() + self._velocity.x() >= max_x:
            self._velocity = QPointF(-abs(self._velocity.x()) * self._bounce_factor,
                                     self._velocity.y())

        # 摩擦
        self._velocity = QPointF(self._velocity.x() * self._friction,
                                 self._velocity.y() * 0.995)

        new_pos = QPointF(pos.x() + self._velocity.x(),
                          pos.y() + self._velocity.y())
        self.move(int(new_pos.x()), int(new_pos.y()))

        # 停止检测
        speed = math.sqrt(self._velocity.x() ** 2 + self._velocity.y() ** 2)
        at_ground = not is_falling and abs(pos.y() - max_y) < 1.5
        if speed < 0.5 and at_ground:
            self._velocity = QPointF(0, 0)
            if self._is_idle:
                self.movie.setPaused(True)
            self._physics_timer.stop()
            self._start_wandering()

    # ---- 动作切换 ----

    def _request_switch(self, name):
        walk_names = get_walk_gifs(self.gif_files)
        if name in walk_names:
            name = random.choice(walk_names)
        manager = PetManager.instance
        if manager:
            manager.switch_to(name,
                              position=self.pos(),
                              is_docked=self._is_docked,
                              dock_side=self._dock_side,
                              wander_enabled=self._wander_enabled,
                              wander_target=self._wander_target,
                              wander_direction=self._wander_direction)

    # ---- 鼠标事件 ----

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._is_teleporting:
            event.accept()
            return
        if self._is_docked:
            self._undock()

        self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        self._press_pos = event.globalPosition().toPoint()
        self._is_dragging = True
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self._physics_timer.stop()
        self._velocity = QPointF(0, 0)
        self._stop_wandering()

        # 切换到挣扎动画
        struggle_name = "struggle"
        if struggle_name in self.gif_files and struggle_name != self.current_action_name:
            self._saved_action = self.current_action_name
            self.current_action_name = struggle_name
            self.movie.stop()
            self.movie = QMovie(self.gif_files[struggle_name])
            self.movie.frameChanged.connect(self.update)
            self.movie.start()
            self._is_idle = False

        self._go_idle()  # pause but show first frame
        self._last_mouse_positions = []

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._is_dragging:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            self.move(new_pos)
            self._last_mouse_positions.append(new_pos)
            if len(self._last_mouse_positions) > 5:
                self._last_mouse_positions.pop(0)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._is_dragging = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        # 恢复之前的动画
        if hasattr(self, '_saved_action') and self._saved_action:
            self.movie.stop()
            self.movie = QMovie(self.gif_files[self._saved_action])
            self.movie.frameChanged.connect(self.update)
            self.current_action_name = self._saved_action
            self.movie.start()
            self.movie.jumpToFrame(0)
            self._is_idle = False
            self._saved_action = None

        # 判断是否有甩出速度
        release_pos = event.globalPosition().toPoint()
        dist = (release_pos - self._press_pos).manhattanLength()

        if dist < 5:
            self._start_wandering()
            self._check_dock()
            if self._is_docked:
                event.accept()
                return

        if len(self._last_mouse_positions) >= 2:
            recent = self._last_mouse_positions[-1]
            older = self._last_mouse_positions[0]
            dx = recent.x() - older.x()
            dy = recent.y() - older.y()
            self._velocity = QPointF(dx * 0.3, dy * 0.3)
            speed = math.sqrt(self._velocity.x() ** 2 + self._velocity.y() ** 2)
            if speed > 5.0:
                # 确定甩出方向的 GIF
                if dx < 0:
                    fling_dir = "left"
                else:
                    fling_dir = "right"
                fling_gif = "walk_left" if fling_dir == "left" else "walk_right"
                if fling_gif in self.gif_files:
                    self.current_action_name = fling_gif
                    self.movie.stop()
                    self.movie = QMovie(self.gif_files[fling_gif])
                    self.movie.frameChanged.connect(self.update)
                    self.movie.start()

                self._physics_bounds = get_current_screen_for_widget(self)
                self._physics_timer.start(16)
            else:
                self._start_wandering()
                self._check_dock()
        else:
            self._start_wandering()

        event.accept()

    def contextMenuEvent(self, event):
        menu = QMenu()
        hide_act = QAction("隐藏小小猪")
        hide_act.triggered.connect(self.hide)
        menu.addAction(hide_act)
        menu.addSeparator()
        quit_act = QAction("退出")
        quit_act.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_act)
        menu.exec(QCursor.pos())

    def closeEvent(self, event):
        if self._portal_window:
            self._portal_window.close()
        self._teleport_anim_timer.stop()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# PetManager
# ---------------------------------------------------------------------------
class PetManager:
    instance = None

    def __init__(self, gif_files):
        PetManager.instance = self
        self.gif_files = gif_files
        self.window = None
        walk_names = get_walk_gifs(gif_files)
        first_action = random.choice(walk_names) if walk_names else list(gif_files.keys())[0]
        self.window = PetWindow(gif_files, first_action)

    def switch_to(self, name, position=None, is_docked=False, dock_side=None,
                  wander_enabled=True, wander_target=None,
                  wander_direction=None, is_idle=False,
                  is_heading_to_portal=False):
        old = self.window
        if old:
            old.movie.stop()
            old.action_timer.stop()
            old._physics_timer.stop()
            old._wobble_timer.stop()
            old._wander_timer.stop()
            old._wander_decide_timer.stop()
            old._dock_timer.stop()
            old._teleport_anim_timer.stop()
            if old._portal_window:
                old._portal_window.close()
            old.close()

        self.window = PetWindow(
            self.gif_files, name,
            position=position, is_docked=is_docked, dock_side=dock_side,
            wander_enabled=wander_enabled, wander_target=wander_target,
            wander_direction=wander_direction, is_idle=is_idle,
            is_heading_to_portal=is_heading_to_portal
        )


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def load_gifs(folder):
    """加载文件夹中所有 GIF 文件"""
    gif_dict = {}
    for filepath in glob.glob(os.path.join(folder, "*.gif")):
        name, _ = os.path.splitext(os.path.basename(filepath))
        gif_dict[name] = filepath
    return gif_dict


def get_walk_gifs(gif_files):
    """Return only walking GIF names (exclude special action GIFs)"""
    return [k for k in gif_files if k not in SPECIAL_GIFS]


def resource_path(relative_path):
    """获取资源路径 (兼容 PyInstaller 打包)"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath('.'), relative_path)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    _macos_init_app()

    init_sizes()

    gif_folder = resource_path("gifs")
    os.makedirs(gif_folder, exist_ok=True)
    gifs = load_gifs(gif_folder)

    if not gifs:
        QMessageBox.critical(None, "Desktop Pet",
                             "Error: No GIF files found in gifs/ folder.")
        sys.exit(1)

    # 系统托盘图标
    first_gif = list(gifs.values())[0]
    tray_movie = QMovie(first_gif)
    tray_movie.jumpToFrame(0)
    tray_pixmap = tray_movie.currentPixmap()

    # 裁剪透明边框
    if not tray_pixmap.isNull():
        img = tray_pixmap.toImage()
        w, h = img.width(), img.height()
        min_x, min_y, max_x, max_y = w, h, 0, 0
        for py in range(h):
            for px in range(w):
                if img.pixelColor(px, py).alpha() > 0:
                    min_x = min(min_x, px)
                    min_y = min(min_y, py)
                    max_x = max(max_x, px)
                    max_y = max(max_y, py)
        if max_x > min_x and max_y > min_y:
            cropped = tray_pixmap.copy(min_x, min_y,
                                       max_x - min_x, max_y - min_y)
            tray_pixmap = cropped.scaled(
                32, 32,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

    tray_icon = QSystemTrayIcon(QIcon(tray_pixmap))
    tray_menu = QMenu()

    show_act = QAction("显示小小猪")
    def _show_pet():
        manager.window.show()
        manager.window.raise_()
        _macos_set_always_on_top(manager.window)
    show_act.triggered.connect(_show_pet)
    tray_menu.addAction(show_act)

    hide_act = QAction("隐藏小小猪")
    hide_act.triggered.connect(lambda: manager.window.hide())
    tray_menu.addAction(hide_act)

    tray_menu.addSeparator()

    quit_act = QAction("退出")
    quit_act.triggered.connect(app.quit)
    tray_menu.addAction(quit_act)

    tray_icon.setContextMenu(tray_menu)
    tray_icon.setToolTip("奇魔小小猪")
    tray_icon.show()

    manager = PetManager(gifs)

    sys.exit(app.exec())
