import logging
import numpy as np
from PyQt5 import QtCore, QtWidgets


logger = logging.getLogger(__name__)


class CameraReadoutDock(QtWidgets.QDockWidget):
    def __init__(self, acxn):
        QtWidgets.QDockWidget.__init__(self, "Camera Readout")
        self.acxn = acxn
        self.setObjectName("CameraReadoutHistogram")
        self.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable |
                         QtWidgets.QDockWidget.DockWidgetFloatable)


    def save_state(self):
        pass

    def restore_state(self):
        pass