import logging
from PyQt5 import QtCore, QtWidgets, QtGui
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.gridspec as gridspec
import matplotlib.cm as cm
import matplotlib.pyplot as plt
import artiq.dashboard.drift_tracker.drift_tracker_config as c


logger = logging.getLogger(__name__)


class Spectrum(QtWidgets.QDockWidget):
    def __init__(self):
        QtWidgets.QDockWidget.__init__(self, "Electronic Spectrum")
        self.setObjectName("ElectronicSpectrum")
        self.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable |
                         QtWidgets.QDockWidget.DockWidgetFloatable)
        self.main_widget = QtWidgets.QWidget()
        self.setWidget(self.main_widget)
        self.make_gui()

    def make_gui(self):
        layout = QtWidgets.QVBoxLayout()
        self.fig = Figure()
        self.fig.patch.set_facecolor((.96, .96, .96))
        self.spec_canvas = FigureCanvas(self.fig)
        self.spec_canvas.setParent(self)  
        self.spec = self.fig.subplots()
        self.spec.set_xlim(left = c.frequency_limit[0], right = c.frequency_limit[1])
        self.spec.set_ylim(bottom = 0, top = 1)
        self.spec.set_xlabel("MHz")
        self.spec.axes.get_yaxis().set_ticks([])
        self.spec.tick_params(which="both", direction="in", top=True,
                              bottom=True, left=False, right=False,
                              length=5)
        self.spec.minorticks_on()
        self.spec.tick_params(which="major", length=10, width=2)
        self.mpl_toolbar = NavigationToolbar(self.spec_canvas, self)
        self.spectral_lines = []
        self.fig.tight_layout()
        layout.addWidget(self.mpl_toolbar)
        layout.addWidget(self.spec_canvas)
        self.main_widget.setLayout(layout)