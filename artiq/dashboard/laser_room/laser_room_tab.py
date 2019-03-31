import labrad
import os
import asyncio
from PyQt5 import QtCore, QtGui, QtWidgets
from artiq import __artiq_dir__ as artiq_dir
from artiq.dashboard.laser_room.laser_dac_dock import LaserDACDock
from artiq.dashboard.laser_room.multiplexer_dock import MultiplexerDock
from artiq.dashboard.laser_room.injection_lock_dock import InjectionLockDock


class LaserRoomTab(QtWidgets.QMainWindow):
    def __init__(self):
        QtWidgets.QMainWindow.__init__(self)

        qfm = QtGui.QFontMetrics(self.font())
        self.resize(140*qfm.averageCharWidth(), 38*qfm.lineSpacing())
        self.exit_request = asyncio.Event()
        self.setup_background()
        self.add_docks()
    
    def closeEvent(self, event):
        event.ignore()
        self.exit_request.set()

    def save_state(self):
        return {"state": bytes(self.saveState()),
                "geometry": bytes(self.saveGeometry()),
                "il1": self.d_injectionlock.il.q1Edit.value(),
                "il2": self.d_injectionlock.il.q2Edit.value(),
                "il3": self.d_injectionlock.il.q3Edit.value(),
                "il4": self.d_injectionlock.il.q4Edit.value()}

    def restore_state(self, state):
        self.restoreGeometry(QtCore.QByteArray(state["geometry"]))
        self.restoreState(QtCore.QByteArray(state["state"]))
        self.d_injectionlock.il.q1Edit.setValue(state["il1"])
        self.d_injectionlock.il.q2Edit.setValue(state["il2"])
        self.d_injectionlock.il.q3Edit.setValue(state["il3"])
        self.d_injectionlock.il.q4Edit.setValue(state["il4"])

    def setup_background(self):
        mdi_area = MdiArea()
        mdi_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        mdi_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setCentralWidget(mdi_area)
    
    def add_docks(self):
        self.d_laserdac = LaserDACDock(self)
        self.d_multiplexer = MultiplexerDock(self)
        self.d_injectionlock = InjectionLockDock(self)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, self.d_laserdac)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.d_multiplexer)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.d_injectionlock)


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
        