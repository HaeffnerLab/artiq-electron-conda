import logging
import numpy as np
from PyQt5 import QtCore, QtWidgets


logger = logging.getLogger(__name__)


class CameraReadoutDock(QtWidgets.QDockWidget):
    def __init__(self, cxn):
        QtWidgets.QDockWidget.__init__(self, "Camera Readout")
        self.setObjectName("CameraReadoutHistogram")
        self.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable |
                         QtWidgets.QDockWidget.DockWidgetFloatable)
        self.cxn = cxn

    def save_state(self):
        pass

    def restore_state(self):
        pass