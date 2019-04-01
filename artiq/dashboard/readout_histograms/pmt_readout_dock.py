import logging
import numpy as np
from PyQt5 import QtCore, QtWidgets
from matplotlib.backends.backend_qt5agg import (NavigationToolbar2QT,
                                                FigureCanvasQTAgg)
from matplotlib.figure import Figure
from twisted.internet.defer import inlineCallbacks
import labrad


logger = logging.getLogger(__name__)


class PMTReadoutDock(QtWidgets.QDockWidget):
    def __init__(self, acxn):
        QtWidgets.QDockWidget.__init__(self, "PMT Readout")
        self.acxn = acxn
        # self.p = cxn.parametervault
        try:
            self.cxn = labrad.connect()
            self.p = self.cxn.parametervault
        except:
            logger.error("Failed to initially connect to labrad.",
                         exc_info=True)
            self.setDisabled(True)
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
        self.fig.tight_layout()
        self.canvas.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                  QtWidgets.QSizePolicy.Expanding)
        self.ax.tick_params(axis="both", direction="in")
        lines = self.p.get_parameter(["StateReadout", "threshold_list"])
        slines = sorted(lines)
        if not list(slines) == list(lines):
            self.p.set_parameter(["StateReadout", "threshold_list", slines])
            lines = slines
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
        self.cxn.disconnect()

    def connect_GUI(self):
        self.canvas.mpl_connect("button_press_event", self.on_click)
        self.n_thresholds.valueChanged.connect(self.n_thresholds_changed)
        self.curr_threshold.valueChanged.connect(self.curr_threshold_changed)

    @inlineCallbacks
    def n_thresholds_changed(self, val):
        p = yield self.acxn.get_server("ParameterVault")
        self.curr_threshold.setMaximum(int(val))
        diff = val - self.number_lines
        self.number_lines = val
        if diff < 0:
            for _ in range(abs(diff)):
                l = self.lines.pop()
                l.remove()
                del l
                self.canvas.draw()
            tlist = yield p.get_parameter(["StateReadout", "threshold_list"])
            tlist = tlist[:diff]
            yield p.set_parameter(["StateReadout", "threshold_list", tlist])

        if diff > 0:
            for _ in range(diff):
                tlist = yield p.get_parameter(["StateReadout", "threshold_list"])
                maxt = max(tlist)
                tlist = np.append(tlist, maxt + 2)
                self.lines.append(self.ax.axvline(maxt + 2, lw=3, color="r"))
                yield p.set_parameter(["StateReadout", "threshold_list", tlist])
                self.canvas.draw()

    def curr_threshold_changed(self, val):
        self.current_line = int(val) - 1

    @inlineCallbacks
    def on_click(self, event):
        p = yield self.acxn.get_server("ParameterVault")
        if type(event.button) == int and not event.xdata is None:
            xval = int(round(event.xdata))
            idx = self.current_line
            tlist = yield p.get_parameter(["StateReadout", "threshold_list"])
            tlist = tlist
            tlist[idx] = xval
            if idx > 0:
                if tlist[idx - 1] >= tlist[idx]:
                    return
            if idx < len(tlist) - 1:
                if tlist[idx] >= tlist[idx + 1]:
                    return 
            yield p.set_parameter(["StateReadout", "threshold_list", tlist])