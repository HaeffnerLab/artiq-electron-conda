import labrad
import os
import asyncio
from PyQt5 import QtCore, QtGui, QtWidgets
from artiq import __artiq_dir__ as artiq_dir
from artiq.dashboard.laser_dac_controller import LaserDACDock
from artiq.dashboard.multiplexer_controller import MultiplexerDock
from artiq.dashboard.injection_lock_controller import InjectionLockDock


class LaserTab(QtWidgets.QMainWindow):
    def __init__(self):
        QtWidgets.QMainWindow.__init__(self)

        qfm = QtGui.QFontMetrics(self.font())
        self.resize(140*qfm.averageCharWidth(), 38*qfm.lineSpacing())

        self.exit_request = asyncio.Event()

        # topWidget = QtWidgets.QWidget()
        # topLayout = QtWidgets.QGridLayout()

        self.setup_background()
        self.add_docks()
    
    def closeEvent(self, event):
        event.ignore()
        self.exit_request.set()

    def save_state(self):
        return {
            "state": bytes(self.saveState()),
            "geometry": bytes(self.saveGeometry())
        }

    def restore_state(self, state):
        self.restoreGeometry(QtCore.QByteArray(state["geometry"]))
        self.restoreState(QtCore.QByteArray(state["state"]))

    def setup_background(self):
        mdi_area = MdiArea()
        mdi_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        mdi_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setCentralWidget(mdi_area)
    
    def add_docks(self):
        d_laserdac = LaserDACDock(self)
        d_multiplexer = MultiplexerDock(self)
        d_injectionlock = InjectionLockDock(self)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, d_laserdac)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, d_multiplexer)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, d_injectionlock)


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



        