from PyQt5 import QtWidgets


class CustomTree(QtWidgets.QTreeWidget):
    def __init__(self):
        QtWidgets.QTreeWidget.__init__(self)
        self.setObjectName("parameter_tree")