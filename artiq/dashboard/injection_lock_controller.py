import labrad
from PyQt5 import QtCore, QtGui, QtWidgets


class InjectionLockDock(QtWidgets.QDockWidget):
    def __init__(self, main_window):
        QtWidgets.QDockWidget.__init__(self, "INJECTION LOCK")
        self.setObjectName("INJECTION LOCK")
        self.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable |
                         QtWidgets.QDockWidget.DockWidgetFloatable)