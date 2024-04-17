
try:
    from PyQt5.QtGui import *
    from PyQt5.QtCore import *
    from PyQt5.QtWidgets import *
except ImportError:
    from PyQt4.QtGui import *
    from PyQt4.QtCore import *

#from PyQt4.QtOpenGL import *

from libs.shape import Shape
from libs.utils import distance, generateColorByText

from config import config as cfg

CURSOR_DEFAULT = Qt.ArrowCursor
CURSOR_POINT = Qt.PointingHandCursor
CURSOR_DRAW = Qt.CrossCursor
CURSOR_MOVE = Qt.ClosedHandCursor
CURSOR_GRAB = Qt.OpenHandCursor

# class Canvas(QGLWidget):


class Canvas(QWidget):
    zoomRequest = pyqtSignal(int)
    scrollRequest = pyqtSignal(int, int)
    newShape = pyqtSignal()
    selectionChanged = pyqtSignal(bool)
    shapeMoved = pyqtSignal()
    drawingPolygon = pyqtSignal(bool)

    draggingSelection = pyqtSignal()

    CREATE, EDIT, DRAG = list(range(3))

    epsilon = 11.0

    def __init__(self, *args, **kwargs):
        super(Canvas, self).__init__(*args, **kwargs)
        # Initialise local state.
        self.mode = self.CREATE
        self.shapes = []
        self.current = None
        self.selectedShape = None  # save the selected shape here
        self.selectedShapeGroup = [] # save the selected shape here
        self.selectedShapeGroupPrev = [] # save the selected shape here
        self.selectedShapeCopy = None
        self.drawingLineColor = QColor(0, 0, 255)
        self.drawingRectColor = QColor(0, 0, 255)

        self.draggingLineColor = QColor(150, 150, 150)
        self.draggingRectColor = QColor(150, 150, 150)

        self.line = Shape(line_color=self.drawingLineColor)
        self.prevPoint = QPointF()
        self.offsets = QPointF(), QPointF()
        self.offsetsGroup = [] #[[QPointF(), QPointF()],[...]]
        self.scale = 1.0
        self.pixmap = QPixmap()
        self.visible = {}
        self._hideBackround = False
        self.hideBackround = False
        self.hShape = None
        self.hVertex = None
        self._painter = QPainter()
        self._cursor = CURSOR_DEFAULT
        # Menus:
        self.menus = (QMenu(), QMenu())
        # Set widget options.
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.WheelFocus)
        self.verified = False
        self.drawSquare = False
        # cyw
        self.timeid = self.startTimer(100)
        self.iswrong = False
        if cfg.INCLUDE_CHINSES:
            self.show_english=False
        else:
            self.show_english=True

    def timerEvent(self, event):
        # cyw
        self.iswrong = False
        for shape in self.shapes:
            if shape.isWrongSize_v2() or self.isoverlap(shape):
                shape.iswrong = True
                self.iswrong = True
            else:
                shape.iswrong = False
        self.repaint()

    def setDrawingColor(self, qColor):
        self.drawingLineColor = qColor
        self.drawingRectColor = qColor

    def setDraggingColor(self, qColor):
        self.draggingLineColor = qColor
        self.draggingRectColor = qColor

    def enterEvent(self, ev):
        self.overrideCursor(self._cursor)

    def leaveEvent(self, ev):
        self.restoreCursor()

    def focusOutEvent(self, ev):
        self.restoreCursor()

    def isVisible(self, shape):
        return self.visible.get(shape, True)

    def drawing(self):
        return self.mode == self.CREATE

    def editing(self):
        return self.mode == self.EDIT

    def dragging(self):
        return self.mode == self.DRAG

    def setEditing(self, value=True):
        self.mode = self.EDIT if value else self.CREATE
        if not value:  # Create
            self.unHighlight()
            self.deSelectShape()
        self.prevPoint = QPointF()
        self.repaint()

    def changeShowEnglish(self, value=True):
        self.show_english=not self.show_english
        print("显示英文标签:", self.show_english)
        self.repaint()

    def setDragging(self, value=True):
        self.mode = self.DRAG if value else self.EDIT
        if not value: 
            #self.unHighlight()
            #self.deSelectShape(deselect_group=True)
            pass
        self.prevPoint = QPointF()
        self.repaint()

    def unHighlight(self):
        if self.hShape:
            self.hShape.highlightClear()
        self.hVertex = self.hShape = None

    def selectedVertex(self):
        return self.hVertex is not None

    def mouseMoveEvent(self, ev):
        """Update line with last point and current coordinates."""
        pos = self.transformPos(ev.pos())

        # Update coordinates in status bar if image is opened
        window = self.parent().window()
        if window.filePath is not None:
            self.parent().window().labelCoordinates.setText(
                'X: %d; Y: %d' % (pos.x(), pos.y()))

        # Polygon drawing.
        if self.drawing():
            self.overrideCursor(CURSOR_DRAW)
            if self.current:
                color = self.drawingLineColor
                if self.outOfPixmap(pos):
                    # Don't allow the user to draw outside the pixmap.
                    # Project the point to the pixmap's edges.
                    pos = self.intersectionPoint(self.current[-1], pos)
                elif len(self.current) > 1 and self.closeEnough(pos, self.current[0]):
                    # Attract line to starting point and colorise to alert the
                    # user:
                    pos = self.current[0]
                    color = self.current.line_color
                    self.overrideCursor(CURSOR_POINT)
                    self.current.highlightVertex(0, Shape.NEAR_VERTEX)

                if self.drawSquare:
                    initPos = self.current[0]
                    minX = initPos.x()
                    minY = initPos.y()
                    min_size = min(abs(pos.x() - minX), abs(pos.y() - minY))
                    directionX = -1 if pos.x() - minX < 0 else 1
                    directionY = -1 if pos.y() - minY < 0 else 1
                    self.line[1] = QPointF(minX + directionX * min_size, minY + directionY * min_size)
                else:
                    self.line[1] = pos

                self.line.line_color = color
                self.prevPoint = QPointF()
                self.current.highlightClear()
            else:
                self.prevPoint = pos
            self.repaint()
            return

        if self.dragging():
            self.overrideCursor(CURSOR_DEFAULT)
            if self.current:
                color = self.draggingLineColor
                if self.outOfPixmap(pos):
                    # Don't allow the user to draw outside the pixmap.
                    # Project the point to the pixmap's edges.
                    pos = self.intersectionPoint(self.current[-1], pos)
                elif len(self.current) > 1 and self.closeEnough(pos, self.current[0]):
                    # Attract line to starting point and colorise to alert the
                    # user:
                    pos = self.current[0]
                    color = self.current.line_color
                    self.overrideCursor(CURSOR_POINT)
                    self.current.highlightVertex(0, Shape.NEAR_VERTEX)
                self.line[1] = pos

                is_contain_shapes = self.insideShapesSelection(self.line)
                self.draggingSelection.emit()

                self.line.line_color = color
                self.prevPoint = QPointF()
                self.current.highlightClear()
            else:
                self.prevPoint = pos
            self.repaint()
            return

        # Polygon copy moving.
        if Qt.RightButton & ev.buttons():
            if self.selectedShapeCopy and self.prevPoint:
                self.overrideCursor(CURSOR_MOVE)
                self.boundedMoveShape(self.selectedShapeCopy, pos)
                self.repaint()
            elif self.selectedShape:
                self.selectedShapeCopy = self.selectedShape.copy()
                self.repaint()
            return

        # Polygon/Vertex moving.
        if Qt.LeftButton & ev.buttons():
            if self.selectedVertex():
                self.boundedMoveVertex(pos)
                self.shapeMoved.emit()
                self.repaint()
            elif len(self.selectedShapeGroup)>0 and self.editing()  and self.prevPoint:
                self.overrideCursor(CURSOR_MOVE)
                self.boundedMoveShape(None, pos, group=True)
                self.shapeMoved.emit()
                self.repaint()
            elif self.selectedShape and self.prevPoint:
                self.overrideCursor(CURSOR_MOVE)
                self.boundedMoveShape(self.selectedShape, pos)
                self.shapeMoved.emit()
                self.repaint()
            else:
                #self.setEditing(True)
                #self.setDragging(True)
                pass
            return

        # Just hovering over the canvas, 2 posibilities:
        # - Highlight shapes
        # - Highlight vertex
        # Update shape/vertex fill and tooltip value accordingly.
        self.setToolTip("Image")
        for shape in reversed([s for s in self.shapes if self.isVisible(s)]):
            # Look for a nearby vertex to highlight. If that fails,
            # check if we happen to be inside a shape.
            index = shape.nearestVertex(pos, self.epsilon)
            if index is not None:
                if self.selectedVertex():
                    self.hShape.highlightClear()
                self.hVertex, self.hShape = index, shape
                shape.highlightVertex(index, shape.MOVE_VERTEX)
                self.overrideCursor(CURSOR_POINT)
                self.setToolTip("Click & drag to move point")
                self.setStatusTip(self.toolTip())
                self.update()
                break
            elif shape.containsPoint(pos):
                if self.selectedVertex():
                    self.hShape.highlightClear()
                self.hVertex, self.hShape = None, shape
                self.setToolTip(
                    "Click & drag to move shape '%s'" % shape.label)
                self.setStatusTip(self.toolTip())
                self.overrideCursor(CURSOR_GRAB)
                self.update()
                break
            else:  # Nothing found, clear highlights, reset state.
                if self.hShape:
                    self.hShape.highlightClear()
                    self.update()
            self.hVertex, self.hShape = None, None
            self.overrideCursor(CURSOR_DEFAULT)

    def mousePressEvent(self, ev):
        pos = self.transformPos(ev.pos())

        if ev.button() == Qt.LeftButton:
            if self.drawing():
                self.handleDrawing(pos)
            else:
                has_shape = self.selectShapePoint(pos, group=True)
                if has_shape:
                    self.setEditing(True)
                else:
                    has_shape = self.selectShapePoint(pos)
                    if not has_shape:
                        self.selectedShapeGroupPrev=self.selectedShapeGroup.copy()
                        self.selectedShapeGroup=[]
                        self.setDragging(True)
                        if self.dragging():
                            self.handleDrawing(pos)
                    else:
                        self.setEditing(True)

                self.prevPoint = pos
                self.repaint()
        elif ev.button() == Qt.RightButton and self.editing():
            self.selectShapePoint(pos)
            self.prevPoint = pos
            self.repaint()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.RightButton:
            menu = self.menus[bool(self.selectedShapeCopy)]
            self.restoreCursor()
            if not menu.exec_(self.mapToGlobal(ev.pos()))\
               and self.selectedShapeCopy:
                # Cancel the move by deleting the shadow copy.
                self.selectedShapeCopy = None
                self.repaint()
        elif ev.button() == Qt.LeftButton and self.dragging() and len(self.selectedShapeGroup) > 0:
            self.deSelectShape(group=True)
            self.finish_drag()
        elif ev.button() == Qt.LeftButton and self.dragging() and len(self.selectedShapeGroup) == 0:
            self.deSelectShape(group=True)
            self.finish_drag()
        elif ev.button() == Qt.LeftButton and self.selectedShape:
            if self.selectedVertex():
                self.overrideCursor(CURSOR_POINT)
            else:
                self.overrideCursor(CURSOR_GRAB)
        elif ev.button() == Qt.LeftButton:
            pos = self.transformPos(ev.pos())
            if self.drawing():
                self.handleDrawing(pos)
            elif self.dragging():
                self.finish_drag()
        #self.setEditing(False)

    def endMove(self, copy=False):
        assert self.selectedShape and self.selectedShapeCopy
        shape = self.selectedShapeCopy
        #del shape.fill_color
        #del shape.line_color
        if copy:
            self.shapes.append(shape)
            self.selectedShape.selected = False
            self.selectedShape = shape
            self.repaint()
        else:
            self.selectedShape.points = [p for p in shape.points]
        self.selectedShapeCopy = None

    def hideBackroundShapes(self, value):
        self.hideBackround = value
        if self.selectedShape:
            # Only hide other shapes if there is a current selection.
            # Otherwise the user will not be able to select a shape.
            self.setHiding(True)
            self.repaint()

    def handleDrawing(self, pos):
        if self.current and self.current.reachMaxPoints() is False:
            initPos = self.current[0]
            targetPos = self.line[1]
            #minX = initPos.x()
            #minY = initPos.y()
            #maxX = targetPos.x()
            #maxY = targetPos.y()

            #vic
            minX, minY, maxX, maxY = self. find_lefttop_rightbottom_of_two_points(initPos, targetPos)

            self.current[0]=QPointF(minX, minY)
            self.current.addPoint(QPointF(maxX, minY))
            self.current.addPoint(QPointF(maxX, maxY))
            #self.current.addPoint(targetPos)
            self.current.addPoint(QPointF(minX, maxY))
            self.finalise()
        elif not self.outOfPixmap(pos):
            self.current = Shape()
            self.current.addPoint(pos)
            self.line.points = [pos, pos]
            self.setHiding()
            self.drawingPolygon.emit(True)
            self.update()

    def setHiding(self, enable=True):
        self._hideBackround = self.hideBackround if enable else False

    def canCloseShape(self):
        return self.drawing() and self.current and len(self.current) > 2

    def mouseDoubleClickEvent(self, ev):
        # We need at least 4 points here, since the mousePress handler
        # adds an extra one before this handler is called.
        if self.canCloseShape() and len(self.current) > 3:
            self.current.popPoint()
            self.finalise()

    def selectShape(self, shape, group=False):
        self.deSelectShape()
        shape.selected = True
        if group:
            self.selectedShape = None
            if shape not in self.selectedShapeGroup:
                self.selectedShapeGroup.append(shape)
            self.setHiding()
            self.selectionChanged.emit(True)
            self.update()
        else:
            self.selectedShape = shape
            self.setHiding()
            self.selectionChanged.emit(True)
            self.update()

    def selectShapePoint(self, point, group=False):
        """Select the first shape created which contains this point."""
        if group:
            for shape in reversed(self.selectedShapeGroup):
                if self.isVisible(shape) and shape.containsPoint(point):
                    self.calculateOffsets(None, point, group=True)
                    return True
            return False
        else:
            self.deSelectShape()
            if self.selectedVertex():  # A vertex is marked for selection.
                index, shape = self.hVertex, self.hShape
                shape.highlightVertex(index, shape.MOVE_VERTEX)
                self.selectShape(shape)
                return True
            for shape in reversed(self.shapes):
                if self.isVisible(shape) and shape.containsPoint(point):
                    self.selectShape(shape)
                    self.calculateOffsets(shape, point)
                    return True
            return False

    def calculateOffsets(self, shape, point, group=False):
        if group:
            self.offsetsGroup=[]
            for shape in self.selectedShapeGroup:
                rect = shape.boundingRect()
                x1 = rect.x() - point.x()
                y1 = rect.y() - point.y()
                x2 = (rect.x() + rect.width()) - point.x()
                y2 = (rect.y() + rect.height()) - point.y()
                offsets = [QPointF(x1, y1), QPointF(x2, y2)]
                self.offsetsGroup.append(offsets)
        else:
            rect = shape.boundingRect()
            x1 = rect.x() - point.x()
            y1 = rect.y() - point.y()
            x2 = (rect.x() + rect.width()) - point.x()
            y2 = (rect.y() + rect.height()) - point.y()
            self.offsets = QPointF(x1, y1), QPointF(x2, y2)

    def snapPointToCanvas(self, x, y):
        """
        Moves a point x,y to within the boundaries of the canvas.
        :return: (x,y,snapped) where snapped is True if x or y were changed, False if not.
        """
        if x < 0 or x > self.pixmap.width() or y < 0 or y > self.pixmap.height():
            x = max(x, 0)
            y = max(y, 0)
            x = min(x, self.pixmap.width())
            y = min(y, self.pixmap.height())
            return x, y, True

        return x, y, False

    def boundedMoveVertex(self, pos):
        index, shape = self.hVertex, self.hShape
        point = shape[index]
        if self.outOfPixmap(pos):
            pos = self.intersectionPoint(point, pos)

        if self.drawSquare:
            opposite_point_index = (index + 2) % 4
            opposite_point = shape[opposite_point_index]

            min_size = min(abs(pos.x() - opposite_point.x()), abs(pos.y() - opposite_point.y()))
            directionX = -1 if pos.x() - opposite_point.x() < 0 else 1
            directionY = -1 if pos.y() - opposite_point.y() < 0 else 1
            shiftPos = QPointF(opposite_point.x() + directionX * min_size - point.x(),
                               opposite_point.y() + directionY * min_size - point.y())
        else:
            shiftPos = pos - point

        shape.moveVertexBy(index, shiftPos)

        lindex = (index + 1) % 4
        rindex = (index + 3) % 4
        lshift = None
        rshift = None
        if index % 2 == 0:
            rshift = QPointF(shiftPos.x(), 0)
            lshift = QPointF(0, shiftPos.y())
        else:
            lshift = QPointF(shiftPos.x(), 0)
            rshift = QPointF(0, shiftPos.y())
        shape.moveVertexBy(rindex, rshift)
        shape.moveVertexBy(lindex, lshift)

    def boundedMoveShape(self, shape, pos, group=False):
        if group:
            if self.outOfPixmap(pos):
                return False  # No need to move
            move_ok=[]
            for idx, selectedShape in enumerate(self.selectedShapeGroup):
                o1 = pos + self.offsetsGroup[idx][0]
                if self.outOfPixmap(o1):
                    pos -= QPointF(min(0, o1.x()), min(0, o1.y()))
                o2 = pos + self.offsetsGroup[idx][1]
                if self.outOfPixmap(o2):
                    pos += QPointF(min(0, self.pixmap.width() - o2.x()),
                                min(0, self.pixmap.height() - o2.y()))
            for idx, selectedShape in enumerate(self.selectedShapeGroup):
                dp = pos - self.prevPoint
                if dp:
                    selectedShape.moveBy(dp)
                    move_ok.append(True)
            self.prevPoint = pos
            return move_ok.count(True)==len(self.selectedShapeGroup)
        else:
            if self.outOfPixmap(pos):
                return False  # No need to move
            o1 = pos + self.offsets[0]
            if self.outOfPixmap(o1):
                pos -= QPointF(min(0, o1.x()), min(0, o1.y()))
            o2 = pos + self.offsets[1]
            if self.outOfPixmap(o2):
                pos += QPointF(min(0, self.pixmap.width() - o2.x()),
                               min(0, self.pixmap.height() - o2.y()))
            # The next line tracks the new position of the cursor
            # relative to the shape, but also results in making it
            # a bit "shaky" when nearing the border and allows it to
            # go outside of the shape's area for some reason. XXX
            #self.calculateOffsets(self.selectedShape, pos)
            dp = pos - self.prevPoint
            if dp:
                shape.moveBy(dp)
                self.prevPoint = pos
                return True
            return False

    def insideShapesSelection(self, mounse_shape):
        is_contain_shapes=[]
        for shape in reversed(self.shapes):
            is_contain=False
            #shape has overlap with mounse_shape
            is_overlap=self.is_overlap_between_shapes(mounse_shape, shape)
            if is_overlap and self.isVisible(shape):
                self.selectShape(shape, group=True)
                is_contain=True

            ##shape complete inside mounse_shape
            #for point in shape.points:
            #    is_overlap_between_shapes()
            #    contain_vertex_num=0
            #    if self.isVisible(shape) and mounse_shape.containsRect(point):
            #        self.selectShape(shape)
            #        contain_vertex_num+=1
            #    if contain_vertex_num>=4:
            #        is_contain=True
            is_contain_shapes.append(is_contain)
        return is_contain_shapes

    def deSelectShape(self, group=False):
        if group:
            for idx, selectedShape in enumerate(self.selectedShapeGroupPrev):
                if selectedShape:
                    self.selectedShapeGroupPrev[idx].selected=False
                    self.selectedShapeGroupPrev[idx]=None
            self.selectedShapeGroupPrev=[]
            self.update()
        else:
            if self.selectedShape:
                self.selectedShape.selected = False
                self.selectedShape = None
                self.setHiding(False)
                self.selectionChanged.emit(False)
                self.update()

    def deleteSelected(self):
        shapes = []
        if len(self.selectedShapeGroup) > 0:
            for idx, selectedShape in enumerate(self.selectedShapeGroup):
                if selectedShape:
                    if selectedShape in self.shapes:
                        self.shapes.remove(selectedShape)
                    self.selectedShapeGroup[idx] = None
                    shapes.append(selectedShape)
                    self.update()
            self.selectedShapeGroup = []
            self.update()
        else:
            if self.selectedShape:
                selectedShape = self.selectedShape
                if selectedShape in self.shapes:
                    self.shapes.remove(selectedShape)
                self.selectedShape = None
                shapes = [selectedShape]
                self.update()
        return shapes

    def copySelectedShape(self):
        if self.selectedShape:
            shape = self.selectedShape.copy()
            self.deSelectShape()
            self.shapes.append(shape)
            shape.selected = True
            self.selectedShape = shape
            self.boundedShiftShape(shape)
            return shape

    def boundedShiftShape(self, shape):
        # Try to move in one direction, and if it fails in another.
        # Give up if both fail.
        point = shape[0]
        offset = QPointF(2.0, 2.0)
        self.calculateOffsets(shape, point)
        self.prevPoint = point
        if not self.boundedMoveShape(shape, point - offset):
            self.boundedMoveShape(shape, point + offset)

    def paintEvent(self, event):
        if not self.pixmap:
            return super(Canvas, self).paintEvent(event)

        p = self._painter
        p.begin(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.HighQualityAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        p.scale(self.scale, self.scale)
        p.translate(self.offsetToCenter())

        p.drawPixmap(0, 0, self.pixmap)
        Shape.scale = self.scale
        for shape in self.shapes:
            if (shape.selected or not self._hideBackround) and self.isVisible(shape):
                shape.fill = shape.selected or shape == self.hShape
                shape.paint(p, self.show_english)

        if self.current:
            if self.drawing():
                self.current.paint(p, self.show_english)
                pass
            elif self.dragging():
                pass
            #self.line.paint(p)

        if self.selectedShapeCopy:
            self.selectedShapeCopy.paint(p)

        # Paint rect
        if self.current is not None and len(self.line) == 2:
            #leftTop = self.line[0]
            #rightBottom = self.line[1]
            #rectWidth = rightBottom.x() - leftTop.x()
            #rectHeight = rightBottom.y() - leftTop.y()
            #p.setPen(self.drawingRectColor)
            #brush = QBrush(Qt.BDiagPattern)
            #p.setBrush(brush)
            #p.drawRect(leftTop.x(), leftTop.y(), rectWidth, rectHeight)

            # vic
            pt0 = self.line[0]
            pt1 = self.line[1]
            min_x, min_y, max_x, max_y = self. find_lefttop_rightbottom_of_two_points(pt0, pt1)

            rectWidth = max_x - min_x
            rectHeight = max_y - min_y

            # vic
            pen = QPen(self.drawingRectColor)
            pen.setWidth(max(cfg.pen_width, int(round(cfg.pen_width / self.scale))))
            p.setPen(pen)
            if  self.drawing():
                brush = QBrush(Qt.NoBrush)
            elif  self.dragging():
                brush = QBrush(Qt.NoBrush)
            p.setBrush(brush)
            p.drawRect(min_x, min_y, rectWidth, rectHeight)

        # crossover locate position
        if self.drawing() and not self.prevPoint.isNull() and not self.outOfPixmap(self.prevPoint):
            # vic
            pen = QPen(QColor(0, 0, 0))
            pen.setWidth(max(cfg.pen_width, int(round(cfg.pen_width / self.scale))))
            p.setPen(pen)
            p.drawLine(self.prevPoint.x(), 0, self.prevPoint.x(), self.pixmap.height())
            p.drawLine(0, self.prevPoint.y(), self.pixmap.width(), self.prevPoint.y())

        self.setAutoFillBackground(True)
        if self.verified:
            pal = self.palette()
            pal.setColor(self.backgroundRole(), QColor(184, 239, 38, 128))
            self.setPalette(pal)
        else:
            pal = self.palette()
            pal.setColor(self.backgroundRole(), QColor(232, 232, 232, 255))
            self.setPalette(pal)
        p.end()

    def find_lefttop_rightbottom_of_two_points(self, pt0, pt1):

        min_x=min(pt0.x(), pt1.x())
        min_y=min(pt0.y(), pt1.y())
        max_x=max(pt0.x(), pt1.x())
        max_y=max(pt0.y(), pt1.y())
        return min_x, min_y, max_x, max_y

    def transformPos(self, point):
        """Convert from widget-logical coordinates to painter-logical coordinates."""
        return point / self.scale - self.offsetToCenter()

    def offsetToCenter(self):
        s = self.scale
        area = super(Canvas, self).size()
        w, h = self.pixmap.width() * s, self.pixmap.height() * s
        aw, ah = area.width(), area.height()
        x = (aw - w) / (2 * s) if aw > w else 0
        y = (ah - h) / (2 * s) if ah > h else 0
        return QPointF(x, y)

    def outOfPixmap(self, p):
        w, h = self.pixmap.width(), self.pixmap.height()
        return not (0 <= p.x() <= w and 0 <= p.y() <= h)

    def cal_area(self, line):  # [x1, y1, x2, y2]
        res = (line[2] - line[0]) * (line[3] - line[1])
        return res

    def cal_overlap_area(self, l1, l2):
        # l1 and l2 are [x1, y1, x2, y2]
        # for iou x min, y min
        xmin = l1[0] if l1[0] > l2[0] else l2[0]
        ymin = l1[1] if l1[1] > l2[1] else l2[1]
        xmax = l1[2] if l1[2] < l2[2] else l2[2]
        ymax = l1[3] if l1[3] < l2[3] else l2[3]

        iou_area = (ymax - ymin) * (xmax - xmin)
        return iou_area

    def cal_iou(self, l1, l2):
        if l2[3] < l1[1] or l2[2] < l1[0] or l2[1] > l1[3] or l2[0] > l1[2]:
            return 0, 0, 0
        area1 = self.cal_area(l1)
        area2 = self.cal_area(l2)
        iou_area = self.cal_overlap_area(l1, l2)
        if area1 + area2 - iou_area<=0:
            iou=0
        else:
            iou = iou_area / (area1 + area2 - iou_area)
        if area1<=0:
            iou1=0
        else:
            iou1 = iou_area / area1
        if area1<=0:
            iou2=0
        else:
            iou2 = iou_area / area2
        return iou, iou1, iou2

    def isoverlap(self, shape):
        return False  # cyw 2019.9.2 don't limit overlap
        box = [shape.points[0].x(), shape.points[0].y(), shape.points[2].x(), shape.points[2].y()]
        for s in self.shapes:
            if s == shape:
                continue
            b = [s.points[0].x(), s.points[0].y(), s.points[2].x(), s.points[2].y()]
            ious = self.cal_iou(box, b)
            if ious[0] > 0.3 or ious[1] > 0.3 or ious[2] > 0.3:
                return True
        return False

    def is_overlap_between_shapes(self, shape, shape_1):
        leftbottom_pt_idx=2
        if len(shape.points)==2:
            leftbottom_pt_idx=1

        pt0 = shape[0]
        pt1 = shape[leftbottom_pt_idx]
        min_x, min_y, max_x, max_y = self. find_lefttop_rightbottom_of_two_points(pt0, pt1)
        box = [min_x, min_y, max_x, max_y]
        leftbottom_pt_idx=2
        if len(shape_1.points)==2:
            leftbottom_pt_idx=1
        pt0 = shape_1[0]
        pt1 = shape_1[leftbottom_pt_idx]
        min_x, min_y, max_x, max_y = self. find_lefttop_rightbottom_of_two_points(pt0, pt1)
        box_1 = [min_x, min_y, max_x, max_y]
        ious = self.cal_iou(box, box_1)
        if ious[0] > 0:
            return True
        return False

    def finish_drag(self):
        self.current = None
        self.setDragging(True)
        self.drawingPolygon.emit(False)
        self.update()

    def finalise(self):
        assert self.current
        # cyw
        if (self.current.isWrongSize_v2() or self.isoverlap(self.current)):
            self.current = None
            self.drawingPolygon.emit(False)
            self.update()
            return

        self.current.close()
        self.shapes.append(self.current)
        self.current = None
        self.setHiding(False)
        self.newShape.emit()
        self.update()

    def closeEnough(self, p1, p2):
        #d = distance(p1 - p2)
        #m = (p1-p2).manhattanLength()
        # print "d %.2f, m %d, %.2f" % (d, m, d - m)
        return distance(p1 - p2) < self.epsilon

    def intersectionPoint(self, p1, p2):
        # Cycle through each image edge in clockwise fashion,
        # and find the one intersecting the current line segment.
        # http://paulbourke.net/geometry/lineline2d/
        size = self.pixmap.size()
        points = [(0, 0),
                  (size.width(), 0),
                  (size.width(), size.height()),
                  (0, size.height())]
        x1, y1 = p1.x(), p1.y()
        x2, y2 = p2.x(), p2.y()
        d, i, (x, y) = min(self.intersectingEdges((x1, y1), (x2, y2), points))
        x3, y3 = points[i]
        x4, y4 = points[(i + 1) % 4]
        if (x, y) == (x1, y1):
            # Handle cases where previous point is on one of the edges.
            if x3 == x4:
                return QPointF(x3, min(max(0, y2), max(y3, y4)))
            else:  # y3 == y4
                return QPointF(min(max(0, x2), max(x3, x4)), y3)

        # Ensure the labels are within the bounds of the image. If not, fix them.
        x, y, _ = self.snapPointToCanvas(x, y)

        return QPointF(x, y)

    def intersectingEdges(self, x1y1, x2y2, points):
        """For each edge formed by `points', yield the intersection
        with the line segment `(x1,y1) - (x2,y2)`, if it exists.
        Also return the distance of `(x2,y2)' to the middle of the
        edge along with its index, so that the one closest can be chosen."""
        x1, y1 = x1y1
        x2, y2 = x2y2
        for i in range(4):
            x3, y3 = points[i]
            x4, y4 = points[(i + 1) % 4]
            denom = (y4 - y3) * (x2 - x1) - (x4 - x3) * (y2 - y1)
            nua = (x4 - x3) * (y1 - y3) - (y4 - y3) * (x1 - x3)
            nub = (x2 - x1) * (y1 - y3) - (y2 - y1) * (x1 - x3)
            if denom == 0:
                # This covers two cases:
                #   nua == nub == 0: Coincident
                #   otherwise: Parallel
                continue
            ua, ub = nua / denom, nub / denom
            if 0 <= ua <= 1 and 0 <= ub <= 1:
                x = x1 + ua * (x2 - x1)
                y = y1 + ua * (y2 - y1)
                m = QPointF((x3 + x4) / 2, (y3 + y4) / 2)
                d = distance(m - QPointF(x2, y2))
                yield d, i, (x, y)

    # These two, along with a call to adjustSize are required for the
    # scroll area.
    def sizeHint(self):
        return self.minimumSizeHint()

    def minimumSizeHint(self):
        if self.pixmap:
            return self.scale * self.pixmap.size()
        return super(Canvas, self).minimumSizeHint()

    def wheelEvent(self, ev):
        qt_version = 4 if hasattr(ev, "delta") else 5
        if qt_version == 4:
            if ev.orientation() == Qt.Vertical:
                v_delta = ev.delta()
                h_delta = 0
            else:
                h_delta = ev.delta()
                v_delta = 0
        else:
            delta = ev.angleDelta()
            h_delta = delta.x()
            v_delta = delta.y()

        mods = ev.modifiers()
        if Qt.ControlModifier == int(mods) and v_delta:
            self.zoomRequest.emit(v_delta)
        else:
            v_delta and self.scrollRequest.emit(v_delta, Qt.Vertical)
            h_delta and self.scrollRequest.emit(h_delta, Qt.Horizontal)
        ev.accept()

    def keyPressEvent(self, ev):
        key = ev.key()
        if key == Qt.Key_Escape and self.current:
            print('ESC press')
            self.current = None
            self.drawingPolygon.emit(False)
            self.update()
        elif key == Qt.Key_Return and self.canCloseShape():
            self.finalise()
        elif key == Qt.Key_Left and self.selectedShape:
            self.moveOnePixel('Left')
        elif key == Qt.Key_Right and self.selectedShape:
            self.moveOnePixel('Right')
        elif key == Qt.Key_Up and self.selectedShape:
            self.moveOnePixel('Up')
        elif key == Qt.Key_Down and self.selectedShape:
            self.moveOnePixel('Down')
        elif key == Qt.Key_Left and len(self.selectedShapeGroup) > 0:
            self.moveOnePixel('Left', group=True)
        elif key == Qt.Key_Right and len(self.selectedShapeGroup) > 0:
            self.moveOnePixel('Right', group=True)
        elif key == Qt.Key_Up and len(self.selectedShapeGroup) > 0:
            self.moveOnePixel('Up', group=True)
        elif key == Qt.Key_Down and len(self.selectedShapeGroup) > 0:
            self.moveOnePixel('Down', group=True)

    def moveOnePixel(self, direction, group=True):
        if group:
            for idx, selectedShape in enumerate(self.selectedShapeGroup):
                if direction == 'Left' and not self.moveOutOfBound(QPointF(-1.0, 0), group, selectedShape):
                    # print("move Left one pixel")
                    selectedShape.points[0] += QPointF(-1.0, 0)
                    selectedShape.points[1] += QPointF(-1.0, 0)
                    selectedShape.points[2] += QPointF(-1.0, 0)
                    selectedShape.points[3] += QPointF(-1.0, 0)
                elif direction == 'Right' and not self.moveOutOfBound(QPointF(1.0, 0), group, selectedShape):
                    # print("move Right one pixel")
                    selectedShape.points[0] += QPointF(1.0, 0)
                    selectedShape.points[1] += QPointF(1.0, 0)
                    selectedShape.points[2] += QPointF(1.0, 0)
                    selectedShape.points[3] += QPointF(1.0, 0)
                elif direction == 'Up' and not self.moveOutOfBound(QPointF(0, -1.0), group, selectedShape):
                    # print("move Up one pixel")
                    selectedShape.points[0] += QPointF(0, -1.0)
                    selectedShape.points[1] += QPointF(0, -1.0)
                    selectedShape.points[2] += QPointF(0, -1.0)
                    selectedShape.points[3] += QPointF(0, -1.0)
                elif direction == 'Down' and not self.moveOutOfBound(QPointF(0, 1.0), group, selectedShape):
                    # print("move Down one pixel")
                    selectedShape.points[0] += QPointF(0, 1.0)
                    selectedShape.points[1] += QPointF(0, 1.0)
                    selectedShape.points[2] += QPointF(0, 1.0)
                    selectedShape.points[3] += QPointF(0, 1.0)
        else:
            if direction == 'Left' and not self.moveOutOfBound(QPointF(-1.0, 0)):
                # print("move Left one pixel")
                self.selectedShape.points[0] += QPointF(-1.0, 0)
                self.selectedShape.points[1] += QPointF(-1.0, 0)
                self.selectedShape.points[2] += QPointF(-1.0, 0)
                self.selectedShape.points[3] += QPointF(-1.0, 0)
            elif direction == 'Right' and not self.moveOutOfBound(QPointF(1.0, 0)):
                # print("move Right one pixel")
                self.selectedShape.points[0] += QPointF(1.0, 0)
                self.selectedShape.points[1] += QPointF(1.0, 0)
                self.selectedShape.points[2] += QPointF(1.0, 0)
                self.selectedShape.points[3] += QPointF(1.0, 0)
            elif direction == 'Up' and not self.moveOutOfBound(QPointF(0, -1.0)):
                # print("move Up one pixel")
                self.selectedShape.points[0] += QPointF(0, -1.0)
                self.selectedShape.points[1] += QPointF(0, -1.0)
                self.selectedShape.points[2] += QPointF(0, -1.0)
                self.selectedShape.points[3] += QPointF(0, -1.0)
            elif direction == 'Down' and not self.moveOutOfBound(QPointF(0, 1.0)):
                # print("move Down one pixel")
                self.selectedShape.points[0] += QPointF(0, 1.0)
                self.selectedShape.points[1] += QPointF(0, 1.0)
                self.selectedShape.points[2] += QPointF(0, 1.0)
                self.selectedShape.points[3] += QPointF(0, 1.0)

        self.shapeMoved.emit()
        self.repaint()

    def moveOutOfBound(self, step, group=False, selectedShape=None):
        if group:
            points = [p1+p2 for p1, p2 in zip(selectedShape.points, [step]*4)]
        else:
            points = [p1+p2 for p1, p2 in zip(self.selectedShape.points, [step]*4)]
        return True in map(self.outOfPixmap, points)

    def setLastLabel(self, text, line_color = None, fill_color = None, text_ch=None):
        assert text
        self.shapes[-1].label = text
        # vic
        if text_ch:
            self.shapes[-1].label_ch=text_ch
        else:
            self.shapes[-1].label_ch=text

        if line_color:
            self.shapes[-1].line_color = line_color

        if fill_color:
            self.shapes[-1].fill_color = fill_color

        return self.shapes[-1]

    def undoLastLine(self):
        assert self.shapes
        self.current = self.shapes.pop()
        self.current.setOpen()
        self.line.points = [self.current[-1], self.current[0]]
        self.drawingPolygon.emit(True)

    def resetAllLines(self):
        assert self.shapes
        self.current = self.shapes.pop()
        self.current.setOpen()
        self.line.points = [self.current[-1], self.current[0]]
        self.drawingPolygon.emit(True)
        self.current = None
        self.drawingPolygon.emit(False)
        self.update()

    def loadPixmap(self, pixmap):
        self.pixmap = pixmap
        self.shapes = []
        self.repaint()

    def loadShapes(self, shapes):
        self.shapes = list(shapes)
        self.current = None
        self.repaint()

    def setShapeVisible(self, shape, value):
        self.visible[shape] = value
        self.repaint()

    def currentCursor(self):
        cursor = QApplication.overrideCursor()
        if cursor is not None:
            cursor = cursor.shape()
        return cursor

    def overrideCursor(self, cursor):
        self._cursor = cursor
        if self.currentCursor() is None:
            QApplication.setOverrideCursor(cursor)
        else:
            QApplication.changeOverrideCursor(cursor)

    def restoreCursor(self):
        QApplication.restoreOverrideCursor()

    def resetState(self):
        self.restoreCursor()
        self.pixmap = None
        self.update()

    def setDrawingShapeToSquare(self, status):
        self.drawSquare = status
