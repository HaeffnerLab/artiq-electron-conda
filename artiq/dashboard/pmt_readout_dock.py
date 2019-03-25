import logging
import numpy as np
from PyQt5 import QtCore, QtWidgets
from matplotlib.backends.backend_qt5agg import (NavigationToolbar2QT,
                                                FigureCanvasQTAgg)
from matplotlib.figure import Figure
from twisted.internet.defer import inlineCallbacks

logger = logging.getLogger(__name__)


class PMTReadoutDock(QtWidgets.QDockWidget):
    def __init__(self, cxn):
        QtWidgets.QDockWidget.__init__(self, "PMT Readout")
        self.cxn = cxn
        self.p = cxn.parametervault
        self.current_line = 0
        self.number_lines = 0
        self.setObjectName("PMTReadoutHistogram")
        self.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable |
                         QtWidgets.QDockWidget.DockWidgetFloatable)
        self.main_widget = QtWidgets.QWidget()
        self.setWidget(self.main_widget)
        self.make_GUI()
        self.connect_GUI()

    def save_state(self):
        pass

    def restore_state(self):
        pass

    

    def make_GUI(self):
        layout = QtWidgets.QGridLayout()

        self.fig  = Figure()
        self.fig.patch.set_facecolor((.96, .96, .96))
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.setParent(self)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_ylim((0, 50))
        self.mpl_toolbar = NavigationToolbar2QT(self.canvas, self)
        self.ax.set_title("PMT Readout", fontsize=25)
        self.fig.tight_layout()
        self.canvas.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                  QtWidgets.QSizePolicy.Expanding)
        self.ax.tick_params(axis="both", direction="in")
        lines = self.p.get_parameter(["StateReadout", "threshold_list"])[1]
        lines.sort()
        self.p.set_parameter(["StateReadout", "threshold_list", lines])
        self.number_lines = len(lines)
        self.lines = [self.ax.axvline(line, lw=3, color="r") for line in lines]
        self.n_thresholds = QtWidgets.QSpinBox()
        self.n_thresholds.setValue(len(lines))
        self.n_thresholds.setMinimum(1)
        self.n_thresholds.setMaximum(10)
        self.curr_threshold = QtWidgets.QSpinBox()
        self.curr_threshold.setValue(1)
        self.curr_threshold.setMinimum(1)
        self.curr_threshold.setMaximum(len(lines))

        layout.addWidget(self.mpl_toolbar, 0, 0)
        layout.addWidget(QtWidgets.QLabel("no. thresholds: "), 0, 1)
        layout.addWidget(self.n_thresholds, 0, 2)
        layout.addWidget(QtWidgets.QLabel("select threshold: "), 0, 3)
        layout.addWidget(self.curr_threshold, 0, 4)
        layout.addWidget(self.canvas, 1, 0, 1, 5)
        self.main_widget.setLayout(layout)

    def connect_GUI(self):
        self.canvas.mpl_connect("button_press_event", self.on_click)
        self.n_thresholds.valueChanged.connect(self.n_thresholds_changed)
        self.curr_threshold.valueChanged.connect(self.curr_threshold_changed)

    def n_thresholds_changed(self, val):
        self.curr_threshold.setMaximum(int(val))
        diff = val - self.number_lines
        self.number_lines = val
        if diff < 0:
            for _ in range(abs(diff)):
                l = self.lines.pop()
                l.remove()
                self.canvas.draw()
            tlist = self.p.get_parameter(["StateReadout", "threshold_list"])[1]
            tlist = tlist[:diff]
            self.p.set_parameter(["StateReadout", "threshold_list", tlist])

        if diff > 0:
            for _ in range(diff):
                self.lines.append(self.ax.axvline(0, lw=3, color="r"))
                tlist = self.p.get_parameter(["StateReadout", "threshold_list"])[1]
                maxt = max(tlist)
                tlist = np.append(tlist, maxt + 1)
                self.p.set_parameter(["StateReadout", "threshold_list", tlist])
                self.canvas.draw()

    def curr_threshold_changed(self, val):
        self.current_line = int(val) - 1

    def on_click(self, event):
        if type(event.button) == int:
            xval = int(round(event.xdata))
            idx = self.current_line
            tlist = self.p.get_parameter(["StateReadout", "threshold_list"])[1]
            tlist[idx] = xval
            if idx > 0:
                if tlist[idx - 1] >= tlist[idx]:
                    return
            if idx < len(tlist) - 1:
                if tlist[idx] >= tlist[idx + 1]:
                    return 
            self.p.set_parameter(["StateReadout", "threshold_list", tlist])
