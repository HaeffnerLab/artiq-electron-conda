from PyQt5 import QtCore, QtWidgets, QtGui
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.gridspec as gridspec
import matplotlib.cm as cm
import matplotlib.pyplot as plt


class LinecenterTracker(QtWidgets.QDockWidget):
    def __init__(self):
        QtWidgets.QDockWidget.__init__(self, "Linecenter Bfield")
        self.setObjectName("LinecenterBfield")
        self.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable |
                         QtWidgets.QDockWidget.DockWidgetFloatable)
        self.main_widget = QtWidgets.QWidget()
        self.setWidget(self.main_widget)
        self.make_gui()

    def make_gui(self):
        layout = QtWidgets.QVBoxLayout()
        self.fig = Figure()
        self.drift_canvas = FigureCanvas(self.fig)
        self.drift_canvas.setParent(self)
        self.fig.patch.set_facecolor((.96, .96, .96))
        gs = gridspec.GridSpec(1, 2)
        self.line_drift = self.fig.add_subplot(gs[0, 0])
        self.line_drift.set_xlabel("Time (min)")
        self.line_drift.set_ylabel("KHz")
        self.line_drift.tick_params(axis="both",
                                    direction="in",
                                    top=True,
                                    right=True,
                                    grid_alpha=0.5)
        self.line_drift.grid(True)
        self.line_drift.set_title("Line Center Drift")
        self.line_drift_lines = []
        self.line_drift_fit_line = []
        self.b_drift = self.fig.add_subplot(gs[0, 1])
        self.b_drift.set_xlabel("Time (min)")
        self.b_drift.set_ylabel("mG")
        self.b_drift.set_title("B Field Drift")
        self.b_drift.tick_params(axis="both",
                                    direction="in",
                                    top=True,
                                    right=True,
                                    grid_alpha=0.5)
        self.b_drift.grid(True)
        self.b_drift_twin = self.b_drift.twinx()
        self.b_drift_twin.set_ylabel("Effective Frequency (kHz)")
        self.b_drift_twin.tick_params(axis="both",
                                      direction="in",
                                      top=True,
                                      right=True,
                                      grid_alpha=0.5)
        self.b_drift_twin_lines = []
        self.b_drift_lines = []
        self.b_drift_fit_line = []
        self.fig.tight_layout()
        mpl_toolbar = NavigationToolbar(self.drift_canvas, self)
        layout.addWidget(mpl_toolbar)
        layout.addWidget(self.drift_canvas)
        layout.setAlignment(QtCore.Qt.AlignRight)
        self.main_widget.setLayout(layout)