import labrad
from PyQt5 import QtCore, QtGui, QtWidgets


class MultiplexerDock(QtWidgets.QDockWidget):
    def __init__(self, main_window):
        QtWidgets.QDockWidget.__init__(self, "MULTIPLEXER")
        self.setObjectName("MULTIPLEXER")
        self.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable |
                         QtWidgets.QDockWidget.DockWidgetFloatable)