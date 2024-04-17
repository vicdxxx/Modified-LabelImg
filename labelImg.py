#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from config import config as cfg
import cv2
import numpy as np
from libs.hashableQListWidgetItem import HashableQListWidgetItem
from libs.version import __version__
from libs.ustr import ustr
from libs.yolo_io import TXT_EXT
from libs.yolo_io import YoloReader
from libs.pascal_voc_io import XML_EXT
from libs.pascal_voc_io import PascalVocReader
from libs.toolBar import ToolBar
from libs.labelFile import LabelFile, LabelFileError
from libs.colorDialog import ColorDialog
from libs.labelDialog import LabelDialog
from libs.zoomWidget import ZoomWidget
from libs.canvas import Canvas
from libs.stringBundle import StringBundle
from libs.shape import Shape, DEFAULT_LINE_COLOR, DEFAULT_FILL_COLOR, DEFAULT_DRAG_COLOR
from libs.settings import Settings
from libs.utils import *
from libs.constants import *
from libs.resources import *
import codecs
import distutils.spawn
import os.path
import platform
import re
import subprocess

from functools import partial
from collections import defaultdict
from exif import Image as exif_Image


try:
    from PyQt5 import QtTest
    from PyQt5.QtGui import *
    from PyQt5.QtCore import *
    from PyQt5.QtWidgets import *
except ImportError:
    # needed for py3+qt4
    # Ref:
    # http://pyqt.sourceforge.net/Docs/PyQt4/incompatible_apis.html
    # http://stackoverflow.com/questions/21217399/pyqt4-qtcore-qvariant-object-instead-of-a-string
    if sys.version_info.major >= 3:
        import sip
        sip.setapi('QVariant', 2)
    from PyQt4.QtGui import *
    from PyQt4.QtCore import *


if cfg.INCLUDE_CHINSES:
    from util_pinyin import pinyin
    from util_pinyin import pinyin_2_chinese


__appname__ = 'labelImg'


class TrackerThread(QtCore.QThread):

    bbox_tracker = QtCore.pyqtSignal(object)

    def __init__(self, shapes_info, prev_image_np, image_np):
        QtCore.QThread.__init__(self)
        self.shapes_info = shapes_info
        self.prev_image_np = prev_image_np
        self.image_np = image_np

    def run(self):
        shapes_info = self.shapes_info
        # np.any(self.prev_image_np!=self.image_np)
        image = self.prev_image_np
        image_new = self.image_np
        trackerType = "CSRT"
        # [Top_Left_X, Top_Left_Y, Width, Height]
        multiTracker = cv2.MultiTracker_create()
        print('MultiTracker_create')
        labels = []
        for item in shapes_info:
            tracker = createTrackerByName(trackerType)
            p1, p2, p3, p4 = item[1]
            width = p2[0] - p1[0]
            height = p4[1] - p1[1]
            bbox = (p1[0], p1[1], width, height)
            #tracker.init(image, bbox)
            multiTracker.add(tracker, image, bbox)
        success, new_boxes = multiTracker.update(image_new)
        self.bbox_tracker.emit((success, new_boxes, shapes_info))


def QImageToCvMat(im_origin):
    '''  Converts a QImage into an opencv MAT format  '''
    incomingImage = im_origin.copy()
    incomingImage = incomingImage.convertToFormat(
        QImage.Format.Format_RGBA8888)

    width = incomingImage.width()
    height = incomingImage.height()

    ptr = incomingImage.bits()
    ptr.setsize(height * width * 4)
    arr = np.frombuffer(ptr, np.uint8).copy().reshape((height, width, 4))
    return arr


trackerTypes = ['BOOSTING', 'MIL', 'KCF', 'TLD',
                'MEDIANFLOW', 'GOTURN', 'MOSSE', 'CSRT']


def createTrackerByName(trackerType):
    # Create a tracker based on tracker name
    if trackerType == trackerTypes[0]:
        tracker = cv2.TrackerBoosting_create()
    elif trackerType == trackerTypes[1]:
        tracker = cv2.TrackerMIL_create()
    elif trackerType == trackerTypes[2]:
        tracker = cv2.TrackerKCF_create()
    elif trackerType == trackerTypes[3]:
        tracker = cv2.TrackerTLD_create()
    elif trackerType == trackerTypes[4]:
        tracker = cv2.TrackerMedianFlow_create()
    elif trackerType == trackerTypes[5]:
        tracker = cv2.TrackerGOTURN_create()
    elif trackerType == trackerTypes[6]:
        tracker = cv2.TrackerMOSSE_create()
    elif trackerType == trackerTypes[7]:
        tracker = cv2.TrackerCSRT_create()
    else:
        tracker = None
        print('Incorrect tracker name')
        print('Available trackers are:')
        for t in trackerTypes:
            print(t)
    return tracker


class WindowMixin(object):

    def menu(self, title, actions=None):
        menu = self.menuBar().addMenu(title)
        if actions:
            addActions(menu, actions)
        return menu

    def toolbar(self, title, actions=None):
        toolbar = ToolBar(title)
        toolbar.setObjectName(u'%sToolBar' % title)
        # toolbar.setOrientation(Qt.Vertical)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        if actions:
            addActions(toolbar, actions)
        self.addToolBar(Qt.LeftToolBarArea, toolbar)
        return toolbar


class MainWindow(QMainWindow, WindowMixin):
    FIT_WINDOW, FIT_WIDTH, MANUAL_ZOOM = list(range(3))

    def __init__(self, defaultFilename=None, defaultPrefdefClassFile=None, defaultSaveDir=None):
        super(MainWindow, self).__init__()
        self.setWindowTitle(__appname__)

        # self.timer=QTimer(self)
        #self.timer.timeout.connect(self.loadFile, self.mImgList[self.mImgList.index(self.filePath)])
        # self.timer.start(1000)

        self.imageData = None
        self.previousImageData = None

        # Load setting in the main thread
        self.settings = Settings()
        self.settings.load()
        settings = self.settings

        # Load string bundle for i18n
        self.stringBundle = StringBundle.getBundle()
        def getStr(strId): return self.stringBundle.getString(strId)

        # Save as Pascal voc xml
        self.is_reserve_annotation = False
        self.is_reserve_annotation_tracker = False
        self.is_reserve_annotation_only_update = False

        self.defaultSaveDir = None

        # vic Init
        if cfg.DEBUG:
            targetDirPath = r"F:\SmartLarder\test\image"
            if os.path.exists(targetDirPath):
                self.defaultSaveDir = targetDirPath
            else:
                self.defaultSaveDir = None

        self.usingPascalVocFormat = True
        self.usingYoloFormat = False

        # For loading all image under a directory
        self.mImgList = []
        self.dirname = None
        self.labelHist = []
        # vic
        self.labelHistChinese = []
        self.labelHistPinYin2Chinese = {}

        self.callEditDialog = False

        self.lastOpenDir = None

        # Whether we need to save or not.
        self.dirty = False

        self._noSelectionSlot = False
        self._beginner = True
        self.screencastViewer = self.getAvailableScreencastViewer()
        self.screencast = "https://youtu.be/p0nR2YsCY_U"

        # Load predefined classes to the list
        # self.labelHist
        self.loadPredefinedClasses(defaultPrefdefClassFile)
        # Main widgets and related state.
        if cfg.INCLUDE_CHINSES:
            self.labelDialog = LabelDialog(
                parent=self, listItem=self.labelHistChinese)
        else:
            self.labelDialog = LabelDialog(
                parent=self, listItem=self.labelHist)
        self.itemsToShapes = {}
        self.shapesToItems = {}
        self.prevLabelText = ''
        self.LabelToCount = {}

        listLayout = QVBoxLayout()
        listLayout.setContentsMargins(0, 0, 0, 0)

        # Create a widget for using default label
        self.useDefaultLabelCheckbox = QCheckBox(getStr('useDefaultLabel'))
        self.useDefaultLabelCheckbox.setChecked(False)
        self.defaultLabelTextLine = QLineEdit()
        useDefaultLabelQHBoxLayout = QHBoxLayout()
        useDefaultLabelQHBoxLayout.addWidget(self.useDefaultLabelCheckbox)
        useDefaultLabelQHBoxLayout.addWidget(self.defaultLabelTextLine)
        useDefaultLabelContainer = QWidget()
        useDefaultLabelContainer.setLayout(useDefaultLabelQHBoxLayout)

        # Create a widget for edit and diffc button
        self.diffcButton = QCheckBox(getStr('useDifficult'))
        self.diffcButton.setChecked(False)
        self.diffcButton.stateChanged.connect(self.btnstate)
        self.editButton = QToolButton()
        self.editButton.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        # Add some of widgets to listLayout
        listLayout.addWidget(self.editButton)
        listLayout.addWidget(self.diffcButton)
        listLayout.addWidget(useDefaultLabelContainer)

        # Create and add a widget for showing current label items
        self.labelList = QListWidget()
        labelListContainer = QWidget()
        labelListContainer.setLayout(listLayout)
        self.labelList.itemActivated.connect(self.labelSelectionChanged)
        self.labelList.itemSelectionChanged.connect(self.labelSelectionChanged)
        self.labelList.itemDoubleClicked.connect(self.editLabel)
        # Connect to itemChanged to detect checkbox changes.
        self.labelList.itemChanged.connect(self.labelItemChanged)
        listLayout.addWidget(self.labelList)

        # cyw
        self.labelCountList = QListWidget()
        self.labelCountList.itemSelectionChanged.connect(
            self.labelCountSelectionChanged)
        listLayout.addWidget(self.labelCountList)

        self.dock = QDockWidget(getStr('boxLabelText'), self)
        self.dock.setObjectName(getStr('labels'))
        self.dock.setWidget(labelListContainer)

        self.fileListWidget = QListWidget()
        self.fileListWidget.itemDoubleClicked.connect(
            self.fileitemDoubleClicked)
        filelistLayout = QVBoxLayout()
        filelistLayout.setContentsMargins(0, 0, 0, 0)
        filelistLayout.addWidget(self.fileListWidget)
        fileListContainer = QWidget()
        fileListContainer.setLayout(filelistLayout)
        self.filedock = QDockWidget(getStr('fileList'), self)
        self.filedock.setObjectName(getStr('files'))
        self.filedock.setWidget(fileListContainer)

        self.zoomWidget = ZoomWidget()
        self.colorDialog = ColorDialog(parent=self)

        self.canvas = Canvas(parent=self)
        self.canvas.zoomRequest.connect(self.zoomRequest)
        self.canvas.setDrawingShapeToSquare(
            settings.get(SETTING_DRAW_SQUARE, False))

        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(True)
        self.scrollBars = {
            Qt.Vertical: scroll.verticalScrollBar(),
            Qt.Horizontal: scroll.horizontalScrollBar()
        }
        self.scrollArea = scroll
        self.canvas.scrollRequest.connect(self.scrollRequest)

        self.canvas.newShape.connect(self.newShape)
        self.canvas.shapeMoved.connect(self.setDirty)
        self.canvas.selectionChanged.connect(self.shapeSelectionChanged)
        self.canvas.drawingPolygon.connect(self.toggleDrawingSensitive)

        self.setCentralWidget(scroll)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.addDockWidget(Qt.RightDockWidgetArea, self.filedock)
        self.filedock.setFeatures(QDockWidget.DockWidgetFloatable)

        self.dockFeatures = QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetFloatable
        self.dock.setFeatures(self.dock.features() ^ self.dockFeatures)

        # Actions
        action = partial(newAction, self)

        # vic
        self.selected_class_idx = 0
        action_select_target_class_1 = action("target class 1", self.select_target_class_1,
                                              '1', 'new', "target class")

        action_select_target_class_2 = action("target class 2", self.select_target_class_2,
                                              '2', 'new', "target class")

        action_select_target_class_3 = action("target class 3", self.select_target_class_3,
                                              '3', 'new', "target class")

        action_select_target_class_4 = action("target class 4", self.select_target_class_4,
                                              '4', 'new', "target class")

        action_select_target_class_5 = action("target class 5", self.select_target_class_5,
                                              '5', 'new', "target class")

        action_select_target_class_6 = action("target class 6", self.select_target_class_6,
                                              '6', 'new', "target class")

        action_select_target_class_7 = action("target class 7", self.select_target_class_7,
                                              '7', 'new', "target class")

        action_select_target_class_8 = action("target class 8", self.select_target_class_8,
                                              '8', 'new', "target class")

        action_select_target_class_9 = action("target class 9", self.select_target_class_9,
                                              '9', 'new', "target class")

        quit = action(getStr('quit'), self.close,
                      'Ctrl+Q', 'quit', getStr('quitApp'))

        open = action(getStr('openFile'), self.openFile,
                      'Ctrl+O', 'open', getStr('openFileDetail'))

        opendir = action(getStr('openDir'), self.openDirDialog,
                         'Ctrl+u', 'open', getStr('openDir'))

        changeSavedir = action(getStr('changeSaveDir'), self.changeSavedirDialog,
                               'Ctrl+r', 'open', getStr('changeSavedAnnotationDir'))

        openAnnotation = action(getStr('openAnnotation'), self.openAnnotationDialog,
                                'Ctrl+Shift+V', 'open', getStr('openAnnotationDetail'))

        reserveAnnotation = action("reserveAnnotation", self.reserveAnnotation,
                                   'v', 'reserve', "reserveAnnotation")

        reserveAnnotationTracker = action("reserveAnnotationTracker", self.reserveAnnotationTracker,
                                          'b', 'reserve_tracker', "reserveAnnotationTracker")

        reserveAnnotationOnlyUpdate = action("reserveAnnotationOnlyUpdate", self.reserveAnnotationOnlyUpdate,
                                             'n', 'reserve_tracker', "reserveAnnotationOnlyUpdate")

        showLabel = action("showLabel", self.showLabel,
                           'f', 'show_label', "showLabel")

        openNextImg = action(getStr('nextImg'), self.openNextImg,
                             'd', 'next', getStr('nextImgDetail'))

        openPrevImg = action(getStr('prevImg'), self.openPrevImg,
                             'a', 'prev', getStr('prevImgDetail'))

        verify = action(getStr('verifyImg'), self.verifyImg,
                        'space', 'verify', getStr('verifyImgDetail'))

        save = action(getStr('save'), self.saveFile,
                      'Ctrl+S', 'save', getStr('saveDetail'), enabled=True)

        save_format = action('&PascalVOC', self.change_format,
                             'Ctrl+', 'format_voc', getStr('changeSaveFormat'), enabled=True)

        saveAs = action(getStr('saveAs'), self.saveFileAs,
                        'Ctrl+Shift+S', 'save-as', getStr('saveAsDetail'), enabled=False)

        close = action(getStr('closeCur'), self.closeFile,
                       'Ctrl+W', 'close', getStr('closeCurDetail'))

        resetAll = action(getStr('resetAll'), self.resetAll,
                          None, 'resetall', getStr('resetAllDetail'))

        color1 = action(getStr('boxLineColor'), self.chooseColor1,
                        'Ctrl+L', 'color_line', getStr('boxLineColorDetail'))

        createMode = action(getStr('crtBox'), self.setCreateMode,
                            'w', 'new', getStr('crtBoxDetail'), enabled=False)

        editMode = action('&Edit RectBox', self.setEditMode,
                          'Ctrl+E', 'edit', u'Move and edit Boxs', enabled=False)

        # vic
        popupEditDialog = action("popup", self.popupEditDialog,
                                 'q', 'new', "popup")

        create = action(getStr('crtBox'), self.createShape,
                        'w', 'new', getStr('crtBoxDetail'), enabled=False)

        editShape = action("edit", self.editShape,
                           'e', 'new', "edit")

        changeShowEnglish = action("changeShowEnglish", self.changeShowEnglish,
                                   's', 'new', "changeShowEnglish")

        # delete = action(getStr('delBox'), self.deleteSelectedShape,
        #                'Delete', 'delete', getStr('delBoxDetail'), enabled=False)
        delete = action(getStr('delBox'), self.deleteSelectedShape,
                        'c', 'delete', getStr('delBoxDetail'), enabled=True)

        copy = action(getStr('dupBox'), self.copySelectedShape,
                      'Ctrl+D', 'copy', getStr('dupBoxDetail'),
                      enabled=False)

        advancedMode = action(getStr('advancedMode'), self.toggleAdvancedMode,
                              'Ctrl+Shift+A', 'expert', getStr(
                                  'advancedModeDetail'),
                              checkable=True)

        hideAll = action('&Hide RectBox', partial(self.togglePolygons, False),
                         'Ctrl+H', 'hide', getStr('hideAllBoxDetail'),
                         enabled=False)
        showAll = action('&Show RectBox', partial(self.togglePolygons, True),
                         'Ctrl+A', 'hide', getStr('showAllBoxDetail'),
                         enabled=False)

        help = action(getStr('tutorialDetail'), self.showTutorialDialog,
                      None, 'help', getStr('tutorialDetail'))
        showInfo = action(getStr('info'), self.showInfoDialog,
                          None, 'help', getStr('info'))

        zoom = QWidgetAction(self)
        zoom.setDefaultWidget(self.zoomWidget)
        self.zoomWidget.setWhatsThis(
            u"Zoom in or out of the image. Also accessible with"
            " %s and %s from the canvas." % (fmtShortcut("Ctrl+[-+]"),
                                             fmtShortcut("Ctrl+Wheel")))
        self.zoomWidget.setEnabled(False)

        zoomIn = action(getStr('zoomin'), partial(self.addZoom, 10),
                        'Ctrl++', 'zoom-in', getStr('zoominDetail'), enabled=False)
        zoomOut = action(getStr('zoomout'), partial(self.addZoom, -10),
                         'Ctrl+-', 'zoom-out', getStr('zoomoutDetail'), enabled=False)
        zoomOrg = action(getStr('originalsize'), partial(self.setZoom, 100),
                         'Ctrl+=', 'zoom', getStr('originalsizeDetail'), enabled=False)
        fitWindow = action(getStr('fitWin'), self.setFitWindow,
                           'Ctrl+F', 'fit-window', getStr('fitWinDetail'),
                           checkable=True, enabled=False)
        fitWidth = action(getStr('fitWidth'), self.setFitWidth,
                          'Ctrl+Shift+F', 'fit-width', getStr(
                              'fitWidthDetail'),
                          checkable=True, enabled=False)
        # Group zoom controls into a list for easier toggling.
        zoomActions = (self.zoomWidget, zoomIn, zoomOut,
                       zoomOrg, fitWindow, fitWidth)
        self.zoomMode = self.MANUAL_ZOOM
        self.scalers = {
            self.FIT_WINDOW: self.scaleFitWindow,
            self.FIT_WIDTH: self.scaleFitWidth,
            # Set to one to scale to 100% when loading files.
            self.MANUAL_ZOOM: lambda: 1,
        }

        edit = action(getStr('editLabel'), self.editLabel,
                      'r', 'edit', getStr('editLabelDetail'),
                      enabled=False)
        self.editButton.setDefaultAction(edit)

        update_label = action('updateCurLabel', self.updateLabel,
                              't',  'edit', 'update_label',
                              enabled=True)

        shapeLineColor = action(getStr('shapeLineColor'), self.chshapeLineColor,
                                icon='color_line', tip=getStr('shapeLineColorDetail'),
                                enabled=False)
        shapeFillColor = action(getStr('shapeFillColor'), self.chshapeFillColor,
                                icon='color', tip=getStr('shapeFillColorDetail'),
                                enabled=False)

        labels = self.dock.toggleViewAction()
        labels.setText(getStr('showHide'))
        labels.setShortcut('Ctrl+Shift+L')

        # Lavel list context menu.
        labelMenu = QMenu()
        addActions(labelMenu, (edit, delete))
        self.labelList.setContextMenuPolicy(Qt.CustomContextMenu)
        self.labelList.customContextMenuRequested.connect(
            self.popLabelListMenu)

        # Draw squares/rectangles
        self.drawSquaresOption = QAction('Draw Squares', self)
        self.drawSquaresOption.setShortcut('Ctrl+Shift+R')
        self.drawSquaresOption.setCheckable(True)
        self.drawSquaresOption.setChecked(
            settings.get(SETTING_DRAW_SQUARE, False))
        self.drawSquaresOption.triggered.connect(self.toogleDrawSquare)

        # Store actions for further handling.
        self.actions = struct(save=save, save_format=save_format, saveAs=saveAs, open=open, close=close, resetAll=resetAll,
                              lineColor=color1, create=create, delete=delete, edit=edit, copy=copy,
                              createMode=createMode, editMode=editMode, advancedMode=advancedMode,
                              shapeLineColor=shapeLineColor, shapeFillColor=shapeFillColor,
                              zoom=zoom, zoomIn=zoomIn, zoomOut=zoomOut, zoomOrg=zoomOrg,
                              fitWindow=fitWindow, fitWidth=fitWidth,
                              zoomActions=zoomActions,

                              action_select_target_class_1=action_select_target_class_1,
                              action_select_target_class_2=action_select_target_class_2,
                              action_select_target_class_3=action_select_target_class_3,
                              action_select_target_class_4=action_select_target_class_4,
                              action_select_target_class_5=action_select_target_class_5,
                              action_select_target_class_6=action_select_target_class_6,
                              action_select_target_class_7=action_select_target_class_7,
                              action_select_target_class_8=action_select_target_class_8,
                              action_select_target_class_9=action_select_target_class_9,

                              reserveAnnotationOnlyUpdate=reserveAnnotationOnlyUpdate,

                              update_label=update_label,

                              popupEditDialog=popupEditDialog,
                              editShape=editShape,
                              changeShowEnglish=changeShowEnglish,

                              reserveAnnotation=reserveAnnotation,
                              reserveAnnotationTracker=reserveAnnotationTracker,
                              showLabel=showLabel,

                              fileMenuActions=(
                                  open, opendir, save, saveAs, close, resetAll, quit),
                              beginner=(), advanced=(),
                              editMenu=(edit, copy, delete,
                                        update_label,

                                        None, color1, self.drawSquaresOption,
                                        action_select_target_class_1,
                                        action_select_target_class_2,
                                        action_select_target_class_3,
                                        action_select_target_class_4,
                                        action_select_target_class_5,
                                        action_select_target_class_6,
                                        action_select_target_class_7,
                                        action_select_target_class_8,
                                        action_select_target_class_9,

                                        reserveAnnotationOnlyUpdate,

                                        popupEditDialog,
                                        editShape,
                                        changeShowEnglish,

                                        reserveAnnotation,
                                        reserveAnnotationTracker,
                                        showLabel,
                                        ),
                              beginnerContext=(create, edit, copy, delete, update_label,
                                               popupEditDialog,
                                               editShape
                                               ),
                              advancedContext=(createMode, editMode, edit, copy, update_label,
                                               delete, shapeLineColor, shapeFillColor,
                                               ),
                              onLoadActive=(
                                  close, create, createMode, editMode),
                              onShapesPresent=(saveAs, hideAll, showAll),
                              )

        self.menus = struct(
            file=self.menu('&File'),
            edit=self.menu('&Edit'),
            view=self.menu('&View'),
            help=self.menu('&Help'),
            recentFiles=QMenu('Open &Recent'),
            labelList=labelMenu)

        # Auto saving : Enable auto saving if pressing next
        self.autoSaving = QAction(getStr('autoSaveMode'), self)
        self.autoSaving.setCheckable(True)
        self.autoSaving.setChecked(settings.get(SETTING_AUTO_SAVE, True))
        # Sync single class mode from PR#106
        self.singleClassMode = QAction(getStr('singleClsMode'), self)
        self.singleClassMode.setShortcut("Alt+s")
        self.singleClassMode.setCheckable(True)
        self.singleClassMode.setChecked(
            settings.get(SETTING_SINGLE_CLASS, False))
        self.lastLabel = None
        # Add option to enable/disable labels being displayed at the top of bounding boxes
        self.displayLabelOption = QAction(getStr('displayLabel'), self)
        self.displayLabelOption.setShortcut("Ctrl+Shift+P")
        self.displayLabelOption.setCheckable(True)
        self.displayLabelOption.setChecked(
            settings.get(SETTING_PAINT_LABEL, True))
        self.displayLabelOption.triggered.connect(self.togglePaintLabelsOption)

        addActions(self.menus.file,
                   (open, opendir, changeSavedir, openAnnotation, self.menus.recentFiles, save, save_format, saveAs, close, resetAll, quit))
        addActions(self.menus.help, (help, showInfo))
        addActions(self.menus.view, (
            self.autoSaving,
            self.singleClassMode,
            self.displayLabelOption,
            labels, advancedMode, None,
            hideAll, showAll, None,
            zoomIn, zoomOut, zoomOrg, None,
            fitWindow, fitWidth))

        self.menus.file.aboutToShow.connect(self.updateFileMenu)

        # Custom context menu for the canvas widget:
        addActions(self.canvas.menus[0], self.actions.beginnerContext)
        addActions(self.canvas.menus[1], (
            action('&Copy here', self.copyShape),
            action('&Move here', self.moveShape)))

        self.tools = self.toolbar('Tools')
        self.actions.beginner = (
            open, opendir, changeSavedir, openNextImg, openPrevImg, verify, save, save_format, None, create, copy, delete, None,
            zoomIn, zoom, zoomOut, fitWindow, fitWidth,
        )

        self.actions.advanced = (
            open, opendir, changeSavedir, openNextImg, openPrevImg, save, save_format, None,
            createMode, editMode, None,
            hideAll, showAll,
        )

        self.statusBar().showMessage('%s started.' % __appname__)
        self.statusBar().show()

        # Application state.
        self.image = QImage()
        self.filePath = ustr(defaultFilename)
        self.recentFiles = []
        self.maxRecent = 7
        self.lineColor = None
        self.fillColor = None
        self.zoom_level = 100
        self.fit_window = False
        # Add Chris
        self.difficult = False

        # Fix the compatible issue for qt4 and qt5. Convert the QStringList to python list
        if settings.get(SETTING_RECENT_FILES):
            if have_qstring():
                recentFileQStringList = settings.get(SETTING_RECENT_FILES)
                self.recentFiles = [ustr(i) for i in recentFileQStringList]
            else:
                self.recentFiles = recentFileQStringList = settings.get(
                    SETTING_RECENT_FILES)

        size = settings.get(SETTING_WIN_SIZE, QSize(600, 500))
        position = QPoint(0, 0)
        saved_position = settings.get(SETTING_WIN_POSE, position)
        # Fix the multiple monitors issue
        for i in range(QApplication.desktop().screenCount()):
            if QApplication.desktop().availableGeometry(i).contains(saved_position):
                position = saved_position
                break
        self.resize(size)
        self.move(position)
        saveDir = ustr(settings.get(SETTING_SAVE_DIR, None))
        self.lastOpenDir = ustr(settings.get(SETTING_LAST_OPEN_DIR, None))
        if self.defaultSaveDir is None and saveDir is not None and os.path.exists(saveDir):
            self.defaultSaveDir = saveDir
            self.statusBar().showMessage('%s started. Annotation will be saved to %s' %
                                         (__appname__, self.defaultSaveDir))
            self.statusBar().show()

        self.restoreState(settings.get(SETTING_WIN_STATE, QByteArray()))
        Shape.line_color = self.lineColor = QColor(
            settings.get(SETTING_LINE_COLOR, DEFAULT_LINE_COLOR))
        Shape.fill_color = self.fillColor = QColor(
            settings.get(SETTING_FILL_COLOR, DEFAULT_FILL_COLOR))
        Shape.drag_color = self.dragColor = QColor(
            settings.get(SETTING_DRAG_COLOR, DEFAULT_DRAG_COLOR))
        self.canvas.setDrawingColor(self.lineColor)
        self.canvas.setDraggingColor(self.dragColor)
        # Add chris
        Shape.difficult = self.difficult

        def xbool(x):
            if isinstance(x, QVariant):
                return x.toBool()
            return bool(x)

        if xbool(settings.get(SETTING_ADVANCE_MODE, False)):
            self.actions.advancedMode.setChecked(True)
            self.toggleAdvancedMode()

        # Populate the File menu dynamically.
        self.updateFileMenu()

        # Since loading the file may take some time, make sure it runs in the background.
        if self.filePath and os.path.isdir(self.filePath):
            self.queueEvent(partial(self.importDirImages, self.filePath or ""))
        elif self.filePath:
            self.queueEvent(partial(self.loadFile, self.filePath or ""))

        # Callbacks:
        self.zoomWidget.valueChanged.connect(self.paintCanvas)

        self.populateModeActions()

        # Display cursor coordinates at the right of status bar
        self.labelCoordinates = QLabel('')
        self.statusBar().addPermanentWidget(self.labelCoordinates)

        # Open Dir if deafult file
        if self.filePath and os.path.isdir(self.filePath):
            self.openDirDialog(dirpath=self.filePath)

        # vic Init
        if cfg.DEBUG:
            if os.path.exists(targetDirPath):
                self.importDirImages(targetDirPath)
                self.setFitWindow()

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Control:
            self.canvas.setDrawingShapeToSquare(False)
        if event.key() == Qt.Key_X:
            self.deleteCurrentImg()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Control:
            # Draw rectangle if Ctrl is pressed
            self.canvas.setDrawingShapeToSquare(True)

    ## Support Functions ##
    def set_format(self, save_format):
        if save_format == FORMAT_PASCALVOC:
            self.actions.save_format.setText(FORMAT_PASCALVOC)
            self.actions.save_format.setIcon(newIcon("format_voc"))
            self.usingPascalVocFormat = True
            self.usingYoloFormat = False
            LabelFile.suffix = XML_EXT

        elif save_format == FORMAT_YOLO:
            self.actions.save_format.setText(FORMAT_YOLO)
            self.actions.save_format.setIcon(newIcon("format_yolo"))
            self.usingPascalVocFormat = False
            self.usingYoloFormat = True
            LabelFile.suffix = TXT_EXT

    def change_format(self):
        if self.usingPascalVocFormat:
            self.set_format(FORMAT_YOLO)
        elif self.usingYoloFormat:
            self.set_format(FORMAT_PASCALVOC)

    def noShapes(self):
        return not self.itemsToShapes

    def toggleAdvancedMode(self, value=True):
        self._beginner = not value
        self.canvas.setEditing(True)
        self.populateModeActions()
        self.editButton.setVisible(not value)
        if value:
            self.actions.createMode.setEnabled(True)
            self.actions.editMode.setEnabled(False)
            self.dock.setFeatures(self.dock.features() | self.dockFeatures)
        else:
            self.dock.setFeatures(self.dock.features() ^ self.dockFeatures)

    def populateModeActions(self):
        if self.beginner():
            tool, menu = self.actions.beginner, self.actions.beginnerContext
        else:
            tool, menu = self.actions.advanced, self.actions.advancedContext
        self.tools.clear()
        addActions(self.tools, tool)
        self.canvas.menus[0].clear()
        addActions(self.canvas.menus[0], menu)
        self.menus.edit.clear()
        actions = (self.actions.create,) if self.beginner()\
            else (self.actions.createMode, self.actions.editMode)
        addActions(self.menus.edit, actions + self.actions.editMenu)

    def setBeginner(self):
        self.tools.clear()
        addActions(self.tools, self.actions.beginner)

    def setAdvanced(self):
        self.tools.clear()
        addActions(self.tools, self.actions.advanced)

    def setDirty(self):
        self.dirty = True
        self.actions.save.setEnabled(True)

    def setClean(self):
        self.dirty = False
        self.actions.save.setEnabled(False)
        self.actions.create.setEnabled(True)

    def toggleActions(self, value=True):
        """Enable/Disable widgets which depend on an opened image."""
        for z in self.actions.zoomActions:
            z.setEnabled(value)
        for action in self.actions.onLoadActive:
            action.setEnabled(value)

    def queueEvent(self, function):
        QTimer.singleShot(0, function)

    def status(self, message, delay=5000):
        self.statusBar().showMessage(message, delay)

    def resetState(self):
        self.itemsToShapes.clear()
        self.shapesToItems.clear()
        self.labelList.clear()
        self.labelCountList.clear()
        self.LabelToCount.clear()
        self.filePath = None
        #self.previousImageData = None
        if self.imageData is not None:
            self.previousImageData = self.imageData
        self.imageData = None
        self.labelFile = None
        self.canvas.resetState()
        self.labelCoordinates.clear()

    def currentItem(self):
        items = self.labelList.selectedItems()
        if items:
            return items[0]
        return None

    def addRecentFile(self, filePath):
        if filePath in self.recentFiles:
            self.recentFiles.remove(filePath)
        elif len(self.recentFiles) >= self.maxRecent:
            self.recentFiles.pop()
        self.recentFiles.insert(0, filePath)

    def beginner(self):
        return self._beginner

    def advanced(self):
        return not self.beginner()

    def getAvailableScreencastViewer(self):
        osName = platform.system()

        if osName == 'Windows':
            return ['C:\\Program Files\\Internet Explorer\\iexplore.exe']
        elif osName == 'Linux':
            return ['xdg-open']
        elif osName == 'Darwin':
            return ['open', '-a', 'Safari']

    ## Callbacks ##
    def showTutorialDialog(self):
        subprocess.Popen(self.screencastViewer + [self.screencast])

    def showInfoDialog(self):
        msg = u'Name:{0} \nApp Version:{1} \n{2} '.format(
            __appname__, __version__, sys.version_info)
        QMessageBox.information(self, u'Information', msg)

    def popupEditDialog(self):
        assert self.beginner()
        self.callEditDialog = not self.callEditDialog
        print("画框模式生效，弹出编辑框框:", self.callEditDialog)
        # self.canvas.setDragging(True)
        # self.actions.dragShape.setEnabled(False)

    def createShape(self):
        print("画框模式")
        assert self.beginner()
        self.canvas.setEditing(False)
        self.actions.create.setEnabled(False)

    def editShape(self):
        print("编辑模式，支持编辑标签，选择多个框，移动框")
        assert self.beginner()
        self.canvas.setEditing(True)
        # self.actions.editShape.setEnabled(False)

    def changeShowEnglish(self):
        self.canvas.changeShowEnglish()

    def toggleDrawingSensitive(self, drawing=True):
        """In the middle of drawing, toggling between modes should be disabled."""
        self.actions.editMode.setEnabled(not drawing)
        if not drawing and self.beginner():
            # Cancel creation.
            #print('Cancel creation.')
            self.canvas.setEditing(True)
            self.canvas.restoreCursor()
            self.actions.create.setEnabled(True)

    def toggleDrawMode(self, edit=True):
        self.canvas.setEditing(edit)
        self.actions.createMode.setEnabled(edit)
        self.actions.editMode.setEnabled(not edit)

    def setCreateMode(self):
        assert self.advanced()
        self.toggleDrawMode(False)

    def setEditMode(self):
        assert self.advanced()
        self.toggleDrawMode(True)
        self.labelSelectionChanged()

    def updateFileMenu(self):
        currFilePath = self.filePath

        def exists(filename):
            return os.path.exists(filename)
        menu = self.menus.recentFiles
        menu.clear()
        files = [f for f in self.recentFiles if f !=
                 currFilePath and exists(f)]
        for i, f in enumerate(files):
            icon = newIcon('labels')
            action = QAction(
                icon, '&%d %s' % (i + 1, QFileInfo(f).fileName()), self)
            action.triggered.connect(partial(self.loadRecent, f))
            menu.addAction(action)

    def popLabelListMenu(self, point):
        self.menus.labelList.exec_(self.labelList.mapToGlobal(point))

    def add_label_with_chinese(self, text, text_ch=None):
        self.labelHist.append(text)
        if cfg.INCLUDE_CHINSES:
            if not text_ch:
                text_ch = pinyin_2_chinese(text)
            self.labelHistChinese.append(text_ch)
            self.labelHistPinYin2Chinese[text] = text_ch

    def editLabel(self):
        print("editLabel")
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:
            return
        text = self.labelDialog.popUp(item.text())
        if text is not None:
            # vic
            if cfg.INCLUDE_CHINSES:
                text = self.adjust_editdialog_text_use_pinyin(text)
            shape = self.itemsToShapes[item]
            if cfg.INCLUDE_CHINSES:
                shape.label_ch = self.labelHistPinYin2Chinese[text]
            item.setText(text)
            item.setBackground(generateColorByText(text))
            self.setDirty()

    def updateLabel(self):
        print("updateLabel")
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:
            return
        text = self.labelHist[self.selected_class_idx]
        if text is not None:
            # vic
            if cfg.INCLUDE_CHINSES:
                text = self.adjust_editdialog_text_use_pinyin(text)
            shape = self.itemsToShapes[item]
            if cfg.INCLUDE_CHINSES:
                shape.label_ch = self.labelHistPinYin2Chinese[text]
            item.setText(text)
            item.setBackground(generateColorByText(text))
            self.setDirty()

    # Tzutalin 20160906 : Add file list and dock to move faster
    def fileitemDoubleClicked(self, item=None):
        im_path = self.im_name_path_dict[ustr(item.text())]
        currIndex = self.mImgList.index(im_path)
        if currIndex < len(self.mImgList):
            filename = self.mImgList[currIndex]
            if filename:
                self.loadFile(filename)

    # Add chris
    def btnstate(self, item=None):
        """ Function to handle difficult examples
        Update on each object """
        if not self.canvas.editing():
            return

        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count()-1)

        difficult = self.diffcButton.isChecked()

        try:
            shape = self.itemsToShapes[item]
        except:
            pass
        # Checked and Update
        try:
            if difficult != shape.difficult:
                shape.difficult = difficult
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(
                    shape, item.checkState() == Qt.Checked)
        except:
            pass

    # React to canvas signals.
    def shapeSelectionChanged(self, selected=False):
        if self._noSelectionSlot:
            self._noSelectionSlot = False
        else:
            shape = self.canvas.selectedShape
            if shape:
                self.shapesToItems[shape].setSelected(True)
            else:
                self.labelList.clearSelection()
        self.labelCountList.clearSelection()  # cyw
        self.actions.delete.setEnabled(selected)
        self.actions.copy.setEnabled(selected)
        self.actions.edit.setEnabled(selected)
        self.actions.shapeLineColor.setEnabled(selected)
        self.actions.shapeFillColor.setEnabled(selected)

    def addLabel(self, shape):
        shape.paintLabel = self.displayLabelOption.isChecked()
        item = HashableQListWidgetItem(shape.label)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        item.setBackground(generateColorByText(shape.label))
        self.itemsToShapes[item] = shape
        self.shapesToItems[shape] = item
        self.labelList.addItem(item)
        # cyw
        self.labelList.sortItems()
        label = shape.label
        find = False
        itemTotal = None
        for i in range(self.labelCountList.count()):
            item = self.labelCountList.item(i)
            text = item.text()
            num_idx = text.rfind(" ")
            itemLabel = text[:num_idx]
            itemCount = text[num_idx+1:]
            #itemLabel, itemCount = item.text().split(" ")
            if itemLabel == label:
                itemCount = int(itemCount) + 1
                item.setText(itemLabel + " " + str(itemCount))
                self.LabelToCount[itemLabel] = itemCount
                find = True
            elif itemLabel == "_Total_":
                itemTotal = item
        if not find:
            item = HashableQListWidgetItem(label + " 1")
            item.setBackground(generateColorByText(label))
            self.LabelToCount[label] = 1
            self.labelCountList.addItem(item)
        if itemTotal:
            itemLabel, itemCount = itemTotal.text().split(" ")
            itemCount = int(itemCount) + 1
            itemTotal.setText(itemLabel + " " + str(itemCount))
        else:
            itemTotal = HashableQListWidgetItem("_Total_ 1")
            itemTotal.setBackground(generateColorByText("_Total_"))
            self.labelCountList.addItem(itemTotal)
        self.labelCountList.sortItems()

        for action in self.actions.onShapesPresent:
            action.setEnabled(True)

    def removeLabel(self, shapes):
        if type(shapes) == list:
            pass
        else:
            shapes = [shapes]
        for shape in shapes:
            if shape is None:
                # print('rm empty label')
                continue
            item = self.shapesToItems[shape]
            self.labelList.takeItem(self.labelList.row(item))
            del self.shapesToItems[shape]
            del self.itemsToShapes[item]
            # cyw
            self.labelList.sortItems()
            label = shape.label
            for i in range(self.labelCountList.count()):
                item = self.labelCountList.item(i)
                itemLabel, itemCount = item.text().split(" ")
                if itemLabel == label:
                    itemCount = int(itemCount) - 1
                    if itemCount == 0:
                        self.labelCountList.takeItem(
                            self.labelCountList.row(item))
                        del self.LabelToCount[itemLabel]
                    else:
                        item.setText(itemLabel + " " + str(itemCount))
                        self.LabelToCount[itemLabel] = itemCount
                    break
            for i in range(self.labelCountList.count()):
                item = self.labelCountList.item(i)
                itemLabel, itemCount = item.text().split(" ")
                if itemLabel == "_Total_":
                    itemCount = int(itemCount) - 1
                    item.setText(itemLabel + " " + str(itemCount))
                    break
            self.labelCountList.sortItems()

    def remove_special_character_in_str(self, label):
        # remove special charactor in UTF-8 with BOM format to UTF-8
        remove_extra_character = False
        if label:
            label_strip = label.strip('\ufeff').strip('\xef\xbb\xbf')
        if label_strip != label:
            remove_extra_character = True
        return label_strip, remove_extra_character

    def loadLabels(self, shapes):
        s = []
        for label, points, line_color, fill_color, difficult,  label_ch in shapes:
            # vic
            label, remove_extra_character = self.remove_special_character_in_str(
                label)
            if label_ch is not None:
                label_ch, _ = self.remove_special_character_in_str(label_ch)
            if remove_extra_character:
                self.dirty = True
            shape = Shape(label=label, label_ch=label_ch)
            for x, y in points:
                # Ensure the labels are within the bounds of the image. If not, fix them.
                x, y, snapped = self.canvas.snapPointToCanvas(x, y)
                if snapped:
                    self.setDirty()

                shape.addPoint(QPointF(x, y))
            shape.difficult = difficult
            shape.close()
            s.append(shape)

            if line_color:
                shape.line_color = QColor(*line_color)
            else:
                shape.line_color = generateColorByText(label)

            if fill_color:
                shape.fill_color = QColor(*fill_color)
            else:
                shape.fill_color = generateColorByText(label)

            self.addLabel(shape)

        self.canvas.loadShapes(s)

    def saveLabels(self, annotationFilePath):
        annotationFilePath = ustr(annotationFilePath)
        if self.labelFile is None:
            self.labelFile = LabelFile()
            self.labelFile.verified = self.canvas.verified

        def format_shape(s):
            return dict(label=s.label, label_ch=s.label_ch,
                        line_color=s.line_color.getRgb(),
                        fill_color=s.fill_color.getRgb(),
                        points=[(p.x(), p.y()) for p in s.points],
                        # add chris
                        difficult=s.difficult)

        shapes = [format_shape(shape) for shape in self.canvas.shapes]
        # Can add differrent annotation formats here
        try:
            if self.usingPascalVocFormat is True:
                if annotationFilePath[-4:].lower() != ".xml":
                    annotationFilePath += XML_EXT
                self.labelFile.savePascalVocFormat(annotationFilePath, shapes, self.filePath, self.imageData,
                                                   self.lineColor.getRgb(), self.fillColor.getRgb(), read_exif=self.read_exif)
            elif self.usingYoloFormat is True:
                if annotationFilePath[-4:].lower() != ".txt":
                    annotationFilePath += TXT_EXT
                self.labelFile.saveYoloFormat(annotationFilePath, shapes, self.filePath, self.imageData, self.labelHist,
                                              self.lineColor.getRgb(), self.fillColor.getRgb(), read_exif=self.read_exif)
            else:
                assert False, 'no valid annotation format'
                #self.labelFile.save(annotationFilePath, shapes, self.filePath, self.imageData,
                #                    self.lineColor.getRgb(), self.fillColor.getRgb())
            print(
                'Image:{0} -> Annotation:{1}'.format(self.filePath, annotationFilePath))
            return True
        except LabelFileError as e:
            self.errorMessage(u'Error saving label data', u'<b>%s</b>' % e)
            return False

    def copySelectedShape(self):
        self.addLabel(self.canvas.copySelectedShape())
        # fix copy and delete
        self.shapeSelectionChanged(True)

    def labelSelectionChanged(self):
        item = self.currentItem()
        if item and self.canvas.editing():
            self._noSelectionSlot = True
            self.canvas.selectShape(self.itemsToShapes[item])
            shape = self.itemsToShapes[item]
            # Add Chris
            self.diffcButton.setChecked(shape.difficult)
        self.labelCountList.clearSelection()  # cyw

    def labelItemChanged(self, item):
        shape = self.itemsToShapes[item]
        label = item.text()
        # vic
        old_label = shape.label
        if label != shape.label:
            text = item.text()
            if cfg.INCLUDE_CHINSES:
                text = self.adjust_editdialog_text_use_pinyin(text)
            shape.label = text
            if cfg.INCLUDE_CHINSES:
                text_ch = self.labelHistPinYin2Chinese[text]
                shape.label_ch = text_ch

            shape.line_color = generateColorByText(shape.label)
            self.setDirty()
        else:  # User probably changed item visibility
            self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)

        # self.labelCountList.clearSelection()  # cyw
        # vic
        find = False
        itemTotal = None
        need_remove_item = None
        need_remove_label = None
        for i in range(self.labelCountList.count()):
            item = self.labelCountList.item(i)
            if not item:
                continue
            text = item.text()
            num_idx = text.rfind(" ")
            itemLabel = text[:num_idx]
            itemCount = text[num_idx+1:]
            #itemLabel, itemCount = item.text().split(" ")
            if itemLabel == old_label:
                itemCount = int(itemCount) - 1
                if itemCount == 0:
                    need_remove_item = item
                    need_remove_label = itemLabel

                item.setText(itemLabel + " " + str(itemCount))
                self.LabelToCount[itemLabel] = itemCount
            if itemLabel == label:
                itemCount = int(itemCount) + 1
                item.setText(itemLabel + " " + str(itemCount))
                self.LabelToCount[itemLabel] = itemCount
                find = True
            elif itemLabel == "_Total_":
                itemTotal = item

        if not find:
            item = HashableQListWidgetItem(label + " 1")
            item.setBackground(generateColorByText(label))
            self.LabelToCount[label] = 1
            self.labelCountList.addItem(item)
        if itemTotal:
            itemLabel, itemCount = itemTotal.text().split(" ")
            itemCount = int(itemCount)
            itemTotal.setText(itemLabel + " " + str(itemCount))
        else:
            itemTotal = HashableQListWidgetItem("_Total_ 1")
            itemTotal.setBackground(generateColorByText("_Total_"))
            self.labelCountList.addItem(itemTotal)

        # if need_remove_item:
        #    self.labelCountList.takeItem(self.labelCountList.row(need_remove_item))
        #    del self.LabelToCount[need_remove_label]
        self.labelCountList.sortItems()

    def labelCountSelectionChanged(self):
        items = self.labelCountList.selectedItems()
        if items:
            item = items[0]
            if self.canvas.editing():
                text = item.text()
                label = text.split(" ")[0]
                for shape in self.canvas.shapes:
                    if label == "_Total_":
                        shape.ischecking = True
                    else:
                        if shape.label == label:
                            shape.ischecking = True
                        else:
                            shape.ischecking = False
        else:
            for shape in self.canvas.shapes:
                shape.ischecking = False
        self.canvas.update()

    def check_character_is_chinese(self, _char):
        if '\u4e00' <= _char <= '\u9fa5':
            return True
        return False

    def adjust_editdialog_text_use_pinyin(self, text):
        has_chinese = False
        if text is None:
            text = "请输入标签"
        for _char in text:
            if self.check_character_is_chinese(_char):
                has_chinese = True
                if text in self.labelHistChinese:
                    idx = self.labelHistChinese.index(text)
                    text = self.labelHist[idx]
                    break
                else:
                    text_pinyin = pinyin(text)
                    if text_pinyin in self.labelHist:
                        idx = self.labelHist.index(text_pinyin)
                        self.labelHistChinese[idx] = text
                        self.labelHistPinYin2Chinese[text_pinyin] = text
                        text = text_pinyin
                        break
                    else:
                        self.labelHist.append(text_pinyin)
                        self.labelHistChinese.append(text)
                        self.labelHistPinYin2Chinese[text_pinyin] = text
                        text = text_pinyin
                        break
        if not has_chinese:
            if text not in self.labelHist:
                text_ch = pinyin_2_chinese(text)
                self.labelHist.append(text)
                self.labelHistChinese.append(text_ch)
                self.labelHistPinYin2Chinese[text] = text_ch
        return text

    # Callback functions:
    def newShape(self):
        """Pop-up and give focus to the label editor.

        position MUST be in global coordinates.
        """
        if not self.useDefaultLabelCheckbox.isChecked() or not self.defaultLabelTextLine.text():
            # if len(self.labelHist) > 0:
            #    self.labelDialog = LabelDialog(
            #        parent=self, listItem=self.labelHist)

            # Sync single class mode from PR#106
            if self.singleClassMode.isChecked() and self.lastLabel:
                text = self.lastLabel
            else:
                if 0 <= self.selected_class_idx < len(self.labelHist):
                    text = self.labelHist[self.selected_class_idx]
                else:
                    if self.prevLabelText:
                        text = self.prevLabelText
                    else:
                        text = "请输入标签"
                # vic
                if self.callEditDialog:
                    text = self.labelDialog.popUp(text=self.prevLabelText)

                if cfg.INCLUDE_CHINSES:
                    text = self.adjust_editdialog_text_use_pinyin(text)

                self.lastLabel = text
        else:
            text = self.defaultLabelTextLine.text()

        # Add Chris
        self.diffcButton.setChecked(False)
        if text is not None:
            # vic
            if cfg.INCLUDE_CHINSES:
                text = self.adjust_editdialog_text_use_pinyin(text)
                self.prevLabelText = self.labelHistPinYin2Chinese[text]
            else:
                self.prevLabelText = text

            generate_color = generateColorByText(text)

            if text in self.labelHistPinYin2Chinese:
                shape = self.canvas.setLastLabel(
                    text, generate_color, generate_color, text_ch=self.labelHistPinYin2Chinese[text])
            else:
                shape = self.canvas.setLastLabel(
                    text, generate_color, generate_color)

            self.addLabel(shape)
            if self.beginner():  # Switch to edit mode.
                # self.canvas.setEditing(True)
                self.actions.create.setEnabled(True)
            else:
                self.actions.editMode.setEnabled(True)
            self.setDirty()
        else:
            # self.canvas.undoLastLine()
            self.canvas.resetAllLines()

    def scrollRequest(self, delta, orientation):
        units = - delta / (8 * 15)
        bar = self.scrollBars[orientation]
        bar.setValue(bar.value() + bar.singleStep() * units)

    def setZoom(self, value):
        self.actions.fitWidth.setChecked(False)
        self.actions.fitWindow.setChecked(False)
        self.zoomMode = self.MANUAL_ZOOM
        self.zoomWidget.setValue(value)

    def addZoom(self, increment=10):
        self.setZoom(self.zoomWidget.value() + increment)

    def zoomRequest(self, delta):
        # get the current scrollbar positions
        # calculate the percentages ~ coordinates
        h_bar = self.scrollBars[Qt.Horizontal]
        v_bar = self.scrollBars[Qt.Vertical]

        # get the current maximum, to know the difference after zooming
        h_bar_max = h_bar.maximum()
        v_bar_max = v_bar.maximum()

        # get the cursor position and canvas size
        # calculate the desired movement from 0 to 1
        # where 0 = move left
        #       1 = move right
        # up and down analogous
        cursor = QCursor()
        pos = cursor.pos()
        relative_pos = QWidget.mapFromGlobal(self, pos)

        cursor_x = relative_pos.x()
        cursor_y = relative_pos.y()

        w = self.scrollArea.width()
        h = self.scrollArea.height()

        # the scaling from 0 to 1 has some padding
        # you don't have to hit the very leftmost pixel for a maximum-left movement
        margin = 0.1
        move_x = (cursor_x - margin * w) / (w - 2 * margin * w)
        move_y = (cursor_y - margin * h) / (h - 2 * margin * h)

        # clamp the values from 0 to 1
        move_x = min(max(move_x, 0), 1)
        move_y = min(max(move_y, 0), 1)

        # zoom in
        units = delta / (8 * 15)
        scale = 10
        self.addZoom(scale * units)

        # get the difference in scrollbar values
        # this is how far we can move
        d_h_bar_max = h_bar.maximum() - h_bar_max
        d_v_bar_max = v_bar.maximum() - v_bar_max

        # get the new scrollbar values
        new_h_bar_value = h_bar.value() + move_x * d_h_bar_max
        new_v_bar_value = v_bar.value() + move_y * d_v_bar_max

        h_bar.setValue(new_h_bar_value)
        v_bar.setValue(new_v_bar_value)

    def setFitWindow(self, value=True):
        if value:
            self.actions.fitWidth.setChecked(False)
        self.zoomMode = self.FIT_WINDOW if value else self.MANUAL_ZOOM
        self.adjustScale()

    def setFitWidth(self, value=True):
        if value:
            self.actions.fitWindow.setChecked(False)
        self.zoomMode = self.FIT_WIDTH if value else self.MANUAL_ZOOM
        self.adjustScale()

    def togglePolygons(self, value):
        for item, shape in self.itemsToShapes.items():
            item.setCheckState(Qt.Checked if value else Qt.Unchecked)

    def read_exif(self, image, unicodeFilePath):
            try:
                reader = exif_Image(unicodeFilePath)
                transform = QTransform()
                if reader.has_exif:
                    pass

                    """
                    QT
                    rotation of the item in degrees clockwise
                    """
                    if reader.orientation == 1:
                        pass
                    elif reader.orientation == 2:
                        image = image.mirrored(horizontal=True, vertical=False)
                    elif reader.orientation == 3:
                        transform.rotate(180.0)
                        image = image.transformed(transform)
                    elif reader.orientation == 4:
                        image = image.mirrored(horizontal=False, vertical=True)
                    elif reader.orientation == 5:
                        transform.rotate(90.0)
                        image = image.transformed(transform)
                        image = image.mirrored(horizontal=True, vertical=False)
                    elif reader.orientation == 6:
                        transform.rotate(90)
                        image = image.transformed(transform)
                    elif reader.orientation == 7:
                        transform.rotate(-90.0)
                        image = image.mirrored(horizontal=True, vertical=False)
                        image = image.transformed(transform)
                    elif reader.orientation == 8:
                        transform.rotate(-90.0)
                        image = image.transformed(transform)
                    else:
                        assert False, 'unknown'
            except Exception as e:
                print(e)
                print('maybe no transform based on exif')
            return image

    def loadFile(self, filePath=None, prevFilePath=None, new_info=None):
        """Load the specified file, or the last opened file if None."""
        self.resetState()
        self.canvas.setEnabled(False)
        if filePath is None:
            filePath = self.settings.get(SETTING_FILENAME)

        # Make sure that filePath is a regular python string, rather than QString
        filePath = ustr(filePath)

        unicodeFilePath = ustr(filePath)
        # Tzutalin 20160906 : Add file list and dock to move faster
        # Highlight the file item
        if unicodeFilePath and self.fileListWidget.count() > 0:
            index = self.mImgList.index(unicodeFilePath)
            fileWidgetItem = self.fileListWidget.item(index)
            fileWidgetItem.setSelected(True)

        if unicodeFilePath and os.path.exists(unicodeFilePath):
            if LabelFile.isLabelFile(unicodeFilePath):
                try:
                    self.labelFile = LabelFile(unicodeFilePath)
                except LabelFileError as e:
                    self.errorMessage(u'Error opening file',
                                      (u"<p><b>%s</b></p>"
                                       u"<p>Make sure <i>%s</i> is a valid label file.")
                                      % (e, unicodeFilePath))
                    self.status("Error reading %s" % unicodeFilePath)
                    return False
                self.imageData = self.labelFile.imageData
                self.lineColor = QColor(*self.labelFile.lineColor)
                self.fillColor = QColor(*self.labelFile.fillColor)
                self.canvas.verified = self.labelFile.verified
            else:
                # Load image:
                # read data first and store for saving into label file.
                self.imageData = read(unicodeFilePath, None)
                self.labelFile = None
                self.canvas.verified = False

            image = QImage.fromData(self.imageData)

            # vic
            #reader = QImageReader(unicodeFilePath)
            image = self.read_exif(image, unicodeFilePath)

            if image.isNull():
                self.errorMessage(u'Error opening file',
                                  u"<p>Make sure <i>%s</i> is a valid image file." % unicodeFilePath)
                self.status("Error reading %s" % unicodeFilePath)
                return False
            self.status("Loaded %s" % os.path.basename(unicodeFilePath))
            self.image = image
            self.filePath = unicodeFilePath
            self.canvas.loadPixmap(QPixmap.fromImage(image))
            if self.labelFile:
                self.loadLabels(self.labelFile.shapes)
            self.setClean()
            self.canvas.setEnabled(True)
            self.adjustScale(initial=True)
            self.paintCanvas()
            self.addRecentFile(self.filePath)
            self.toggleActions(True)

            # Label xml file and show bound box according to its filename
            # if self.usingPascalVocFormat is True:
            if self.defaultSaveDir is not None:
                basename = os.path.basename(os.path.splitext(self.filePath)[0])
                xmlPath = os.path.join(self.defaultSaveDir, basename + XML_EXT)
                txtPath = os.path.join(self.defaultSaveDir, basename + TXT_EXT)

                """Annotation file priority:
                PascalXML > YOLO
                """
                consider_prev_im = self.is_reserve_annotation_tracker or self.is_reserve_annotation_only_update
                if os.path.isfile(xmlPath) and not consider_prev_im and new_info is None:
                    self.loadPascalXMLByFilename(xmlPath)
                elif os.path.isfile(txtPath) and not consider_prev_im and new_info is None:
                    self.loadYOLOTXTByFilename(txtPath)
                elif self.usingPascalVocFormat and self.is_reserve_annotation:
                    if new_info is not None:
                        self.loadPascalXMLByFilename(
                            xmlPath, None, None, new_info)
                    else:
                        if prevFilePath:
                            if consider_prev_im:
                                self.previousImageData = read(
                                    prevFilePath, None)
                                previousImage = QImage.fromData(
                                    self.previousImageData)
                                prev_image_np = QImageToCvMat(previousImage)
                                image_np = QImageToCvMat(image)
                            else:
                                prev_image_np = None
                                image_np = None
                            basename = os.path.basename(
                                os.path.splitext(prevFilePath)[0])
                            xmlPath = os.path.join(
                                self.defaultSaveDir, basename + XML_EXT)
                            print('prev xmlPath:', xmlPath)
                            self.loadPascalXMLByFilename(
                                xmlPath, prev_image_np, image_np)
                            self.dirty = True
            else:
                xmlPath = os.path.splitext(filePath)[0] + XML_EXT
                txtPath = os.path.splitext(filePath)[0] + TXT_EXT
                if os.path.isfile(xmlPath) and not self.is_reserve_annotation_tracker and new_info is None:
                    self.loadPascalXMLByFilename(xmlPath)
                elif os.path.isfile(txtPath) and not self.is_reserve_annotation_tracker and new_info is None:
                    self.loadYOLOTXTByFilename(txtPath)
                elif self.usingPascalVocFormat and self.is_reserve_annotation:
                    if new_info is not None:
                        self.loadPascalXMLByFilename(
                            xmlPath, None, None, new_info)
                    else:
                        if prevFilePath:
                            if self.is_reserve_annotation_tracker or self.is_reserve_annotation_only_update:
                                self.previousImageData = read(
                                    prevFilePath, None)
                                previousImage = QImage.fromData(
                                    self.previousImageData)
                                prev_image_np = QImageToCvMat(previousImage)
                                image_np = QImageToCvMat(image)
                            else:
                                prev_image_np = None
                                image_np = None
                            basename = os.path.basename(
                                os.path.splitext(prevFilePath)[0])
                            xmlPath = os.path.join(
                                self.defaultSaveDir, basename + XML_EXT)
                            print('prev xmlPath:', xmlPath)
                            self.loadPascalXMLByFilename(
                                xmlPath, prev_image_np, image_np)
                            self.dirty = True
            if new_info is not None:
                self.dirty = True

            self.setWindowTitle(__appname__ + ' ' + filePath)

            # vic
            # Default : select last item if there is at least one item
            # if self.labelList.count():
            #    self.labelList.setCurrentItem(self.labelList.item(self.labelList.count()-1))
            #    self.labelList.item(self.labelList.count()-1).setSelected(True)

            self.canvas.setFocus(True)
            return True
        return False

    def resizeEvent(self, event):
        if self.canvas and not self.image.isNull()\
           and self.zoomMode != self.MANUAL_ZOOM:
            self.adjustScale()
        super(MainWindow, self).resizeEvent(event)

    def paintCanvas(self):
        assert not self.image.isNull(), "cannot paint null image"
        self.canvas.scale = 0.01 * self.zoomWidget.value()
        self.canvas.adjustSize()
        self.canvas.update()

    def adjustScale(self, initial=False):
        value = self.scalers[self.FIT_WINDOW if initial else self.zoomMode]()
        self.zoomWidget.setValue(int(100 * value))

    def scaleFitWindow(self):
        """Figure out the size of the pixmap in order to fit the main widget."""
        e = 2.0  # So that no scrollbars are generated.
        w1 = self.centralWidget().width() - e
        h1 = self.centralWidget().height() - e
        a1 = w1 / h1
        # Calculate a new scale value based on the pixmap's aspect ratio.
        w2 = self.canvas.pixmap.width() - 0.0
        h2 = self.canvas.pixmap.height() - 0.0
        a2 = w2 / h2
        return w1 / w2 if a2 >= a1 else h1 / h2

    def scaleFitWidth(self):
        # The epsilon does not seem to work too well here.
        w = self.centralWidget().width() - 2.0
        return w / self.canvas.pixmap.width()

    def closeEvent(self, event):
        if not self.mayContinue():
            event.ignore()
        settings = self.settings
        # If it loads images from dir, don't load it at the begining
        if self.dirname is None:
            settings[SETTING_FILENAME] = self.filePath if self.filePath else ''
        else:
            settings[SETTING_FILENAME] = ''

        settings[SETTING_WIN_SIZE] = self.size()
        settings[SETTING_WIN_POSE] = self.pos()
        settings[SETTING_WIN_STATE] = self.saveState()
        settings[SETTING_LINE_COLOR] = self.lineColor
        settings[SETTING_FILL_COLOR] = self.fillColor
        settings[SETTING_RECENT_FILES] = self.recentFiles
        settings[SETTING_ADVANCE_MODE] = not self._beginner
        if self.defaultSaveDir and os.path.exists(self.defaultSaveDir):
            settings[SETTING_SAVE_DIR] = ustr(self.defaultSaveDir)
        else:
            settings[SETTING_SAVE_DIR] = ''

        if self.lastOpenDir and os.path.exists(self.lastOpenDir):
            settings[SETTING_LAST_OPEN_DIR] = self.lastOpenDir
        else:
            settings[SETTING_LAST_OPEN_DIR] = ''

        settings[SETTING_AUTO_SAVE] = self.autoSaving.isChecked()
        settings[SETTING_SINGLE_CLASS] = self.singleClassMode.isChecked()
        settings[SETTING_PAINT_LABEL] = self.displayLabelOption.isChecked()
        settings[SETTING_DRAW_SQUARE] = self.drawSquaresOption.isChecked()
        settings.save()

    def loadRecent(self, filename):
        if self.mayContinue():
            self.loadFile(filename)

    def scanAllImages(self, folderPath):
        extensions = ['.%s' % fmt.data().decode("ascii").lower()
                      for fmt in QImageReader.supportedImageFormats()]
        print("extensions:", extensions)
        images = []
        # extensions=["jpg","png"]
        for root, dirs, files in os.walk(folderPath):
            print("root:", root)
            # print("files:",files)
            for file in files:
                if file.lower().endswith(tuple(extensions)):
                    relativePath = os.path.join(root, file)
                    path = ustr(os.path.abspath(relativePath))
                    #path = os.path.abspath(relativePath)
                    images.append(path)
        natural_sort(images, key=lambda x: x.lower())
        return images

    def changeSavedirDialog(self, _value=False):
        if self.defaultSaveDir is not None:
            path = ustr(self.defaultSaveDir)
        else:
            path = '.'

        dirpath = ustr(QFileDialog.getExistingDirectory(self,
                                                        '%s - Save annotations to the directory' % __appname__, path,  QFileDialog.ShowDirsOnly
                                                        | QFileDialog.DontResolveSymlinks))

        if dirpath is not None and len(dirpath) > 1:
            self.defaultSaveDir = dirpath

        self.statusBar().showMessage('%s . Annotation will be saved to %s' %
                                     ('Change saved folder', self.defaultSaveDir))
        self.statusBar().show()

    def openAnnotationDialog(self, _value=False):
        if self.filePath is None:
            self.statusBar().showMessage('Please select image first')
            self.statusBar().show()
            return

        path = os.path.dirname(ustr(self.filePath))\
            if self.filePath else '.'
        if self.usingPascalVocFormat:
            filters = "Open Annotation XML file (%s)" % ' '.join(['*.xml'])
            filename = ustr(QFileDialog.getOpenFileName(
                self, '%s - Choose a xml file' % __appname__, path, filters))
            if filename:
                if isinstance(filename, (tuple, list)):
                    filename = filename[0]
            self.loadPascalXMLByFilename(filename)

    def reserveAnnotation(self, _value=False):
        self.is_reserve_annotation = not self.is_reserve_annotation
        print("is_reserve_annotation:", self.is_reserve_annotation)

    def reloadFile(self, track_result):
        success, new_boxes, prev_shapes_info = track_result
        new_info = (new_boxes, prev_shapes_info)
        print("start reloadFile")
        print("track success:", success)
        if success:
            self.loadFile(filePath=self.filePath,
                          prevFilePath=None, new_info=new_info)
            self.saveFile()
            print("finish saveFile")
        print("finish reloadFile")

    def reserveAnnotationTracker(self, _value=False):
        print("start reserveAnnotationTracker")
        self.is_reserve_annotation_tracker = True
        self.loadFile(
            self.filePath, self.mImgList[self.mImgList.index(self.filePath)-1])
        self.is_reserve_annotation_tracker = False

    def reserveAnnotationOnlyUpdate(self, _value=False):
        print("start is_reserve_annotation_only_update")
        self.is_reserve_annotation_only_update = True
        self.loadFile(
            self.filePath, self.mImgList[self.mImgList.index(self.filePath)-1])
        self.is_reserve_annotation_only_update = False

    def showLabel(self, _value=False):
        print("change show_label")
        cfg.show_label = not cfg.show_label
        print("show_label:", cfg.show_label)

    def openDirDialog(self, _value=False, dirpath=None):
        if not self.mayContinue():
            return

        defaultOpenDirPath = dirpath if dirpath else '.'
        if self.lastOpenDir and os.path.exists(self.lastOpenDir):
            defaultOpenDirPath = self.lastOpenDir
        else:
            defaultOpenDirPath = os.path.dirname(
                self.filePath) if self.filePath else '.'

        targetDirPath = ustr(QFileDialog.getExistingDirectory(self,
                                                              '%s - Open Directory' % __appname__, defaultOpenDirPath,
                                                              QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks))
        self.defaultSaveDir = targetDirPath  # cyw xml dir same as img dir
        self.importDirImages(targetDirPath)

    def importDirImages(self, dirpath):
        if not self.mayContinue() or not dirpath:
            return

        self.lastOpenDir = dirpath
        self.dirname = dirpath
        self.filePath = None
        self.fileListWidget.clear()
        self.mImgList = self.scanAllImages(dirpath)
        # print("self.mImgList",self.mImgList)
        self.openNextImg()

        self.im_name_path_dict = {}
        for imgPath in self.mImgList:
            baseImgPath = os.path.basename(imgPath)
            self.im_name_path_dict[baseImgPath] = imgPath
            item = QListWidgetItem(baseImgPath)
            self.fileListWidget.addItem(item)

    def verifyImg(self, _value=False):
        # Proceding next image without dialog if having any label
        if self.filePath is not None:
            try:
                self.labelFile.toggleVerify()
            except AttributeError:
                # If the labelling file does not exist yet, create if and
                # re-save it with the verified attribute.
                self.saveFile()
                if self.labelFile != None:
                    self.labelFile.toggleVerify()
                else:
                    return

            self.canvas.verified = self.labelFile.verified
            self.paintCanvas()
            self.saveFile()

    def openPrevImg(self, _value=False):
        # Proceding prev image without dialog if having any label
        if self.autoSaving.isChecked():
            if self.defaultSaveDir is not None:
                if self.dirty is True:
                    self.saveFile()
            else:
                self.changeSavedirDialog()
                return

        if not self.mayContinue():
            return

        if len(self.mImgList) <= 0:
            return

        if self.filePath is None:
            return

        currIndex = self.mImgList.index(self.filePath)
        if currIndex - 1 >= 0:
            filename = self.mImgList[currIndex - 1]
            print("prev img name:", filename)
            if filename:
                self.loadFile(filename)
                self.setFitWindow()

    def openNextImg(self, _value=False):
        # Proceding prev image without dialog if having any label
        if self.autoSaving.isChecked():
            if self.defaultSaveDir is not None:
                if self.dirty is True:
                    self.saveFile()
            else:
                self.changeSavedirDialog()
                return

        if not self.mayContinue():
            return

        if len(self.mImgList) <= 0:
            return

        filename = None
        prev_filename = None
        if self.filePath is None:
            filename = self.mImgList[0]
        else:
            currIndex = self.mImgList.index(self.filePath)
            if currIndex + 1 < len(self.mImgList):
                filename = self.mImgList[currIndex + 1]
                prev_filename = self.mImgList[currIndex]

        print("next img name:", filename)
        if filename:
            self.loadFile(filename, prev_filename)
            self.setFitWindow()

    def deleteCurrentImg(self):
        if len(self.mImgList) <= 0:
            return
        if self.filePath is None:
            return
        yes, no = QMessageBox.Yes, QMessageBox.No
        msg = u'You will delete current image, proceed anyway?'
        if no == QMessageBox.warning(self, u'Attention', msg, yes | no):
            return

        currIndex = self.mImgList.index(self.filePath)
        if currIndex + 1 < len(self.mImgList):
            filename = self.mImgList[currIndex + 1]
        elif currIndex - 1 >= 0:
            filename = self.mImgList[currIndex - 1]
        else:
            filename = None
        self.mImgList.remove(self.filePath)
        os.remove(self.filePath)
        label_file = self.filePath[:-3] + 'xml'
        if os.path.exists(label_file):
            os.remove(label_file)
        if filename:
            self.loadFile(filename)
        else:
            self.resetState()
            self.setClean()
            self.toggleActions(False)
            self.canvas.setEnabled(False)
            self.actions.saveAs.setEnabled(False)

    def select_target_class_1(self, _value=False):
        self.selected_class_idx = 0
        print("idx:", self.selected_class_idx+1, "select class:",
              self.labelHist[self.selected_class_idx], self.labelHistChinese[self.selected_class_idx])

    def select_target_class_2(self, _value=False):
        self.selected_class_idx = 1
        print("idx:", self.selected_class_idx+1, "select class:",
              self.labelHist[self.selected_class_idx], self.labelHistChinese[self.selected_class_idx])

    def select_target_class_3(self, _value=False):
        self.selected_class_idx = 2
        print("idx:", self.selected_class_idx+1, "select class:",
              self.labelHist[self.selected_class_idx], self.labelHistChinese[self.selected_class_idx])

    def select_target_class_4(self, _value=False):
        self.selected_class_idx = 3
        print("idx:", self.selected_class_idx+1, "select class:",
              self.labelHist[self.selected_class_idx], self.labelHistChinese[self.selected_class_idx])

    def select_target_class_5(self, _value=False):
        self.selected_class_idx = 4
        print("idx:", self.selected_class_idx+1, "select class:",
              self.labelHist[self.selected_class_idx], self.labelHistChinese[self.selected_class_idx])

    def select_target_class_6(self, _value=False):
        self.selected_class_idx = 5
        print("idx:", self.selected_class_idx+1, "select class:",
              self.labelHist[self.selected_class_idx], self.labelHistChinese[self.selected_class_idx])

    def select_target_class_7(self, _value=False):
        self.selected_class_idx = 6
        print("idx:", self.selected_class_idx+1, "select class:",
              self.labelHist[self.selected_class_idx], self.labelHistChinese[self.selected_class_idx])

    def select_target_class_8(self, _value=False):
        self.selected_class_idx = 7
        print("idx:", self.selected_class_idx+1, "select class:",
              self.labelHist[self.selected_class_idx], self.labelHistChinese[self.selected_class_idx])

    def select_target_class_9(self, _value=False):
        self.selected_class_idx = 8
        print("idx:", self.selected_class_idx+1, "select class:",
              self.labelHist[self.selected_class_idx], self.labelHistChinese[self.selected_class_idx])

    def openFile(self, _value=False):
        if not self.mayContinue():
            return
        path = os.path.dirname(ustr(self.filePath)) if self.filePath else '.'
        formats = ['*.%s' % fmt.data().decode("ascii").lower()
                   for fmt in QImageReader.supportedImageFormats()]
        filters = "Image & Label files (%s)" % ' '.join(
            formats + ['*%s' % LabelFile.suffix])
        filename = QFileDialog.getOpenFileName(
            self, '%s - Choose Image or Label file' % __appname__, path, filters)
        if filename:
            if isinstance(filename, (tuple, list)):
                filename = filename[0]
            self.loadFile(filename)

    def saveFile(self, _value=False):
        if self.canvas.iswrong:  # cyw
            QMessageBox.warning(
                self, u'Wrong Shape', 'You have wrong shape, you must fix is', QMessageBox.Ok)
            return
        if self.defaultSaveDir is not None and len(ustr(self.defaultSaveDir)):
            if self.filePath:
                imgFileName = os.path.basename(self.filePath)
                savedFileName = os.path.splitext(imgFileName)[0]
                savedPath = os.path.join(ustr(self.defaultSaveDir), savedFileName)
                self._saveFile(savedPath)
        else:
            imgFileDir = os.path.dirname(self.filePath)
            imgFileName = os.path.basename(self.filePath)
            savedFileName = os.path.splitext(imgFileName)[0]
            savedPath = os.path.join(imgFileDir, savedFileName)
            self._saveFile(savedPath if self.labelFile else self.saveFileDialog(removeExt=False))

    def saveFileAs(self, _value=False):
        assert not self.image.isNull(), "cannot save empty image"
        self._saveFile(self.saveFileDialog())

    def saveFileDialog(self, removeExt=True):
        caption = '%s - Choose File' % __appname__
        filters = 'File (*%s)' % LabelFile.suffix
        openDialogPath = self.currentPath()
        dlg = QFileDialog(self, caption, openDialogPath, filters)
        dlg.setDefaultSuffix(LabelFile.suffix[1:])
        dlg.setAcceptMode(QFileDialog.AcceptSave)
        filenameWithoutExtension = os.path.splitext(self.filePath)[0]
        dlg.selectFile(filenameWithoutExtension)
        dlg.setOption(QFileDialog.DontUseNativeDialog, False)
        if dlg.exec_():
            fullFilePath = ustr(dlg.selectedFiles()[0])
            if removeExt:
                # Return file path without the extension.
                return os.path.splitext(fullFilePath)[0]
            else:
                return fullFilePath
        return ''

    def _saveFile(self, annotationFilePath):
        if annotationFilePath and self.saveLabels(annotationFilePath):
            self.setClean()
            self.statusBar().showMessage('Saved to  %s' % annotationFilePath)
            self.statusBar().show()

    def closeFile(self, _value=False):
        if not self.mayContinue():
            return
        self.resetState()
        self.setClean()
        self.toggleActions(False)
        self.canvas.setEnabled(False)
        self.actions.saveAs.setEnabled(False)

    def resetAll(self):
        self.settings.reset()
        self.close()
        proc = QProcess()
        proc.startDetached(os.path.abspath(__file__))

    def mayContinue(self):
        return not (self.dirty and not self.discardChangesDialog())

    def discardChangesDialog(self):
        yes, no = QMessageBox.Yes, QMessageBox.No
        msg = u'You have unsaved changes, proceed anyway?'
        return yes == QMessageBox.warning(self, u'Attention', msg, yes | no)

    def errorMessage(self, title, message):
        return QMessageBox.critical(self, title,
                                    '<p><b>%s</b></p>%s' % (title, message))

    def currentPath(self):
        return os.path.dirname(self.filePath) if self.filePath else '.'

    def chooseColor1(self):
        color = self.colorDialog.getColor(self.lineColor, u'Choose line color',
                                          default=DEFAULT_LINE_COLOR)
        if color:
            self.lineColor = color
            Shape.line_color = color
            self.canvas.setDrawingColor(color)
            self.canvas.update()
            self.setDirty()

    def deleteSelectedShape(self):
        self.removeLabel(self.canvas.deleteSelected())
        self.setDirty()
        if self.noShapes():
            for action in self.actions.onShapesPresent:
                action.setEnabled(False)

    def chshapeLineColor(self):
        color = self.colorDialog.getColor(self.lineColor, u'Choose line color',
                                          default=DEFAULT_LINE_COLOR)
        if color:
            self.canvas.selectedShape.line_color = color
            self.canvas.update()
            self.setDirty()

    def chshapeFillColor(self):
        color = self.colorDialog.getColor(self.fillColor, u'Choose fill color',
                                          default=DEFAULT_FILL_COLOR)
        if color:
            self.canvas.selectedShape.fill_color = color
            self.canvas.update()
            self.setDirty()

    def copyShape(self):
        self.canvas.endMove(copy=True)
        self.addLabel(self.canvas.selectedShape)
        self.setDirty()

    def moveShape(self):
        self.canvas.endMove(copy=False)
        self.setDirty()

    def loadPredefinedClasses(self, predefClassesFile):
        if os.path.exists(predefClassesFile) is True:
            with codecs.open(predefClassesFile, 'r', 'utf8') as f:
                for line in f:
                    line = line.strip()
                    idx = line.find(" ")
                    if idx == -1:
                        name = line
                        name_ch = None
                    else:
                        name = line[:idx]
                        name_ch = line[idx+1:]
                    if self.labelHist is None:
                        self.labelHist = [name]
                        self.labelHistChinese = [name_ch]
                    else:
                        self.labelHist.append(name)
                        self.labelHistChinese.append(name_ch)
                    self.labelHistPinYin2Chinese[name] = name_ch
                assert len(self.labelHist) == len(
                    self.labelHistChinese) == len(self.labelHistPinYin2Chinese)

    def loadPascalXMLByFilename(self, xmlPath, image=None, image_new=None, new_info=None):
        if self.filePath is None:
            return
        if os.path.isfile(xmlPath) is False and new_info is None:
            return

        self.set_format(FORMAT_PASCALVOC)

        tVocParseReader = PascalVocReader(xmlPath)
        shapes_info = tVocParseReader.getShapesInfo()
        if self.is_reserve_annotation_tracker:
            if image is not None and image_new is not None:
                image = image[:, :, :3]
                image_new = image_new[:, :, :3]
                print('MultiTracker_create')
                tracker_thread = TrackerThread(shapes_info, image, image_new)
                tracker_thread.bbox_tracker.connect(self.reloadFile)
                print('multiTracker.update(image_new)')
                tracker_thread.start()
                QtTest.QTest.qWait(100)

        if new_info is not None:
            print('multiTracker success')
            (new_boxes, prev_shapes_info) = new_info
            shapes_info = prev_shapes_info
            for i, newbox in enumerate(new_boxes):
                p1_ = (round(newbox[0]), round(newbox[1]))
                p2_ = (round(newbox[0] + newbox[2]), round(newbox[1]))
                p3_ = (round(newbox[0] + newbox[2]),
                       round(newbox[1] + newbox[3]))
                p4_ = (round(newbox[0]), round(newbox[1] + newbox[3]))
                shapes_info[i] = list(shapes_info[i])
                shapes_info[i][1] = [p1_, p2_, p3_, p4_]
                shapes_info[i] = tuple(shapes_info[i])

        self.loadLabels(shapes_info)
        self.canvas.verified = tVocParseReader.verified

    def loadYOLOTXTByFilename(self, txtPath):
        if self.filePath is None:
            return
        if os.path.isfile(txtPath) is False:
            return

        self.set_format(FORMAT_YOLO)
        tYoloParseReader = YoloReader(txtPath, self.image)
        shapes = tYoloParseReader.getShapes()
        print(shapes)
        self.loadLabels(shapes)
        self.canvas.verified = tYoloParseReader.verified

    def togglePaintLabelsOption(self):
        for shape in self.canvas.shapes:
            shape.paintLabel = self.displayLabelOption.isChecked()

    def toogleDrawSquare(self):
        self.canvas.setDrawingShapeToSquare(self.drawSquaresOption.isChecked())


def inverted(color):
    return QColor(*[255 - v for v in color.getRgb()])


def read(filename, default=None):
    try:
        with open(filename, 'rb') as f:
            return f.read()
    except:
        return default


def get_main_app(argv=[]):
    """
    Standard boilerplate Qt application code.
    Do everything but app.exec_() -- so that we can test the application in one thread
    """
    app = QApplication(argv)
    app.setApplicationName(__appname__)
    app.setWindowIcon(newIcon("app"))
    # Tzutalin 201705+: Accept extra agruments to change predefined class file
    # Usage : labelImg.py image predefClassFile saveDir
    win = MainWindow(argv[1] if len(argv) >= 2 else None,
                     argv[2] if len(argv) >= 3 else os.path.join(
                         os.path.dirname(sys.argv[0]),
                         'data', 'predefined_classes.txt'),
                     argv[3] if len(argv) >= 4 else None)
    win.show()
    return app, win


def main():
    '''construct main app and run it'''
    app, _win = get_main_app(sys.argv)
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
