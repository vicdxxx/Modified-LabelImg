#!/usr/bin/python
# -*- coding: utf-8 -*-


try:
    from PyQt5.QtGui import *
    from PyQt5.QtCore import *
except ImportError:
    from PyQt4.QtGui import *
    from PyQt4.QtCore import *

from libs.utils import distance
import sys
from config import config as cfg

DEFAULT_LINE_COLOR = QColor(0, 255, 0, 255)
DEFAULT_FILL_COLOR = QColor(255, 0, 0, 128)
DEFAULT_DRAG_COLOR = QColor(150, 150, 150, 255)
DEFAULT_SELECT_LINE_COLOR = QColor(255, 255, 255)
DEFAULT_SELECT_FILL_COLOR = QColor(0, 128//2, 255//2, 155//2)
DEFAULT_VERTEX_FILL_COLOR = QColor(0, 255, 0, 255)
DEFAULT_HVERTEX_FILL_COLOR = QColor(255, 0, 0)
DEFAULT_ISWRONG_FILL_COLOR = QColor(255, 0, 0, 128)
DEFAULT_ISWRONG_SELECT_FILL_COLOR = QColor(255, 0, 0, 155)
DEFAULT_ISCHECKING_FILL_COLOR = QColor(0, 255, 0, 80)
DEFAULT_ISCHECKING_SELECT_FILL_COLOR = QColor(0, 255, 0, 100)
MIN_Y_LABEL = 1


class Shape(object):
    P_SQUARE, P_ROUND = range(2)

    MOVE_VERTEX, NEAR_VERTEX = range(2)

    # The following class variables influence the drawing
    # of _all_ shape objects.
    line_color = DEFAULT_LINE_COLOR
    fill_color = DEFAULT_FILL_COLOR
    drag_color = DEFAULT_DRAG_COLOR
    select_line_color = DEFAULT_SELECT_LINE_COLOR
    select_fill_color = DEFAULT_SELECT_FILL_COLOR
    vertex_fill_color = DEFAULT_VERTEX_FILL_COLOR
    hvertex_fill_color = DEFAULT_HVERTEX_FILL_COLOR
    iswrong_fill_color = DEFAULT_ISWRONG_FILL_COLOR
    iswrong_select_fill_color = DEFAULT_ISWRONG_SELECT_FILL_COLOR
    ischecking_fill_color = DEFAULT_ISCHECKING_FILL_COLOR
    ischecking_select_fill_color = DEFAULT_ISCHECKING_SELECT_FILL_COLOR

    point_type = P_ROUND
    # 8
    point_size = cfg.point_size
    scale = cfg.scale
    # 2
    pen_width = cfg.pen_width
    # 16
    font_point_size = cfg.font_point_size
    show_label_margin = cfg.show_label_margin

    def __init__(self, label=None, line_color=None, difficult=False, paintLabel=False, label_ch=None):
        label = self.remove_special_character_in_str(label)
        label_ch = self.remove_special_character_in_str(label_ch)

        self.label = label
        self.label_ch = label_ch
        self.points = []
        self.fill = False
        self.selected = False
        self.difficult = difficult
        self.paintLabel = paintLabel

        self._highlightIndex = None
        self._highlightMode = self.NEAR_VERTEX
        self._highlightSettings = {
            self.NEAR_VERTEX: (4, self.P_ROUND),
            self.MOVE_VERTEX: (1.5, self.P_SQUARE),
        }

        self._closed = False
        self.iswrong = False
        self.ischecking = False

        if line_color is not None:
            # Override the class line_color attribute
            # with an object attribute. Currently this
            # is used for drawing the pending line a different color.
            self.line_color = line_color

    def remove_special_character_in_str(self, label):
        #remove special charactor in UTF-8 with BOM format to UTF-8
        if label:
            label=label.strip('\ufeff').strip('\xef\xbb\xbf')
        return label

    def close(self):
        self._closed = True

    def reachMaxPoints(self):
        if len(self.points) >= 4:
            return True
        return False

    def addPoint(self, point):
        if not self.reachMaxPoints():
            self.points.append(point)

    def popPoint(self):
        if self.points:
            return self.points.pop()
        return None

    def isClosed(self):
        return self._closed

    def setOpen(self):
        self._closed = False

    def isWrongSize(self):
        return ((self.points[0] == self.points[-1])
                or (self.points[1].x() - self.points[0].x() < 15)
                or (self.points[3].y() - self.points[0].y() < 15))

    def isWrongSize_v2(self):
        is_wrong=self.points[0] == self.points[-1]
        is_wrong&=abs(self.points[1].x() - self.points[0].x()) < 15
        is_wrong&=abs(self.points[3].y() - self.points[0].y()) < 15
        return is_wrong

    def paint(self, painter, show_english=False):
        if self.points:
            self.line_color.setAlpha(255)
            color = self.select_line_color if self.selected else self.line_color
            pen = QPen(color)
            # Try using integer sizes for smoother drawing(?)
            pen.setWidth(max(self.pen_width, int(round(self.pen_width / self.scale))))  # cyw
            painter.setPen(pen)

            line_path = QPainterPath()
            vrtx_path = QPainterPath()

            line_path.moveTo(self.points[0])
            # Uncommenting the following line will draw 2 paths
            # for the 1st vertex, and make it non-filled, which
            # may be desirable.
            #self.drawVertex(vrtx_path, 0)

            for i, p in enumerate(self.points):
                line_path.lineTo(p)
                self.drawVertex(vrtx_path, i)
            if self.isClosed():
                line_path.lineTo(self.points[0])

            painter.drawPath(line_path)
            painter.drawPath(vrtx_path)
            painter.fillPath(vrtx_path, self.vertex_fill_color)

            # Draw text at the top-left
            if self.paintLabel:
                min_x = sys.maxsize
                min_y = sys.maxsize
                for point in self.points:
                    min_x = min(min_x, point.x()+self.show_label_margin)
                    min_y = min(min_y, point.y()-2*self.show_label_margin)
                if min_x != sys.maxsize and min_y != sys.maxsize:
                    font = QFont()
                    font.setPointSize(self.font_point_size)  # cyw
                    font.setBold(True)
                    painter.setFont(font)
                    if(self.label == None):
                        self.label = ""
                    if(min_y < MIN_Y_LABEL):
                        min_y += MIN_Y_LABEL
                    #painter.drawText(min_x, min_y, self.label)
                    # vic
                    if cfg.show_label:
                        if self.label_ch and not show_english:
                            painter.drawText(min_x, min_y, self.label_ch)
                        else:
                            painter.drawText(min_x, min_y, self.label)

            # vic
            if self.fill:
                if self.selected:
                    color = self.select_fill_color
                else:
                    color=QColor(self.fill_color.red(),self.fill_color.green(),self.fill_color.blue(),self.fill_color.alpha()*0.5)
                painter.fillPath(line_path, color)
            if self.iswrong:  # cyw
                color = self.iswrong_select_fill_color if self.selected else self.iswrong_fill_color
                painter.fillPath(line_path, color)
            if self.ischecking:
                color = self.ischecking_select_fill_color if self.selected else self.ischecking_fill_color
                painter.fillPath(line_path, color)

    def drawVertex(self, path, i):
        d = self.point_size / self.scale
        shape = self.point_type
        point = self.points[i]
        if i == self._highlightIndex:
            size, shape = self._highlightSettings[self._highlightMode]
            d *= size
        if self._highlightIndex is not None:
            self.vertex_fill_color = self.hvertex_fill_color
        else:
            self.vertex_fill_color = Shape.vertex_fill_color
        if shape == self.P_SQUARE:
            path.addRect(point.x() - d / 2, point.y() - d / 2, d, d)
        elif shape == self.P_ROUND:
            path.addEllipse(point, d / 2.0, d / 2.0)
        else:
            assert False, "unsupported vertex shape"

    def nearestVertex(self, point, epsilon):
        for i, p in enumerate(self.points):
            if distance(p - point) <= epsilon:
                return i
        return None

    def containsPoint(self, point):
        return self.makePath().contains(point)

    def containsRect(self, rect):
        x,y,x1,y1=rect
        point=[x,y]
        point1=[x1,y1]
        path=self.makePath()
        if path.contains(point) and path.contains(point1):
            return True
        return False

    def makePath(self):
        path = QPainterPath(self.points[0])
        for p in self.points[1:]:
            path.lineTo(p)
        return path

    def boundingRect(self):
        return self.makePath().boundingRect()

    def moveBy(self, offset):
        self.points = [p + offset for p in self.points]

    def moveVertexBy(self, i, offset):
        self.points[i] = self.points[i] + offset

    def highlightVertex(self, i, action):
        self._highlightIndex = i
        self._highlightMode = action

    def highlightClear(self):
        self._highlightIndex = None

    def copy(self):
        shape = Shape("%s" %self.label, label_ch=self.label_ch)
        shape.points = [p for p in self.points]
        shape.fill = self.fill
        shape.selected = self.selected
        shape._closed = self._closed
        if self.line_color != Shape.line_color:
            shape.line_color = self.line_color
        if self.fill_color != Shape.fill_color:
            shape.fill_color = self.fill_color
        shape.difficult = self.difficult
        return shape

    def __len__(self):
        return len(self.points)

    def __getitem__(self, key):
        return self.points[key]

    def __setitem__(self, key, value):
        self.points[key] = value
