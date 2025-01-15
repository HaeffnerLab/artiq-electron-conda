import labrad
import logging
import asyncio
import os
from artiq import __artiq_dir__ as artiq_dir
from PyQt5 import QtCore, QtGui, QtWidgets
from TimeTagger import createTimeTagger, Counter, \
                       Countrate, Histogram, LOW, \
                       HIGH, freeTimeTagger, scanTimeTagger, \
                       ConstantFractionDiscriminator
import numpy as np
import datetime
import tqdm
from time import sleep
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.pyplot as plt


from artiq.dashboard.time_tagger.histogram_dock import HistogramDock
from artiq.dashboard.time_tagger.ROI_count_dock import ROICountDock

class TimeTagger(QtWidgets.QMainWindow):
    def __init__(self):
        QtWidgets.QMainWindow.__init__(self)

        qfm = QtGui.QFontMetrics(self.font())
        self.resize(140*qfm.averageCharWidth(), 38*qfm.lineSpacing())
        self.exit_request = asyncio.Event()
        self.setup_time_tagger()
        self.setup_layout()
        self.add_docks()
        self.setup_buttons()
        self.main_widget.setLayout(self.layout)
        
        
    

    def setup_time_tagger(self):
        tagger = createTimeTagger()
        tagger.reset()
        trigger = 0.5
        tagger.setTriggerLevel(1, trigger)
        tagger.setDeadtime(1, 100000)
        self.tagger = tagger


    def setup_buttons(self):
        self.setup_hist_buttons()
        self.setup_roi_buttons()

        
    def setup_hist_buttons(self):
        hist_start_button = QtWidgets.QPushButton("Start Histogram")
        hist_start_button.clicked.connect(self.hist_dock.start_plot)
        self.layout.addWidget(hist_start_button)
        self.layout.setAlignment(QtCore.Qt.AlignRight)

        hist_continue_button = QtWidgets.QPushButton("Resume Histogram")
        hist_continue_button.clicked.connect(self.hist_dock.continue_plot)
        self.layout.addWidget(hist_continue_button)
        self.layout.setAlignment(QtCore.Qt.AlignRight)

        hist_end_button = QtWidgets.QPushButton("Pause Histogram")
        hist_end_button.clicked.connect(self.hist_dock.end_plot)
        self.layout.addWidget(hist_end_button)
        self.layout.setAlignment(QtCore.Qt.AlignRight)


    def setup_roi_buttons(self):
        roi_start_button = QtWidgets.QPushButton("Start ROI Count")
        roi_start_button.clicked.connect(self.roi_dock.start_plot)
        self.layout.addWidget(roi_start_button)
        self.layout.setAlignment(QtCore.Qt.AlignRight)

        roi_resume_button = QtWidgets.QPushButton("Resume ROI Count")
        roi_resume_button.clicked.connect(self.roi_dock.continue_plot)
        self.layout.addWidget(roi_resume_button)
        self.layout.setAlignment(QtCore.Qt.AlignRight)

        roi_end_button = QtWidgets.QPushButton("Pause ROI Count")
        roi_end_button.clicked.connect(self.roi_dock.end_plot)
        self.layout.addWidget(roi_end_button)
        self.layout.setAlignment(QtCore.Qt.AlignRight)


    def closeEvent(self, event):
        event.ignore()
        self.exit_request.set()


    def save_state(self):
        return {"state": bytes(self.saveState()),
                "geometry": bytes(self.saveGeometry()),
                }


    def restore_state(self, state):
        self.restoreGeometry(QtCore.QByteArray(state["geometry"]))
        self.restoreState(QtCore.QByteArray(state["state"]))
        

    def setup_layout(self):
        self.main_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.main_widget)
        layout = QtWidgets.QVBoxLayout()
        mdi_area = MdiArea()
        mdi_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        mdi_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        #self.setCentralWidget(mdi_area)
        layout.addWidget(mdi_area)
        self.layout = layout
        
    
    def add_docks(self):
        self.add_histogram_dock()
        self.add_ROI_dock()


    def add_histogram_dock(self):
        hist_dock = HistogramDock(self.tagger)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, hist_dock)
        self.hist_dock = hist_dock


    def add_ROI_dock(self):
        roi_dock = ROICountDock(self.tagger)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, roi_dock)
        self.roi_dock = roi_dock
        
        
        


class MdiArea(QtWidgets.QMdiArea):
    # redundant
    def __init__(self):
        QtWidgets.QMdiArea.__init__(self)
        self.pixmap = QtGui.QPixmap(os.path.join(
            artiq_dir, "gui", "logo_ver.svg"))

    def paintEvent(self, event):
        QtWidgets.QMdiArea.paintEvent(self, event)
        painter = QtGui.QPainter(self.viewport())
        x = (self.width() - self.pixmap.width())//2
        y = (self.height() - self.pixmap.height())//2
        painter.setOpacity(1)
        painter.drawPixmap(x, y, self.pixmap)